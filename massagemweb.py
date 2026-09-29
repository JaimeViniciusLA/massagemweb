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
    page_title="SPA Massagem - Sistema de Gestão",
    page_icon="💆‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILIZAÇÃO CSS PERSONALIZADA ---
st.markdown("""
<style>
    /* Estilo do fundo principal */
    .stApp {
        background-color: #f8fafc;
    }
    
    /* Estilização dos Cards de Métricas (KPIs) */
    .metric-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 18px 22px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        border-left: 5px solid #2563eb;
        margin-bottom: 10px;
    }
    .metric-card p {
        margin: 0;
        color: #64748b;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-card h2 {
        margin: 6px 0 0 0;
        color: #0f172a;
        font-size: 1.8rem;
        font-weight: 700;
    }

    /* Estilização de botões primários e secundários */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        border: none;
        transition: all 0.2s ease;
    }
    
    /* Ajustes dos recipientes expansíveis */
    .streamlit-expanderHeader {
        font-weight: 600;
        color: #1e293b;
    }
    
    /* Ocultar marca d'água e cabeçalhos padrão se necessário */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


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

# --- GERAÇÃO DE RELATÓRIO PDF ---
def gerar_pdf_bytes(agenda, status_agendamentos, mes, semana):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30
    )
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle", parent=styles["Heading1"], fontSize=16, leading=20, textColor=colors.HexColor("#1E293B")
    )
    subtitle_style = ParagraphStyle(
        "SubTitleStyle", parent=styles["Normal"], fontSize=10, leading=14, textColor=colors.HexColor("#2563EB")
    )

    elements.append(Paragraph("<b>ESCALA SEMANAL DE MASSAGEM DE BEM-ESTAR</b>", title_style))
    elements.append(
        Paragraph(
            f"Período: {mes} / {semana} - Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}",
            subtitle_style,
        )
    )
    elements.append(Spacer(1, 15))

    data = [["Período", "Dia e Horário", "Matrícula", "Colaborador Agendado", "Status"]]

    for horario, colaborador in agenda.items():
        partes = horario.split(" | ")
        p_periodo = partes[0] if len(partes) > 0 else ""
        p_diahora = partes[1] if len(partes) > 1 else horario

        if colaborador not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] and "[" in colaborador and "]" in colaborador:
            mat = colaborador.split("]")[0].replace("[", "").strip()
            nome = colaborador.split("]")[1].strip()
        else:
            mat = "—"
            nome = colaborador

        st_status = status_agendamentos.get(horario, "Pendente")
        data.append([p_periodo, p_diahora, mat, nome, st_status])

    t = Table(data, colWidths=[110, 160, 60, 140, 70])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
        ])
    )

    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

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


# --- BARRA LATERAL (PAINEL DE NAVEGAÇÃO E PERÍODO) ---
with st.sidebar:
    st.image("https://img.icons8.com/isometric-folders/100/massage.png", width=65)
    st.title("SPA Massagem")
    st.caption("Painel de Gestão e Sorteios")
    st.markdown("---")

    st.subheader("🗓️ Filtro de Período")
    meses = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    agora = datetime.datetime.now()
    mes_selecionado = st.selectbox("Selecione o Mês", meses, index=agora.month - 1)
    ano_selecionado = st.number_input("Ano", min_value=2024, max_value=2030, value=agora.year)

    st.markdown("---")
    st.markdown("<b>Desenvolvido para RH & Bem-Estar</b>", unsafe_allow_html=True)


# Carrega dados do arquivo correspondente
dados = carregar_dados(mes_selecionado, ano_selecionado)
pessoas = dados.get("pessoas", [])
agenda = dados.get("agenda", {})
status_agendamentos = dados.get("status_agendamentos", {})


# --- DASHBOARD DE MÉTRICAS (KPIs VISUAIS) ---
st.title("💆‍♂️ Dashboard de Gestão de Massagens")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)

total_cad = len(pessoas)
aptos_count = sum(1 for p in pessoas if p.get("apto", True))
atendidos_count = sum(1 for p in pessoas if p.get("participou_semana", False))
vagos_count = sum(1 for p in agenda.values() if p == "--- VAGO ---")

with kpi1:
    st.markdown(f'''
    <div class="metric-card" style="border-left-color: #2563eb;">
        <p>Total Cadastrados</p>
        <h2>👥 {total_cad}</h2>
    </div>
    ''', unsafe_allow_html=True)

with kpi2:
    st.markdown(f'''
    <div class="metric-card" style="border-left-color: #10b981;">
        <p>Aptos / Ativos</p>
        <h2>✅ {aptos_count}</h2>
    </div>
    ''', unsafe_allow_html=True)

with kpi3:
    st.markdown(f'''
    <div class="metric-card" style="border-left-color: #f59e0b;">
        <p>Atendidos Semana</p>
        <h2>💆 {atendidos_count}</h2>
    </div>
    ''', unsafe_allow_html=True)

with kpi4:
    st.markdown(f'''
    <div class="metric-card" style="border-left-color: #6366f1;">
        <p>Horários Vagos</p>
        <h2>📅 {vagos_count}</h2>
    </div>
    ''', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# --- NAVEGAÇÃO POR ABAS ---
tab1, tab2 = st.tabs(["👥 Cadastro & Gestão de Colaboradores", "📅 Grade de Horários & Sorteios"])

# --- ABA 1: COLABORADORES ---
with tab1:
    col_cad, col_imp = st.columns([3, 2])

    with col_cad:
        with st.expander("➕ Cadastrar Novo Colaborador", expanded=True):
            with st.form("form_cadastrar", clear_on_submit=True):
                c1, c2, c3 = st.columns([1, 2, 2])
                mat_in = c1.text_input("Matrícula")
                nome_in = c2.text_input("Nome Completo")
                tel_in = c3.text_input("Telefone (WhatsApp)")
                submit_add = st.form_submit_button("Salvar Colaborador", use_container_width=True)

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
                                "faltas": 0,
                            })
                            dados["pessoas"] = pessoas
                            salvar_dados(dados, mes_selecionado, ano_selecionado)
                            st.success(f"✅ {nome_in} cadastrado com sucesso!")
                            st.rerun()
                        else:
                            st.warning("⚠️ Matrícula já existente.")
                    else:
                        st.warning("⚠️ Preencha Matrícula e Nome Completo.")

    with col_imp:
        with st.expander("📥 Importação via Ficheiro CSV", expanded=True):
            uploaded_csv = st.file_uploader("Carregar planilha em CSV", type=["csv"])
            if uploaded_csv is not None:
                try:
                    df_imp = pd.read_csv(uploaded_csv, sep=None, engine='python')
                    novos = 0
                    for _, row in df_imp.iterrows():
                        mat = str(row.get("matricula", row.get("Matricula", "AUTO"))).strip()
                        nome = str(row.get("nome", row.get("Nome", ""))).strip()
                        tel = str(row.get("telefone", row.get("Telefone", ""))).strip()
                        if nome and not any(p["nome"].lower() == nome.lower() for p in pessoas):
                            pessoas.append({
                                "matricula": mat, "nome": nome, "telefone": tel,
                                "apto": True, "participou_semana": False,
                                "total_participacoes": 0, "faltas": 0
                            })
                            novos += 1
                    dados["pessoas"] = pessoas
                    salvar_dados(dados, mes_selecionado, ano_selecionado)
                    st.success(f"🎉 {novos} colaboradores importados!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao processar ficheiro CSV: {e}")

    st.markdown("### 📋 Quadro de Colaboradores")
    if pessoas:
        df_pessoas = pd.DataFrame(pessoas)
        
        # Renomear colunas para melhor exibição
        cols_map = {
            "matricula": "Matrícula",
            "nome": "Nome do Colaborador",
            "telefone": "Telefone / Whats",
            "apto": "Apto (Ativo)",
            "participou_semana": "Foi nesta Semana?",
            "total_participacoes": "Sessões Acumuladas",
            "faltas": "Faltas"
        }
        df_display = df_pessoas.rename(columns=cols_map)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        st.markdown("#### ⚙️ Ações Rápidas de Gestão")
        act_col1, act_col2 = st.columns(2)

        with act_col1:
            mat_toggle = st.selectbox(
                "Selecionar por Matrícula:", [p["matricula"] for p in pessoas], key="sb_toggle_mat"
            )
            if st.button("🏖️ Alternar Status (Ativo / Férias)", use_container_width=True):
                for p in pessoas:
                    if p["matricula"] == mat_toggle:
                        p["apto"] = not p.get("apto", True)
                dados["pessoas"] = pessoas
                salvar_dados(dados, mes_selecionado, ano_selecionado)
                st.rerun()

        with act_col2:
            st.write(" ")
            st.write(" ")
            if st.button("🔄 Iniciar Nova Semana (Zerar Presença Semanal)", use_container_width=True):
                for p in pessoas:
                    p["participou_semana"] = False
                dados["pessoas"] = pessoas
                salvar_dados(dados, mes_selecionado, ano_selecionado)
                st.success("Presenças da semana reiniciadas com sucesso!")
                st.rerun()
    else:
        st.info("Nenhum colaborador cadastrado para este mês.")

# --- ABA 2: GRADE E SORTEIOS ---
with tab2:
    with st.expander("⚡ Gerador de Grade de Horários", expanded=False):
        c_sem, c_ini, c_fim, c_dur = st.columns(4)
        semana_sel = c_sem.selectbox(
            "Semana do Mês", ["1ª Semana", "2ª Semana", "3ª Semana", "4ª Semana", "5ª Semana"]
        )
        dias_sel = st.multiselect(
            "Dias da Semana",
            ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"],
            default=["Segunda", "Quarta", "Sexta"]
        )

        h_inicio = c_ini.time_input("Horário Início", datetime.time(8, 0))
        h_fim = c_fim.time_input("Horário Fim", datetime.time(17, 0))
        duracao_min = c_dur.number_input("Duração por Sessão (min)", min_value=10, max_value=120, value=30)

        if st.button("Criar Grade de Horários", use_container_width=True):
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
            st.success(f"{novos} novos horários adicionados à grade!")
            st.rerun()

    st.markdown("### 🗓️ Agenda Semanal de Atendimentos")

    if agenda:
        # Ações de Controle e Relatórios
        ca1, ca2, ca3, ca4 = st.columns(4)
        
        if ca1.button("🎲 Sortear TODOS os Vagos", use_container_width=True):
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

        if ca2.button("🧹 Limpar Apenas Sorteados", use_container_width=True):
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

        if ca3.button("🗑️ Limpar Grade Completa", use_container_width=True):
            dados["agenda"] = {}
            dados["status_agendamentos"] = {}
            salvar_dados(dados, mes_selecionado, ano_selecionado)
            st.rerun()

        if REPORTLAB_DISPONIVEL:
            semana_nome = list(agenda.keys())[0].split(" | ")[0].split(" - ")[1] if agenda else "1ª Semana"
            pdf_data = gerar_pdf_bytes(agenda, status_agendamentos, mes_selecionado, semana_nome)
            ca4.download_button(
                label="📄 Exportar para PDF",
                data=pdf_data,
                file_name=f"Escala_Massagem_{mes_selecionado}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

        # Edição Individual de Agendamento
        with st.expander("✍️ Agendamento Manual / Bloqueio / Presença", expanded=False):
            col_e1, col_e2, col_e3 = st.columns(3)
            horario_edit = col_e1.selectbox("Selecione o Horário Slot", list(agenda.keys()), key="sb_edit_h")
            
            opcoes_colab = ["--- VAGO ---", "🔒 [BLOQUEADO]"] + [f"[{p.get('matricula')}] {p['nome']}" for p in pessoas]
            colab_manual = col_e2.selectbox("Atribuir Colaborador", opcoes_colab, key="sb_edit_c")
            st_manual = col_e3.selectbox("Status Presença", ["Pendente", "Realizado", "Falta"], key="sb_edit_st")

            if st.button("Salvar Alteração Manual", use_container_width=True):
                antigo = agenda.get(horario_edit)
                if antigo not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] and antigo != colab_manual:
                    for p in pessoas:
                        if f"[{p.get('matricula')}] {p['nome']}" == antigo:
                            p["participou_semana"] = False
                            p["total_participacoes"] = max(0, p.get("total_participacoes", 1) - 1)

                agenda[horario_edit] = colab_manual
                status_agendamentos[horario_edit] = st_manual

                if colab_manual not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] and antigo != colab_manual:
                    for p in pessoas:
                        if f"[{p.get('matricula')}] {p['nome']}" == colab_manual:
                            p["participou_semana"] = True
                            p["total_participacoes"] = p.get("total_participacoes", 0) + 1

                dados["agenda"] = agenda
                dados["pessoas"] = pessoas
                dados["status_agendamentos"] = status_agendamentos
                salvar_dados(dados, mes_selecionado, ano_selecionado)
                st.success("Horário atualizado com sucesso!")
                st.rerun()

        # Tabela Visual da Agenda
        df_agenda = pd.DataFrame([
            {
                "Horário Slot": h,
                "Colaborador Agendado": p,
                "Status Presença": status_agendamentos.get(h, "Pendente"),
            }
            for h, p in agenda.items()
        ])
        st.dataframe(df_agenda, use_container_width=True, hide_index=True)

        # --- PAINEL DE NOTIFICAÇÕES WHATSAPP ---
        st.markdown("---")
        st.subheader("💬 Central de Lembretes via WhatsApp")

        opcoes_lembrete = []
        mapa_horarios = {}

        for h, colab in agenda.items():
            if colab not in ["--- VAGO ---", "🔒 [BLOQUEADO]"]:
                partes = h.split(" | ")
                dia_hora_curto = partes[1] if len(partes) > 1 else h
                rotulo = f"{colab} ➔ {dia_hora_curto}"
                opcoes_lembrete.append(rotulo)
                mapa_horarios[rotulo] = (h, colab)

        if opcoes_lembrete:
            selecionados = st.multiselect(
                "Selecione um ou vários colaboradores agendados para disparar o lembrete:",
                options=opcoes_lembrete,
                default=[],
            )

            if selecionados:
                st.markdown("#### 🔗 Links de Envio Personalizados")
                for rotulo in selecionados:
                    horario_orig, colab_orig = mapa_horarios[rotulo]

                    p_obj = next(
                        (p for p in pessoas if f"[{p.get('matricula')}] {p['nome']}" == colab_orig),
                        None,
                    )

                    if p_obj and p_obj.get("telefone"):
                        tel = "".join(filter(str.isdigit, str(p_obj["telefone"])))
                        if not tel.startswith("55"):
                            tel = "55" + tel

                        msg = (
                            f"Olá *{p_obj['nome']}*! 👋\n\n"
                            f"Lembrete da sua sessão de *Massagem Relaxante*:\n"
                            f"📅 *Horário:* {horario_orig}\n\n"
                            f"Por favor, chegue com 5 minutos de antecedência. Bom relaxamento! 💆‍♂️✨"
                        )

                        link = f"https://web.whatsapp.com/send?phone={tel}&text={urllib.parse.quote(msg)}"
                        st.markdown(f"👉 **{p_obj['nome']}**: [Enviar mensagem via WhatsApp Web]({link})")
                    else:
                        st.warning(f"⚠️ {colab_orig}: Sem número de telefone registado.")
        else:
            st.info("Nenhum colaborador agendado na grade para envio de lembretes.")
    else:
        st.info("Nenhuma grade de horários gerada para o mês selecionado.")
