"""PDF generators for Bathqube quotes (ReportLab — pure Python).

Three documents, all from the same file:
  - generate_bathqube_pdf(quote)             — customer-facing revised estimate
  - generate_bathqube_work_order_pdf(quote)  — workshop-floor cutting sheet
                                                (no prices, dimensions in mm)
  - generate_bathqube_receipt_pdf(receipt)   — payment receipt for a single
                                                inflow (UTR-audited, cumulative
                                                summary of all paid-to-date)
"""

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


# Standard Indian-receipt practice — every payment receipt prints the
# amount in words below the figure ("Rupees Five Thousand only") so the
# value can't be tampered with. Indian numbering: thousand → lakh
# (100,000) → crore (10,000,000). Handles amounts up to 99 crore which
# is well above any realistic single receipt.
def _money_in_words(amount):
    try:
        amt = float(amount)
    except Exception:
        return ''
    UNITS = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
             'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
             'Seventeen', 'Eighteen', 'Nineteen']
    TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

    def _under_100(n):
        if n < 20:
            return UNITS[n]
        return TENS[n // 10] + ('' if n % 10 == 0 else ' ' + UNITS[n % 10])

    def _under_1000(n):
        if n == 0:
            return ''
        if n < 100:
            return _under_100(n)
        rest = n % 100
        return UNITS[n // 100] + ' Hundred' + (' ' + _under_100(rest) if rest else '')

    rupees = int(amt)
    paise = round((amt - rupees) * 100)
    parts = []
    crore = rupees // 10000000
    rupees %= 10000000
    lakh = rupees // 100000
    rupees %= 100000
    thousand = rupees // 1000
    rupees %= 1000
    if crore > 0:
        parts.append(_under_100(crore) + ' Crore')
    if lakh > 0:
        parts.append(_under_100(lakh) + ' Lakh')
    if thousand > 0:
        parts.append(_under_100(thousand) + ' Thousand')
    if rupees > 0:
        parts.append(_under_1000(rupees))
    rupees_words = ' '.join(parts) if parts else 'Zero'
    words = f"Rupees {rupees_words}"
    if paise > 0:
        words += f" and {_under_100(paise)} Paise"
    return words + ' only'


def _bq_parse_item_desc(desc):
    """Parse a Bathqube line-item description back into structured pieces.

    Item descriptions are seeded by `_bathqube_seed_items_from_config` as:
        "{enc_name} — {type_label} ({spec}) · Panel {N}: {size_str} [{sqft} sq.ft @ ₹{rate}/sq.ft]"

    We need three things for the grouped-enclosure layout:
      - enc_name           — to group panels together under an enclosure header
      - type_label + spec  — to render the enclosure header card
      - panel_no, size_str — for the per-row description
      - sqft, rate         — for the dedicated columns

    For free-form extras (added by BD during revise — discounts,
    installation lines, etc.) none of this matches; we return None for
    the structured fields and the caller renders the row as a flat
    extra at the end of the items table.
    """
    import re as _re
    if not desc:
        return None
    # Enclosure header pattern: "<name> — <type_label>(?: (<spec>))? · Panel <N>: <size> [...sqft...]"
    rx = _re.compile(
        r'^(?P<enc>.+?) — (?P<type>.+?)(?: \((?P<spec>[^)]*)\))? · Panel (?P<panel>\d+): '
        r'(?P<size>.+?) \[\s*(?P<sqft>[\d.,]+)\s*sq\.ft(?:\s*@\s*₹\s*(?P<rate>[\d.,]+)/sq\.ft)?\s*\]\s*$'
    )
    m = rx.match(desc)
    if not m:
        return None
    return {
        'enc_name':  m.group('enc').strip(),
        'type_label': m.group('type').strip(),
        'spec':      (m.group('spec') or '').strip(),
        'panel_no':  int(m.group('panel')),
        'size_str':  m.group('size').strip(),
        'sqft':      float(m.group('sqft').replace(',', '')),
        'rate':      float(m.group('rate').replace(',', '')) if m.group('rate') else None,
    }


def _bq_group_items_by_enclosure(items):
    """Group BathqubeQuoteItem rows by enclosure, preserving order.

    Returns: (groups, extras)
      groups = [{ 'enc_name': str, 'type_label': str, 'spec': str,
                  'items': [(it, parsed), ...], 'subtotal': float }, ...]
      extras = [it, ...] — rows whose description didn't parse as a
                            panel (BD-added free-form lines)
    """
    groups = []
    extras = []
    by_name = {}
    for it in items:
        parsed = _bq_parse_item_desc(it.description or '')
        if parsed is None:
            extras.append(it)
            continue
        key = parsed['enc_name']
        if key not in by_name:
            g = {
                'enc_name':   parsed['enc_name'],
                'type_label': parsed['type_label'],
                'spec':       parsed['spec'],
                'items':      [],
                'subtotal':   0.0,
            }
            by_name[key] = g
            groups.append(g)
        by_name[key]['items'].append((it, parsed))
        by_name[key]['subtotal'] += float(it.amount or 0)
    return groups, extras


def generate_bathqube_pdf(quote):
    """Render the revised customer estimate PDF.

    Layout mirrors the configurator-generated fresh quote
    (`glassyplatform/src/lib/estimatePdf.tsx`) so customers see a
    consistent document whether the bill came off the website or was
    revised in vcore — header company block, big estimate badge, meta
    strip, Bill To, subject line, enclosure-grouped items, totals with
    amount in words, signature, then page 2 with notes / T&Cs / bank
    details + UPI QR.

    Calculation logic is NOT touched here — totals come from whatever
    `_bathqube_recompute_totals` already wrote to the quote row (KAN-60
    constraint).
    """
    cfg = quote.config or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Bathqube Revised Estimate {quote.estimate_number or quote.id}",
    )

    styles = getSampleStyleSheet()
    h_brand   = ParagraphStyle('brand', parent=styles['Heading1'], textColor=BRAND_BLUE,
                               fontSize=18, leading=20, spaceAfter=2)
    h_sub     = ParagraphStyle('sub', parent=styles['Normal'], textColor=MUTED, fontSize=8.5, leading=11)
    h_section = ParagraphStyle('section', parent=styles['Heading3'], textColor=BRAND_BLUE,
                               fontSize=9, spaceBefore=14, spaceAfter=4,
                               textTransform='uppercase')
    body = ParagraphStyle('body', parent=styles['Normal'], fontSize=10, leading=14)
    revised_label = ParagraphStyle(
        'rl', parent=styles['Normal'], textColor=ACCENT_AMBER,
        fontSize=8.5, alignment=TA_RIGHT, fontName='Helvetica-Bold',
    )

    story = []

    # ─── HEADER: company block | giant "REVISED ESTIMATE" badge ───
    # Full company block (name + tagline + address + GSTIN + URL + phone)
    # mirrors the fresh estimatePdf.tsx exactly.
    company_para = ParagraphStyle('co', parent=h_sub, fontSize=8.5, leading=11.5)
    header_left = [
        Paragraph("<b>Bathqube</b>", h_brand),
        Paragraph("Shower Enclosures &amp; Bathroom Fittings", company_para),
        Paragraph("Bengaluru, Karnataka 560034, India", company_para),
        Paragraph("GSTIN: 29AALCV4455A1Z7", company_para),
        Paragraph("bathqube.com &nbsp;·&nbsp; +91 85500 11196", company_para),
    ]
    # Two-line giant badge so the "REVISED" qualifier reads clearly at
    # the top-right (per BD: "still a revise quote, that tag should be
    # shown") without losing the visual prominence of the fresh quote's
    # 36pt ESTIMATE marque.
    badge_style = ParagraphStyle(
        'bdg', parent=styles['Normal'],
        textColor=colors.HexColor('#0F4C81'),
        fontSize=30, leading=32, alignment=TA_RIGHT, fontName='Helvetica-Bold',
    )
    sub_badge = ParagraphStyle(
        'sbdg', parent=styles['Normal'],
        textColor=ACCENT_AMBER, fontSize=10, alignment=TA_RIGHT,
        fontName='Helvetica-Bold', spaceBefore=2,
    )
    header_right = [
        Paragraph(
            # Faded background-style "ESTIMATE" with opacity ~12% — using
            # a light blue equivalent since ReportLab Paragraph can't take
            # CSS opacity. Visual result is the same wash effect.
            '<font color="#CFDDEA">Estimate</font>',
            badge_style,
        ),
        Paragraph("REVISED", sub_badge),
    ]
    header_tbl = Table([[header_left, header_right]], colWidths=[100 * mm, 70 * mm])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, BRAND_BLUE),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(header_tbl)

    # ─── META STRIP: estimate # | date | valid 15 days | place of supply ───
    meta_label = ParagraphStyle('ml', parent=h_sub, fontSize=7,
                                textColor=MUTED, textTransform='uppercase',
                                leading=9)
    meta_value = ParagraphStyle('mv', parent=body, fontSize=10,
                                fontName='Helvetica-Bold', leading=12)
    issued = (quote.updated_at or quote.created_at).strftime('%d %b %Y')
    meta_cells = [[
        [Paragraph("Estimate No.", meta_label),
         Paragraph(quote.estimate_number or f'BQ-{quote.id}', meta_value)],
        [Paragraph("Estimate Date", meta_label),
         Paragraph(issued, meta_value)],
        [Paragraph("Valid For", meta_label),
         Paragraph("15 days", meta_value)],
        [Paragraph("Place of Supply", meta_label),
         Paragraph("Karnataka (29)", meta_value)],
    ]]
    meta_tbl = Table(meta_cells, colWidths=[42 * mm, 42 * mm, 42 * mm, 48 * mm])
    meta_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F0F5FA')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(Spacer(1, 12))
    story.append(meta_tbl)

    # ─── BILL TO ───
    bill_label = ParagraphStyle('bll', parent=h_sub, fontSize=7.5,
                                textColor=MUTED, textTransform='uppercase',
                                spaceBefore=14, spaceAfter=4, leading=9)
    bill_name  = ParagraphStyle('bln', parent=styles['Normal'], fontSize=13,
                                fontName='Helvetica-Bold', leading=15, spaceAfter=2)
    bill_line  = ParagraphStyle('blr', parent=h_sub, fontSize=9, leading=12)
    story.append(Paragraph("Bill To", bill_label))
    story.append(Paragraph(quote.customer_name or '—', bill_name))
    if quote.email:
        story.append(Paragraph(f"Email: {quote.email}", bill_line))
    story.append(Paragraph(f"Phone: {quote.phone or '—'}", bill_line))
    if quote.site_address:
        addr_full = quote.site_address + (f" — {quote.pincode}" if quote.pincode else '')
        story.append(Paragraph(f"Address: {addr_full}", bill_line))
    elif quote.pincode:
        story.append(Paragraph(f"Pincode: {quote.pincode}", bill_line))

    # ─── ITEMS (grouped by enclosure) ───
    from utils.bathqube_dimensions import get_dimension_unit  # noqa
    items = list(quote.items) if quote.items else []
    groups, extras = _bq_group_items_by_enclosure(items)

    # Compute subject-line stats. Each item row represents ONE panel of an
    # enclosure priced for `it.quantity` identical sets — so a physical
    # count multiplies by qty, matching the fresh estimatePdf.tsx totals
    # (glassyplatform src/lib/estimatePdf.tsx:237-241). Without this, an
    # enclosure marked qty=2 would understate panels + sqft in the subject
    # line and the on-row arithmetic (sqft × rate) wouldn't tie to amount.
    total_panels = sum(int(it.quantity or 1) for g in groups for (it, _p) in g['items'])
    total_sqft   = sum(p['sqft'] * float(it.quantity or 1) for g in groups for (it, p) in g['items'])

    # Subject row — short summary of the bill in human terms
    subj_label = ParagraphStyle('sjl', parent=h_sub, fontSize=9, textColor=MUTED)
    subj_value = ParagraphStyle('sjv', parent=styles['Normal'], fontSize=9,
                                fontName='Helvetica-Bold')
    if groups:
        subject_text = (
            f"Shower Enclosure Estimate — {len(groups)} enclosure"
            f"{'s' if len(groups) != 1 else ''}, "
            f"{total_panels} panel{'s' if total_panels != 1 else ''}, "
            f"{total_sqft:.2f} sq.ft total"
        )
    else:
        subject_text = "Shower Enclosure Estimate — revised"
    subj_tbl = Table([[
        Paragraph("Subject:", subj_label),
        Paragraph(subject_text, subj_value),
    ]], colWidths=[20 * mm, 154 * mm])
    subj_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#D8E4ED')),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(subj_tbl)

    # ─── ITEMS TABLE — enclosure-grouped (mirrors fresh layout) ───
    desc_title = ParagraphStyle('dt', parent=body, fontSize=9.5,
                                fontName='Helvetica-Bold', leading=12)
    desc_line  = ParagraphStyle('dl', parent=body, fontSize=8.5,
                                textColor=MUTED, leading=10.5)
    grp_name   = ParagraphStyle('gn', parent=body, fontSize=10,
                                fontName='Helvetica-Bold', textColor=BRAND_BLUE, leading=12)
    grp_lbl    = ParagraphStyle('gl', parent=h_sub, fontSize=7,
                                textColor=MUTED, textTransform='uppercase', leading=9)
    grp_spec   = ParagraphStyle('gs', parent=h_sub, fontSize=8.5,
                                textColor=MUTED, leading=11)

    if groups:
        # Header row only (groups are rendered as separate tables so
        # the group-header card sits between rows visually).
        col_widths = [10 * mm, 86 * mm, 18 * mm, 22 * mm, 38 * mm]
        # Column header strip — own one-row table that sits above all groups
        header_row = [['#', 'Item & Description', 'Sq ft', 'Rate', 'Amount (INR)']]
        col_header_tbl = Table(header_row, colWidths=col_widths)
        col_header_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (2, 0), (-1, 0), 'RIGHT'),
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),
            ('TOPPADDING', (0, 0), (-1, 0), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            ('LEFTPADDING', (0, 0), (-1, 0), 10),
            ('RIGHTPADDING', (0, 0), (-1, 0), 10),
        ]))
        story.append(Spacer(1, 12))
        story.append(col_header_tbl)

        global_idx = 0
        for g_idx, g in enumerate(groups, start=1):
            # Group header card (Enclosure N + name/type + spec line).
            # Every item in a group came from the same enclosure so they
            # share the enclosure quantity — surface it on the header when
            # qty > 1 so the customer sees "× 2 sets" up-front (mirrors
            # estimatePdf.tsx :330).
            spec_line = g['spec'] or ''
            enc_qty = int(g['items'][0][0].quantity or 1) if g['items'] else 1
            spec_with_qty = (
                f"{spec_line} · Qty: {enc_qty} set{'s' if enc_qty > 1 else ''}"
                if enc_qty > 1
                else spec_line
            )
            grp_card = Table([[
                [Paragraph(f"Enclosure {g_idx}", grp_lbl),
                 Paragraph(f"{g['enc_name']} — {g['type_label']}", grp_name),
                 Paragraph(spec_with_qty, grp_spec) if spec_with_qty else Paragraph('', grp_spec)],
            ]], colWidths=[sum(col_widths)])
            grp_card.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F0F5FA')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ]))
            story.append(grp_card)

            # Panel rows. When the enclosure quantity is > 1 each item row
            # represents that panel × N identical sets — amount was already
            # stored as (single-panel-sqft × rate × qty) at seed time
            # (`_bathqube_seed_items_from_config`). The Sq ft column shows
            # the effective (× qty) sqft so on-row math (sqft × rate =
            # amount) ties out; otherwise a qty>1 row reads as if the
            # numbers don't add up. Mirrors estimatePdf.tsx :340-364.
            rows = []
            for (it, p) in g['items']:
                global_idx += 1
                qty = int(it.quantity or 1)
                eff_sqft = p['sqft'] * qty

                title = (
                    f"{g['type_label']} — Panel {p['panel_no']}"
                    + (f" × {qty} sets" if qty > 1 else "")
                )
                desc_block = [Paragraph(title, desc_title)]
                if g['spec']:
                    desc_block.append(Paragraph(g['spec'], desc_line))
                size_text = f"Size: {p['size_str']}"
                if qty > 1:
                    size_text += (
                        f" · {p['sqft']:.2f} sqft × {qty} sets = {eff_sqft:.2f} sqft"
                    )
                desc_block.append(Paragraph(size_text, desc_line))

                rate_cell = f"{p['rate']:,.0f}" if p['rate'] is not None else '—'
                rows.append([
                    str(global_idx),
                    desc_block,
                    f"{eff_sqft:.2f}",
                    rate_cell,
                    f"{float(it.amount or 0):,.2f}",
                ])
            panel_tbl = Table(rows, colWidths=col_widths)
            panel_style = [
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTNAME', (-1, 0), (-1, -1), 'Helvetica-Bold'),
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, LIGHT_GREY),
                ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ]
            # Alternating row tint, like the fresh PDF
            for ri in range(0, len(rows), 2):
                panel_style.append(
                    ('BACKGROUND', (0, ri), (-1, ri), colors.HexColor('#FAFCFE'))
                )
            panel_tbl.setStyle(TableStyle(panel_style))
            story.append(panel_tbl)

            # Per-enclosure subtotal strip
            sub_tbl = Table(
                [['', Paragraph(f"<font color='#666'>Subtotal — {g['enc_name']}</font>",
                                ParagraphStyle('grpsub', parent=body, fontSize=9, alignment=TA_RIGHT)),
                  f"{g['subtotal']:,.2f}"]],
                colWidths=[col_widths[0] + col_widths[1] + col_widths[2], col_widths[3], col_widths[4]],
            )
            sub_tbl.setStyle(TableStyle([
                ('ALIGN', (-1, 0), (-1, 0), 'RIGHT'),
                ('FONTNAME', (-1, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (-1, 0), (-1, 0), 9.5),
                ('LINEABOVE', (1, 0), (-1, 0), 0.5, MUTED),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, 0), 10),
                ('RIGHTPADDING', (0, 0), (-1, 0), 10),
            ]))
            story.append(sub_tbl)

        # Extras (BD-added free-form rows — installation, manual discount, etc.)
        if extras:
            ex_header = Table(
                [[Paragraph("Additional charges", grp_lbl)]],
                colWidths=[sum(col_widths)],
            )
            ex_header.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FDF7E7')),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ]))
            story.append(ex_header)

            ex_rows = []
            for it in extras:
                global_idx += 1
                ex_rows.append([
                    str(global_idx),
                    Paragraph(it.description or '', desc_title),
                    '—',
                    f"{float(it.rate or 0):,.2f}",
                    f"{float(it.amount or 0):,.2f}",
                ])
            ex_tbl = Table(ex_rows, colWidths=col_widths)
            ex_style = [
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTNAME', (-1, 0), (-1, -1), 'Helvetica-Bold'),
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, LIGHT_GREY),
                ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ]
            # Highlight negative-amount rows (manual discount)
            for ri, it in enumerate(extras):
                if float(it.amount or 0) < 0:
                    ex_style.append(('TEXTCOLOR', (0, ri), (-1, ri), colors.HexColor('#B45309')))
            ex_tbl.setStyle(TableStyle(ex_style))
            story.append(ex_tbl)
    else:
        # No items + no enclosures parsed — fall back to a single-line
        # summary so the PDF still renders something meaningful for the
        # rare legacy quote that has neither config data nor items.
        story.append(Paragraph(
            f"<b>{cfg.get('typeLabel') or 'Shower Enclosure'}</b> — "
            f"{cfg.get('materialLabel') or ''}, {cfg.get('thicknessLabel') or ''}, "
            f"{cfg.get('fittingLabel') or ''}", body))
    story.append(Spacer(1, 6))

    # ─── TOTALS BLOCK — right-aligned, mirrors fresh quote layout ───
    # Calculation values are read straight off the quote row (already
    # recomputed by _bathqube_recompute_totals). We do NOT recompute
    # anything here — only present.
    gst_half     = (float(quote.gst_percentage or 18)) / 2
    discount_pct = float(quote.discount_percent or 0)
    discount_amt = float(quote.discount_amount or 0)
    subtotal     = float(quote.subtotal or 0)
    taxable      = max(0.0, subtotal - discount_amt)

    totals_rows = [['Sub Total', _money(subtotal)]]
    if discount_amt > 0:
        totals_rows.append([f'Discount ({discount_pct:g}%)', f'-{_money(discount_amt)}'])
    totals_rows.append(['Total Taxable Amount', _money(taxable)])
    totals_rows += [
        [f'CGST ({gst_half:g}%)', _money(quote.cgst)],
        [f'SGST ({gst_half:g}%)', _money(quote.sgst)],
    ]
    # Final total — when revised, revised_total IS the current total.
    final_total = float(quote.revised_total or 0) if (quote.has_revision and quote.revised_total is not None) else float(quote.total or 0)
    totals_rows.append(['Total', _money(final_total)])
    if quote.amount_received and float(quote.amount_received) > 0:
        totals_rows.append(['Received', _money(quote.amount_received)])
        totals_rows.append(['Balance payable', _money(quote.balance_payable)])

    totals_tbl = Table(totals_rows, colWidths=[44 * mm, 44 * mm], hAlign='RIGHT')
    style_cmds = [
        ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    for i, row in enumerate(totals_rows):
        if row[0] == 'Total':
            style_cmds += [
                ('BACKGROUND', (0, i), (-1, i), BRAND_BLUE),
                ('TEXTCOLOR', (0, i), (-1, i), colors.white),
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                ('FONTSIZE', (0, i), (-1, i), 12),
                ('TOPPADDING', (0, i), (-1, i), 8),
                ('BOTTOMPADDING', (0, i), (-1, i), 8),
                ('LEFTPADDING', (0, i), (-1, i), 10),
                ('RIGHTPADDING', (0, i), (-1, i), 10),
            ]
        elif row[0] == 'Total Taxable Amount':
            style_cmds += [
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                ('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#1A1A1A')),
                ('LINEABOVE', (0, i), (-1, i), 0.5, LIGHT_GREY),
            ]
        elif row[0] == 'Balance payable':
            style_cmds += [
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
            ]
        elif row[0].startswith('Discount '):
            style_cmds += [
                ('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#065F46')),
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
            ]
    totals_tbl.setStyle(TableStyle(style_cmds))
    story.append(Spacer(1, 8))
    story.append(totals_tbl)

    # Amount in words — formatted like the fresh quote ("Rupees ... only")
    story.append(Spacer(1, 8))
    words = _money_in_words(final_total)
    words_para = ParagraphStyle('words', parent=body, fontSize=9.5,
                                fontName='Helvetica-Bold',
                                textColor=colors.HexColor('#1A1A1A'))
    words_lbl  = ParagraphStyle('wlbl', parent=h_sub, fontSize=8,
                                textColor=MUTED, textTransform='uppercase')
    story.append(Paragraph("Total in Words", words_lbl))
    story.append(Paragraph(words, words_para))

    # ─── Signature block (mirrors fresh quote layout) ───
    story.append(Spacer(1, 26))
    sig_label = ParagraphStyle('sgl', parent=h_sub, fontSize=8, textColor=MUTED)
    sig_name  = ParagraphStyle('sgn', parent=body, fontSize=9,
                               fontName='Helvetica-Bold',
                               textColor=colors.HexColor('#1A1A1A'),
                               alignment=TA_RIGHT)
    sig_role  = ParagraphStyle('sgr', parent=h_sub, fontSize=8,
                               textColor=MUTED, alignment=TA_RIGHT)
    sig_tbl = Table([[
        '',
        [Paragraph("For Vetrova Tech Services Pvt Ltd", sig_role),
         Spacer(1, 22),
         Paragraph("Authorised Signatory", sig_name)],
    ]], colWidths=[88 * mm, 86 * mm])
    sig_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(sig_tbl)

    # Page-bottom validity strip
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "<font color='#9CA3AF' size='8'>Estimate validity: 15 days from issue · "
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


