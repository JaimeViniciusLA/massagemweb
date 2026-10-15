import calendar
import datetime
import io
import json
import os
import random
import re
import urllib.parse
import pandas as pd
from nicegui import ui

# Tenta importar ReportLab para PDF
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_DISPONIVEL = True
except ImportError:
    REPORTLAB_DISPONIVEL = False

# --- CONFIGURAÇÕES DE DATAS ---
MESES_DICT = {
    "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4, "Maio": 5, "Junho": 6,
    "Julho": 7, "Agosto": 8, "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
}
DIAS_PT = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}

# --- ESTADO GLOBAL ---
agora = datetime.datetime.now()
estado = {
    "mes_nome": list(MESES_DICT.keys())[agora.month - 1],
    "ano": agora.year,
    "dt_selecionada": agora.date(),
    "filtro_colaborador": "",
    "filtro_status": "Todos",
    "dados": {"pessoas": [], "agenda": {}, "status_agendamentos": {}, "tipo_agendamento": {}}
}

# --- AUXILIARES DE PARSING E ORDENAÇÃO ---
def parse_chave_slot(chave):
    """Extrai (data, hora_inicio) a partir da string da chave do slot para ordenação cronológica."""
    try:
        partes = chave.split(" | ")
        dia_parte = partes[0]
        hora_parte = partes[1] if len(partes) > 1 else "00:00"
        
        # Extrai data entre parênteses: ex "(13/10/2026)"
        dt_str = dia_parte.split("(")[1].split(")")[0] if "(" in dia_parte and ")" in dia_parte else ""
        dt_obj = datetime.datetime.strptime(dt_str, "%d/%m/%Y").date() if dt_str else datetime.date.min
        
        # Extrai horário de início: ex "08:30"
        h_ini = hora_parte.split(" às ")[0].strip() if " às " in hora_parte else hora_parte
        h_obj = datetime.datetime.strptime(h_ini, "%H:%M").time() if h_ini else datetime.time.min
        
        return (dt_obj, h_obj)
    except Exception:
        return (datetime.date.min, datetime.time.min)

def extrair_info_colaborador(colab_str):
    """Retorna (matricula, nome) de uma string de agendamento de colaborador."""
    if not colab_str or colab_str in ["--- VAGO ---", "🔒 [BLOQUEADO]"]:
        return ("—", colab_str or "--- VAGO ---")
    if "[" in colab_str and "]" in colab_str:
        mat = colab_str.split("]")[0].replace("[", "").strip()
        nome = colab_str.split("]")[1].strip()
        return (mat, nome)
    return ("—", colab_str.strip())

# --- PERSISTÊNCIA DE DADOS ---
ARQUIVO_COLABORADORES_GLOBAL = "colaboradores.json"

def obter_nome_arquivo():
    return f"massagem_{estado['mes_nome']}_{estado['ano']}.json"

def carregar_dados():
    # 1. Carrega base de colaboradores permanente (se existir)
    colaboradores_base = []
    if os.path.exists(ARQUIVO_COLABORADORES_GLOBAL):
        try:
            with open(ARQUIVO_COLABORADORES_GLOBAL, "r", encoding="utf-8") as f:
                colaboradores_base = json.load(f)
        except Exception:
            colaboradores_base = []

    # 2. Carrega dados do mês
    filename = obter_nome_arquivo()
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                dados = json.load(f)
                agenda_limpa, status_limpo, tipo_limpo = {}, {}, {}
                for k, v in dados.get("agenda", {}).items():
                    nova_chave = k.split(" - ")[0] if " - " in k else k
                    agenda_limpa[nova_chave] = v
                    status_limpo[nova_chave] = dados.get("status_agendamentos", {}).get(k, "Pendente")
                    tipo_limpo[nova_chave] = dados.get("tipo_agendamento", {}).get(k, "Sorteado" if v not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] else "N/A")
                
                # Pessoas do mês ou da base permanente
                pessoas_mes = dados.get("pessoas", [])
                if not pessoas_mes and colaboradores_base:
                    pessoas_mes = [dict(p, total_participacoes=0, faltas=0, participou_semana=False) for p in colaboradores_base]
                elif pessoas_mes and not colaboradores_base:
                    colaboradores_base = pessoas_mes
                    try:
                        with open(ARQUIVO_COLABORADORES_GLOBAL, "w", encoding="utf-8") as fg:
                            json.dump(colaboradores_base, fg, ensure_ascii=False, indent=4)
                    except Exception:
                        pass

                dados["pessoas"] = pessoas_mes
                dados["agenda"] = agenda_limpa
                dados["status_agendamentos"] = status_limpo
                dados["tipo_agendamento"] = tipo_limpo
                estado["dados"] = dados
                sincronizar_contadores()
                return
        except Exception:
            pass

    # Novo mês: herda colaboradores da base central sem perder o cadastro
    novas_pessoas = [dict(p, total_participacoes=0, faltas=0, participou_semana=False) for p in colaboradores_base]
    estado["dados"] = {
        "pessoas": novas_pessoas,
        "agenda": {},
        "status_agendamentos": {},
        "tipo_agendamento": {}
    }
    sincronizar_contadores()

def sincronizar_contadores():
    pessoas = estado["dados"].get("pessoas", [])
    agenda = estado["dados"].get("agenda", {})
    status_map = estado["dados"].get("status_agendamentos", {})
    
    contagem_participacoes = {}
    contagem_faltas = {}
    colabs_semana = set()

    ref_dt = estado.get("dt_selecionada") or datetime.date.today()
    ref_ano, ref_semana, _ = ref_dt.isocalendar()

    for h, colab in agenda.items():
        if colab not in ["--- VAGO ---", "🔒 [BLOQUEADO]"]:
            st = status_map.get(h, "Pendente")
            contagem_participacoes[colab] = contagem_participacoes.get(colab, 0) + 1
            if st == "Falta":
                contagem_faltas[colab] = contagem_faltas.get(colab, 0) + 1

            slot_dt, _ = parse_chave_slot(h)
            if slot_dt != datetime.date.min:
                s_ano, s_sem, _ = slot_dt.isocalendar()
                if s_ano == ref_ano and s_sem == ref_semana:
                    colabs_semana.add(colab)

    for p in pessoas:
        chave_p = f"[{p.get('matricula')}] {p['nome']}"
        p["participou_semana"] = chave_p in colabs_semana
        p["total_participacoes"] = contagem_participacoes.get(chave_p, 0)
        p["faltas"] = contagem_faltas.get(chave_p, 0)
    
    estado["dados"]["pessoas"] = pessoas

