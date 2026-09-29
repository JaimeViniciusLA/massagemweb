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
    .badge-agendado {
        background-color: #1e3a8a;
        color: #93c5fd;
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
                for k, v in dados.get("agenda", {}).items():
                    nova_chave = k.replace(" - 1ª Semana", "").replace(" - 2ª Semana", "").replace(" - 3ª Semana", "").replace(" - 4ª Semana", "").replace(" - 5ª Semana", "")
                    agenda_limpa[nova_chave] = v
                    status_limpo[nova_chave] = dados.get("status_agendamentos", {}).get(k, "Pendente")
                
                dados["agenda"] = agenda_limpa
                dados["status_agendamentos"] = status_limpo
                return dados
        except Exception:
            pass
    return {"pessoas": [], "agenda": {}, "status_agendamentos": {}}

def salvar_dados(dados, mes_nome, ano):
    filename = obter_nome_arquivo(mes_nome, ano)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)


# --- GERAÇÃO DE PDF ---
def gerar_pdf_bytes(agenda, status_agendamentos, mes):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Heading1"], fontSize=16, leading=20, textColor=colors.HexColor("#1E293B"))
    subtitle_style = ParagraphStyle("SubTitleStyle", parent=styles["Normal"], fontSize=10, leading=14, textColor=colors.HexColor("#2563EB"))

    elements.append(Paragraph("<b>ESCALA DE MASSAGEM DE BEM-ESTAR</b>", title_style))
    elements.append(Paragraph(f"Período: {mes} - Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style))
    elements.append(Spacer(1, 15))

    data = [["Data / Dia", "Horário Slot", "Matrícula", "Colaborador Agendado", "Status"]]

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
        data.append([p_dia_data, p_diahora, mat, nome, st_status])

    t = Table(data, colWidths=[130, 140, 60, 140, 70])
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

# Dicionário de tradução dos dias
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

        if st.button("Gerar Slots no Período Selecionado", use_container_width=True, type="primary"):
            if data_inicio > data_fim:
                st.error("A Data de Início não pode ser maior que a Data de Fim.")
            else:
                novos = 0
                dia_atual = data_inicio

                # Percorre rigorosamente do dia de início até o dia de fim
                while dia_atual <= data_fim:
                    nome_dia_pt = DIAS_PT[dia_atual.weekday()]
                    
                    # Gera horários apenas se o dia da semana estiver selecionado
                    if nome_dia_pt in dias_sel:
                        data_str = dia_atual.strftime("%d/%m/%Y")
                        curr = datetime.datetime.combine(dia_atual, h_inicio)
                        end = datetime.datetime.combine(dia_atual, h_fim)

                        while curr < end:
                            nxt = curr + datetime.timedelta(minutes=duracao_min)
                            if nxt > end:
                                break
                            
                            chave = f"{nome_dia_pt} ({data_str}) | {curr.strftime('%H:%M')} às {nxt.strftime('%H:%M')}"
                            
                            if chave not in agenda:
                                agenda[chave] = "--- VAGO ---"
                                status_agendamentos[chave] = "Pendente"
                                novos += 1
                            curr = nxt

                    dia_atual += datetime.timedelta(days=1)

                dados["agenda"] = agenda
                dados["status_agendamentos"] = status_agendamentos
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
                escolhido["participou_semana"] = True
                escolhido["total_participacoes"] = escolhido.get("total_participacoes", 0) + 1

            dados["agenda"] = agenda
            dados["pessoas"] = pessoas
            dados["status_agendamentos"] = status_agendamentos
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
            dados["agenda"] = agenda
            dados["pessoas"] = pessoas
            dados["status_agendamentos"] = status_agendamentos
            salvar_dados(dados, mes_selecionado, ano_selecionado)
            st.rerun()

        if col_btn3.button("🗑️ **Apagar Grade Completa**", use_container_width=True):
            dados["agenda"] = {}
            dados["status_agendamentos"] = {}
            salvar_dados(dados, mes_selecionado, ano_selecionado)
            st.rerun()

        if REPORTLAB_DISPONIVEL:
            pdf_data = gerar_pdf_bytes(agenda, status_agendamentos, mes_selecionado)
            col_btn4.download_button("📄 **Exportar PDF**", data=pdf_data, file_name=f"Escala_{mes_selecionado}.pdf", mime="application/pdf", use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)

        modo_visao = st.radio("Modo de Visualização:", ["📊 Visualização em Tabela Completa", "🎴 Visualização em Cards (Interativo)"], horizontal=True)

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

                if colab == "--- VAGO ---":
                    badge_html = '<span class="badge-vago">VAGO</span>'
                elif colab == "🔒 [BLOQUEADO]":
                    badge_html = '<span class="badge-falta">BLOQUEADO</span>'
                elif st_atual == "Realizado":
                    badge_html = '<span class="badge-realizado">REALIZADO</span>'
                elif st_atual == "Falta":
                    badge_html = '<span class="badge-falta">FALTA</span>'
                else:
                    badge_html = '<span class="badge-agendado">AGENDADO</span>'

                with grid_cols[col_idx % 3]:
                    with st.container(border=True):
                        st.markdown(f"**📅 {dia_data_rotulo}**")
                        st.markdown(f"**⏰ Slot:** {hora_slot} &nbsp; {badge_html}", unsafe_allow_html=True)
                        st.markdown(f"**Colaborador:** {colab}")
                        
                        c_act1, c_act2, c_act3 = st.columns(3)
                        
                        if colab == "--- VAGO ---":
                            if c_act1.button("🎲 Sortear", key=f"btn_sort_{h}", use_container_width=True):
                                urna = obter_elegiveis_equitativos(pessoas)
                                if urna:
                                    esc = random.choice(urna)
                                    agenda[h] = f"[{esc.get('matricula', 'N/A')}] {esc['nome']}"
                                    esc["participou_semana"] = True
                                    esc["total_participacoes"] = esc.get("total_participacoes", 0) + 1
                                    dados["agenda"] = agenda
                                    dados["pessoas"] = pessoas
                                    salvar_dados(dados, mes_selecionado, ano_selecionado)
                                    st.rerun()
                        else:
                            if c_act1.button("✅ Presença", key=f"btn_pres_{h}", use_container_width=True):
                                status_agendamentos[h] = "Realizado"
                                dados["status_agendamentos"] = status_agendamentos
                                salvar_dados(dados, mes_selecionado, ano_selecionado)
                                st.rerun()
                                
                            if c_act2.button("❌ Falta", key=f"btn_falta_{h}", use_container_width=True):
                                status_agendamentos[h] = "Falta"
                                dados["status_agendamentos"] = status_agendamentos
                                salvar_dados(dados, mes_selecionado, ano_selecionado)
                                st.rerun()

                        p_obj = next((p for p in pessoas if f"[{p.get('matricula')}] {p['nome']}" == colab), None)
                        if p_obj and p_obj.get("telefone"):
                            tel = "".join(filter(str.isdigit, str(p_obj["telefone"])))
                            if not tel.startswith("55"): tel = "55" + tel
                            msg = urllib.parse.quote(f"Olá *{p_obj['nome']}*! Lembrete da sua Massagem: {dia_data_rotulo} às {hora_slot}")
                            c_act3.markdown(f"[💬 Whats](https://web.whatsapp.com/send?phone={tel}&text={msg})")

                col_idx += 1

        else:
            df_agenda = pd.DataFrame([
                {"Data / Dia": h.split(" | ")[0], "Horário Slot": h.split(" | ")[1] if " | " in h else h, "Colaborador Agendado": p, "Status": status_agendamentos.get(h, "Pendente")}
                for h, p in agenda.items()
            ])
            st.dataframe(df_agenda, use_container_width=True, hide_index=True)

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

    with c_cad2:
        with st.container(border=True):
            st.markdown("### 📥 **Importar CSV**")
            up_file = st.file_uploader("Upload de Planilha CSV", type=["csv"])
            if up_file is not None:
                try:
                    df_imp = pd.read_csv(up_file, sep=None, engine='python')
                    novos = 0
                    for _, row in df_imp.iterrows():
                        mat = str(row.get("matricula", row.get("Matricula", "AUTO"))).strip()
                        nome = str(row.get("nome", row.get("Nome", ""))).strip()
                        tel = str(row.get("telefone", row.get("Telefone", ""))).strip()
                        if nome and not any(p["nome"].lower() == nome.lower() for p in pessoas):
                            pessoas.append({"matricula": mat, "nome": nome, "telefone": tel, "apto": True, "participou_semana": False, "total_participacoes": 0, "faltas": 0})
                            novos += 1
                    dados["pessoas"] = pessoas
                    salvar_dados(dados, mes_selecionado, ano_selecionado)
                    st.success(f"🎉 {novos} colaboradores importados!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro no CSV: {e}")

    st.markdown("### 👥 **Base de Colaboradores**")
    
    if pessoas:
        if "editando_mat" not in st.session_state:
            st.session_state["editando_mat"] = None

        for p in pessoas:
            mat = p["matricula"]
            is_apto = p.get("apto", True)
            status_txt = "✅ Ativo" if is_apto else "🏖️ Inativo (Férias)"
            btn_inativar_txt = "🏖️ Inativar" if is_apto else "✅ Ativar"
            
            with st.container(border=True):
                col_detalhes, col_act_inativar, col_act_editar, col_act_excluir = st.columns([5, 1.2, 1.2, 1.2])
                
                with col_detalhes:
                    st.markdown(
                        f"**{p['nome']}** &nbsp; `<small>[Mat: {mat}]</small>` &nbsp; <small>({status_txt})</small> &nbsp; | &nbsp; "
                        f"<small>📱 {p.get('telefone', 'Sem número')} &nbsp;|&nbsp; 📊 Sessões: {p.get('total_participacoes', 0)} &nbsp;|&nbsp; ❌ Faltas: {p.get('faltas', 0)}</small>",
                        unsafe_allow_html=True
                    )
                
                with col_act_inativar:
                    if st.button(btn_inativar_txt, key=f"btn_direct_apto_{mat}", use_container_width=True):
                        p["apto"] = not is_apto
                        dados["pessoas"] = pessoas
                        salvar_dados(dados, mes_selecionado, ano_selecionado)
                        st.rerun()

                with col_act_editar:
                    if st.button("✏️ Editar", key=f"btn_direct_edit_{mat}", use_container_width=True):
                        if st.session_state["editando_mat"] == mat:
                            st.session_state["editando_mat"] = None
                        else:
                            st.session_state["editando_mat"] = mat
                        st.rerun()

                with col_act_excluir:
                    if st.button("🗑️ Excluir", key=f"btn_direct_del_{mat}", use_container_width=True):
                        pessoas = [item for item in pessoas if item["matricula"] != mat]
                        dados["pessoas"] = pessoas
                        salvar_dados(dados, mes_selecionado, ano_selecionado)
                        st.session_state["editando_mat"] = None
                        st.warning("🗑️ Colaborador excluído com sucesso!")
                        st.rerun()

            if st.session_state["editando_mat"] == mat:
                with st.container(border=True):
                    st.markdown(f"##### ✏️ Editando Dados de **{p['nome']}**")
                    with st.form(key=f"form_edit_simple_{mat}"):
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