# ─────────────────────────────────────────────────────────────────────────────
# Work Order PDF — workshop-floor document for the glass cutters.
# ─────────────────────────────────────────────────────────────────────────────


def _panel_dims_mm(panel, source_unit):
    """Convert a panel's (width, height) in source_unit to a "W × H mm"
    string. Workshop standard is mm; we always render in mm regardless of
    what the customer typed on the configurator so the cutter doesn't
    have to convert.

    PROD bug fix (BSP-000190, 2026-06-30): when source_unit was 'ft' but
    the panel values were actually mm (a bad legacy top-level unit hint
    that wasn't per-enclosure-corrected), this multiplied 840mm × 304.8 →
    256,032mm, printing garbage on the work order. Caller now passes a
    per-enclosure-resolved unit; this function is defensive too — when
    unit is 'mm' we short-circuit and skip the to_inches round-trip
    (also handles the accidental values-already-in-mm case safely).
    """
    from utils.bathqube_dimensions import to_inches
    unit = (source_unit or 'ft').lower()
    if unit == 'mm':
        w_mm = float(panel.get('width')  or 0)
        h_mm = float(panel.get('height') or 0)
    else:
        w_mm = to_inches(panel.get('width'),  unit) * 25.4
        h_mm = to_inches(panel.get('height'), unit) * 25.4
    return f"{w_mm:.0f} × {h_mm:.0f} mm"


