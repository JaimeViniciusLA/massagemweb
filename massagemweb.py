import csv
import datetime
import io
import json
import os
import random
import urllib.parse
import pandas as pd
import streamlit as st

# Tenta importar o ReportLab para geração de PDF
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_DISPONIVEL = True
except ImportError:
    REPORTLAB_DISPONIVEL = False

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="SPA Massagem - Enterprise Dashboard",
    page_icon="💆‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILIZAÇÃO CSS DE NÍVEL SAAS ---
st.markdown("""
<style>
    .stApp {
        background-color: #0f172a;
    }
    .badge-vago {
        background-color: #334155;
        color: #94a3b8;
        padding: 3px 8px;
        border-radius: 10px;
        font-size: 0.70rem;
        font-weight: 700;
    }
    .badge-sorteado {
        background-color: #1e3a8a;
        color: #93c5fd;
        padding: 3px 8px;
        border-radius: 10px;
        font-size: 0.70rem;
        font-weight: 700;
    }
    .badge-manual {
        background-color: #581c87;
        color: #e9d5ff;
        padding: 3px 8px;
        border-radius: 10px;
        font-size: 0.70rem;
        font-weight: 700;
    }
    .badge-realizado {
        background-color: #064e3b;
        color: #6ee7b7;
        padding: 3px 8px;
        border-radius: 10px;
        font-size: 0.70rem;
        font-weight: 700;
    }
    .badge-falta {
        background-color: #7f1d1d;
        color: #fca5a5;
        padding: 3px 8px;
        border-radius: 10px;
        font-size: 0.70rem;
        font-weight: 700;
    }
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 12px 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    div[data-testid="stMetric"] label {
        color: #94a3b8 !important;
        font-size: 0.8rem !important;
        font-weight: 600;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #38bdf8 !important;
        font-size: 1.6rem !important;
        font-weight: 700;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# --- PERSISTÊNCIA DE DADOS ---
def obter_nome_arquivo(mes_nome, ano):
    return f"massagem_{mes_nome}_{ano}.json"

def carregar_dados(mes_nome, ano):
    filename = obter_nome_arquivo(mes_nome, ano)
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                dados = json.load(f)
                agenda_limpa = {}
                status_limpo = {}
                tipo_limpo = {}
                for k, v in dados.get("agenda", {}).items():
                    nova_chave = k.replace(" - 1ª Semana", "").replace(" - 2ª Semana", "").replace(" - 3ª Semana", "").replace(" - 4ª Semana", "").replace(" - 5ª Semana", "")
                    agenda_limpa[nova_chave] = v
                    status_limpo[nova_chave] = dados.get("status_agendamentos", {}).get(k, "Pendente")
                    tipo_limpo[nova_chave] = dados.get("tipo_agendamento", {}).get(k, "Sorteado" if v not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] else "N/A")
                
                dados["agenda"] = agenda_limpa
                dados["status_agendamentos"] = status_limpo
                dados["tipo_agendamento"] = tipo_limpo
                return dados
        except Exception:
            pass
    return {"pessoas": [], "agenda": {}, "status_agendamentos": {}, "tipo_agendamento": {}}

def salvar_dados(dados, mes_nome, ano):
    filename = obter_nome_arquivo(mes_nome, ano)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)


# --- GERAÇÃO DE PDF ---
def gerar_pdf_bytes(agenda, status_agendamentos, tipo_agendamento, mes):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Heading1"], fontSize=16, leading=20, textColor=colors.HexColor("#1E293B"))
    subtitle_style = ParagraphStyle("SubTitleStyle", parent=styles["Normal"], fontSize=10, leading=14, textColor=colors.HexColor("#2563EB"))

    elements.append(Paragraph("<b>ESCALA DE MASSAGEM DE BEM-ESTAR</b>", title_style))
    elements.append(Paragraph(f"Período: {mes} - Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style))
    elements.append(Spacer(1, 15))

    data = [["Data / Dia", "Horário Slot", "Matrícula", "Colaborador Agendado", "Origem", "Status"]]

    for horario, colaborador in agenda.items():
        partes = horario.split(" | ")
        p_dia_data = partes[0] if len(partes) > 0 else ""
        p_diahora = partes[1] if len(partes) > 1 else horario

        if colaborador not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] and "[" in colaborador and "]" in colaborador:
            mat = colaborador.split("]")[0].replace("[", "").strip()
            nome = colaborador.split("]")[1].strip()
        else:
            mat = "—"
            nome = colaborador

        st_status = status_agendamentos.get(horario, "Pendente")
        st_tipo = tipo_agendamento.get(horario, "Sorteado")
        data.append([p_dia_data, p_diahora, mat, nome, st_tipo, st_status])

    t = Table(data, colWidths=[110, 120, 50, 130, 65, 65])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
    ]))

    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# --- ALGORITMO DE SORTEIO ---
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


# --- BARRA LATERAL ---
with st.sidebar:
    st.markdown("## 💆‍♂️ **SPA Massagem**")
    st.caption("Enterprise Corporate Wellness")
    st.markdown("---")

    st.markdown("### 🗓 **Filtro de Período**")
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    agora = datetime.datetime.now()
    mes_selecionado = st.sidebar.selectbox("Mês de Referência", meses, index=agora.month - 1)
    ano_selecionado = st.sidebar.number_input("Ano", min_value=2024, max_value=2030, value=agora.year)

    st.markdown("---")
    st.caption("🔒 Ambiente Seguro • Snowflake Cloud")


# Carregar dados
dados = carregar_dados(mes_selecionado, ano_selecionado)
pessoas = dados.get("pessoas", [])
agenda = dados.get("agenda", {})
status_agendamentos = dados.get("status_agendamentos", {})
tipo_agendamento = dados.get("tipo_agendamento", {})


# --- PAINEL SUPERIOR (KPIs) ---
st.title("💆‍♂️ Gestão de Massagem Corporativa")
st.caption(f"Visualizando dados de **{mes_selecionado} de {ano_selecionado}**")

k1, k2, k3, k4 = st.columns(4)
total_cad = len(pessoas)
aptos_count = sum(1 for p in pessoas if p.get("apto", True))
atendidos_count = sum(1 for p in pessoas if p.get("participou_semana", False))
vagos_count = sum(1 for p in agenda.values() if p == "--- VAGO ---")

k1.metric("Total de Colaboradores", total_cad, delta="Cadastrados")
k2.metric("Colaboradores Aptos", aptos_count, delta="Ativos")
k3.metric("Atendidos na Semana", atendidos_count, delta="Concluídos")
k4.metric("Horários Disponíveis", vagos_count, delta="Vagos")

st.markdown("<br>", unsafe_allow_html=True)


# --- NAVEGAÇÃO POR ABAS ---
tab1, tab2 = st.tabs(["📅 **Grade de Agendamentos & Sorteios**", "👥 **Base de Colaboradores**"])

DIAS_PT = {
    0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"
}

# --- ABA 1: GRADE E AGENDAMENTOS ---
with tab1:
    with st.expander("⚡ **Configuração & Gerador de Grade por Período de Datas**", expanded=False):
        c_dt_ini, c_dt_fim, c_ini, c_fim, c_dur = st.columns(5)
        
        data_inicio = c_dt_ini.date_input("Data de Início", value=datetime.date.today(), format="DD/MM/YYYY")
        data_fim = c_dt_fim.date_input("Data de Fim", value=datetime.date.today() + datetime.timedelta(days=7), format="DD/MM/YYYY")
        
        dias_sel = st.multiselect("Dias de Atendimento no Período", ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"], default=["Segunda", "Terça", "Quarta", "Quinta", "Sexta"])

        h_inicio = c_ini.time_input("Horário Inicial", datetime.time(8, 0))
        h_fim = c_fim.time_input("Horário Final", datetime.time(17, 0))
        duracao_min = c_dur.number_input("Minutos por Sessão", min_value=10, max_value=120, value=30)

        st.markdown("---")
        st.markdown("##### 🍽️ **Configuração de Intervalo / Almoço**")
        c_alm1, c_alm2, c_alm3 = st.columns([2, 1.5, 1.2])
        tem_almoco = c_alm1.checkbox("Possui Intervalo / Almoço no Período?", value=True)
        h_alm_inicio = c_alm2.time_input("Início do Intervalo", datetime.time(12, 0), disabled=not tem_almoco)
        h_alm_fim = c_alm3.time_input("Fim do Intervalo", datetime.time(13, 0), disabled=not tem_almoco)

        if st.button("Gerar Slots no Período Selecionado", use_container_width=True, type="primary"):
            if data_inicio > data_fim:
                st.error("A Data de Início não pode ser maior que a Data de Fim.")
            elif tem_almoco and h_alm_inicio >= h_alm_fim:
                st.error("O Horário de Início do Intervalo deve ser menor que o Horário de Fim.")
            else:
                novos = 0
                dia_atual = data_inicio

                while dia_atual <= data_fim:
                    nome_dia_pt = DIAS_PT[dia_atual.weekday()]
                    
                    if nome_dia_pt in dias_sel:
                        data_str = dia_atual.strftime("%d/%m/%Y")
                        curr = datetime.datetime.combine(dia_atual, h_inicio)
                        end = datetime.datetime.combine(dia_atual, h_fim)

                        dt_alm_ini = datetime.datetime.combine(dia_atual, h_alm_inicio)
                        dt_alm_fim = datetime.datetime.combine(dia_atual, h_alm_fim)

                        while curr < end:
                            nxt = curr + datetime.timedelta(minutes=duracao_min)
                            if nxt > end:
                                break
                            
                            if tem_almoco:
                                if not (nxt <= dt_alm_ini or curr >= dt_alm_fim):
                                    curr = nxt
                                    continue

                            chave = f"{nome_dia_pt} ({data_str}) | {curr.strftime('%H:%M')} às {nxt.strftime('%H:%M')}"
                            
                            if chave not in agenda:
                                agenda[chave] = "--- VAGO ---"
                                status_agendamentos[chave] = "Pendente"
                                tipo_agendamento[chave] = "N/A"
                                novos += 1
                            curr = nxt

                    dia_atual += datetime.timedelta(days=1)

                dados["agenda"] = agenda
                dados["status_agendamentos"] = status_agendamentos
                dados["tipo_agendamento"] = tipo_agendamento
                salvar_dados(dados, mes_selecionado, ano_selecionado)
                st.success(f"✅ {novos} horários gerados entre {data_inicio.strftime('%d/%m/%Y')} e {data_fim.strftime('%d/%m/%Y')}!")
                st.rerun()

    if agenda:
        col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)

        if col_btn1.button("🎲 **Sortear TODOS os Vagos**", use_container_width=True, type="primary"):
            vagos = [h for h, p in agenda.items() if p == "--- VAGO ---"]
            for h in vagos:
                urna = obter_elegiveis_equitativos(pessoas)
                if not urna:
                    break
                escolhido = random.choice(urna)
                nome_disp = f"[{escolhido.get('matricula', 'N/A')}] {escolhido['nome']}"
                agenda[h] = nome_disp
                status_agendamentos[h] = "Pendente"
                tipo_agendamento[h] = "Sorteado"
                escolhido["participou_semana"] = True
                escolhido["total_participacoes"] = escolhido.get("total_participacoes", 0) + 1

            dados["agenda"] = agenda
            dados["pessoas"] = pessoas
            dados["status_agendamentos"] = status_agendamentos
            dados["tipo_agendamento"] = tipo_agendamento
            salvar_dados(dados, mes_selecionado, ano_selecionado)
            st.rerun()

        if col_btn2.button("🧹 **Limpar Sorteados**", use_container_width=True):
            for h, p in agenda.items():
                if p not in ["--- VAGO ---", "🔒 [BLOQUEADO]"]:
                    for pessoa in pessoas:
                        if f"[{pessoa.get('matricula')}] {pessoa['nome']}" == p:
                            pessoa["participou_semana"] = False
                            pessoa["total_participacoes"] = max(0, pessoa.get("total_participacoes", 1) - 1)
                    agenda[h] = "--- VAGO ---"
                    status_agendamentos[h] = "Pendente"
                    tipo_agendamento[h] = "N/A"
            dados["agenda"] = agenda
            dados["pessoas"] = pessoas
            dados["status_agendamentos"] = status_agendamentos
            dados["tipo_agendamento"] = tipo_agendamento
            salvar_dados(dados, mes_selecionado, ano_selecionado)
            st.rerun()

        if col_btn3.button("🗑️ **Apagar Grade Completa**", use_container_width=True):
            dados["agenda"] = {}
            dados["status_agendamentos"] = {}
            dados["tipo_agendamento"] = {}
            salvar_dados(dados, mes_selecionado, ano_selecionado)
            st.rerun()

        if REPORTLAB_DISPONIVEL:
            pdf_data = gerar_pdf_bytes(agenda, status_agendamentos, tipo_agendamento, mes_selecionado)
            col_btn4.download_button("📄 **Exportar PDF**", data=pdf_data, file_name=f"Escala_{mes_selecionado}.pdf", mime="application/pdf", use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        modo_visao = st.radio("Modo de Visualização:", ["🎴 Visualização em Cards (Interativo)", "📊 Visualização em Tabela Completa"], horizontal=True)

        if "slot_sub_manual" not in st.session_state:
            st.session_state["slot_sub_manual"] = None

        if "Cards" in modo_visao:
            st.markdown("### 🎴 Slots de Atendimento por Data")
            
            dias_com_data = list(set([h.split(" | ")[0] for h in agenda.keys() if " | " in h]))
            dia_filtro = st.selectbox("Filtrar por Dia e Data:", ["Todas as Datas"] + sorted(dias_com_data))

            grid_cols = st.columns(3)
            col_idx = 0

            for h, colab in agenda.items():
                partes = h.split(" | ")
                dia_data_rotulo = partes[0]
                hora_slot = partes[1] if len(partes) > 1 else h

                if dia_filtro != "Todas as Datas" and dia_data_rotulo != dia_filtro:
                    continue

                st_atual = status_agendamentos.get(h, "Pendente")
                tp_atual = tipo_agendamento.get(h, "Sorteado")

                if colab == "--- VAGO ---":
                    badge_html = '<span class="badge-vago">VAGO</span>'
                elif colab == "🔒 [BLOQUEADO]":
                    badge_html = '<span class="badge-falta">BLOQUEADO</span>'
                elif st_atual == "Realizado":
                    badge_html = '<span class="badge-realizado">REALIZADO</span>'
                elif st_atual == "Falta":
                    badge_html = '<span class="badge-falta">FALTA</span>'
                else:
                    if tp_atual == "Manual":
                        badge_html = '<span class="badge-manual">AGENDADO (MANUAL)</span>'
                    else:
                        badge_html = '<span class="badge-sorteado">AGENDADO (SORTEADO)</span>'

                with grid_cols[col_idx % 3]:
                    with st.container(border=True):
                        st.markdown(f"**📅 {dia_data_rotulo}**")
                        st.markdown(f"**⏰ Slot:** {hora_slot} &nbsp; {badge_html}", unsafe_allow_html=True)
                        
                        # EXIBIÇÃO COM OS DOIS BOTÕES COMPACTOS DO LADO DO NOME
                        c_nome_txt, c_btn_sub, c_btn_sort = st.columns([3.5, 0.9, 0.9])
                        
                        with c_nome_txt:
                            st.markdown(f"**Colaborador:**\n{colab}")

                        if colab != "--- VAGO ---":
                            with c_btn_sub:
                                if st.button("✍️", key=f"card_btn_sub_{h}", help="Substituir à Mão"):
                                    st.session_state["slot_sub_manual"] = h if st.session_state["slot_sub_manual"] != h else None
                                    st.rerun()
                            
                            with c_btn_sort:
                                if st.button("🎲", key=f"card_btn_sort_{h}", help="Re-sortear Automático"):
                                    for p in pessoas:
                                        if f"[{p.get('matricula')}] {p['nome']}" == colab:
                                            p["participou_semana"] = False
                                            p["total_participacoes"] = max(0, p.get("total_participacoes", 1) - 1)

                                    urna = obter_elegiveis_equitativos(pessoas)
                                    if urna:
                                        substitut_auto = random.choice(urna)
                                        agenda[h] = f"[{substitut_auto.get('matricula', 'N/A')}] {substitut_auto['nome']}"
                                        status_agendamentos[h] = "Pendente"
                                        tipo_agendamento[h] = "Sorteado"
                                        substitut_auto["participou_semana"] = True
                                        substitut_auto["total_participacoes"] = substitut_auto.get("total_participacoes", 0) + 1
                                        st.toast(f"🎲 Sorteado: {substitut_auto['nome']}")
                                    else:
                                        agenda[h] = "--- VAGO ---"
                                        tipo_agendamento[h] = "N/A"
                                        st.toast("Sem aptos na urna. Slot resetado.")

                                    dados["agenda"] = agenda
                                    dados["pessoas"] = pessoas
                                    dados["status_agendamentos"] = status_agendamentos
                                    dados["tipo_agendamento"] = tipo_agendamento
                                    salvar_dados(dados, mes_selecionado, ano_selecionado)
                                    st.rerun()
                        else:
                            with c_btn_sort:
                                if st.button("🎲", key=f"card_btn_sort_vago_{h}", help="Sortear Automático"):
                                    urna = obter_elegiveis_equitativos(pessoas)
                                    if urna:
                                        esc = random.choice(urna)
                                        agenda[h] = f"[{esc.get('matricula', 'N/A')}] {esc['nome']}"
                                        status_agendamentos[h] = "Pendente"
                                        tipo_agendamento[h] = "Sorteado"
                                        esc["participou_semana"] = True
                                        esc["total_participacoes"] = esc.get("total_participacoes", 0) + 1
                                        dados["agenda"] = agenda
                                        dados["pessoas"] = pessoas
                                        dados["status_agendamentos"] = status_agendamentos
                                        dados["tipo_agendamento"] = tipo_agendamento
                                        salvar_dados(dados, mes_selecionado, ano_selecionado)
                                        st.rerun()
                            with c_btn_sub:
                                if st.button("✍️", key=f"card_btn_sub_vago_{h}", help="Substituir à Mão"):
                                    st.session_state["slot_sub_manual"] = h if st.session_state["slot_sub_manual"] != h else None
                                    st.rerun()

                        # AÇÕES INFERIORES DO CARD
                        c_bot1, c_bot2 = st.columns([2, 1])
                        if colab != "--- VAGO ---":
                            if c_bot1.button("✅ Presença", key=f"btn_pres_{h}", use_container_width=True):
                                status_agendamentos[h] = "Realizado"
                                dados["status_agendamentos"] = status_agendamentos
                                salvar_dados(dados, mes_selecionado, ano_selecionado)
                                st.rerun()

                            p_obj = next((p for p in pessoas if f"[{p.get('matricula')}] {p['nome']}" == colab), None)
                            if p_obj and p_obj.get("telefone"):
                                tel = "".join(filter(str.isdigit, str(p_obj["telefone"])))
                                if not tel.startswith("55"): tel = "55" + tel
                                msg = urllib.parse.quote(f"Olá *{p_obj['nome']}*! Lembrete da sua Massagem: {dia_data_rotulo} às {hora_slot}")
                                c_bot2.markdown(f"[💬 Whats](https://web.whatsapp.com/send?phone={tel}&text={msg})")

                        # SUB-PAINEL DE SUBSTITUIÇÃO À MÃO
                        if st.session_state["slot_sub_manual"] == h:
                            with st.container(border=True):
                                st.markdown("##### ✍️ **Substituir Funcionário à Mão**")
                                opcoes_m = ["--- VAGO ---", "🔒 [BLOQUEADO]"] + [f"[{p.get('matricula', 'N/A')}] {p['nome']}" for p in pessoas]
                                idx_m = opcoes_m.index(colab) if colab in opcoes_m else 0
                                novo_m_sel = st.selectbox("Escolha o Colaborador", opcoes_m, index=idx_m, key=f"sb_m_{h}")
                                
                                if st.button("💾 Confirmar Troca Manual", key=f"btn_conf_m_{h}", use_container_width=True, type="primary"):
                                    if colab not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] and colab != novo_m_sel:
                                        for p in pessoas:
                                            if f"[{p.get('matricula')}] {p['nome']}" == colab:
                                                p["participou_semana"] = False
                                                p["total_participacoes"] = max(0, p.get("total_participacoes", 1) - 1)

                                    agenda[h] = novo_m_sel
                                    status_agendamentos[h] = "Pendente"
                                    tipo_agendamento[h] = "Manual" if novo_m_sel not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] else "N/A"

                                    if novo_m_sel not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] and colab != novo_m_sel:
                                        for p in pessoas:
                                            if f"[{p.get('matricula')}] {p['nome']}" == novo_m_sel:
                                                p["participou_semana"] = True
                                                p["total_participacoes"] = p.get("total_participacoes", 0) + 1

                                    dados["agenda"] = agenda
                                    dados["pessoas"] = pessoas
                                    dados["status_agendamentos"] = status_agendamentos
                                    dados["tipo_agendamento"] = tipo_agendamento
                                    salvar_dados(dados, mes_selecionado, ano_selecionado)
                                    st.session_state["slot_sub_manual"] = None
                                    st.success("✅ Alteração manual salva!")
                                    st.rerun()

                col_idx += 1

        else:
            # VISUALIZAÇÃO EM TABELA COM BOTÕES INTERATIVOS LADO A LADO POR LINHA
            st.markdown("### 📊 Agenda Interativa em Tabela")

            for h_idx, (h, colab) in enumerate(agenda.items()):
                partes = h.split(" | ")
                dia_data_rotulo = partes[0]
                hora_slot = partes[1] if len(partes) > 1 else h

                st_atual = status_agendamentos.get(h, "Pendente")
                tp_atual = tipo_agendamento.get(h, "Sorteado")

                with st.container(border=True):
                    col_t1, col_t2, col_t3, col_t4, col_t5, col_t6 = st.columns([1.8, 1.2, 3.2, 0.5, 0.5, 1.2])

                    with col_t1:
                        st.markdown(f"**{dia_data_rotulo}**")
                    with col_t2:
                        st.markdown(f"⏰ `{hora_slot}`")
                    with col_t3:
                        st.markdown(f"**{colab}**")
                    
                    # BOTÃO COMPACTO 1: SUBSTITUIR À MÃO NA LINHA
                    with col_t4:
                        if st.button("✍️", key=f"tab_row_sub_{h_idx}", help="Substituir Colaborador à Mão"):
                            st.session_state["slot_sub_manual"] = h if st.session_state["slot_sub_manual"] != h else None
                            st.rerun()

                    # BOTÃO COMPACTO 2: SORTEAR AUTOMÁTICO NA LINHA
                    with col_t5:
                        if st.button("🎲", key=f"tab_row_sort_{h_idx}", help="Re-sortear Automático via Urna"):
                            if colab not in ["--- VAGO ---", "🔒 [BLOQUEADO]"]:
                                for p in pessoas:
                                    if f"[{p.get('matricula')}] {p['nome']}" == colab:
                                        p["participou_semana"] = False
                                        p["total_participacoes"] = max(0, p.get("total_participacoes", 1) - 1)

                            urna = obter_elegiveis_equitativos(pessoas)
                            if urna:
                                substitut_auto = random.choice(urna)
                                agenda[h] = f"[{substitut_auto.get('matricula', 'N/A')}] {substitut_auto['nome']}"
                                status_agendamentos[h] = "Pendente"
                                tipo_agendamento[h] = "Sorteado"
                                substitut_auto["participou_semana"] = True
                                substitut_auto["total_participacoes"] = substitut_auto.get("total_participacoes", 0) + 1
                                st.toast(f"🎲 Sorteado: {substitut_auto['nome']}")
                            else:
                                agenda[h] = "--- VAGO ---"
                                tipo_agendamento[h] = "N/A"
                                st.toast("Sem aptos na urna. Slot resetado.")

                            dados["agenda"] = agenda
                            dados["pessoas"] = pessoas
                            dados["status_agendamentos"] = status_agendamentos
                            dados["tipo_agendamento"] = tipo_agendamento
                            salvar_dados(dados, mes_selecionado, ano_selecionado)
                            st.rerun()

                    with col_t6:
                        st.markdown(f"`{tp_atual}` | `{st_atual}`")

                # PAINEL EXPANSÍVEL DE SUBSTITUIÇÃO À MÃO QUANDO CLICADO NA TABELA
                if st.session_state["slot_sub_manual"] == h:
                    with st.container(border=True):
                        st.markdown(f"##### ✍️️ Substituir à Mão para o Horário: `{h}`")
                        opcoes_m = ["--- VAGO ---", "🔒 [BLOQUEADO]"] + [f"[{p.get('matricula', 'N/A')}] {p['nome']}" for p in pessoas]
                        idx_m = opcoes_m.index(colab) if colab in opcoes_m else 0
                        novo_m_sel = st.selectbox("Selecione o Colaborador", opcoes_m, index=idx_m, key=f"sb_tab_m_{h_idx}")
                        
                        if st.button("💾 Confirmar Troca Manual", key=f"btn_tab_conf_m_{h_idx}", use_container_width=True, type="primary"):
                            if colab not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] and colab != novo_m_sel:
                                for p in pessoas:
                                    if f"[{p.get('matricula')}] {p['nome']}" == colab:
                                        p["participou_semana"] = False
                                        p["total_participacoes"] = max(0, p.get("total_participacoes", 1) - 1)

                            agenda[h] = novo_m_sel
                            status_agendamentos[h] = "Pendente"
                            tipo_agendamento[h] = "Manual" if novo_m_sel not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] else "N/A"

                            if novo_m_sel not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] and colab != novo_m_sel:
                                for p in pessoas:
                                    if f"[{p.get('matricula')}] {p['nome']}" == novo_m_sel:
                                        p["participou_semana"] = True
                                        p["total_participacoes"] = p.get("total_participacoes", 0) + 1

                            dados["agenda"] = agenda
                            dados["pessoas"] = pessoas
                            dados["status_agendamentos"] = status_agendamentos
                            dados["tipo_agendamento"] = tipo_agendamento
                            salvar_dados(dados, mes_selecionado, ano_selecionado)
                            st.session_state["slot_sub_manual"] = None
                            st.success("✅ Substituição manual realizada com sucesso!")
                            st.rerun()

    else:
        st.info("Nenhum horário gerado para a grade deste mês.")


# --- ABA 2: BASE DE COLABORADORES ---
with tab2:
    c_cad1, c_cad2 = st.columns([3, 2])

    with c_cad1:
        with st.container(border=True):
            st.markdown("### ➕ **Novo Colaborador**")
            with st.form("form_novo_colab", clear_on_submit=True):
                col_m, col_n, col_t = st.columns([1, 2, 2])
                mat_in = col_m.text_input("Matrícula")
                nome_in = col_n.text_input("Nome Completo")
                tel_in = col_t.text_input("WhatsApp (com DDD)")
                sub = st.form_submit_button("Cadastrar", use_container_width=True, type="primary")

                if sub:
                    if mat_in and nome_in:
                        if not any(p["matricula"] == mat_in for p in pessoas):
                            pessoas.append({"matricula": mat_in, "nome": nome_in, "telefone": tel_in, "apto": True, "participou_semana": False, "total_participacoes": 0, "faltas": 0})
                            dados["pessoas"] = pessoas
                            salvar_dados(dados, mes_selecionado, ano_selecionado)
                            st.success(f"✅ {nome_in} cadastrado!")
                            st.rerun()
                        else:
                            st.warning("⚠️ Matrícula existente.")

    # --- IMPORTAÇÃO ROBUSTA ---
    with c_cad2:
        with st.container(border=True):
            st.markdown("### 📥 **Importar Planilha (CSV / Excel)**")
            up_file = st.file_uploader("Upload de Planilha CSV ou Excel", type=["csv", "xlsx", "xls"])
            if up_file is not None:
                df_imp = None
                nome_arq = up_file.name.lower()
                
                try:
                    if nome_arq.endswith(".xlsx") or nome_arq.endswith(".xls"):
                        df_imp = pd.read_excel(up_file)
                    else:
                        encodings_para_testar = ['utf-8', 'utf-8-sig', 'latin-1', 'iso-8859-1', 'cp1252']
                        for enc in encodings_para_testar:
                            try:
                                up_file.seek(0)
                                df_imp = pd.read_csv(up_file, sep=None, engine='python', encoding=enc)
                                break
                            except Exception:
                                continue
                except Exception as e:
                    st.error(f"Erro na leitura do arquivo: {e}")

                if df_imp is not None:
                    col_nome = next((c for c in df_imp.columns if any(k in str(c).lower() for k in ["nome", "func", "colab", "pessoa", "employee"])), None)
                    col_mat = next((c for c in df_imp.columns if any(k in str(c).lower() for k in ["matr", "code", "id", "registro"])), None)
                    col_tel = next((c for c in df_imp.columns if any(k in str(c).lower() for k in ["tel", "whats", "cel", "fone", "phone"])), None)

                    if col_nome is None and len(df_imp.columns) > 0:
                        col_nome = df_imp.columns[0]

                    novos = 0
                    for idx_row, row in df_imp.iterrows():
                        raw_nome = row.get(col_nome, "") if col_nome else ""
                        nome = str(raw_nome).strip() if pd.notna(raw_nome) else ""

                        if not nome or nome.lower() == "nan":
                            continue

                        raw_mat = row.get(col_mat, "") if col_mat else ""
                        mat = str(raw_mat).strip() if pd.notna(raw_mat) and str(raw_mat).strip().lower() != "nan" else ""
                        if mat.endswith(".0"): mat = mat[:-2]

                        if not mat:
                            mat = f"MAT_{len(pessoas) + 1:04d}"

                        raw_tel = row.get(col_tel, "") if col_tel else ""
                        tel = str(raw_tel).strip() if pd.notna(raw_tel) and str(raw_tel).strip().lower() != "nan" else ""
                        if tel.endswith(".0"): tel = tel[:-2]

                        if not any(p["nome"].lower() == nome.lower() for p in pessoas):
                            pessoas.append({"matricula": mat, "nome": nome, "telefone": tel, "apto": True, "participou_semana": False, "total_participacoes": 0, "faltas": 0})
                            novos += 1

                    if novos > 0:
                        dados["pessoas"] = pessoas
                        salvar_dados(dados, mes_selecionado, ano_selecionado)
                        st.success(f"🎉 {novos} novos colaboradores adicionados com sucesso!")
                        st.rerun()
                    else:
                        st.info("ℹ️ Os colaboradores desta planilha já estão cadastrados na base.")
                else:
                    st.error("Não foi possível processar o arquivo. Verifique o formato enviado.")

    st.markdown("### 👥 **Base de Colaboradores**")
    
    if pessoas:
        if "editando_mat" not in st.session_state:
            st.session_state["editando_mat"] = None

        for idx, p in enumerate(pessoas):
            mat = p.get("matricula", f"AUTO_{idx}")
            is_apto = p.get("apto", True)
            status_txt = "✅ Ativo" if is_apto else "🏖️ Inativo (Férias)"
            btn_inativar_txt = "🏖️ Inativar" if is_apto else "✅ Ativar"
            
            with st.container(border=True):
                col_detalhes, col_act_inativar, col_act_editar, col_act_excluir = st.columns([5, 1.2, 1.2, 1.2])
                
                with col_detalhes:
                    st.markdown(
                        f"**{p['nome']}** &nbsp; *(Mat: {mat})* &nbsp; • &nbsp; **{status_txt}** &nbsp; | &nbsp; "
                        f"📱 **Whats:** {p.get('telefone', 'Sem número')} &nbsp; | &nbsp; 📊 **Sessões:** {p.get('total_participacoes', 0)} &nbsp; | &nbsp; ❌ **Faltas:** {p.get('faltas', 0)}"
                    )
                
                with col_act_inativar:
                    if st.button(btn_inativar_txt, key=f"btn_direct_apto_{mat}_{idx}", use_container_width=True):
                        p["apto"] = not is_apto
                        dados["pessoas"] = pessoas
                        salvar_dados(dados, mes_selecionado, ano_selecionado)
                        st.rerun()

                with col_act_editar:
                    if st.button("✏️ Editar", key=f"btn_direct_edit_{mat}_{idx}", use_container_width=True):
                        if st.session_state["editando_mat"] == f"{mat}_{idx}":
                            st.session_state["editando_mat"] = None
                        else:
                            st.session_state["editando_mat"] = f"{mat}_{idx}"
                        st.rerun()

                with col_act_excluir:
                    if st.button("🗑️ Excluir", key=f"btn_direct_del_{mat}_{idx}", use_container_width=True):
                        pessoas.pop(idx)
                        dados["pessoas"] = pessoas
                        salvar_dados(dados, mes_selecionado, ano_selecionado)
                        st.session_state["editando_mat"] = None
                        st.warning("🗑️ Colaborador excluído com sucesso!")
                        st.rerun()

            if st.session_state["editando_mat"] == f"{mat}_{idx}":
                with st.container(border=True):
                    st.markdown(f"##### ✏️ Editando Dados de **{p['nome']}**")
                    with st.form(key=f"form_edit_simple_{mat}_{idx}"):
                        e_c1, e_c2, e_c3 = st.columns([2, 2, 1])
                        novo_nome_val = e_c1.text_input("Nome Completo", value=p["nome"])
                        novo_tel_val = e_c2.text_input("WhatsApp", value=p.get("telefone", ""))
                        novo_tot_val = e_c3.number_input("Sessões Acumuladas", value=p.get("total_participacoes", 0), min_value=0)

                        btn_salvar_colab = st.form_submit_button("💾 Salvar Alterações", use_container_width=True, type="primary")
                        
                        if btn_salvar_colab:
                            p["nome"] = novo_nome_val
                            p["telefone"] = novo_tel_val
                            p["total_participacoes"] = novo_tot_val
                            dados["pessoas"] = pessoas
                            salvar_dados(dados, mes_selecionado, ano_selecionado)
                            st.session_state["editando_mat"] = None
                            st.success("✅ Cadastro atualizado!")
                            st.rerun()

        st.markdown("---")
        if st.button("🔄 **Zerar Frequência Semanal de Todos**", use_container_width=True):
            for p in pessoas:
                p["participou_semana"] = False
            dados["pessoas"] = pessoas
            salvar_dados(dados, mes_selecionado, ano_selecionado)
            st.success("Frequências da semana zeradas!")
            st.rerun()