def salvar_dados():
    sincronizar_contadores()
    
    # 1. Limpa chaves órfãs antes de salvar
    chaves_validas = set(estado["dados"]["agenda"].keys())
    estado["dados"]["status_agendamentos"] = {k: v for k, v in estado["dados"]["status_agendamentos"].items() if k in chaves_validas}
    estado["dados"]["tipo_agendamento"] = {k: v for k, v in estado["dados"]["tipo_agendamento"].items() if k in chaves_validas}

    # 2. Salva arquivo do mês com gravação atômica segura
    filename = obter_nome_arquivo()
    temp_filename = f"{filename}.tmp"
    with open(temp_filename, "w", encoding="utf-8") as f:
        json.dump(estado["dados"], f, ensure_ascii=False, indent=4)
    os.replace(temp_filename, filename)

    # 3. Mantém sincronizada a base permanente de colaboradores
    try:
        colabs_persist = []
        for p in estado["dados"].get("pessoas", []):
            colabs_persist.append({
                "matricula": p.get("matricula", "").strip(),
                "nome": p.get("nome", "").strip(),
                "telefone": p.get("telefone", "").strip(),
                "apto": p.get("apto", True)
            })
        temp_glob = f"{ARQUIVO_COLABORADORES_GLOBAL}.tmp"
        with open(temp_glob, "w", encoding="utf-8") as fg:
            json.dump(colabs_persist, fg, ensure_ascii=False, indent=4)
        os.replace(temp_glob, ARQUIVO_COLABORADORES_GLOBAL)
    except Exception:
        pass

# --- EXPORTAÇÕES ---
def gerar_excel_bytes(dt_str=None):
    buffer = io.BytesIO()
    rows = []
    
    chaves_ordenadas = sorted(estado["dados"]["agenda"].keys(), key=parse_chave_slot)
    for h in chaves_ordenadas:
        if dt_str and dt_str not in h: continue
        partes = h.split(" | ")
        dia = partes[0] if len(partes) > 0 else ""
        hora = partes[1] if len(partes) > 1 else h
        colab = estado["dados"]["agenda"][h]
        mat, nome = extrair_info_colaborador(colab)

        rows.append({
            "Data / Dia": dia,
            "Horário Slot": hora,
            "Matrícula": mat,
            "Colaborador Agendado": nome,
            "Origem": estado["dados"]["tipo_agendamento"].get(h, "N/A"),
            "Status Presença": estado["dados"]["status_agendamentos"].get(h, "Pendente")
        })
        
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Agenda Massagem")
        worksheet = writer.sheets["Agenda Massagem"]
        # Ajuste inteligente da largura de colunas no Excel
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = col[0].column_letter
            worksheet.column_dimensions[col_letter].width = max(max_len + 4, 12)
    buffer.seek(0)
    return buffer.getvalue()

