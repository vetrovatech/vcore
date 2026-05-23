"""PDF generator for revised Bathqube estimates (uses ReportLab — pure Python)."""

from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
)


BRAND_BLUE = colors.HexColor('#0F4C81')
ACCENT_AMBER = colors.HexColor('#92400E')
LIGHT_GREY = colors.HexColor('#E5E7EB')
MUTED = colors.HexColor('#6B7280')


def _money(v):
    try:
        return f"INR {float(v):,.2f}"
    except Exception:
        return f"INR {v}"


def generate_bathqube_pdf(quote):
    """Render revised estimate PDF, returns bytes."""
    cfg = quote.config or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Bathqube Revised Estimate {quote.estimate_number or quote.id}",
    )

    styles = getSampleStyleSheet()
    h_brand = ParagraphStyle('brand', parent=styles['Heading1'], textColor=BRAND_BLUE,
                             fontSize=22, leading=24, spaceAfter=2)
    h_sub = ParagraphStyle('sub', parent=styles['Normal'], textColor=MUTED, fontSize=9)
    h_section = ParagraphStyle('section', parent=styles['Heading3'], textColor=BRAND_BLUE,
                               fontSize=9, spaceBefore=14, spaceAfter=4,
                               textTransform='uppercase')
    body = ParagraphStyle('body', parent=styles['Normal'], fontSize=10, leading=14)
    revised_tag = ParagraphStyle('tag', parent=styles['Normal'], textColor=ACCENT_AMBER,
                                 fontSize=9, alignment=TA_RIGHT, backColor=colors.HexColor('#FEF3C7'))

    story = []

    # Header
    header_data = [[
        [Paragraph("<b>Bathqube</b>", h_brand),
         Paragraph("Premium Shower Enclosures · Bengaluru, India", h_sub)],
        [Paragraph("<b>REVISED ESTIMATE</b>", revised_tag),
         Paragraph(f"<font size=12><b>{quote.estimate_number or ('BQ-' + str(quote.id))}</b></font>",
                   ParagraphStyle('en', parent=styles['Normal'], alignment=TA_RIGHT)),
         Paragraph(f"Issued {(quote.updated_at or quote.created_at).strftime('%d %b %Y')}",
                   ParagraphStyle('iss', parent=h_sub, alignment=TA_RIGHT))],
    ]]
    header_tbl = Table(header_data, colWidths=[100 * mm, 70 * mm])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, BRAND_BLUE),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(header_tbl)

    # Customer
    story.append(Paragraph("CUSTOMER", h_section))
    cust = [
        ['Name', quote.customer_name or '—'],
        ['Phone', quote.phone or '—'],
    ]
    if quote.email: cust.append(['Email', quote.email])
    if quote.pincode: cust.append(['Pincode', quote.pincode])
    if quote.site_address: cust.append(['Site address', quote.site_address])
    t = Table(cust, colWidths=[35 * mm, 130 * mm])
    t.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t)

    # Line items
    story.append(Paragraph("ITEMS", h_section))
    items = list(quote.items) if quote.items else []
    if items:
        rows = [['Description', 'Qty', 'Rate (INR)', 'Amount (INR)']]
        for it in items:
            rows.append([
                Paragraph(it.description, body),
                f"{float(it.quantity):g}",
                f"{float(it.rate):,.2f}",
                f"{float(it.amount):,.2f}",
            ])
        items_tbl = Table(rows, colWidths=[95 * mm, 18 * mm, 28 * mm, 32 * mm], repeatRows=1)
        items_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F9FAFB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), MUTED),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, LIGHT_GREY),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]
        # Highlight discount/negative rows
        for i, it in enumerate(items, start=1):
            if float(it.amount or 0) < 0:
                items_style.append(('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#B45309')))
        items_tbl.setStyle(TableStyle(items_style))
        story.append(items_tbl)
    else:
        # No items yet (shouldn't happen post-revision) — fall back to config summary
        story.append(Paragraph(
            f"<b>{cfg.get('typeLabel') or 'Shower Enclosure'}</b> — "
            f"{cfg.get('materialLabel') or ''}, {cfg.get('thicknessLabel') or ''}, "
            f"{cfg.get('fittingLabel') or ''}", body))
    story.append(Spacer(1, 12))

    # Totals (right-aligned block)
    gst_half = (float(quote.gst_percentage or 18)) / 2
    totals_rows = [
        ['Subtotal', _money(quote.subtotal)],
        [f'CGST ({gst_half:g}%)', _money(quote.cgst)],
        [f'SGST ({gst_half:g}%)', _money(quote.sgst)],
    ]
    if quote.has_revision and quote.revised_total is not None:
        totals_rows.append(['Original total', _money(quote.total)])
        totals_rows.append(['Revised total', _money(quote.revised_total)])
    else:
        totals_rows.append(['Total payable', _money(quote.total)])
    if quote.amount_received and float(quote.amount_received) > 0:
        totals_rows.append(['Received', _money(quote.amount_received)])
        totals_rows.append(['Balance payable', _money(quote.balance_payable)])

    totals_tbl = Table(totals_rows, colWidths=[40 * mm, 40 * mm], hAlign='RIGHT')
    style_cmds = [
        ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    # Find revised row and emphasise
    for i, row in enumerate(totals_rows):
        if row[0] == 'Revised total':
            style_cmds += [
                ('TEXTCOLOR', (0, i), (-1, i), ACCENT_AMBER),
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                ('FONTSIZE', (0, i), (-1, i), 12),
                ('LINEABOVE', (0, i), (-1, i), 1, colors.black),
            ]
        if row[0] == 'Balance payable':
            style_cmds += [
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
            ]
    totals_tbl.setStyle(TableStyle(style_cmds))
    story.append(totals_tbl)

    # Footer
    story.append(Spacer(1, 40))
    story.append(Paragraph(
        "<font color='#9CA3AF' size='8'>Estimate validity: 30 days from issue · "
        "For any questions WhatsApp +91 85500 11196</font>",
        styles['Normal'],
    ))

    doc.build(story)
    return buf.getvalue()
