#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo para geração do Relatório Fotográfico de Instalação / Substituição
e unificação com a Folha de O.S. Concluída (Assinada).

Página 1: Ordem de Serviço Assinada (convertida proporcionalmente para A4 caso seja imagem ou mantida caso seja PDF).
Página 2: Relatório Fotográfico Oficial em Folha A4 com Grade 2x2:
          - 1. Unidade Evaporadora
          - 2. Unidade Condensadora
          - 3. Tubulação Frigorígera Aparente
          - 4. Dreno Aparente
"""

import os
import io
import time
import pypdf
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas


def _redimensionar_foto(caminho, max_w, max_h):
    """Calcula as dimensões proporcionais e retorna elemento de imagem para ReportLab."""
    try:
        if not caminho or not os.path.isfile(caminho):
            return None
        with PILImage.open(caminho) as im:
            orig_w, orig_h = im.size
            if orig_w <= 0 or orig_h <= 0:
                return None
            ratio = min(max_w / orig_w, max_h / orig_h)
            new_w = orig_w * ratio
            new_h = orig_h * ratio
            return RLImage(caminho, width=new_w, height=new_h)
    except Exception as e:
        print(f"[RELATORIO-FOTOGRAFICO] Erro ao redimensionar {caminho}: {e}")
        return None


def gerar_pdf_conclusao_instalacao(os_info, arquivo_os_path, fotos_dict, output_pdf_path):
    """
    Gera o PDF unificado contendo:
    Página 1: O.S. assinada (PDF ou Imagem ajustada em A4)
    Página 2: Relatório fotográfico em tabela 2x2 com as legendas oficiais
    """
    writer = pypdf.PdfWriter()

    # ----------------------------------------------------
    # PÁGINA 1: Ordem de Serviço Assinada
    # ----------------------------------------------------
    if arquivo_os_path and os.path.isfile(arquivo_os_path):
        ext = os.path.splitext(arquivo_os_path)[1].lower()
        if ext == '.pdf':
            try:
                reader_os = pypdf.PdfReader(arquivo_os_path)
                for page in reader_os.pages:
                    writer.add_page(page)
            except Exception as e:
                print(f"[RELATORIO-FOTOGRAFICO] Erro ao ler PDF da O.S.: {e}")
        else:
            # É imagem (JPG, PNG, WEBP): renderiza página A4 com a imagem centralizada
            try:
                buf_p1 = io.BytesIO()
                c_p1 = canvas.Canvas(buf_p1, pagesize=A4)
                w_a4, h_a4 = A4
                margin = 20
                max_w = w_a4 - 2 * margin
                max_h = h_a4 - 2 * margin

                with PILImage.open(arquivo_os_path) as im:
                    orig_w, orig_h = im.size
                    ratio = min(max_w / orig_w, max_h / orig_h)
                    new_w = orig_w * ratio
                    new_h = orig_h * ratio
                    pos_x = (w_a4 - new_w) / 2
                    pos_y = (h_a4 - new_h) / 2
                    c_p1.drawImage(arquivo_os_path, pos_x, pos_y, width=new_w, height=new_h, preserveAspectRatio=True)
                    c_p1.showPage()
                    c_p1.save()

                buf_p1.seek(0)
                reader_p1 = pypdf.PdfReader(buf_p1)
                if len(reader_p1.pages) > 0:
                    writer.add_page(reader_p1.pages[0])
            except Exception as e:
                print(f"[RELATORIO-FOTOGRAFICO] Erro ao converter imagem da O.S. para página 1: {e}")

    # ----------------------------------------------------
    # PÁGINA 2: Relatório Fotográfico (2x2 A4 com legendas)
    # ----------------------------------------------------
    buf_p2 = io.BytesIO()
    doc = SimpleDocTemplate(
        buf_p2,
        pagesize=A4,
        leftMargin=20,
        rightMargin=20,
        topMargin=20,
        bottomMargin=20
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle('T1', fontName='Helvetica-Bold', fontSize=10, leading=12, alignment=1, textColor=colors.HexColor('#1e293b'))
    style_sub = ParagraphStyle('T2', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#475569'))
    style_bar = ParagraphStyle('TB', fontName='Helvetica-Bold', fontSize=9, leading=11, alignment=1, textColor=colors.white)
    style_info = ParagraphStyle('TI', fontName='Helvetica', fontSize=7.5, leading=9.5, textColor=colors.HexColor('#1e293b'))
    style_legenda = ParagraphStyle('TL', fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=1, textColor=colors.white)

    story = [
        Paragraph("ESTADO DO CEARÁ — PODER JUDICIÁRIO", style_title),
        Paragraph("TRIBUNAL DE JUSTIÇA — GERÊNCIA DE MANUTENÇÃO E ZELADORIA (SGME)", style_sub),
        Spacer(1, 4)
    ]

    # Barra de Título
    t_bar = Table([[Paragraph("RELATÓRIO FOTOGRÁFICO DE INSTALAÇÃO / SUBSTITUIÇÃO DE EQUIPAMENTO", style_bar)]], colWidths=[555])
    t_bar.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#1e3a8a')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(t_bar)
    story.append(Spacer(1, 3))

    # Metadados da O.S.
    os_id = os_info.get('id', '-')
    dt_concl = os_info.get('data_conclusao_str') or time.strftime('%d/%m/%Y')
    contrato = os_info.get('contrato_str', '-')
    comarca = os_info.get('comarca', '-')
    predio = os_info.get('predio', '-')
    sala = os_info.get('sala', '-')
    equip = f"{os_info.get('tipo_equipamento', '')} {os_info.get('capacidade', '')} {os_info.get('marca', '')}".strip() or '-'
    tombo = os_info.get('tombo', 'S/T') or 'S/T'

    info_data = [
        [Paragraph(f"<b>O.S. Nº:</b> {os_id} | <b>Conclusão:</b> {dt_concl} | <b>Contrato:</b> {contrato}", style_info)],
        [Paragraph(f"<b>Localização:</b> {comarca} — {predio} ({sala})", style_info)],
        [Paragraph(f"<b>Equipamento Instalado:</b> {equip} | <b>Tombo Patrimonial:</b> <font color='#1d4ed8'><b>{tombo}</b></font>", style_info)]
    ]
    t_info = Table(info_data, colWidths=[555])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 6))

    # Configuração da grade 2x2 de fotos
    card_w = 272
    foto_max_w = 260
    foto_max_h = 280

    itens_foto = [
        (fotos_dict.get('evaporadora'), "1. UNIDADE EVAPORADORA"),
        (fotos_dict.get('condensadora'), "2. UNIDADE CONDENSADORA"),
        (fotos_dict.get('tubulacao'), "3. TUBULAÇÃO FRIGORÍFERA APARENTE"),
        (fotos_dict.get('dreno'), "4. DRENO APARENTE")
    ]

    celulas = []
    for path_foto, legenda in itens_foto:
        img_elem = None
        if path_foto and os.path.isfile(path_foto):
            img_elem = _redimensionar_foto(path_foto, foto_max_w, foto_max_h)
        if not img_elem:
            img_elem = Paragraph("<font color='#64748b'><i>[Foto não anexada]</i></font>", style_sub)

        t_card = Table([[img_elem], [Paragraph(legenda, style_legenda)]], colWidths=[card_w], rowHeights=[290, 16])
        t_card.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
            ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#1e40af')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#94a3b8')),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('VALIGN', (0,0), (-1,0), 'MIDDLE'),
            ('ALIGN', (0,1), (-1,1), 'CENTER'),
            ('VALIGN', (0,1), (-1,1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        celulas.append(t_card)

    t_grid = Table([[celulas[0], celulas[1]], [celulas[2], celulas[3]]], colWidths=[277, 277], rowHeights=[312, 312])
    t_grid.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(t_grid)

    doc.build(story)
    buf_p2.seek(0)
    reader_p2 = pypdf.PdfReader(buf_p2)
    for page in reader_p2.pages:
        writer.add_page(page)

    with open(output_pdf_path, 'wb') as f_out:
        writer.write(f_out)

    return output_pdf_path