def generate_bathqube_work_order_pdf(quote):
    """Render a workshop-floor Work Order PDF for the glass cutters.

    Design goals (per the manager's feedback):
      - PURE BLACK & WHITE — no colors. The workshop person is older and
        prints can degrade colour fidelity; high-contrast B&W is the
        legibility standard. Heavy borders, bold typography, and white
        backgrounds throughout.
      - BIG BOLD where it counts. Panel dimensions (mm), enclosure name,
        and glass type/thickness are the things a cutter reads most;
        those get the largest, boldest treatment. Labels are small caps
        in muted gray (but still B&W-printable).
      - STACKED enclosures with a strong black bar between them, so
        Enclosure 1 / 2 / 3 never blur into each other even on a worn
        photocopy.
      - PRIVACY — customer name + phone NOT printed. Site address only.
      - SINGLE A4 PAGE so the worker physically can't misplace half the job.

    Includes:
      - Brand wordmark + WO number + B&W priority badge
      - Job summary (site, order date, delivery ETA, panel count, area, handler)
      - Per-enclosure block: name + type, glass specs inline, panel table
      - Workshop notes (bordered box) if BD typed any
      - Signature block (cut · verify · dispatch)
    """
    cfg = quote.config or {}

    # Local B&W palette — overrides the file-level BRAND_BLUE etc.
    INK = colors.HexColor('#000000')             # primary text + strong borders
    INK_SOFT = colors.HexColor('#1F2937')        # body / heavy text
    LABEL = colors.HexColor('#4B5563')           # small-cap muted labels
    HAIR = colors.HexColor('#9CA3AF')            # thin separators
    BG_WHITE = colors.white
    BG_STRIPE = colors.HexColor('#F3F4F6')       # light row alternation

    buf = BytesIO()
    # Tight margins so 3 enclosures still fit on a single A4 sheet
    # alongside header, job grid, notes, and signature block.
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=12 * mm, bottomMargin=10 * mm,
        title=f"Bathqube Work Order {quote.estimate_number or quote.id}",
    )

    # ── Styles (all B&W) ─────────────────────────────────────────────────
    styles = getSampleStyleSheet()
    h_brand = ParagraphStyle('wo_brand', parent=styles['Heading1'],
                             textColor=INK, fontSize=15, leading=17,
                             fontName='Helvetica-Bold', spaceAfter=0)
    h_sub = ParagraphStyle('wo_sub', parent=styles['Normal'],
                           textColor=LABEL, fontSize=8)
    h_section = ParagraphStyle('wo_section', parent=styles['Heading3'],
                               textColor=INK, fontSize=9,
                               spaceBefore=8, spaceAfter=4,
                               fontName='Helvetica-Bold')
    body = ParagraphStyle('wo_body', parent=styles['Normal'],
                          fontSize=9.5, leading=12, textColor=INK_SOFT)
    body_sm = ParagraphStyle('wo_body_sm', parent=styles['Normal'],
                             fontSize=8.5, leading=11, textColor=INK_SOFT)
    big_no = ParagraphStyle('wo_no', parent=styles['Normal'], fontSize=18,
                            fontName='Helvetica-Bold', alignment=TA_RIGHT,
                            textColor=INK, leading=20)
    big_label = ParagraphStyle('wo_lbl', parent=styles['Normal'], fontSize=7.5,
                               textColor=LABEL, alignment=TA_RIGHT,
                               fontName='Helvetica-Bold')
    job_label = ParagraphStyle('wo_jl', parent=styles['Normal'], fontSize=7.5,
                               textColor=LABEL, fontName='Helvetica-Bold')
    job_value = ParagraphStyle('wo_jv', parent=styles['Normal'], fontSize=10,
                               leading=12, textColor=INK,
                               fontName='Helvetica-Bold')

    # Enclosure-block typography — bigger, bolder. These are the bits the
    # worker actually reads.
    enc_name = ParagraphStyle('enc_name', parent=styles['Normal'],
                              fontSize=13, leading=15, fontName='Helvetica-Bold',
                              textColor=INK)
    enc_type = ParagraphStyle('enc_type', parent=styles['Normal'],
                              fontSize=10, leading=12, fontName='Helvetica-Bold',
                              textColor=INK, alignment=TA_RIGHT)
    spec_label_s = ParagraphStyle('spec_lbl', parent=styles['Normal'],
                                  fontSize=7, textColor=LABEL,
                                  fontName='Helvetica-Bold')
    spec_value_s = ParagraphStyle('spec_val', parent=styles['Normal'],
                                  fontSize=11, leading=13,
                                  fontName='Helvetica-Bold', textColor=INK)
    dim_value = ParagraphStyle('dim_val', parent=styles['Normal'],
                               fontSize=14, leading=16,
                               fontName='Helvetica-Bold', textColor=INK)
    panel_no = ParagraphStyle('p_no', parent=styles['Normal'],
                              fontSize=12, leading=14, alignment=TA_CENTER,
                              fontName='Helvetica-Bold', textColor=INK)
    panel_area = ParagraphStyle('p_area', parent=styles['Normal'],
                                fontSize=10, leading=12, alignment=TA_LEFT,
                                textColor=INK_SOFT)

    story = []

    # ── Header ───────────────────────────────────────────────────────────
    wo_number = quote.estimate_number or f"BQ-{quote.id}"
    issued = (quote.updated_at or quote.created_at).strftime('%d %b %Y')

    wo_row = getattr(quote, 'work_order', None)
    priority = (wo_row.priority if wo_row else None) or 'normal'

    def _priority_badge(prio):
        """Black-and-white badge. Solid black box with white text for
        URGENT so it's unmissable even on a degraded photocopy."""
        prio = (prio or 'normal').lower()
        if prio == 'urgent':
            label = 'URGENT'
            bg = INK
            fg = colors.white
            border_w = 0
        elif prio == 'low':
            label = 'LOW PRIORITY'
            bg = BG_WHITE
            fg = LABEL
            border_w = 0.5
        else:
            label = 'NORMAL'
            bg = BG_WHITE
            fg = INK
            border_w = 1.0
        p = ParagraphStyle('badge', parent=styles['Normal'], fontSize=9,
                           fontName='Helvetica-Bold', alignment=TA_CENTER,
                           textColor=fg, leading=11)
        tbl = Table([[Paragraph(label, p)]], colWidths=[32 * mm])
        style = [
            ('BACKGROUND', (0, 0), (-1, -1), bg),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        if border_w:
            style.append(('BOX', (0, 0), (-1, -1), border_w, INK))
        tbl.setStyle(TableStyle(style))
        return tbl

    header = Table([[
        [Paragraph("<b>Bathqube</b>", h_brand),
         Paragraph("Glass workshop work order", h_sub),
         Spacer(1, 3),
         _priority_badge(priority)],
        [Paragraph("WORK ORDER", big_label),
         Paragraph(wo_number, big_no),
         Paragraph(f"Generated {issued}",
                   ParagraphStyle('iss', parent=h_sub, alignment=TA_RIGHT))],
    ]], colWidths=[100 * mm, 82 * mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 2.0, INK),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(header)

    # ── Job details strip ────────────────────────────────────────────────
    src_unit = cfg.get('dimensionUnit') or 'ft'
    enclosures = cfg.get('enclosures') or []

    total_panels = 0
    total_sqft = 0.0
    for enc in enclosures:
        qty = int(enc.get('quantity') or 1)
        for p in (enc.get('glassPanels') or []):
            total_panels += qty
            total_sqft += float(p.get('sqft') or 0) * qty

    order_date = (quote.purchased_at or quote.updated_at or quote.created_at).strftime('%d %b %Y')

    delivery_eta_str = '—'
    if wo_row and wo_row.delivery_eta:
        delivery_eta_str = wo_row.delivery_eta.strftime('%d %b %Y')

    site_line = quote.site_address or '—'
    if quote.pincode:
        site_line = f"{site_line} · PIN {quote.pincode}"

    handler_name = '—'
    if wo_row and wo_row.ops_assignee:
        handler_name = wo_row.ops_assignee.username

    def _field(label, value, paragraph_style=job_value):
        return [
            Paragraph(label.upper(), job_label),
            Paragraph(value, paragraph_style),
        ]

    # Client name — kept on this internal WO (workshop staff find it
    # useful when calling about the order). Added per manager update
    # 2026-06-18 after the earlier "remove customer" decision was
    # walked back for workshop use.
    client_name = quote.customer_name or '—'

    job_grid = Table([
        [
            _field('Client', client_name),
            _field('Site location', site_line),
            _field('Delivery ETA', delivery_eta_str),
        ],
        [
            _field('Order date', order_date),
            _field('Total panels', f"{total_panels}"),
            _field('Total area', f"{total_sqft:.2f} sq.ft"),
        ],
    ], colWidths=[60 * mm, 72 * mm, 50 * mm])
    job_grid.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, HAIR),
    ]))
    story.append(job_grid)

    # ── Glass specification ──────────────────────────────────────────────
    story.append(Paragraph("GLASS SPECIFICATION", h_section))

    if not enclosures:
        story.append(Paragraph(
            f"<b>{cfg.get('typeLabel') or 'Shower Enclosure'}</b> "
            f"— {cfg.get('materialLabel') or ''}, "
            f"{cfg.get('thicknessLabel') or ''}, "
            f"{cfg.get('fittingLabel') or ''}", body))
    else:
        # ── Single Excel-style table covering ALL enclosures ─────────────
        # Per the manager: one tabular sheet, no colour fills, thin black
        # grid lines like a spreadsheet. Each enclosure starts with two
        # span rows (title + spec line), followed by one row per panel.
        # The four manager-highlighted bits — dimensions (mm), glass
        # thickness, glass enclosure type, glass type — are rendered in
        # bold so the worker's eye latches onto them.

        # Style helpers used inside the table cells. Sizes dialled down
        # one notch from v6 per manager feedback: the relative hierarchy
        # (big bold values, small muted labels) is preserved, just at a
        # smaller overall scale so the table feels less heavy.
        cell_body = ParagraphStyle('cell', parent=styles['Normal'],
                                   fontSize=9, leading=11, textColor=INK)
        cell_body_b = ParagraphStyle('cell_b', parent=cell_body,
                                     fontName='Helvetica-Bold')
        cell_dim = ParagraphStyle('cell_dim', parent=styles['Normal'],
                                  fontSize=11, leading=13, textColor=INK,
                                  fontName='Helvetica-Bold')
        cell_pnum = ParagraphStyle('cell_pnum', parent=styles['Normal'],
                                   fontSize=10, leading=12, alignment=TA_CENTER,
                                   fontName='Helvetica-Bold', textColor=INK)
        cell_area = ParagraphStyle('cell_area', parent=styles['Normal'],
                                   fontSize=8.5, leading=11, textColor=INK)
        title_para_st = ParagraphStyle('enc_title', parent=styles['Normal'],
                                       fontSize=10, leading=13, textColor=INK,
                                       fontName='Helvetica')
        spec_para_st = ParagraphStyle('enc_specs', parent=styles['Normal'],
                                      fontSize=9, leading=12, textColor=INK)

        # First row: column headers
        rows = [['#', 'DIMENSIONS (mm)', 'AREA', 'CUTTER NOTES']]
        styles_cmds = []

        # Header row styling — uppercase bold, thin line below.
        styles_cmds += [
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('TEXTCOLOR', (0, 0), (-1, 0), INK),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (2, 0), 'LEFT'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ]

        r = 1
        for idx, enc in enumerate(enclosures, start=1):
            name = enc.get('name') or f'Enclosure {idx}'
            type_label = enc.get('typeLabel') or '—'
            glass_type = enc.get('materialLabel') or '—'
            glass_thickness = enc.get('thicknessLabel') or '—'
            glass_fitting = enc.get('fittingLabel') or '—'
            glass_hardware = enc.get('hardwareTypeLabel') or '—'
            qty = int(enc.get('quantity') or 1)
            qty_label = f"  ×{qty}" if qty > 1 else ""

            # Per-enclosure unit resolution — matches the seed / revise
            # priority chain: per-enc dimensionUnit > top-level > 'ft'.
            # Fixes BSP-000190 where top-level said 'ft' but per-enc was
            # 'mm'. Without this, _panel_dims_mm treated 840mm as 840ft
            # and printed 256,032 × 667,512 mm.
            enc_unit = (enc.get('dimensionUnit')
                        or cfg.get('dimensionUnit')
                        or 'ft').lower()

            # Title row (spans all 4 cols). Enclosure Type is BOLD per
            # manager's highlight list. Name stays regular.
            title = Paragraph(
                f"<b>ENCLOSURE {idx}:</b> {name}{qty_label}"
                f" &nbsp;—&nbsp; <b>{type_label}</b>",
                title_para_st,
            )
            rows.append([title, '', '', ''])
            styles_cmds += [
                ('SPAN', (0, r), (3, r)),
                ('LEFTPADDING', (0, r), (-1, r), 6),
                ('RIGHTPADDING', (0, r), (-1, r), 6),
                ('TOPPADDING', (0, r), (-1, r), 7),
                ('BOTTOMPADDING', (0, r), (-1, r), 3),
                # Slightly heavier line above each enclosure title so
                # the eye can find the section breaks at a glance.
                ('LINEABOVE', (0, r), (-1, r), 1.0, INK),
            ]
            r += 1

            # Spec row (spans all 4 cols of the main table). Per the
            # manager's latest feedback: labels go SMALL on top, values
            # go BIG + BOLD below — same hierarchy for all four bits so
            # the worker's eye is pulled to the values, not the labels.
            #
            # Implemented as a 4-cell sub-Table inside the spanned cell.
            # Each sub-cell stacks label (7pt, muted) above value
            # (13pt Helvetica-Bold, black). The sub-table has no
            # borders; the outer Excel-grid borders from the main
            # table give the only visual separators.
            spec_label = ParagraphStyle('spec_label_inline',
                                        parent=styles['Normal'],
                                        fontSize=6.5, leading=8,
                                        fontName='Helvetica-Bold',
                                        textColor=LABEL)
            spec_value = ParagraphStyle('spec_value_inline',
                                        parent=styles['Normal'],
                                        fontSize=11, leading=13,
                                        fontName='Helvetica-Bold',
                                        textColor=INK)

            def _spec_cell(lbl, val):
                return [
                    Paragraph(lbl, spec_label),
                    Spacer(1, 1),
                    Paragraph(val or '—', spec_value),
                ]

            specs_sub = Table([[
                _spec_cell('GLASS TYPE',      glass_type),
                _spec_cell('GLASS THICKNESS', glass_thickness),
                _spec_cell('GLASS FITTING',   glass_fitting),
                _spec_cell('GLASS HARDWARE',  glass_hardware),
            ]], colWidths=[45 * mm, 45 * mm, 45 * mm, 47 * mm])
            specs_sub.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            rows.append([specs_sub, '', '', ''])
            styles_cmds += [
                ('SPAN', (0, r), (3, r)),
                # Outer cell padding kept tight — the sub-table cells
                # have their own internal padding.
                ('LEFTPADDING', (0, r), (-1, r), 2),
                ('RIGHTPADDING', (0, r), (-1, r), 2),
                ('TOPPADDING', (0, r), (-1, r), 6),
                ('BOTTOMPADDING', (0, r), (-1, r), 7),
            ]
            r += 1

            # Panel rows. Dimensions cell stays the boldest+biggest in
            # the row — that's the value the cutter measures off (mm
            # called out specifically for highlight by manager).
            panels = enc.get('glassPanels') or []
            for pi, p in enumerate(panels, start=1):
                dims_text = _panel_dims_mm(p, enc_unit)
                rows.append([
                    Paragraph(f"P{pi}", cell_pnum),
                    Paragraph(dims_text, cell_dim),
                    Paragraph(f"{float(p.get('sqft') or 0):.2f} sq.ft", cell_area),
                    '',  # blank — cutter writes here during processing
                ])
                styles_cmds += [
                    ('ALIGN', (0, r), (0, r), 'CENTER'),
                    ('ALIGN', (1, r), (2, r), 'LEFT'),
                    ('VALIGN', (0, r), (-1, r), 'MIDDLE'),
                    ('TOPPADDING', (0, r), (-1, r), 5),
                    ('BOTTOMPADDING', (0, r), (-1, r), 5),
                ]
                r += 1

        # Global table styling — Excel-style thin black grid on every
        # cell, no colour fills anywhere. The SPAN commands above
        # automatically suppress interior grid lines inside spans.
        styles_cmds += [
            ('INNERGRID', (0, 0), (-1, -1), 0.4, INK),
            ('BOX', (0, 0), (-1, -1), 0.7, INK),
            ('LEFTPADDING', (0, 1), (-1, -1), 6),  # data rows default
            ('RIGHTPADDING', (0, 1), (-1, -1), 6),
        ]

        # ColWidths match the standard header layout used elsewhere on
        # the page so the table fills the full content width cleanly.
        main_tbl = Table(rows, colWidths=[14 * mm, 60 * mm, 26 * mm, 82 * mm])
        main_tbl.setStyle(TableStyle(styles_cmds))
        story.append(main_tbl)
        story.append(Spacer(1, 8))

    # ── Workshop notes — black-bordered box, NOT amber. Big bold heading. ─
    cutting = (wo_row and wo_row.cutting_notes) or None
    if cutting:
        notes_heading = Paragraph(
            "WORKSHOP NOTES",
            ParagraphStyle('wn_h', parent=styles['Normal'], fontSize=9,
                           fontName='Helvetica-Bold', textColor=INK,
                           spaceBefore=4, spaceAfter=2),
        )
        notes_body = Paragraph(
            cutting.replace('\n', '<br/>'),
            ParagraphStyle('wn_b', parent=body, fontSize=10, leading=13,
                           textColor=INK, fontName='Helvetica-Bold'),
        )
        notes_tbl = Table([[notes_heading], [notes_body]],
                          colWidths=[182 * mm])
        notes_tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOX', (0, 0), (-1, -1), 1.0, INK),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, INK),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(notes_tbl)
        story.append(Spacer(1, 6))

    # ── Signature block ──────────────────────────────────────────────────
    sig_rows = [
        ['Glass cut by',  '__________________________', 'Date',     '_______________'],
        ['Verified by',   '__________________________', 'Date',     '_______________'],
        ['Dispatched',    '__________________________', 'Vehicle #', '_______________'],
    ]
    sig_tbl = Table(sig_rows, colWidths=[28 * mm, 65 * mm, 22 * mm, 55 * mm])
    sig_tbl.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, -1), INK),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, HAIR),
    ]))
    story.append(sig_tbl)

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Payment Receipt PDF — one inflow per row, cumulative summary on the PDF.
# ─────────────────────────────────────────────────────────────────────────────


