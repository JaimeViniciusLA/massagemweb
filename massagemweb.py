import csv
import datetime
import json
import os
import random
import urllib.parse
import pandas as pd
import streamlit as st

# Configuração da página no Streamlit
st.set_page_config(
    page_title="Sistema de Gestão de Massagens",
    page_icon="💆‍♂️",
    layout="wide"
)

# --- FUNÇÕES DE PERSISTÊNCIA DE DADOS ---
def obter_nome_arquivo(mes_nome, ano):
    return f"massagem_{mes_nome}_{ano}.json"

def carregar_dados(mes_nome, ano):
    filename = obter_nome_arquivo(mes_nome, ano)
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"pessoas": [], "agenda": {}, "status_agendamentos": {}}

def salvar_dados(dados, mes_nome, ano):
    filename = obter_nome_arquivo(mes_nome, ano)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

# --- ALGORITMO DE SORTEIO COM PESOS ---
def obter_elegiveis_equitativos(pessoas):
    aptos = [p for p in pessoas if p.get("apto", True)]
    if not aptos:
        return []

    candidatos = [p for p in aptos if not p.get("participou_semana", False)]
    if not candidatos:
        candidatos = aptos

    max_sessoes = max(p.get("total_participacoes", 0) for p in candidatos) if candidatos else 0
    urna = []
    for p in candidatos:
        peso = (max_sessoes - p.get("total_participacoes", 0)) + 1
        urna.extend([p] * peso)
    return urna

# --- INTERFACE PRINCIPAL ---
st.title("💆‍♂️ Sistema de Gestão e Sorteio de Massagens")

# Seleção de Período na Barra Lateral
st.sidebar.header("🗓️ Seleção de Período")
meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
agora = datetime.datetime.now()
mes_selecionado = st.sidebar.selectbox("Mês", meses, index=agora.month - 1)
ano_selecionado = st.sidebar.number_input("Ano", min_value=2024, max_value=2030, value=agora.year)

# Carrega os dados do mês
dados = carregar_dados(mes_selecionado, ano_selecionado)
pessoas = dados.get("pessoas", [])
agenda = dados.get("agenda", {})
status_agendamentos = dados.get("status_agendamentos", {})

# Painel de KPIs no Topo
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Cadastrados", len(pessoas))
col2.metric("Aptos / Ativos", sum(1 for p in pessoas if p.get("apto", True)))
col3.metric("Atendidos na Semana", sum(1 for p in pessoas if p.get("participou_semana", False)))
col4.metric("Horários Vagos", sum(1 for p in agenda.values() if p == "--- VAGO ---"))

st.markdown("---")

# Navegação por Abas
tab1, tab2 = st.tabs(["👥 Colaboradores", "📅 Grade & Sorteios"])

# --- ABA 1: COLABORADORES ---
with tab1:
    st.subheader("Cadastrar Colaborador")
    with st.form("form_cadastrar"):
        c1, c2, c3 = st.columns([1, 2, 2])
        mat_in = c1.text_input("Matrícula")
        nome_in = c2.text_input("Nome Completo")
        tel_in = c3.text_input("Telefone (WhatsApp com DDD)")
        submit_add = st.form_submit_button("➕ Adicionar Colaborador")

        if submit_add:
            if mat_in and nome_in:
                if not any(p["matricula"] == mat_in for p in pessoas):
                    pessoas.append({
                        "matricula": mat_in,
                        "nome": nome_in,
                        "telefone": tel_in,
                        "apto": True,
                        "participou_semana": False,
                        "total_participacoes": 0,
                        "faltas": 0
                    })
                    dados["pessoas"] = pessoas
                    salvar_dados(dados, mes_selecionado, ano_selecionado)
                    st.success(f"{nome_in} cadastrado com sucesso!")
                    st.rerun()
                else:
                    st.warning("Matrícula já cadastrada!")
            else:
                st.warning("Preencha a matrícula e o nome.")

    st.subheader("Lista de Colaboradores")
    if pessoas:
        df_pessoas = pd.DataFrame(pessoas)
        st.dataframe(df_pessoas, use_container_width=True)

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            mat_toggle = st.selectbox("Selecione por Matrícula para alternar Aptidão/Status", [p["matricula"] for p in pessoas])
            if st.button("🏖️ Alternar Aptidão (Ativo/Férias)"):
                for p in pessoas:
                    if p["matricula"] == mat_toggle:
                        p["apto"] = not p.get("apto", True)
                dados["pessoas"] = pessoas
                salvar_dados(dados, mes_selecionado, ano_selecionado)
                st.rerun()

        with col_act2:
            if st.button("🔄 Iniciar Nova Semana (Zerar Status Semanal)"):
                for p in pessoas:
                    p["participou_semana"] = False
                dados["pessoas"] = pessoas
                salvar_dados(dados, mes_selecionado, ano_selecionado)
                st.success("Nova semana iniciada!")
                st.rerun()
    else:
        st.info("Nenhum colaborador cadastrado ainda.")