def gerar_pdf_bytes(dt_str=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Heading1"], fontSize=15, textColor=colors.HexColor("#0f172a"))
    sub_style = ParagraphStyle("S", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#334155"))
    cell_style = ParagraphStyle("C", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#0f172a"))
    hdr_style = ParagraphStyle("H", parent=styles["Normal"], fontSize=8, fontName="Helvetica-Bold", textColor=colors.white)

    elements.append(Paragraph("<b>ESCALA DE MASSAGEM CORPORATIVA</b>", title_style))
    elements.append(Paragraph(f"Período: {dt_str or estado['mes_nome'] + '/' + str(estado['ano'])} | Emitido em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}", sub_style))
    elements.append(Spacer(1, 12))

    data = [[
        Paragraph("<b>Data / Dia</b>", hdr_style),
        Paragraph("<b>Horário</b>", hdr_style),
        Paragraph("<b>Matrícula</b>", hdr_style),
        Paragraph("<b>Colaborador</b>", hdr_style),
        Paragraph("<b>Status</b>", hdr_style)
    ]]

    chaves_ordenadas = sorted(estado["dados"]["agenda"].keys(), key=parse_chave_slot)
    itens_filtrados = [h for h in chaves_ordenadas if not dt_str or dt_str in h]

    if not itens_filtrados:
        data.append([
            Paragraph("Nenhum agendamento encontrado", cell_style),
            Paragraph("—", cell_style),
            Paragraph("—", cell_style),
            Paragraph("—", cell_style),
            Paragraph("—", cell_style)
        ])
    else:
        for h in itens_filtrados:
            partes = h.split(" | ")
            dia = partes[0] if len(partes) > 0 else ""
            hora = partes[1] if len(partes) > 1 else h
            colab = estado["dados"]["agenda"][h]
            mat, nome = extrair_info_colaborador(colab)
            st = estado["dados"]["status_agendamentos"].get(h, "Pendente")
            
            data.append([
                Paragraph(dia, cell_style),
                Paragraph(hora, cell_style),
                Paragraph(mat, cell_style),
                Paragraph(nome, cell_style),
                Paragraph(st, cell_style)
            ])

    t = Table(data, colWidths=[120, 95, 65, 185, 80])
    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
    ]
    if len(data) > 1:
        table_styles.append(("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")))
    t.setStyle(TableStyle(table_styles))
    
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

# --- INTERFACE NICEGUI ---
@ui.page('/')
def main_page():
    carregar_dados()

    # CABEÇALHO DA PÁGINA (ALTO CONTRASTE)
    with ui.header().classes('bg-slate-900 text-white p-4 flex justify-between items-center shadow-lg'):
        with ui.row().classes('items-center gap-3'):
            ui.label('💆‍♂️ SPA Massagem Corporativa').classes('text-2xl font-black tracking-wide text-white')
            ui.badge('v2.2 Alto Contraste', color='amber-9').classes('text-xs font-black text-slate-950 px-2 py-0.5')
        ui.label('Painel de Gestão e Sorteio').classes('text-sm font-bold text-slate-200')

    with ui.row().classes('w-full no-wrap gap-4 p-4 bg-slate-100 min-h-screen'):
        
        # BARRA LATERAL (CALENDÁRIO & PERÍODO)
        with ui.card().classes('w-80 p-4 bg-white border border-slate-300 shadow-sm rounded-xl self-start'):
            ui.label('🗓️ Período de Atendimento').classes('text-lg font-black text-slate-900 mb-2')
            
            def ao_mudar_periodo():
                estado['dt_selecionada'] = None
                carregar_dados()
                renderizar_calendario.refresh()
                renderizar_tudo.refresh()

            ui.select(list(MESES_DICT.keys()), value=estado['mes_nome'], label='Mês de Referência', on_change=ao_mudar_periodo).bind_value(estado, 'mes_nome').props('outlined dense bg-color=white').classes('w-full font-bold text-slate-900')
            ui.number('Ano', value=estado['ano'], format='%d', on_change=ao_mudar_periodo).bind_value(estado, 'ano').props('outlined dense bg-color=white').classes('w-full font-bold text-slate-900 mt-2')

            ui.separator().classes('my-4')
            ui.label('📅 Calendário do Mês').classes('text-md font-black text-slate-900')
            
            def selecionar_mes_inteiro():
                estado['dt_selecionada'] = None
                renderizar_calendario.refresh()
                renderizar_tudo.refresh()

            ui.button('🌐 Ver Mês Inteiro na Tabela', on_click=selecionar_mes_inteiro).classes('w-full bg-slate-800 hover:bg-slate-900 text-white font-extrabold mb-3 shadow-sm py-2 rounded-lg')

            # GRADE DO CALENDÁRIO COM ALTO CONTRASTE
            @ui.refreshable
            def renderizar_calendario():
                num_m = MESES_DICT[estado['mes_nome']]
                cal = calendar.Calendar(firstweekday=calendar.SUNDAY)
                matriz = cal.monthdayscalendar(int(estado['ano']), num_m)

                with ui.grid(columns=7).classes('w-full text-center gap-1'):
                    ui.label('D').classes('font-black text-red-700 text-xs py-1')
                    for d in ["S", "T", "Q", "Q", "S"]:
                        ui.label(d).classes('font-black text-slate-900 text-xs py-1')
                    ui.label('S').classes('font-black text-red-700 text-xs py-1')

                    for week in matriz:
                        for idx_dia, day in enumerate(week):
                            if day == 0:
                                ui.label('•').classes('text-slate-300 font-bold')
                            else:
                                dt_b = datetime.date(int(estado['ano']), num_m, day)
                                dt_s = dt_b.strftime("%d/%m/%Y")
                                is_sel = (estado['dt_selecionada'] == dt_b)
                                is_fim_de_semana = (idx_dia == 0 or idx_dia == 6)
                                is_hoje = (datetime.date.today() == dt_b)
                                
                                slots_dia = [h for h in estado["dados"]["agenda"].keys() if dt_s in h]
                                tem_grade = len(slots_dia) > 0
                                tem_pend = any(estado["dados"]["status_agendamentos"].get(h) == "Pendente" for h in slots_dia)
                                
                                prefixo = ""
                                if tem_grade:
                                    prefixo = "🔴" if tem_pend else "🔵"

                                btn_lbl = f"{prefixo}{day:02d}" if prefixo else f"{day:02d}"
                                
                                def clique_dia(d=dt_b):
                                    estado['dt_selecionada'] = d
                                    renderizar_calendario.refresh()
                                    renderizar_tudo.refresh()

                                btn_day = ui.button(btn_lbl, on_click=clique_dia)
                                btn_day.classes('p-0 h-8 text-xs font-black shadow-none rounded-lg')
                                
                                # CORES DE ALTO CONTRASTE WCAG
                                if is_hoje:
                                    # DIA ATUAL (HOJE): SEMPRE VERDE SÓLIDO!
                                    borda_sel = 'border: 3px solid #0f172a !important;' if is_sel else 'border: 1px solid #14532d !important;'
                                    btn_day.style(f'background-color: #16a34a !important; color: #ffffff !important; font-weight: 900; {borda_sel}')
                                elif is_fim_de_semana:
                                    # FIM DE SEMANA (SÁB/DOM): SEMPRE VERMELHO SÓLIDO!
                                    borda_sel = 'border: 3px solid #0f172a !important;' if is_sel else 'border: 1px solid #991b1b !important;'
                                    btn_day.style(f'background-color: #dc2626 !important; color: #ffffff !important; font-weight: 900; {borda_sel}')
                                elif is_sel:
                                    # DIA NORMAL SELECIONADO: AZUL
                                    btn_day.style('background-color: #1d4ed8 !important; color: #ffffff !important; font-weight: 900; border: 2px solid #0f172a !important;')
                                else:
                                    # DIA NORMAL NÃO SELECIONADO: BRANCO
                                    btn_day.style('background-color: #ffffff !important; color: #0f172a !important; border: 1px solid #cbd5e1 !important; font-weight: 800;')

            renderizar_calendario()

            ui.separator().classes('my-4')
            ui.label('Legenda de Status:').classes('text-xs font-black text-slate-900 mb-1')
            with ui.column().classes('gap-1 text-xs font-bold text-slate-800'):
                ui.label('🟩 Dia Atual (Hoje)')
                ui.label('🔴 Grade com massagens pendentes')
                ui.label('🔵 Todas massagens concluídas')
                ui.label('🟥 Fim de Semana (Domingo e Sábado)')

        # PAINEL PRINCIPAL DA DIREITA
        with ui.column().classes('flex-1 gap-4'):
            @ui.refreshable
            def renderizar_tudo():
                dt_filtro_str = estado['dt_selecionada'].strftime("%d/%m/%Y") if estado['dt_selecionada'] else None

                # KPI CARDS CONTEXTUAIS COM CORES VIVAS E ALTO CONTRASTE
                with ui.row().classes('w-full gap-3 flex-wrap'):
                    agenda_total = estado["dados"]["agenda"]
                    status_total = estado["dados"]["status_agendamentos"]
                    
                    slots_contexto = {h: colab for h, colab in agenda_total.items() if not dt_filtro_str or dt_filtro_str in h}
                    total_slots = len(slots_contexto)
                    vagos_ctx = sum(1 for colab in slots_contexto.values() if colab == "--- VAGO ---")
                    realizados_ctx = sum(1 for h in slots_contexto.keys() if status_total.get(h) == "Realizado")
                    faltas_ctx = sum(1 for h in slots_contexto.keys() if status_total.get(h) == "Falta")
                    
                    total_atendiveis = realizados_ctx + faltas_ctx
                    taxa_presenca = f"{round((realizados_ctx / total_atendiveis) * 100)}%" if total_atendiveis > 0 else "—"

                    kpis = [
                        ("Total Horários", total_slots, "text-slate-950", "border-slate-300"),
                        ("Horários Vagos", vagos_ctx, "text-amber-800", "border-amber-300"),
                        ("Atendidos", realizados_ctx, "text-emerald-800", "border-emerald-300"),
                        ("Faltas", faltas_ctx, "text-rose-800", "border-rose-300"),
                        ("Taxa Presença", taxa_presenca, "text-blue-900", "border-blue-300")
                    ]

                    for label, val, cor, b_cor in kpis:
                        with ui.card().classes(f'flex-1 min-w-[130px] p-3 bg-white border-2 {b_cor} rounded-xl shadow-xs'):
                            ui.label(label).classes('text-[11px] font-black text-slate-700 uppercase tracking-wider')
                            ui.label(str(val)).classes(f'text-2xl font-black {cor}')

                # PAINEL DE ABAS
                with ui.tabs().classes('w-full bg-white border-b-2 border-slate-300 rounded-t-lg shadow-xs') as tabs:
                    tab1 = ui.tab('📅 Grade de Agendamentos & Sorteios').classes('font-black text-slate-800')
                    tab2 = ui.tab('👥 Base de Colaboradores').classes('font-black text-slate-800')

                with ui.tab_panels(tabs, value=tab1).classes('w-full bg-transparent'):
                    
                    # TAB 1: AGENDA E SORTEIO
                    with ui.tab_panel(tab1).classes('p-0 gap-4'):
                        
                        # PASSO 1: GERAR HORÁRIOS COM DESIGN NÍTIDO E INTERVALO DE ALMOÇO
                        with ui.card().classes('w-full p-4 bg-white border border-slate-300 rounded-xl shadow-xs gap-4'):
                            ui.label('🛠️ Passo 1: Gerar e Configurar Grade de Horários').classes('text-lg font-black text-slate-900')
                            
                            # LINHA 1: JORNADA DE TRABALHO (CAMPOS COM BORDAS DEFINIDAS)
                            with ui.row().classes('w-full items-center gap-4 flex-wrap'):
                                dt_in = ui.input('Data Massagem (DD/MM/AAAA)', value=dt_filtro_str or datetime.date.today().strftime("%d/%m/%Y")).props('outlined dense bg-color=white').classes('w-56 font-bold text-slate-900')
                                h_ini = ui.input('Horário Inicial', value='08:00').props('outlined dense bg-color=white').classes('w-32 font-bold text-slate-900')
                                h_fim = ui.input('Horário Final', value='17:00').props('outlined dense bg-color=white').classes('w-32 font-bold text-slate-900')
                                dur_min = ui.number('Duração (min)', value=30, min=5, max=180).props('outlined dense bg-color=white').classes('w-32 font-bold text-slate-900')

                            # LINHA 2: INTERVALO / ALMOÇO COM ALTO CONTRASTE
                            with ui.row().classes('w-full items-center gap-4 flex-wrap bg-amber-50 p-3 rounded-xl border-2 border-amber-300 shadow-xs'):
                                chk_almoco = ui.checkbox('🍽️ Pausar para Intervalo / Almoço?', value=True).classes('text-slate-900 font-black text-sm')
                                h_alm_ini = ui.input('Início Almoço', value='12:00').props('outlined dense bg-color=white').classes('w-32 font-bold text-slate-900')
                                h_alm_fim = ui.input('Fim Almoço', value='13:00').props('outlined dense bg-color=white').classes('w-32 font-bold text-slate-900')
                                ui.label('ℹ️ Nenhum horário de massagem será criado dentro deste intervalo.').classes('text-xs text-amber-950 font-bold italic')

                            def gerar_grade():
                                try:
                                    if not dt_in.value or not h_ini.value or not h_fim.value:
                                        ui.notify("⚠️ Preencha todos os campos de data e horário!", type='warning')
                                        return

                                    duracao = int(dur_min.value or 0)
                                    if duracao < 5:
                                        ui.notify("⚠️ A duração do slot deve ser de pelo menos 5 minutos!", type='warning')
                                        return

                                    curr = datetime.datetime.strptime(f"{dt_in.value} {h_ini.value}", "%d/%m/%Y %H:%M")
                                    end = datetime.datetime.strptime(f"{dt_in.value} {h_fim.value}", "%d/%m/%Y %H:%M")
                                    
                                    if curr >= end:
                                        ui.notify("⚠️ O Horário Inicial deve ser menor que o Horário Final!", type='warning')
                                        return

                                    dt_alm_i = datetime.datetime.strptime(f"{dt_in.value} {h_alm_ini.value}", "%d/%m/%Y %H:%M") if chk_almoco.value else None
                                    dt_alm_f = datetime.datetime.strptime(f"{dt_in.value} {h_alm_fim.value}", "%d/%m/%Y %H:%M") if chk_almoco.value else None

                                    if chk_almoco.value and dt_alm_i >= dt_alm_f:
                                        ui.notify("⚠️ Início do almoço deve ser menor que o Fim!", type='warning')
                                        return

                                    dt_obj = curr.date()
                                    nome_dia = DIAS_PT[dt_obj.weekday()]
                                    data_str = dt_obj.strftime("%d/%m/%Y")
                                    novos = 0

                                    while curr < end:
                                        nxt = curr + datetime.timedelta(minutes=duracao)
                                        if nxt > end: break
                                        
                                        # Pula slots que colidem com intervalo de almoço
                                        if chk_almoco.value:
                                            if curr < dt_alm_f and nxt > dt_alm_i:
                                                curr = dt_alm_f
                                                continue

                                        chave = f"{nome_dia} ({data_str}) | {curr.strftime('%H:%M')} às {nxt.strftime('%H:%M')}"
                                        if chave not in estado["dados"]["agenda"]:
                                            estado["dados"]["agenda"][chave] = "--- VAGO ---"
                                            estado["dados"]["status_agendamentos"][chave] = "Pendente"
                                            estado["dados"]["tipo_agendamento"][chave] = "N/A"
                                            novos += 1
                                        curr = nxt

                                    salvar_dados()
                                    estado['dt_selecionada'] = dt_obj
                                    ui.notify(f"✅ {novos} horários gerados com sucesso!", type='positive')
                                    renderizar_calendario.refresh()
                                    renderizar_tudo.refresh()
                                except Exception as e:
                                    ui.notify(f"Erro ao gerar horários: {e}", type='negative')

                            with ui.row().classes('w-full justify-start mt-1'):
                                btn_g = ui.button('➕ GERAR HORÁRIOS', on_click=gerar_grade).classes('text-white font-black h-11 px-8 rounded-lg shadow-md')
                                btn_g.style('background-color: #2563eb !important;')

                        # PASSO 2: SORTEIO E AÇÕES (BOTÕES DE EXPORTAÇÃO NO CANTO DIREITO)
                        with ui.card().classes('w-full p-4 bg-white border border-slate-300 rounded-xl shadow-xs gap-2'):
                            alvo_str = f"Dia {dt_filtro_str}" if dt_filtro_str else f"Mês de {estado['mes_nome']}/{estado['ano']}"
                            ui.label(f'🎲 Passo 2: Sorteio e Ações ({alvo_str})').classes('text-lg font-black text-slate-900')
                            
                            with ui.row().classes('w-full items-center justify-between gap-3 p-1 flex-wrap'):
                                # AÇÕES PRINCIPAIS (ESQUERDA)
                                with ui.row().classes('items-center gap-2 flex-wrap'):
                                    
                                    # SORTEIO BALANCEADO
                                    def executar_sorteio():
                                        chaves_ordenadas = sorted(estado["dados"]["agenda"].keys(), key=parse_chave_slot)
                                        vagos = [h for h in chaves_ordenadas if estado["dados"]["agenda"][h] == "--- VAGO ---" and (not dt_filtro_str or dt_filtro_str in h)]
                                        
                                        if not vagos:
                                            ui.notify("⚠️ Nenhum horário vago para sortear no período selecionado.", type='warning')
                                            return

                                        aptos = [p for p in estado["dados"]["pessoas"] if p.get("apto", True)]
                                        if not aptos:
                                            ui.notify("⚠️ Nenhum colaborador apto para o sorteio.", type='warning')
                                            return

                                        contagem_dinamica = {f"[{p.get('matricula')}] {p['nome']}": p.get('total_participacoes', 0) for p in aptos}
                                        faltas_map = {f"[{p.get('matricula')}] {p['nome']}": p.get('faltas', 0) for p in aptos}
                                        sorteados_count = 0

                                        for h in vagos:
                                            dia_slot = h.split(" | ")[0]
                                            ja_no_dia = set(
                                                c for k, c in estado["dados"]["agenda"].items()
                                                if k.startswith(dia_slot) and c not in ["--- VAGO ---", "🔒 [BLOQUEADO]"]
                                            )
                                            
                                            candidatos = [p for p in aptos if f"[{p.get('matricula')}] {p['nome']}" not in ja_no_dia]
                                            if not candidatos:
                                                continue

                                            max_s = max(contagem_dinamica[f"[{p.get('matricula')}] {p['nome']}"] for p in candidatos)
                                            urna = []
                                            for p in candidatos:
                                                ch = f"[{p.get('matricula')}] {p['nome']}"
                                                part = contagem_dinamica[ch]
                                                falt = faltas_map.get(ch, 0)
                                                peso = max(1, (max_s - part) + 1 - falt)
                                                urna.extend([p] * peso)

                                            if not urna:
                                                continue

                                            esc = random.choice(urna)
                                            chave_esc = f"[{esc.get('matricula')}] {esc['nome']}"
                                            estado["dados"]["agenda"][h] = chave_esc
                                            estado["dados"]["status_agendamentos"][h] = "Pendente"
                                            estado["dados"]["tipo_agendamento"][h] = "Sorteado"
                                            
                                            contagem_dinamica[chave_esc] += 1
                                            sorteados_count += 1

                                        salvar_dados()
                                        renderizar_calendario.refresh()
                                        renderizar_tudo.refresh()
                                        ui.notify(f"🎲 Sorteio concluído! {sorteados_count} slot(s) preenchido(s).", type='positive')

                                    # CONFIRMAÇÃO DE LIMPEZA
                                    async def confirmar_limpar():
                                        with ui.dialog() as dialog, ui.card().classes('p-4'):
                                            ui.label(f'Tem certeza que deseja desocupar os horários de {alvo_str}?').classes('font-black text-slate-900')
                                            ui.label('Os horários voltarão para "--- VAGO ---" mantendo a grade criada.').classes('text-xs text-slate-600')
                                            with ui.row().classes('justify-end gap-2 mt-4'):
                                                ui.button('Cancelar', on_click=dialog.close).props('flat')
                                                def executar_limpeza():
                                                    for h in list(estado["dados"]["agenda"].keys()):
                                                        if not dt_filtro_str or dt_filtro_str in h:
                                                            if estado["dados"]["agenda"][h] != "🔒 [BLOQUEADO]":
                                                                estado["dados"]["agenda"][h] = "--- VAGO ---"
                                                                estado["dados"]["status_agendamentos"][h] = "Pendente"
                                                                estado["dados"]["tipo_agendamento"][h] = "N/A"
                                                    salvar_dados()
                                                    dialog.close()
                                                    renderizar_calendario.refresh()
                                                    renderizar_tudo.refresh()
                                                    ui.notify("🧹 Horários desocupados com sucesso!", type='positive')
                                                ui.button('Confirmar Limpeza', on_click=executar_limpeza).classes('bg-amber-600 text-white font-bold')
                                        dialog.open()

                                    # CONFIRMAÇÃO DE EXCLUSÃO
                                    async def confirmar_exclusao():
                                        with ui.dialog() as dialog, ui.card().classes('p-4'):
                                            ui.label(f'⚠️ EXCLUIR GRADE ({alvo_str})?').classes('font-black text-rose-700 text-lg')
                                            ui.label('Todos os horários deste período serão apagados permanentemente!').classes('text-xs text-slate-700')
                                            with ui.row().classes('justify-end gap-2 mt-4'):
                                                ui.button('Cancelar', on_click=dialog.close).props('flat')
                                                def executar_del():
                                                    for h in list(estado["dados"]["agenda"].keys()):
                                                        if not dt_filtro_str or dt_filtro_str in h:
                                                            del estado["dados"]["agenda"][h]
                                                    salvar_dados()
                                                    dialog.close()
                                                    renderizar_calendario.refresh()
                                                    renderizar_tudo.refresh()
                                                    ui.notify("🗑️ Grade excluída com sucesso!", type='negative')
                                                ui.button('Sim, Excluir', on_click=executar_del).classes('bg-rose-700 text-white font-bold')
                                        dialog.open()

                                    # 1. SORTEAR -> AZUL
                                    b_sort = ui.button(f'🎲 SORTEAR ({alvo_str.upper()})', on_click=executar_sorteio).classes('text-white font-black shadow-md px-4 rounded-lg')
                                    b_sort.style('background-color: #2563eb !important;')

                                    # 2. LIMPAR -> LARANJA
                                    b_limp = ui.button('🧹 LIMPAR', on_click=confirmar_limpar).classes('text-white font-black shadow-md px-4 rounded-lg')
                                    b_limp.style('background-color: #ea580c !important;')

                                    # 3. EXCLUIR DIA -> VERMELHO
                                    label_btn_del = f"🗑️ EXCLUIR {'DIA' if dt_filtro_str else 'MÊS'}"
                                    b_excl = ui.button(label_btn_del, on_click=confirmar_exclusao).classes('text-white font-black shadow-md px-4 rounded-lg')
                                    b_excl.style('background-color: #dc2626 !important;')

                                # EXPORTAÇÕES (DIREITA)
                                with ui.row().classes('items-center gap-2'):
                                    if REPORTLAB_DISPONIVEL:
                                        def baixar_pdf():
                                            pdf_b = gerar_pdf_bytes(dt_filtro_str)
                                            nome_f = f"Escala_{dt_filtro_str.replace('/', '-') if dt_filtro_str else estado['mes_nome'] + '_' + str(estado['ano'])}.pdf"
                                            ui.download(pdf_b, nome_f)
                                        # 4. PDF -> VERMELHO
                                        b_pdf = ui.button('📄 PDF', on_click=baixar_pdf).classes('text-white font-black shadow-md px-4 rounded-lg')
                                        b_pdf.style('background-color: #dc2626 !important;')

                                    def baixar_excel():
                                        xls_b = gerar_excel_bytes(dt_filtro_str)
                                        nome_f = f"Escala_{dt_filtro_str.replace('/', '-') if dt_filtro_str else estado['mes_nome'] + '_' + str(estado['ano'])}.xlsx"
                                        ui.download(xls_b, nome_f)
                                    # 5. EXCEL -> VERDE
                                    b_xls = ui.button('📊 EXCEL', on_click=baixar_excel).classes('text-white font-black shadow-md px-4 rounded-lg')
                                    b_xls.style('background-color: #16a34a !important;')

                        # PASSO 3: AGENDA DETALHADA COM ALTO CONTRASTE E FILTROS RÁPIDOS
                        with ui.card().classes('w-full p-4 bg-white border border-slate-300 rounded-xl shadow-xs'):
                            with ui.row().classes('w-full items-center justify-between mb-2 flex-wrap gap-2'):
                                ui.label(f'📋 Agenda de Atendimentos ({alvo_str})').classes('text-lg font-black text-slate-900')
                                
                                # FILTROS RÁPIDOS DE STATUS (NOVO!)
                                with ui.row().classes('items-center gap-1 flex-wrap'):
                                    opcoes_st = [("Todos", "Todos"), ("Vagos", "Vago"), ("Pendentes", "Pendente"), ("Realizados", "Realizado"), ("Faltas", "Falta"), ("Bloqueados", "Bloqueado")]
                                    for rotulo, val_filtro in opcoes_st:
                                        is_ativo = (estado.get('filtro_status', 'Todos') == val_filtro)
                                        classes_badge = 'bg-blue-900 text-white shadow-xs' if is_ativo else 'bg-slate-200 text-slate-800 hover:bg-slate-300'
                                        
                                        def set_st(f=val_filtro):
                                            estado['filtro_status'] = f
                                            renderizar_tudo.refresh()
                                            
                                        ui.button(rotulo, on_click=lambda f=val_filtro: set_st(f)).classes(f'text-xs font-black py-0.5 px-3 rounded-full {classes_badge}')

                            chaves_ordenadas = sorted(estado["dados"]["agenda"].keys(), key=parse_chave_slot)
                            agenda_exibida = [h for h in chaves_ordenadas if not dt_filtro_str or dt_filtro_str in h]

                            # Aplicação do filtro de status
                            filtro_st = estado.get("filtro_status", "Todos")
                            if filtro_st == "Vago":
                                agenda_exibida = [h for h in agenda_exibida if estado["dados"]["agenda"][h] == "--- VAGO ---"]
                            elif filtro_st == "Bloqueado":
                                agenda_exibida = [h for h in agenda_exibida if estado["dados"]["agenda"][h] == "🔒 [BLOQUEADO]"]
                            elif filtro_st == "Realizado":
                                agenda_exibida = [h for h in agenda_exibida if estado["dados"]["status_agendamentos"].get(h) == "Realizado"]
                            elif filtro_st == "Falta":
                                agenda_exibida = [h for h in agenda_exibida if estado["dados"]["status_agendamentos"].get(h) == "Falta"]
                            elif filtro_st == "Pendente":
                                agenda_exibida = [h for h in agenda_exibida if estado["dados"]["agenda"][h] not in ["--- VAGO ---", "🔒 [BLOQUEADO]"] and estado["dados"]["status_agendamentos"].get(h) == "Pendente"]

                            if not agenda_exibida:
                                ui.label('Nenhum horário correspondente ao filtro nesta data.').classes('text-slate-700 italic font-bold p-3')
                            else:
                                # Cabeçalho da tabela com fundo slate escuro nítido
                                with ui.row().classes('w-full items-center justify-between p-2.5 bg-slate-800 text-white rounded-lg text-xs font-black mb-2'):
                                    ui.label('Dia / Data').classes('w-28')
                                    ui.label('Horário').classes('w-36')
                                    ui.label('Colaborador').classes('flex-1')
                                    ui.label('Status & Origem').classes('w-44 text-center')
                                    ui.label('Ações').classes('w-56 text-right')

                                tel_map = {f"[{p.get('matricula')}] {p['nome']}": p.get('telefone', '') for p in estado["dados"]["pessoas"]}

                                for h in agenda_exibida:
                                    colab = estado["dados"]["agenda"][h]
                                    partes = h.split(" | ")
                                    dia = partes[0] if len(partes) > 0 else ""
                                    hora = partes[1] if len(partes) > 1 else h
                                    st_atual = estado["dados"]["status_agendamentos"].get(h, "Pendente")
                                    tp_atual = estado["dados"]["tipo_agendamento"].get(h, "N/A")

                                    is_vago = (colab == "--- VAGO ---")
                                    is_bloqueado = (colab == "🔒 [BLOQUEADO]")

                                    cor_linha = 'bg-white'
                                    if is_bloqueado:
                                        cor_linha = 'bg-slate-100 opacity-80'
                                    elif is_vago:
                                        cor_linha = 'bg-blue-50/40'

                                    with ui.row().classes(f'w-full items-center justify-between p-2.5 border-b border-slate-200 hover:bg-slate-100 rounded-lg {cor_linha}'):
                                        ui.label(dia).classes('w-28 font-black text-slate-900 text-xs')
                                        
                                        # Horário em destaque de alto contraste
                                        ui.label(f"⏰ {hora}").classes('w-36 font-black text-slate-950 text-xs bg-slate-200 border border-slate-300 px-2 py-1 rounded-md text-center')
                                        
                                        # Colaborador com texto nítido
                                        if is_bloqueado:
                                            ui.label('🔒 BLOQUEADO').classes('flex-1 font-bold text-slate-500 italic text-sm')
                                        elif is_vago:
                                            ui.label('--- DISPONÍVEL (VAGO) ---').classes('flex-1 font-black text-blue-800 italic text-sm')
                                        else:
                                            ui.label(colab).classes('flex-1 font-black text-slate-950 text-sm')

                                        # STATUS COM BADGES SÓLIDAS DE ALTO CONTRASTE (WCAG AAA)
                                        with ui.row().classes('w-44 justify-center items-center gap-1'):
                                            if is_bloqueado:
                                                ui.badge('BLOQUEADO', color='grey-9').classes('text-xs font-black text-white px-2 py-0.5')
                                            elif is_vago:
                                                ui.badge('VAGO', color='blue-8').classes('text-xs font-black text-white px-2 py-0.5')
                                            else:
                                                cor_badge = 'green-8' if st_atual == 'Realizado' else ('red-8' if st_atual == 'Falta' else 'amber-9')
                                                cor_txt = 'text-white' if st_atual != 'Pendente' else 'text-slate-950'
                                                ui.badge(st_atual.upper(), color=cor_badge).classes(f'text-xs font-black {cor_txt} px-2 py-0.5')
                                                ui.badge(tp_atual, color='slate-700').classes('text-[10px] font-bold text-white px-1.5')

                                        # BARRA DE AÇÕES DO SLOT
                                        with ui.row().classes('w-56 justify-end items-center gap-1'):
                                            def alt_status(slot=h, novo_st="Realizado"):
                                                if estado["dados"]["agenda"].get(slot) in ["--- VAGO ---", "🔒 [BLOQUEADO]"]:
                                                    ui.notify("Não é possível alterar status de horários vagos ou bloqueados.", type='warning')
                                                    return
                                                estado["dados"]["status_agendamentos"][slot] = "Pendente" if estado["dados"]["status_agendamentos"].get(slot) == novo_st else novo_st
                                                salvar_dados()
                                                renderizar_calendario.refresh()
                                                renderizar_tudo.refresh()

                                            # 1. Presença
                                            if not is_bloqueado and not is_vago:
                                                ui.button('✅', on_click=lambda s=h: alt_status(s, "Realizado")).props('flat dense text-color=green-9').tooltip('Confirmar Presença (Realizado)')
                                                ui.button('❌', on_click=lambda s=h: alt_status(s, "Falta")).props('flat dense text-color=red-9').tooltip('Registrar Falta')

                                                # WhatsApp Direto com mensagem formatada
                                                tel = re.sub(r'\D', '', tel_map.get(colab, ''))
                                                if tel:
                                                    msg = f"Olá! Lembrete do seu horário de massagem corporativa: {dia} às {hora}. Favor comparecer com 5 min de antecedência!"
                                                    link_wa = f"https://wa.me/55{tel}?text={urllib.parse.quote(msg)}"
                                                    ui.button('💬', on_click=lambda url=link_wa: ui.navigate.to(url, new_tab=True)).props('flat dense text-color=emerald-8').tooltip('Avisar no WhatsApp')

                                            # 2. Bloquear / Desbloquear Slot
                                            def alternar_bloqueio(slot=h):
                                                if estado["dados"]["agenda"][slot] == "🔒 [BLOQUEADO]":
                                                    estado["dados"]["agenda"][slot] = "--- VAGO ---"
                                                    estado["dados"]["status_agendamentos"][slot] = "Pendente"
                                                    estado["dados"]["tipo_agendamento"][slot] = "N/A"
                                                else:
                                                    estado["dados"]["agenda"][slot] = "🔒 [BLOQUEADO]"
                                                    estado["dados"]["status_agendamentos"][slot] = "N/A"
                                                    estado["dados"]["tipo_agendamento"][slot] = "N/A"
                                                salvar_dados()
                                                renderizar_calendario.refresh()
                                                renderizar_tudo.refresh()

                                            ui.button('🔒' if not is_bloqueado else '🔓', on_click=lambda s=h: alternar_bloqueio(s)).props('flat dense text-color=slate-8').tooltip('Bloquear/Desbloquear Slot')

                                            # 3. Agendamento Manual / Encaixe
                                            def abrir_agendamento_manual(slot=h):
                                                with ui.dialog() as diag_m, ui.card().classes('p-4 min-w-[350px]'):
                                                    ui.label(f'Agendar Manualmente - {slot}').classes('font-black text-slate-900')
                                                    opcoes = {f"[{p.get('matricula')}] {p['nome']}": f"[{p.get('matricula')}] {p['nome']}" for p in estado["dados"]["pessoas"]}
                                                    sel_c = ui.select(opcoes, label='Selecione o Colaborador').props('outlined dense').classes('w-full font-bold')
                                                    
                                                    with ui.row().classes('justify-end gap-2 mt-4'):
                                                        ui.button('Cancelar', on_click=diag_m.close).props('flat')
                                                        def confirmar_manual():
                                                            if sel_c.value:
                                                                estado["dados"]["agenda"][slot] = sel_c.value
                                                                estado["dados"]["status_agendamentos"][slot] = "Pendente"
                                                                estado["dados"]["tipo_agendamento"][slot] = "Manual"
                                                                salvar_dados()
                                                                diag_m.close()
                                                                renderizar_calendario.refresh()
                                                                renderizar_tudo.refresh()
                                                                ui.notify("Colaborador agendado com sucesso!", type='positive')
                                                        ui.button('Agendar', on_click=confirmar_manual).classes('bg-blue-700 text-white font-bold')
                                                diag_m.open()

                                            ui.button('✏️', on_click=lambda s=h: abrir_agendamento_manual(s)).props('flat dense text-color=blue-9').tooltip('Agendamento/Troca Manual')

                                            # 4. Desocupar slot individual
                                            if not is_vago and not is_bloqueado:
                                                def liberar_slot(slot=h):
                                                    estado["dados"]["agenda"][slot] = "--- VAGO ---"
                                                    estado["dados"]["status_agendamentos"][slot] = "Pendente"
                                                    estado["dados"]["tipo_agendamento"][slot] = "N/A"
                                                    salvar_dados()
                                                    renderizar_calendario.refresh()
                                                    renderizar_tudo.refresh()
                                                ui.button('🧹', on_click=lambda s=h: liberar_slot(s)).props('flat dense text-color=amber-9').tooltip('Liberar Horário (Voltar a Vago)')

                                            # 5. Excluir este slot específico
                                            def excluir_slot(slot=h):
                                                if slot in estado["dados"]["agenda"]:
                                                    del estado["dados"]["agenda"][slot]
                                                salvar_dados()
                                                renderizar_calendario.refresh()
                                                renderizar_tudo.refresh()
                                            ui.button('🗑️', on_click=lambda s=h: excluir_slot(s)).props('flat dense text-color=rose-8').tooltip('Excluir este Horário')

                    # TAB 2: BASE DE COLABORADORES COM ALTO CONTRASTE
                    with ui.tab_panel(tab2).classes('p-0 gap-4'):
                        with ui.card().classes('w-full p-4 bg-white border border-slate-300 rounded-xl shadow-xs'):
                            ui.label('👥 Cadastro de Novo Colaborador').classes('text-lg font-black text-slate-900 mb-2')
                            
                            with ui.row().classes('w-full items-center gap-3 flex-wrap'):
                                mat_in = ui.input('Matrícula').props('outlined dense bg-color=white').classes('w-32 font-bold text-slate-900')
                                nom_in = ui.input('Nome Completo').props('outlined dense bg-color=white').classes('flex-1 font-bold text-slate-900')
                                tel_in = ui.input('WhatsApp (com DDD)').props('outlined dense bg-color=white').classes('w-48 font-bold text-slate-900')

                                def add_colab():
                                    matricula = mat_in.value.strip() if mat_in.value else ""
                                    nome = nom_in.value.strip().upper() if nom_in.value else ""
                                    telefone = tel_in.value.strip() if tel_in.value else ""

                                    if not matricula or not nome:
                                        ui.notify("⚠️ Matrícula e Nome são obrigatórios!", type='warning')
                                        return

                                    if any(p.get("matricula", "").strip() == matricula for p in estado["dados"]["pessoas"]):
                                        ui.notify("⚠️ Já existe um colaborador com esta matrícula!", type='warning')
                                        return

                                    novo_c = {
                                        "matricula": matricula,
                                        "nome": nome,
                                        "telefone": telefone,
                                        "apto": True,
                                        "total_participacoes": 0,
                                        "faltas": 0,
                                        "participou_semana": False
                                    }
                                    estado["dados"]["pessoas"].append(novo_c)
                                    salvar_dados()
                                    mat_in.value, nom_in.value, tel_in.value = '', '', ''
                                    renderizar_tudo.refresh()
                                    ui.notify(f"Colaborador {nome} cadastrado com sucesso!", type='positive')

                                b_cad = ui.button('Cadastrar', on_click=add_colab).classes('bg-blue-700 hover:bg-blue-800 text-white font-black h-10 px-6 rounded-lg shadow-sm')

                            ui.separator().classes('my-4')
                            
                            # BARRA DE BUSCA E CONTADORES
                            with ui.row().classes('w-full items-center justify-between mb-2 flex-wrap gap-2'):
                                ui.label(f'Colaboradores Cadastrados ({len(estado["dados"]["pessoas"])})').classes('text-md font-black text-slate-900')
                                search_in = ui.input(placeholder='🔍 Buscar por nome ou matrícula...').bind_value(estado, 'filtro_colaborador').on('input', renderizar_tudo.refresh).props('outlined dense bg-color=white').classes('w-80 font-bold text-slate-900')

                            # LISTA DE COLABORADORES FILTRADA
                            termo = estado.get('filtro_colaborador', '').lower().strip()
                            pessoas_filtradas = [
                                p for p in estado["dados"]["pessoas"]
                                if not termo or termo in p.get("nome", "").lower() or termo in p.get("matricula", "").lower()
                            ]

                            if not pessoas_filtradas:
                                ui.label('Nenhum colaborador encontrado com o termo digitado.').classes('italic text-slate-600 font-bold p-2')
                            else:
                                for p in pessoas_filtradas:
                                    mat = p.get('matricula', '')
                                    nome = p.get('nome', '')
                                    tel = p.get('telefone', '')
                                    apto = p.get('apto', True)
                                    sess = p.get('total_participacoes', 0)
                                    faltas = p.get('faltas', 0)

                                    with ui.row().classes('w-full items-center justify-between p-2.5 border-b border-slate-200 hover:bg-slate-50 rounded-lg'):
                                        with ui.column().classes('gap-0 flex-1'):
                                            with ui.row().classes('items-center gap-2'):
                                                ui.label(nome).classes('font-black text-slate-950 text-sm')
                                                ui.badge(f"Mat: {mat}", color='blue-9').classes('text-xs font-bold')
                                                if not apto:
                                                    ui.badge('INAPTO', color='red-8').classes('text-xs font-black text-white')
                                            ui.label(f"📱 WhatsApp: {tel or 'Não informado'}").classes('text-xs text-slate-700 font-medium')

                                        with ui.row().classes('items-center gap-4'):
                                            ui.label(f"Sessões: {sess}").classes('text-xs font-black text-blue-950')
                                            ui.label(f"Faltas: {faltas}").classes(f"text-xs font-black {'text-rose-700' if faltas > 0 else 'text-slate-600'}")

                                            # Alternar Apto / Inapto
                                            def toggle_apto(m=mat):
                                                for colab_obj in estado["dados"]["pessoas"]:
                                                    if colab_obj.get("matricula") == m:
                                                        colab_obj["apto"] = not colab_obj.get("apto", True)
                                                        break
                                                salvar_dados()
                                                renderizar_tudo.refresh()

                                            btn_apto = ui.button('Apto' if apto else 'Inapto', on_click=lambda m=mat: toggle_apto(m))
                                            btn_apto.classes(f"text-xs font-black text-white px-3 py-1 rounded-md {'bg-emerald-700' if apto else 'bg-rose-700'}")

                                            # Excluir colaborador com confirmação
                                            async def confirmar_del_colab(m=mat, n=nome):
                                                with ui.dialog() as diag_c, ui.card().classes('p-4'):
                                                    ui.label(f'Excluir colaborador {n} (Mat: {m})?').classes('font-black text-slate-900')
                                                    with ui.row().classes('justify-end gap-2 mt-4'):
                                                        ui.button('Cancelar', on_click=diag_c.close).props('flat')
                                                        def del_confirmado():
                                                            estado["dados"]["pessoas"] = [c for c in estado["dados"]["pessoas"] if c.get("matricula") != m]
                                                            salvar_dados()
                                                            diag_c.close()
                                                            renderizar_tudo.refresh()
                                                            ui.notify(f"Colaborador {n} removido.", type='negative')
                                                        ui.button('Sim, Excluir', on_click=del_confirmado).classes('bg-rose-700 text-white font-bold')
                                                diag_c.open()

                                            ui.button('🗑️', on_click=lambda m=mat, n=nome: confirmar_del_colab(m, n)).props('flat dense text-color=rose-8').tooltip('Excluir Colaborador')

            renderizar_tudo()

# --- EXECUÇÃO PROTEGIDA ---
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='SPA Massagem Corporativa', port=8080, reload=True)
