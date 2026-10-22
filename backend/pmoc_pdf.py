# -*- coding: utf-8 -*-
"""
Gerador Oficial de PDF do PMOC (Anexo 2 TJCE) - Individual por Equipamento
e Relatório Consolidado de Fechamento de Ciclo por Comarca (com suporte a REPROVADO para avaliação de pagamento).
"""
import io
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def html_esc(val):
    if val is None:
        return ''
    return xml_escape(str(val))


def gerar_pdf_pmoc_buffer(pmoc_info, checklist_itens, historico=None, lista_equipamentos=None):
    """
    Gera o comprovante oficial individual de execução do PMOC (Anexo 2 TJCE)
    para um único equipamento.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * 2.83,
        rightMargin=15 * 2.83,
        topMargin=12 * 2.83,
        bottomMargin=12 * 2.83
    )

    styles = getSampleStyleSheet()
    style_top_right = ParagraphStyle('TopRight', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=2)
    style_title = ParagraphStyle('DocTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=11, alignment=1)
    style_sub = ParagraphStyle('DocSub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1)
    style_hdr = ParagraphStyle('SecHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1, textColor=colors.black)
    style_lbl = ParagraphStyle('ColLabel', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=8.5, alignment=0)
    style_val = ParagraphStyle('ColVal', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=8.5, alignment=0)
    style_check_lbl = ParagraphStyle('CheckLbl', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.5, leading=8, alignment=1)
    style_check_val = ParagraphStyle('CheckVal', parent=styles['Normal'], fontName='Helvetica', fontSize=6.5, leading=8)
    style_check_status = ParagraphStyle('CheckStatus', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.5, leading=8, alignment=1)

    pmoc_id = pmoc_info['id']
    ano_comp = pmoc_info['ano_competencia']
    mes_comp = pmoc_info['mes_competencia']
    num_pmoc_fmt = f"{int(pmoc_id):04d}.{int(mes_comp):02d}.{int(ano_comp)}"

    rotulo_period = {
        'M': 'Mensal',
        'T': 'Trimestral',
        'S': 'Semestral',
        'A': 'Anual'
    }.get(pmoc_info.get('periodicidade'), 'Mensal')

    dt_geracao_fmt = datetime.fromtimestamp(pmoc_info['data_geracao'] / 1000).strftime('%d/%m/%Y') if pmoc_info.get('data_geracao') else '-'
    dt_exec_fmt = datetime.fromtimestamp(pmoc_info['data_execucao'] / 1000).strftime('%d/%m/%Y') if pmoc_info.get('data_execucao') else '-'

    st_raw = (pmoc_info.get('status') or '').lower()
    if st_raw == 'reprovada':
        status_fmt = '<font color="#b91c1c"><b>REPROVADO (AVALIAÇÃO FISCAL)</b></font>'
    elif st_raw == 'concluida':
        status_fmt = '<font color="#047857"><b>CONCLUÍDA</b></font>'
    else:
        status_fmt = f"<b>{html_esc(st_raw.upper())}</b>"

    elements = []

    elements.append(Paragraph(f"<b>PMOC Nº {num_pmoc_fmt}</b>", style_top_right))
    elements.append(Spacer(1, 3))

    data_tab1 = [
        [Paragraph("ESTADO DO CEARÁ - PODER JUDICIÁRIO<br/>TRIBUNAL DE JUSTIÇA - GERÊNCIA DE MANUTENÇÃO E ZELADORIA", style_title), ""],
        [Paragraph("ANEXO 2 - PLANO DE MANUTENÇÃO, OPERAÇÃO E CONTROLE (PMOC) - DOCUMENTO INDIVIDUAL DO EQUIPAMENTO", style_sub), ""],
        [Paragraph("1 - IDENTIFICAÇÃO DO AMBIENTE E CONTRATANTE", style_hdr), ""],
        [Paragraph("UNIDADE JURISDICIONAL:", style_lbl), Paragraph(f"COMARCA DE {html_esc(pmoc_info.get('comarca') or '-')} - {html_esc(pmoc_info.get('predio') or '-')}", style_val)],
        [Paragraph("LOCAL / SALA:", style_lbl), Paragraph(html_esc(pmoc_info.get('sala') or '-'), style_val)],
        [Paragraph("CONTRATANTE:", style_lbl), Paragraph("TRIBUNAL DE JUSTIÇA DO ESTADO DO CEARÁ (TJCE)", style_val)],
        [Paragraph("CONTRATO VINCULADO:", style_lbl), Paragraph(f"<b>{html_esc(pmoc_info.get('numero_contrato') or '-')}</b> - {html_esc(pmoc_info.get('nome_empresa') or '-')}", style_val)],
        [Paragraph("2 - IDENTIFICAÇÃO DO EQUIPAMENTO", style_hdr), ""],
        [Paragraph("TIPO / MODELO:", style_lbl), Paragraph(f"<b>{html_esc(pmoc_info.get('tipo_equipamento') or '-')}</b> {html_esc(pmoc_info.get('capacidade') or '')}", style_val)],
        [Paragraph("MARCA / FABRICANTE:", style_lbl), Paragraph(html_esc(pmoc_info.get('marca') or '-'), style_val)],
        [Paragraph("CPA / TOMBO PATRIMONIAL:", style_lbl), Paragraph(f"<b>{html_esc(pmoc_info.get('tombo') or 'S/T')}</b>", style_val)],
        [Paragraph("3 - DADOS DA MANUTENÇÃO PREVENTIVA", style_hdr), ""],
        [Paragraph("COMPETÊNCIA / PERIODICIDADE:", style_lbl), Paragraph(f"<b>{int(mes_comp):02d}/{ano_comp}</b> - Ciclo Executado: <b>{pmoc_info.get('periodicidade', 'M')} ({rotulo_period.upper()})</b>", style_val)],
        [Paragraph("STATUS DA O.S. PREVENTIVA:", style_lbl), Paragraph(status_fmt, style_val)],
        [Paragraph("DATAS (ABERTURA / CONCLUSÃO):", style_lbl), Paragraph(f"Gerada em: {dt_geracao_fmt} | Concluída em: {dt_exec_fmt}", style_val)],
        [Paragraph("MEDIÇÕES ELÉTRICAS E TÉRMICAS:", style_lbl), Paragraph(f"Tensão: <b>{html_esc(pmoc_info.get('tensao_medida') or '-')}</b> | Corrente: <b>{html_esc(pmoc_info.get('corrente_medida') or '-')}</b> | Temp. Insuflamento: <b>{html_esc(pmoc_info.get('temperatura_insuflamento') or '-')}</b> | Temp. Retorno: <b>{html_esc(pmoc_info.get('temperatura_retorno') or '-')}</b>", style_val)],
        [Paragraph("OBSERVAÇÕES TÉCNICAS:", style_lbl), Paragraph(html_esc(pmoc_info.get('observacoes_execucao') or 'Manutenção preventiva realizada dentro dos padrões normativos.'), style_val)]
    ]

    if st_raw == 'reprovada' and pmoc_info.get('justificativa_fiscal'):
        data_tab1.append([
            Paragraph("PARECER DA FISCALIZAÇÃO:", style_lbl),
            Paragraph(f'<font color="#b91c1c"><b>REPROVADO: {html_esc(pmoc_info.get("justificativa_fiscal"))}</b></font>', style_val)
        ])

    t1 = Table(data_tab1, colWidths=[65 * 2.83, 115 * 2.83])
    t1.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('SPAN', (0, 1), (1, 1)),
        ('SPAN', (0, 2), (1, 2)),
        ('SPAN', (0, 7), (1, 7)),
        ('SPAN', (0, 11), (1, 11)),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 2), (1, 2), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (0, 7), (1, 7), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (0, 11), (1, 11), colors.HexColor('#f1f5f9')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(t1)
    elements.append(Spacer(1, 4))

    data_tab2 = [
        [Paragraph("Item", style_check_lbl), Paragraph("Conjunto / Componente / Atividade Realizada", style_check_lbl), Paragraph("Situação", style_check_lbl), Paragraph("Obs / Apontamento", style_check_lbl)]
    ]

    rotulos_status = {
        'conforme': 'CONFORME',
        'corrigido': 'CORRIGIDO',
        'nao_conforme': 'NÃO CONF.',
        'nao_se_aplica': 'N/A'
    }

    for item in checklist_itens:
        st_val = rotulos_status.get(item.get('status_item', 'conforme'), 'CONFORME')
        data_tab2.append([
            Paragraph(html_esc(item.get('item_codigo', '-')), style_check_status),
            Paragraph(f"<b>[{html_esc(item.get('grupo', ''))}]</b> {html_esc(item.get('item_descricao', ''))}", style_check_val),
            Paragraph(f"<b>{st_val}</b>", style_check_status),
            Paragraph(html_esc(item.get('observacao') or '-'), style_check_val)
        ])

    t2 = Table(data_tab2, colWidths=[12 * 2.83, 110 * 2.83, 24 * 2.83, 34 * 2.83])
    t2.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
    ]))
    elements.append(t2)
    elements.append(Spacer(1, 5))

    tecnico_nome = html_esc(pmoc_info.get('nome_executante') or pmoc_info.get('nome_empresa') or 'TÉCNICO EXECUTANTE')
    empresa_nome = html_esc(pmoc_info.get('nome_empresa') or '-')

    data_tab3 = [
        [Paragraph("4 - RESPONSÁVEL PELA EXECUÇÃO / CONTRATADA", style_hdr), ""],
        [Paragraph("EMPRESA CONTRATADA:", style_lbl), Paragraph(empresa_nome, style_val)],
        [Paragraph("TÉCNICO / EXECUTANTE:", style_lbl), Paragraph(f"<b>{tecnico_nome}</b>", style_val)],
        [Paragraph("DATA DE CONCLUSÃO:", style_lbl), Paragraph(dt_exec_fmt, style_val)]
    ]

    t3 = Table(data_tab3, colWidths=[65 * 2.83, 115 * 2.83])
    t3.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(t3)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"PMOC_{num_pmoc_fmt}.pdf"
    return buffer, nome_arquivo


def gerar_pdf_relatorio_ciclo_buffer(relatorio):
    """
    Gera o Relatório de Fechamento de Ciclo de Manutenção Preventiva:
    - Lista todos os equipamentos do contrato separados por Comarca.
    - Aponta por qual tipo de manutenção o equipamento passou (M, T, S, A).
    - Caso reprovada pelo fiscal (para avaliação de pagamento), aponta "REPROVADO".
    - Se não realizou a preventiva, aponta "Não Realizada".
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * 2.83,
        rightMargin=12 * 2.83,
        topMargin=12 * 2.83,
        bottomMargin=12 * 2.83
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle('RelTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, alignment=1)
    style_sub = ParagraphStyle('RelSub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=11, alignment=1, textColor=colors.HexColor('#1e293b'))
    style_info = ParagraphStyle('RelInfo', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=10, alignment=0)
    style_comarca_hdr = ParagraphStyle('ComarcaHdr', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=11, textColor=colors.white)
    style_th = ParagraphStyle('TabTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.8, leading=8.5, alignment=1)
    style_td = ParagraphStyle('TabTD', parent=styles['Normal'], fontName='Helvetica', fontSize=6.5, leading=8)
    style_td_center = ParagraphStyle('TabTDCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=6.5, leading=8, alignment=1)
    style_td_bold = ParagraphStyle('TabTDBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.8, leading=8.5, alignment=1)
    style_td_reprovado = ParagraphStyle('TabTDRepr', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.8, leading=8.5, alignment=1, textColor=colors.HexColor('#dc2626'))
    style_td_nao_realizada = ParagraphStyle('TabTDNao', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.8, leading=8.5, alignment=1, textColor=colors.HexColor('#b91c1c'))

    ano = relatorio['ano']
    mes = relatorio['mes']
    contrato_desc = relatorio.get('contrato_descricao') or 'TODOS OS CONTRATOS VINCULADOS'
    resumo = relatorio.get('resumo') or {}
    comarcas_lista = relatorio.get('comarcas') or []

    elements = []

    hdr_data = [
        [Paragraph("ESTADO DO CEARÁ - PODER JUDICIÁRIO<br/>TRIBUNAL DE JUSTIÇA - SISTEMA DE GESTÃO DE MANUTENÇÃO DE EQUIPAMENTOS (SGME)", style_title)],
        [Paragraph(f"RELATÓRIO DE FECHAMENTO DE CICLO DE MANUTENÇÃO PREVENTIVA (PMOC) — COMPETÊNCIA {int(mes):02d}/{ano}", style_sub)],
        [Paragraph(
            f"<b>Contrato(s):</b> {html_esc(contrato_desc)}<br/>"
            f"<b>Total de Equipamentos:</b> {resumo.get('total_equipamentos', 0)} | "
            f"<b>Preventivas Concluídas (Regulares):</b> {resumo.get('total_realizadas', 0)} "
            f"(<b>M:</b> {resumo.get('M', 0)} | <b>T:</b> {resumo.get('T', 0)} | <b>S:</b> {resumo.get('S', 0)} | <b>A:</b> {resumo.get('A', 0)}) | "
            f"<b>Reprovadas (Avaliação Fiscal):</b> {resumo.get('reprovadas', 0)} | "
            f"<b>Não Realizadas:</b> {resumo.get('nao_realizadas', 0)} | "
            f"<b>Índice de Conformidade p/ Pagamento:</b> {resumo.get('percentual_execucao', 0)}%",
            style_info
        )]
    ]
    t_hdr = Table(hdr_data, colWidths=[186 * 2.83])
    t_hdr.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_hdr)
    elements.append(Spacer(1, 8))

    for Bloco in comarcas_lista:
        nome_com = Bloco['comarca']
        eqs = Bloco['equipamentos']
        qtd_tot = Bloco['total']
        qtd_ok = Bloco['realizadas']
        qtd_rep = Bloco.get('reprovadas', 0)
        qtd_nao = Bloco['nao_realizadas']

        tab_com_hdr = Table(
            [[Paragraph(f"COMARCA: {html_esc(nome_com)}   •   Total: {qtd_tot} equip. | Concluídas: {qtd_ok} | Reprovadas: {qtd_rep} | Não Realizadas: {qtd_nao}", style_comarca_hdr)]],
            colWidths=[186 * 2.83]
        )
        tab_com_hdr.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1e293b')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(tab_com_hdr)

        rows = [[
            Paragraph("Nº", style_th),
            Paragraph("Tombo", style_th),
            Paragraph("Prédio / Sala", style_th),
            Paragraph("Equipamento / Marca / Cap.", style_th),
            Paragraph("Contrato", style_th),
            Paragraph("O.S. PMOC", style_th),
            Paragraph("Data Exec.", style_th),
            Paragraph("Manutenção / Status", style_th)
        ]]

        for idx, eq in enumerate(eqs, 1):
            realizada = eq.get('realizada', False)
            reprovada = eq.get('reprovada', False)
            tipo_manut = eq.get('manutencao_apontada', 'Não Realizada')
            if reprovada or tipo_manut == 'REPROVADO':
                p_manut = Paragraph("<b>REPROVADO</b>", style_td_reprovado)
            elif realizada:
                p_manut = Paragraph(f"<b>{html_esc(tipo_manut)}</b>", style_td_bold)
            else:
                p_manut = Paragraph("<b>Não Realizada</b>", style_td_nao_realizada)

            rows.append([
                Paragraph(str(idx), style_td_center),
                Paragraph(f"<b>{html_esc(eq.get('tombo') or 'S/T')}</b>", style_td_center),
                Paragraph(f"{html_esc(eq.get('predio') or '-')} / {html_esc(eq.get('sala') or '-')}", style_td),
                Paragraph(f"{html_esc(eq.get('tipo_equipamento') or '-')} {html_esc(eq.get('capacidade') or '')} ({html_esc(eq.get('marca') or '-')})", style_td),
                Paragraph(html_esc(eq.get('numero_contrato') or '-'), style_td_center),
                Paragraph(html_esc(eq.get('num_pmoc') or '-'), style_td_center),
                Paragraph(html_esc(eq.get('data_execucao_fmt') or '-'), style_td_center),
                p_manut
            ])

        t_eqs = Table(
            rows,
            colWidths=[9 * 2.83, 18 * 2.83, 42 * 2.83, 44 * 2.83, 21 * 2.83, 18 * 2.83, 14 * 2.83, 20 * 2.83],
            repeatRows=1
        )
        t_eqs.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(t_eqs)
        elements.append(Spacer(1, 6))

    dt_emissao = datetime.now().strftime('%d/%m/%Y %H:%M')
    elements.append(Paragraph(f"Relatório emitido pelo SGME em {dt_emissao}", ParagraphStyle('Footer', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=7, alignment=2)))

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"Relatorio_Ciclo_PMOC_{int(mes):02d}_{ano}.pdf"
    return buffer, nome_arquivo
