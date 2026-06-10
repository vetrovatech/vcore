"""PDF generator for revised Bathqube estimates (uses ReportLab — pure Python)."""

import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
    PageBreak, Image,
)


# Path to the UPI QR shown on the payment page. Copied from glassyplatform's
# /public/upi-qr.jpeg so the vcore-generated estimate matches the website-
# generated one byte-for-byte. If the file is missing the QR block is skipped
# rather than failing PDF generation.
_QR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'images', 'upi-qr.jpeg',
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

    # Dimensions submitted — only for quotes that have a dimensionUnit on
    # configData (post-feature). Legacy quotes skip this block so existing
    # PDFs reissued for old quotes look unchanged. Always in the customer's
    # original unit (NOT inches) so the PDF mirrors what they typed.
    from utils.bathqube_dimensions import get_dimension_unit, format_enclosures_email
    dim_unit = get_dimension_unit(cfg)
    if dim_unit:
        enclosures_for_dims = cfg.get('enclosures') or []
        if enclosures_for_dims:
            story.append(Paragraph(f"DIMENSIONS SUBMITTED ({dim_unit})", h_section))
            dims_text = format_enclosures_email(enclosures_for_dims, dim_unit)
            # Render line-by-line so each panel sits on its own row.
            dims_body = ParagraphStyle('dimsbody', parent=body, fontSize=9, leading=12)
            for line in dims_text.split('\n'):
                # Replace leading spaces with non-breaking spaces so Paragraph
                # preserves the indent on the "Panel N:" rows.
                rendered = line.replace('   ', '&nbsp;&nbsp;&nbsp;')
                story.append(Paragraph(rendered or '&nbsp;', dims_body))

    # Line items
    story.append(Paragraph("ITEMS", h_section))
    items = list(quote.items) if quote.items else []
    if items:
        # KAN-45: column structure mirrors the original Bathqube estimate
        # PDF — a dedicated Sq.ft column and a per-sqft Rate column.
        # For seeded panel items, we parse the trailing "[N sq.ft @ ₹X/sq.ft]"
        # bracket out of the description and surface those values in their
        # own columns (cleaner than embedding them as a sub-line). For
        # free-form extras (added by staff during revise — no bracket on
        # their description) we show "—" in Sq.ft and use the stored rate
        # as a per-unit number, matching the existing semantics.
        import re as _re
        SQFT_RX = _re.compile(r'^(.*?)\s*\[\s*([\d.,]+)\s*sq\.ft(?:\s*@\s*₹\s*([\d.,]+)/sq\.ft)?\s*\]\s*$')
        # Header text uses no rupee glyph because the default Helvetica
        # ReportLab uses for table cells lacks ₹ and renders it as a
        # "missing glyph" box. The Amount column header makes the
        # currency clear from context.
        rows = [['Description', 'Sq.ft', 'Rate / sq.ft', 'Qty', 'Amount (INR)']]
        for it in items:
            desc_text = it.description or ''
            match = SQFT_RX.search(desc_text)
            if match:
                main_desc = match.group(1)
                sqft_val = match.group(2)
                ppsft_val = match.group(3)  # may be None for legacy items
                sqft_cell = sqft_val
                rate_cell = f"{float(ppsft_val.replace(',', '')):,.0f}" if ppsft_val else '—'
            else:
                # Extras / legacy / free-form lines — no sqft block
                main_desc = desc_text
                sqft_cell = '—'
                rate_cell = f"{float(it.rate):,.2f}"
            rows.append([
                Paragraph(main_desc, body),
                sqft_cell,
                rate_cell,
                f"{float(it.quantity):g}",
                f"{float(it.amount):,.2f}",
            ])
        items_tbl = Table(
            rows,
            colWidths=[80 * mm, 18 * mm, 22 * mm, 15 * mm, 30 * mm],
            repeatRows=1,
        )
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

    # Totals (right-aligned block) — discount applies BEFORE GST.
    gst_half = (float(quote.gst_percentage or 18)) / 2
    discount_pct = float(quote.discount_percent or 0)
    discount_amt = float(quote.discount_amount or 0)
    totals_rows = [
        ['Subtotal', _money(quote.subtotal)],
    ]
    if discount_amt > 0:
        totals_rows.append([f'Discount ({discount_pct:g}%)', f'-{_money(discount_amt)}'])
        taxable = max(0.0, float(quote.subtotal or 0) - discount_amt)
        totals_rows.append(['Taxable', _money(taxable)])
    totals_rows += [
        [f'CGST ({gst_half:g}%)', _money(quote.cgst)],
        [f'SGST ({gst_half:g}%)', _money(quote.sgst)],
    ]
    # The customer should see ONE clean total — not the history of revisions.
    # When this bill has been revised, the revised_total IS the current total;
    # we don't show what it used to be (that's in the internal audit log on the
    # vcore view page).
    final_total = quote.revised_total if (quote.has_revision and quote.revised_total is not None) else quote.total
    totals_rows.append(['Total payable', _money(final_total)])
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
    # Find special rows and emphasise
    for i, row in enumerate(totals_rows):
        if row[0] == 'Total payable':
            style_cmds += [
                ('TEXTCOLOR', (0, i), (-1, i), BRAND_BLUE),
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                ('FONTSIZE', (0, i), (-1, i), 12),
                ('LINEABOVE', (0, i), (-1, i), 1, colors.black),
            ]
        if row[0] == 'Balance payable':
            style_cmds += [
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
            ]
        # Discount row — green tint so it's visually distinct (savings shown as positive thing)
        if row[0].startswith('Discount '):
            style_cmds += [
                ('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#065F46')),
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

    # ─────────────────────────────────────────────────────────────────────
    # Page 2 — Notes · Terms & Conditions · Bank / Payment Details + UPI QR
    # Mirrors the configurator PDF (estimatePdf.tsx) so a customer sees the
    # same annex regardless of whether the bill was generated on the website
    # or revised in vcore.
    # ─────────────────────────────────────────────────────────────────────
    story.append(PageBreak())

    note_body = ParagraphStyle('note', parent=styles['Normal'], fontSize=9,
                               leading=13, leftIndent=10, spaceAfter=3)

    story.append(Paragraph("NOTES", h_section))
    for line in [
        "All prices shown already include transportation, labour, and installation — no extra charges beyond what is listed.",
        "Prices may change only if additions or deletions are made to the estimate.",
        "Delivery and installation are scheduled on separate days.",
        "Estimate validity: 15 days from the date of issue.",
        "<b>Payment Terms:</b> 15% on booking · 80% before delivery · 5% on installation day.",
    ]:
        story.append(Paragraph(f"• {line}", note_body))

    story.append(Paragraph("TERMS &amp; CONDITIONS", h_section))
    for line in [
        "<b>Lead Time</b> — Installations are completed within 7–10 days in Bengaluru after order confirmation and final measurement.",
        "<b>Cancellation</b> — 100% refund if glass has not been sent to the factory. After processing: 25% fee for clear/frosted.",
        "<b>Liability</b> — Our liability is limited to the advance received.",
        "<b>Force Majeure</b> — In cases of unavoidable cancellation by Bathqube, advances will be fully refunded.",
    ]:
        story.append(Paragraph(f"{line}", note_body))

    # Bank details + QR side by side
    story.append(Paragraph("BANK &amp; PAYMENT DETAILS", h_section))
    bank_label = ParagraphStyle('bl', parent=styles['Normal'], fontSize=9, textColor=MUTED)
    bank_value = ParagraphStyle('bv', parent=styles['Normal'], fontSize=9,
                                fontName='Helvetica-Bold')
    bank_rows = [
        [Paragraph('Account Name', bank_label), Paragraph('Vetrova Tech Services Private Limited', bank_value)],
        [Paragraph('Bank Name', bank_label), Paragraph('IDFC First Bank', bank_value)],
        [Paragraph('Account Number', bank_label), Paragraph('10249972220', bank_value)],
        [Paragraph('IFSC Code', bank_label), Paragraph('IDFB0080158', bank_value)],
        [Paragraph('Account Type', bank_label), Paragraph('Current', bank_value)],
        [Paragraph('UPI ID', bank_label), Paragraph('8550011196@ybl', bank_value)],
    ]
    bank_tbl = Table(bank_rows, colWidths=[35 * mm, 75 * mm])
    bank_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9FAFB')),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))

    qr_cell = []
    if os.path.exists(_QR_PATH):
        qr_img = Image(_QR_PATH, width=38 * mm, height=38 * mm)
        qr_cell.append(qr_img)
        qr_cell.append(Paragraph(
            "<font color='#6B7280' size='8'>Scan to pay via UPI</font>",
            ParagraphStyle('qrl', parent=styles['Normal'], alignment=TA_CENTER, spaceBefore=4),
        ))

    pay_block = Table(
        [[bank_tbl, qr_cell]],
        colWidths=[110 * mm, 55 * mm],
    )
    pay_block.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    story.append(pay_block)

    doc.build(story)
    return buf.getvalue()