def generate_bathqube_receipt_pdf(receipt):
    """Render a polished, professional payment receipt PDF.

    Layout (top → bottom):
      1.  Slim brand bar at the very top — solid blue accent for instant
          identification at a glance.
      2.  Brand mark (BATHQUBE) + receipt metadata header.
      3.  Two-column "Received From" / "Reference" section.
      4.  Hero amount panel — large bordered box with the figure, words,
          and payment method/UTR.
      5.  Payment summary — clean right-aligned breakdown with subtle
          dividers and bold totals; "Balance due ₹0 ✓" when fully paid.
      6.  Notes (when present) + Issued-by audit line.
      7.  Authorised signature block.
      8.  Company block (legal entity, address, contact) at the foot.
      9.  Computer-generated micro-disclaimer.

    Re-generating an old receipt's PDF reproduces the same cumulative
    numbers because we rebuild "previously paid" from sibling receipts
    with received_at <= this one each time.
    """
    quote = receipt.quote
    cfg = quote.config or {}  # noqa: F841 (parity with other generators)

    # ── Colour palette ───────────────────────────────────────────────────
    # Mostly grayscale + one brand-blue accent. Restrained, modern look.
    INK = colors.HexColor('#0F172A')          # heading / primary text
    INK_SOFT = colors.HexColor('#1F2937')     # body text
    LABEL = colors.HexColor('#6B7280')        # small-caps muted labels
    LINE = colors.HexColor('#E5E7EB')         # subtle dividers
    PANEL_BG = colors.HexColor('#F8FAFC')     # very light gray-blue for hero
    PANEL_EDGE = colors.HexColor('#CBD5E1')   # panel border
    SUCCESS = colors.HexColor('#047857')      # "fully paid" green for balance=0
    DUE = colors.HexColor('#B45309')          # amber for outstanding balance
    HAIRLINE = colors.HexColor('#E5E7EB')

    buf = BytesIO()
    # Slightly tighter top margin so we can paint a brand accent bar
    # flush with the top edge.
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=14 * mm, bottomMargin=18 * mm,
        title=f"Bathqube Payment Receipt {receipt.receipt_number}",
    )

    # ── Typography styles ────────────────────────────────────────────────
    styles = getSampleStyleSheet()

    h_brand = ParagraphStyle('r_brand', parent=styles['Heading1'],
                             textColor=INK, fontSize=22, leading=24,
                             fontName='Helvetica-Bold', spaceAfter=0)
    h_brand_sub = ParagraphStyle('r_brand_sub', parent=styles['Normal'],
                                 textColor=LABEL, fontSize=9, leading=12,
                                 spaceBefore=2)
    receipt_label = ParagraphStyle('r_rl', parent=styles['Normal'],
                                   textColor=BRAND_BLUE, fontSize=10,
                                   alignment=TA_RIGHT, leading=12,
                                   fontName='Helvetica-Bold',
                                   spaceAfter=2)
    receipt_no = ParagraphStyle('r_rno', parent=styles['Normal'],
                                textColor=INK, fontSize=14,
                                alignment=TA_RIGHT, leading=16,
                                fontName='Helvetica-Bold')
    receipt_date = ParagraphStyle('r_rd', parent=styles['Normal'],
                                  textColor=LABEL, fontSize=9,
                                  alignment=TA_RIGHT, leading=11,
                                  spaceBefore=2)

    h_section = ParagraphStyle('r_section', parent=styles['Normal'],
                               textColor=BRAND_BLUE, fontSize=8,
                               fontName='Helvetica-Bold',
                               spaceBefore=0, spaceAfter=4,
                               leading=10)

    body = ParagraphStyle('r_body', parent=styles['Normal'], fontSize=10,
                          leading=13, textColor=INK_SOFT)
    body_b = ParagraphStyle('r_body_b', parent=body, fontName='Helvetica-Bold',
                            fontSize=12, leading=15, textColor=INK)
    body_s = ParagraphStyle('r_body_s', parent=body, fontSize=9, leading=12,
                            textColor=LABEL)

    # Hero amount typography — generous leading so descenders never bleed.
    money_caption = ParagraphStyle('r_money_cap', parent=styles['Normal'],
                                   textColor=LABEL, fontSize=9,
                                   alignment=TA_CENTER, leading=11,
                                   fontName='Helvetica-Bold')
    money_big = ParagraphStyle('r_money', parent=styles['Normal'], fontSize=30,
                               fontName='Helvetica-Bold', alignment=TA_CENTER,
                               textColor=BRAND_BLUE, leading=38,
                               spaceBefore=0, spaceAfter=0)
    words_caption = ParagraphStyle('r_words', parent=styles['Normal'],
                                   fontSize=10, alignment=TA_CENTER,
                                   textColor=INK_SOFT, leading=14,
                                   fontName='Helvetica-Oblique')
    method_caption = ParagraphStyle('r_method', parent=styles['Normal'],
                                    fontSize=9.5, alignment=TA_CENTER,
                                    textColor=INK_SOFT, leading=12)

    story = []

    # ── 1. Top brand accent bar ──────────────────────────────────────────
    # Thin solid brand-blue stripe across the top of the page so the
    # receipt is instantly identifiable, even at thumbnail size.
    accent_bar = Table([[' ']], colWidths=[170 * mm])
    accent_bar.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_BLUE),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LINEABOVE', (0, 0), (-1, 0), 4, BRAND_BLUE),
    ]))
    story.append(accent_bar)
    story.append(Spacer(1, 16))

    # ── 2. Brand mark + receipt metadata ─────────────────────────────────
    issued = receipt.received_at.strftime('%d %b %Y')
    header = Table([[
        [
            Paragraph("BATHQUBE", h_brand),
            Paragraph("Premium Shower Enclosures · Bengaluru, India",
                      h_brand_sub),
        ],
        [
            Paragraph("PAYMENT RECEIPT", receipt_label),
            Paragraph(receipt.receipt_number, receipt_no),
            Paragraph(f"Dated {issued}", receipt_date),
        ],
    ]], colWidths=[100 * mm, 70 * mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, LINE),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(header)
    story.append(Spacer(1, 14))

    # ── 3. Two-column "Received From" + "Reference" ──────────────────────
    # Received from — customer block (name + contact + address)
    cust_lines = [Paragraph(f"{quote.customer_name or '—'}", body_b)]
    contact_bits = []
    if quote.phone: contact_bits.append(quote.phone)
    if quote.email: contact_bits.append(quote.email)
    if contact_bits:
        cust_lines.append(Paragraph(' · '.join(contact_bits), body))
    if quote.site_address:
        addr = quote.site_address
        if quote.pincode:
            addr = f"{addr}, {quote.pincode}"
        cust_lines.append(Paragraph(addr, body))

    # Reference — estimate ref + date + project line
    inv_no = quote.estimate_number or f"BQ-{quote.id}"
    inv_date = quote.created_at.strftime('%d %b %Y')
    ref_lines = [
        Paragraph(f"Estimate <font color='{INK.hexval()}'><b>{inv_no}</b></font>",
                  body_b),
        Paragraph(f"dated {inv_date}", body),
        Paragraph("For shower enclosure work", body_s),
    ]

    received_from_cell = [
        Paragraph("RECEIVED FROM", h_section),
        *cust_lines,
    ]
    reference_cell = [
        Paragraph("REFERENCE", h_section),
        *ref_lines,
    ]

    two_col = Table([[received_from_cell, reference_cell]],
                    colWidths=[95 * mm, 75 * mm])
    two_col.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 20))

    # ── 4. Hero amount panel ─────────────────────────────────────────────
    # Bordered box with subtle background tint. Three lines vertically
    # centred with generous padding so the figure never crowds the words
    # or the method line.
    method_label_txt = (receipt.payment_method or 'bank_transfer'
                        ).replace('_', ' ').title()
    ref_bits = []
    if receipt.utr_number: ref_bits.append(f"UTR {receipt.utr_number}")
    if receipt.cheque_number: ref_bits.append(f"Cheque #{receipt.cheque_number}")
    ref_line = ' · '.join(ref_bits) if ref_bits else ''
    pay_method_text = f"<b>via {method_label_txt}</b>"
    if ref_line:
        pay_method_text += f" &nbsp;·&nbsp; {ref_line}"

    amount_panel_inner = [
        [Paragraph("AMOUNT RECEIVED", money_caption)],
        [Paragraph(_money(receipt.amount), money_big)],
        [Paragraph(_money_in_words(receipt.amount), words_caption)],
        [Spacer(1, 4)],
        [Paragraph(pay_method_text, method_caption)],
    ]
    amount_panel = Table(amount_panel_inner, colWidths=[170 * mm])
    amount_panel.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PANEL_BG),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        # Vertical rhythm row-by-row so caption / figure / words /
        # method don't crowd or collide.
        ('TOPPADDING', (0, 0), (0, 0), 16),
        ('BOTTOMPADDING', (0, 0), (0, 0), 6),
        ('TOPPADDING', (0, 1), (0, 1), 0),
        ('BOTTOMPADDING', (0, 1), (0, 1), 4),
        ('TOPPADDING', (0, 2), (0, 2), 2),
        ('BOTTOMPADDING', (0, 2), (0, 2), 6),
        ('TOPPADDING', (0, 4), (0, 4), 0),
        ('BOTTOMPADDING', (0, 4), (0, 4), 16),
        ('LEFTPADDING', (0, 0), (-1, -1), 18),
        ('RIGHTPADDING', (0, 0), (-1, -1), 18),
        # Thin border on three sides + bold blue stripe on the left
        # for that "official statement" look.
        ('BOX', (0, 0), (-1, -1), 0.6, PANEL_EDGE),
        ('LINEBEFORE', (0, 0), (0, -1), 3.5, BRAND_BLUE),
    ]))
    story.append(amount_panel)
    story.append(Spacer(1, 22))

    # ── 5. Payment summary table ─────────────────────────────────────────
    # Rebuild "previously paid" from sibling receipts dated ≤ this one
    # (id tiebreak for same-day) so a re-generated receipt reflects the
    # right running total as of its own date.
    siblings = list(quote.payment_receipts or [])
    prior_paid = sum(
        float(r.amount or 0)
        for r in siblings
        if r.id != receipt.id
        and (r.received_at, r.id) <= (receipt.received_at, receipt.id)
    )
    total_to_date = prior_paid + float(receipt.amount or 0)
    invoice_total = float(
        quote.revised_total if (quote.has_revision
                                and quote.revised_total is not None)
        else (quote.total or 0)
    )
    balance = max(0.0, invoice_total - total_to_date)
    fully_paid = balance == 0.0

    # Section title
    story.append(Paragraph("PAYMENT SUMMARY", h_section))

    # Cleaner labels + the visual "+" prefix on the row that adds to the
    # running total, so the math reads naturally top-to-bottom.
    summary_rows = [
        ['Invoice total',           _money(invoice_total)],
        ['Previously paid',         _money(prior_paid)],
        ['This receipt',          f"+ {_money(receipt.amount)}"],
        ['Total paid to date',      _money(total_to_date)],
        ['Balance due',           f"{_money(balance)}{' ✓' if fully_paid else ''}"],
    ]
    sum_tbl = Table(summary_rows, colWidths=[110 * mm, 60 * mm], hAlign='LEFT')
    style_cmds = [
        ('TEXTCOLOR', (0, 0), (0, -1), INK_SOFT),
        ('TEXTCOLOR', (1, 0), (1, -1), INK_SOFT),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        # Hairlines between rows for that ledger feel.
        ('LINEBELOW', (0, 0), (-1, 0), 0.4, HAIRLINE),
        ('LINEBELOW', (0, 1), (-1, 1), 0.4, HAIRLINE),
        ('LINEBELOW', (0, 2), (-1, 2), 0.6, INK_SOFT),   # heavier above totals
        ('LINEBELOW', (0, 3), (-1, 3), 0.4, HAIRLINE),
    ]
    for i, row in enumerate(summary_rows):
        if row[0] == 'This receipt':
            style_cmds += [
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                ('TEXTCOLOR', (0, i), (-1, i), INK),
            ]
        if row[0] == 'Total paid to date':
            style_cmds += [
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                ('FONTSIZE', (0, i), (-1, i), 11),
                ('TEXTCOLOR', (0, i), (-1, i), BRAND_BLUE),
            ]
        if row[0] == 'Balance due':
            style_cmds += [
                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                ('FONTSIZE', (0, i), (-1, i), 12),
                ('TEXTCOLOR', (0, i), (-1, i),
                 SUCCESS if fully_paid else DUE),
            ]
    sum_tbl.setStyle(TableStyle(style_cmds))
    story.append(sum_tbl)
    story.append(Spacer(1, 16))

    # ── 6. Notes + issued-by ──────────────────────────────────────────────
    if receipt.notes:
        notes_tbl = Table([[
            Paragraph("Notes", body_s),
            Paragraph(receipt.notes,
                      ParagraphStyle('r_notes', parent=body, fontSize=9.5,
                                     leading=12, textColor=INK_SOFT,
                                     fontName='Helvetica-Oblique')),
        ]], colWidths=[20 * mm, 150 * mm])
        notes_tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(notes_tbl)
        story.append(Spacer(1, 6))

    creator_name = (receipt.creator.username
                    if getattr(receipt, 'creator', None) else None)
    if creator_name:
        # Fall back to `received_at` for receipts that haven't been
        # persisted yet (created_at is DB-default and stays None until
        # the first commit). PDF previews shouldn't crash on transient
        # rows.
        when = receipt.created_at or receipt.received_at
        when_str = when.strftime('%d %b %Y') + (
            f", {when.strftime('%I:%M %p')}" if hasattr(when, 'hour') else ''
        )
        story.append(Paragraph(
            f"<font color='{LABEL.hexval()}' size='9'>Issued by "
            f"<b>{creator_name}</b> on {when_str}</font>",
            styles['Normal'],
        ))

    # ── 7. Signature block ───────────────────────────────────────────────
    story.append(Spacer(1, 32))
    sig_tbl = Table([
        ['', ''],  # empty space for the actual signatures
        ['Authorised signature', 'Company stamp'],
    ], colWidths=[80 * mm, 80 * mm])
    sig_tbl.setStyle(TableStyle([
        ('LINEABOVE', (0, 1), (0, 1), 0.5, INK_SOFT),
        ('LINEABOVE', (1, 1), (1, 1), 0.5, INK_SOFT),
        ('TEXTCOLOR', (0, 1), (-1, 1), LABEL),
        ('FONTSIZE', (0, 1), (-1, 1), 8.5),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, 0), 26),
        ('TOPPADDING', (0, 1), (-1, 1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 0),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 0),
    ]))
    story.append(sig_tbl)

    # ── 8. Company block (legal entity, address, contact) ────────────────
    story.append(Spacer(1, 28))
    company_block = Table([
        [Paragraph("Vetrova Tech Services Private Limited",
                   ParagraphStyle('co_name', parent=styles['Normal'],
                                  fontSize=10, alignment=TA_CENTER,
                                  textColor=INK,
                                  fontName='Helvetica-Bold'))],
        [Paragraph("Bengaluru, Karnataka, India",
                   ParagraphStyle('co_addr', parent=styles['Normal'],
                                  fontSize=9, alignment=TA_CENTER,
                                  textColor=LABEL))],
        [Paragraph("WhatsApp +91 85500 11196  ·  support@bathqube.com  ·  bathqube.com",
                   ParagraphStyle('co_contact', parent=styles['Normal'],
                                  fontSize=8.5, alignment=TA_CENTER,
                                  textColor=LABEL))],
    ], colWidths=[170 * mm])
    company_block.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LINEABOVE', (0, 0), (-1, 0), 0.5, LINE),
    ]))
    # Padding inside the first row needs a little more breathing room from
    # the line above.
    story.append(Spacer(1, 0))
    story.append(company_block)

    # ── 9. Disclaimer ────────────────────────────────────────────────────
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<font color='#9CA3AF' size='7.5'>This is a computer-generated "
        "receipt and does not require a physical signature.</font>",
        ParagraphStyle('foot', parent=styles['Normal'], alignment=TA_CENTER),
    ))

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Receipt number helper — call from the route that creates a new receipt.
# ─────────────────────────────────────────────────────────────────────────────


def next_receipt_number(db_session):
    """Return the next sequential receipt number in the form
    BQ-RCP-YYYY-NNNN. Counter is per-calendar-year so the running number
    resets each January. Uses MAX(receipt_number) of the current year as
    a fast lookup — no separate counter table needed.

    Called inside the same transaction that inserts the new receipt row,
    so collisions are vanishingly unlikely. If two parallel inserts ever
    pick the same number, the unique index on receipt_number will reject
    the duplicate and the route can retry."""
    from datetime import datetime as _dt
    from sqlalchemy import text as _text
    year = _dt.utcnow().year
    prefix = f"BQ-RCP-{year}-"
    row = db_session.execute(_text(
        "SELECT MAX(receipt_number) FROM bathqube_payment_receipts "
        "WHERE receipt_number LIKE :prefix"
    ), {'prefix': prefix + '%'}).first()
    last = row[0] if row else None
    if not last:
        nxt = 1
    else:
        try:
            nxt = int(last.rsplit('-', 1)[-1]) + 1
        except (ValueError, IndexError):
            nxt = 1
    return f"{prefix}{nxt:04d}"
