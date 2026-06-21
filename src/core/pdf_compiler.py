import os
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.fonts import addMapping

def compile_markdown_to_pdf(md_path: str, pdf_path: str) -> None:
    """将 Markdown 论文编译为 PDF (使用 STSong-Light 支持中文)"""
    # 注册中文 CID 字体 (Unicode 包装器)
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    # 注册字体映射以避免 ReportLab 解析 bold/italic 异常
    addMapping('STSong-Light', 0, 0, 'STSong-Light')
    addMapping('STSong-Light', 1, 0, 'STSong-Light')
    addMapping('STSong-Light', 0, 1, 'STSong-Light')
    addMapping('STSong-Light', 1, 1, 'STSong-Light')
    
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    styles = getSampleStyleSheet()
    
    # 自定义样式使用 STSong-Light 字体
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='STSong-Light',
        fontSize=20,
        leading=24,
        alignment=1,  # 居中
        spaceAfter=15
    )
    h1_style = ParagraphStyle(
        'DocH1',
        parent=styles['Heading1'],
        fontName='STSong-Light',
        fontSize=15,
        leading=18,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        'DocH2',
        parent=styles['Heading2'],
        fontName='STSong-Light',
        fontSize=12,
        leading=15,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )
    h3_style = ParagraphStyle(
        'DocH3',
        parent=styles['Heading3'],
        fontName='STSong-Light',
        fontSize=10,
        leading=13,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['BodyText'],
        fontName='STSong-Light',
        fontSize=9,
        leading=13,
        spaceAfter=6
    )
    list_style = ParagraphStyle(
        'DocList',
        parent=styles['Normal'],
        fontName='STSong-Light',
        fontSize=9,
        leading=13,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=3
    )
    table_cell_style = ParagraphStyle(
        'DocTableCell',
        parent=styles['Normal'],
        fontName='STSong-Light',
        fontSize=8,
        leading=10
    )

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    
    story = []
    in_table = False
    table_data = []
    
    def clean_text(txt):
        txt = txt.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # 粗体 **text** -> <b>text</b>
        txt = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', txt)
        # 斜体 *text* -> <i>text</i>
        txt = re.sub(r'\*(.*?)\*', r'<i>\1</i>', txt)
        return txt

    for line in lines:
        stripped = line.strip()
        
        # 表格处理
        if stripped.startswith('|') and stripped.endswith('|'):
            if not in_table:
                in_table = True
                table_data = []
            
            # 过滤掉分割线行如 |---|---|
            if re.match(r'^\|[\s:-|]*\|$', stripped):
                continue
                
            cells = [clean_text(c.strip()) for c in stripped.split('|')[1:-1]]
            cell_paragraphs = [Paragraph(c, table_cell_style) for c in cells]
            table_data.append(cell_paragraphs)
            continue
        else:
            if in_table:
                if table_data:
                    t = Table(table_data, hAlign='LEFT')
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
                        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                        ('VALIGN', (0,0), (-1,-1), 'TOP'),
                        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                        ('TOPPADDING', (0,0), (-1,-1), 4),
                        ('LEFTPADDING', (0,0), (-1,-1), 6),
                        ('RIGHTPADDING', (0,0), (-1,-1), 6),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                    ]))
                    story.append(t)
                    story.append(Spacer(1, 10))
                in_table = False
                table_data = []
                
        if not stripped:
            continue
            
        # 标题处理
        if stripped.startswith('# '):
            story.append(Paragraph(clean_text(stripped[2:]), title_style))
            story.append(Spacer(1, 10))
        elif stripped.startswith('## '):
            story.append(Paragraph(clean_text(stripped[3:]), h1_style))
        elif stripped.startswith('### '):
            story.append(Paragraph(clean_text(stripped[4:]), h2_style))
        elif stripped.startswith('#### '):
            story.append(Paragraph(clean_text(stripped[5:]), h3_style))
        # 列表项目
        elif stripped.startswith('- ') or stripped.startswith('* '):
            story.append(Paragraph(f"&bull; {clean_text(stripped[2:])}", list_style))
        elif re.match(r'^\d+\.\s', stripped):
            match = re.match(r'^(\d+)\.\s(.*)', stripped)
            num = match.group(1)
            item_text = match.group(2)
            story.append(Paragraph(f"{num}. {clean_text(item_text)}", list_style))
        else:
            story.append(Paragraph(clean_text(stripped), body_style))
            
    doc.build(story)