# --- ABA 2: GRADE E SORTEIOS ---
with tab2:
    st.subheader("Configuração da Grade de Horários")
    c_sem, c_ini, c_fim, c_dur = st.columns(4)
    semana_sel = c_sem.selectbox("Semana do Mês", ["1ª Semana", "2ª Semana", "3ª Semana", "4ª Semana", "5ª Semana"])
    dias_sel = st.multiselect("Dias da Semana", ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"], default=["Segunda", "Quarta", "Sexta"])
    
    h_inicio = c_ini.time_input("Horário Início", datetime.time(8, 0))
    h_fim = c_fim.time_input("Horário Fim", datetime.time(17, 0))
    duracao_min = c_dur.number_input("Duração (min)", min_value=10, max_value=120, value=30)

    if st.button("⚡ Criar Horários na Grade"):
        novos = 0
        for dia in dias_sel:
            curr = datetime.datetime.combine(datetime.date.today(), h_inicio)
            end = datetime.datetime.combine(datetime.date.today(), h_fim)
            while curr < end:
                nxt = curr + datetime.timedelta(minutes=duracao_min)
                if nxt > end:
                    break
                chave = f"{mes_selecionado} - {semana_sel} | {dia} {curr.strftime('%H:%M')} às {nxt.strftime('%H:%M')}"
                if chave not in agenda:
                    agenda[chave] = "--- VAGO ---"
                    status_agendamentos[chave] = "Pendente"
                    novos += 1
                curr = nxt
        dados["agenda"] = agenda
        dados["status_agendamentos"] = status_agendamentos
        salvar_dados(dados, mes_selecionado, ano_selecionado)
        st.success(f"{novos} horários adicionados!")
        st.rerun()

    st.markdown("---")
    st.subheader("Agenda de Massagens")

    if agenda:
        # Ações de Sorteio
        ca1, ca2, ca3 = st.columns(3)
        if ca1.button("🎲 Sortear TODOS os Vagos"):
            vagos = [h for h, p in agenda.items() if p == "--- VAGO ---"]
            for h in vagos:
                urna = obter_elegiveis_equitativos(pessoas)
                if not urna:
                    break
                escolhido = random.choice(urna)
                nome_disp = f"[{escolhido.get('matricula', 'N/A')}] {escolhido['nome']}"
                agenda[h] = nome_disp
                status_agendamentos[h] = "Pendente"
                escolhido["participou_semana"] = True
                escolhido["total_participacoes"] = escolhido.get("total_participacoes", 0) + 1

            dados["agenda"] = agenda
            dados["pessoas"] = pessoas
            dados["status_agendamentos"] = status_agendamentos
            salvar_dados(dados, mes_selecionado, ano_selecionado)
            st.rerun()

        if ca2.button("🧹 Limpar Sorteados (Manter Horários)"):
            for h, p in agenda.items():
                if p not in ["--- VAGO ---", "🔒 [BLOQUEADO]"]:
                    for pessoa in pessoas:
                        if f"[{pessoa.get('matricula')}] {pessoa['nome']}" == p:
                            pessoa["participou_semana"] = False
                            pessoa["total_participacoes"] = max(0, pessoa.get("total_participacoes", 1) - 1)
                    agenda[h] = "--- VAGO ---"
                    status_agendamentos[h] = "Pendente"
            dados["agenda"] = agenda
            dados["pessoas"] = pessoas
            dados["status_agendamentos"] = status_agendamentos
            salvar_dados(dados, mes_selecionado, ano_selecionado)
            st.rerun()

        if ca3.button("🗑️ Limpar Grade Completa"):
            dados["agenda"] = {}
            dados["status_agendamentos"] = {}
            salvar_dados(dados, mes_selecionado, ano_selecionado)
            st.rerun()

        # Exibição em Tabela do Streamlit
        df_agenda = pd.DataFrame([
            {"Horário": h, "Colaborador": p, "Status": status_agendamentos.get(h, "Pendente")}
            for h, p in agenda.items()
        ])
        st.dataframe(df_agenda, use_container_width=True)

        # Envio de Lembrete via WhatsApp Web
        st.subheader("💬 Enviar Lembrete via WhatsApp")
        horario_whats = st.selectbox("Selecione o Horário para Lembrar", list(agenda.keys()))
        colab_whats = agenda.get(horario_whats)

        if colab_whats and colab_whats not in ["--- VAGO ---", "🔒 [BLOQUEADO]"]:
            p_obj = next((p for p in pessoas if f"[{p.get('matricula')}] {p['nome']}" == colab_whats), None)
            if p_obj and p_obj.get("telefone"):
                tel = "".join(filter(str.isdigit, p_obj["telefone"]))
                if not tel.startswith("55"):
                    tel = "55" + tel
                msg = f"Olá *{p_obj['nome']}*! 👋\nLembrete da sua Massagem:\n📅 *{horario_whats}*"
                link = f"https://web.whatsapp.com/send?phone={tel}&text={urllib.parse.quote(msg)}"
                st.markdown(f"[👉 Clique aqui para abrir o WhatsApp Web com a mensagem pronta]({link})")
            else:
                st.caption("Colaborador sem telefone cadastrado.")
    else:
        st.info("Nenhum horário gerado na grade.")