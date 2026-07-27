"""PDF generator for Vetrova Interni configurator quotes (Phase 1).

One document: `generate_vetrova_quote_pdf(quote)` → bytes.

Rendered from the current DB state (VetrovaQuote + VetrovaQuoteItem[])
so it always reflects BD's latest edits via the revise flow, not the
frozen customer-facing PDF glassyplatform emailed at submit time.

Design mirrors `vetrova_upvc_pdf.py` — same brand palette (Vetrova
forest + brass), same document skeleton (masthead → customer block →
items table → totals → T&C → legal footer). Compact, single-page for
≤5 items, spills naturally beyond.

ReportLab — pure Python, no headless browser. Output is bytes for both
the in-app preview/download route and (future) customer email attachment.
"""

import base64
import json
import os
from datetime import timedelta
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    KeepTogether,
)


# Vetrova brand palette — sourced from vetrova.in (`VIMark.tsx`) so the
# PDF matches the site exactly.
VI_FOREST     = colors.HexColor('#0F2A22')
VI_BRASS      = colors.HexColor('#C19A4E')
VI_BRASS_DEEP = colors.HexColor('#8A6A2E')
VI_CREAM      = colors.HexColor('#F5F0E1')
VI_MUTED      = colors.HexColor('#6B7280')
VI_LIGHT      = colors.HexColor('#E5E7EB')


def _inr(v):
    try:
        return f"₹{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return "₹0"


def _fmt_ft(v):
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return "0"


def _selections_summary(item_selections):
    """One-liner summary — 'glassType: Fabric Laminated · thickness: 12mm'."""
    if not item_selections:
        return ''
    return ' · '.join(f'{k}: {v}' for k, v in item_selections.items())


def _panels_summary(panels, dim_unit):
    """List of 'Panel 1: 4 × 6 ft' / 'Door 1: 3 × 7 ft × 2'."""
    if not panels:
        return None
    lines = []
    p_n = 0
    d_n = 0
    for p in panels:
        is_door = (p.get('kind') == 'door')
        if is_door:
            d_n += 1
            n = d_n
        else:
            p_n += 1
            n = p_n
        noun = 'Door' if is_door else 'Panel'
        w = p.get('widthFt', 0)
        h = p.get('heightFt', 0)
        qty = p.get('qty', 1)
        sfx = f" × {qty}" if qty and int(qty) > 1 else ''
        lines.append(f"{noun} {n}: {w} × {h} {dim_unit or 'ft'}{sfx}")
    return lines


def _data_url_to_image_flowable(data_url, width_mm=22, height_mm=22):
    """Decode a base64 data URL into a ReportLab Image flowable.

    Returns None on any decode failure — the caller falls back to a
    'Customer artwork attached' text line. Kept small (~22mm square) so
    it fits in the description column without breaking the table layout.
    """
    if not data_url or not isinstance(data_url, str):
        return None
    if not data_url.startswith('data:image/'):
        return None
    try:
        header, b64 = data_url.split(',', 1)
        raw = base64.b64decode(b64)
        return Image(BytesIO(raw), width=width_mm * mm, height=height_mm * mm, kind='proportional')
    except Exception:
        return None


def generate_vetrova_quote_pdf(quote):
    """Render `quote` (a VetrovaQuote row) to PDF bytes.

    Reads `quote.items` (VetrovaQuoteItem[]) for line items;
    `quote.subtotal / cgst / sgst / grand_total / revised_total` for
    totals (already computed by recompute_totals()).
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"Vetrova Quote {quote.quote_ref}",
        author='Vetrova Interni',
    )

    ss = getSampleStyleSheet()
    base_font = 'Helvetica'
    base_bold = 'Helvetica-Bold'

    s_h1 = ParagraphStyle('h1', parent=ss['Heading1'],
                          fontName=base_bold, fontSize=16, textColor=VI_FOREST,
                          leading=19, spaceAfter=2)
    s_h2 = ParagraphStyle('h2', parent=ss['Heading2'],
                          fontName=base_bold, fontSize=11, textColor=VI_FOREST,
                          leading=13, spaceAfter=4)
    s_body = ParagraphStyle('body', parent=ss['BodyText'],
                            fontName=base_font, fontSize=9, textColor=VI_FOREST,
                            leading=11, spaceAfter=0)
    s_body_sm = ParagraphStyle('body_sm', parent=s_body, fontSize=8, leading=10, textColor=VI_MUTED)
    s_body_r  = ParagraphStyle('body_r',  parent=s_body, alignment=TA_RIGHT)
    s_body_b  = ParagraphStyle('body_b',  parent=s_body, fontName=base_bold)
    s_body_br = ParagraphStyle('body_br', parent=s_body, fontName=base_bold, alignment=TA_RIGHT)
    s_muted   = ParagraphStyle('muted',   parent=s_body, fontSize=8, textColor=VI_MUTED, leading=10)

    story = []

    # ── Masthead ──────────────────────────────────────────────────────
    from datetime import datetime
    today = datetime.utcnow()
    valid_until = quote.valid_until or (today + timedelta(days=10))

    header_data = [[
        Paragraph('<b>VETROVA INTERNI</b><br/><font color="#8A6A2E" size="8">Modular glass systems, made to measure</font>',
                  ParagraphStyle('mast', parent=s_body, fontName=base_bold, fontSize=14,
                                 textColor=VI_FOREST, leading=17)),
        Paragraph(
            f'<b><font size="10">QUOTATION</font></b><br/>'
            f'<font size="8" color="#6B7280">Ref: <b>{quote.quote_ref}</b><br/>'
            f'Date: {today.strftime("%d %b %Y")}<br/>'
            f'Valid until: {valid_until.strftime("%d %b %Y")}'
            + (f'<br/>Revision: {quote.revision_count}' if (quote.revision_count or 0) > 0 else '')
            + '</font>',
            ParagraphStyle('meta', parent=s_body, alignment=TA_RIGHT, leading=11)),
    ]]
    header_tbl = Table(header_data, colWidths=[100 * mm, 80 * mm])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.75, VI_BRASS),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6 * mm))

    # ── Bill-to block ─────────────────────────────────────────────────
    bill_lines = [f'<b>{quote.customer_name or "—"}</b>']
    if quote.phone:        bill_lines.append(quote.phone)
    if quote.email:        bill_lines.append(quote.email)
    if quote.site_address: bill_lines.append(quote.site_address.replace('\n', '<br/>'))
    if quote.pincode:      bill_lines.append(f'Pincode: {quote.pincode}')

    bill_tbl = Table([[
        Paragraph('<font color="#6B7280" size="8">BILL TO</font><br/>' + '<br/>'.join(bill_lines), s_body),
        Paragraph(
            '<font color="#6B7280" size="8">FROM</font><br/>'
            '<b>Vetrova Tech Services Pvt Ltd</b><br/>'
            'Bengaluru, Karnataka<br/>'
            'support@glassy.in',
            ParagraphStyle('from', parent=s_body, alignment=TA_RIGHT)),
    ]], colWidths=[100 * mm, 80 * mm])
    bill_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
    ]))
    story.append(bill_tbl)

    # ── Line items table ──────────────────────────────────────────────
    story.append(Paragraph('Line items', s_h2))

    items_head = [
        Paragraph('<b>#</b>',           s_body),
        Paragraph('<b>Description</b>', s_body),
        Paragraph('<b>Size · Qty</b>',  s_body_r),
        Paragraph('<b>Rate</b>',        s_body_r),
        Paragraph('<b>Amount</b>',      s_body_r),
    ]
    items_rows = [items_head]

    for it in (quote.items or []):
        # Description cell — category, optional label, selections summary,
        # panels list, fabric code, uploaded image thumbnail.
        desc_bits = [f'<b>{it.category_label}</b>']
        if it.label:
            desc_bits.append(f'<font color="#6B7280"> · {it.label}</font>')
        desc_html = ''.join(desc_bits)
        desc_flow = [Paragraph(desc_html, s_body)]

        sel_sum = _selections_summary(it.selections_parsed)
        if sel_sum:
            desc_flow.append(Paragraph(sel_sum, s_body_sm))

        panels_lines = _panels_summary(it.panels_parsed, it.dimension_unit)
        if panels_lines:
            desc_flow.append(Paragraph('<br/>'.join(panels_lines), s_body_sm))

        if it.fabric_code:
            desc_flow.append(Paragraph(f'Fabric: <b>{it.fabric_code}</b>', s_body_sm))

        img_flow = _data_url_to_image_flowable(it.uploaded_image_data_url, 22, 22)
        if img_flow is not None:
            desc_flow.append(Spacer(1, 2))
            desc_flow.append(img_flow)
            desc_flow.append(Paragraph('Customer-uploaded artwork', s_body_sm))

        if it.notes:
            desc_flow.append(Paragraph(f'<font color="#6B7280"><i>Note: {it.notes}</i></font>', s_body_sm))

        # Size · Qty column
        is_sqft = (it.dimension_kind == 'square_feet')
        if it.panels_parsed:
            p_ct = sum(1 for p in it.panels_parsed if p.get('kind') != 'door')
            d_ct = sum(1 for p in it.panels_parsed if p.get('kind') == 'door')
            sz_top = f"{float(it.running_ft or 0):.1f} sqft" if is_sqft else f"{_fmt_ft(it.running_ft)} ft"
            sz_bot_bits = []
            if p_ct: sz_bot_bits.append(f"{p_ct} panel" + ('' if p_ct == 1 else 's'))
            if d_ct: sz_bot_bits.append(f"{d_ct} door" + ('' if d_ct == 1 else 's'))
            sz_html = f"{sz_top}<br/><font color='#6B7280' size='7'>{' · '.join(sz_bot_bits)}</font>"
        elif is_sqft:
            sz_html = f"{float(it.running_ft or 0):.1f} sqft × {_fmt_ft(it.quantity)}"
        else:
            sz_html = f"{_fmt_ft(it.running_ft)} ft × {_fmt_ft(it.quantity)}"

        rate_unit = '/sqft' if is_sqft else '/ft'
        items_rows.append([
            Paragraph(str(it.sort_order), s_body),
            desc_flow,
            Paragraph(sz_html, s_body_r),
            Paragraph(f"{_inr(it.rate_per_unit)}{rate_unit}", s_body_r),
            Paragraph(_inr(it.subtotal), s_body_br),
        ])

    if len(items_rows) == 1:
        items_rows.append([
            '', Paragraph('<i>No line items yet — add via Revise.</i>', s_muted),
            '', '', '',
        ])

    items_tbl = Table(items_rows, colWidths=[8 * mm, 92 * mm, 30 * mm, 22 * mm, 28 * mm],
                      repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0), VI_CREAM),
        ('TEXTCOLOR',   (0, 0), (-1, 0), VI_FOREST),
        ('LINEBELOW',   (0, 0), (-1, 0), 0.5, VI_BRASS),
        ('LINEBELOW',   (0, 1), (-1, -1), 0.25, VI_LIGHT),
        ('VALIGN',      (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',(0, 0), (-1, -1), 5),
        ('TOPPADDING',  (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── Totals ────────────────────────────────────────────────────────
    subtotal = float(quote.subtotal or 0)
    transport = float(quote.transport_charges or 0)
    cgst = float(quote.cgst or 0)
    sgst = float(quote.sgst or 0)
    grand = float(quote.grand_total or 0)
    revised = float(quote.revised_total) if quote.revised_total is not None else None
    gst_pct = float(quote.gst_percentage or 18)

    tot_rows = [
        ['Subtotal', _inr(subtotal)],
    ]
    if transport > 0:
        tot_rows.append(['Transport charges', _inr(transport)])
    tot_rows.append([f'CGST @ {gst_pct/2:g}%', _inr(cgst)])
    tot_rows.append([f'SGST @ {gst_pct/2:g}%', _inr(sgst)])
    tot_rows.append(['Grand total (incl. GST)', _inr(grand)])
    if revised is not None:
        tot_rows.append(['Revised total', _inr(revised)])

    tot_tbl = Table(
        [[Paragraph(f'<b>{r[0]}</b>' if i == len(tot_rows) - 1 or (i == len(tot_rows) - 1 and revised is None) else r[0],
                    s_body_r),
          Paragraph(f'<b>{r[1]}</b>' if i == len(tot_rows) - 1 else r[1], s_body_br)]
         for i, r in enumerate(tot_rows)],
        colWidths=[40 * mm, 30 * mm],
        hAlign='RIGHT',
    )
    tot_tbl.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE',    (0, -1), (-1, -1), 0.5, VI_BRASS),
        ('BACKGROUND',   (0, -1), (-1, -1), VI_CREAM),
        ('TOPPADDING',   (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
    ]))
    story.append(tot_tbl)
    story.append(Spacer(1, 6 * mm))

    # ── T&C / footer ──────────────────────────────────────────────────
    story.append(Paragraph('Terms &amp; conditions', s_h2))
    tc = (
        '• Prices are indicative and valid for the period above. Site measurement may adjust final quantities.<br/>'
        '• 50% advance on order confirmation; balance before installation.<br/>'
        '• Lead time depends on category — typically 14–28 days from confirmed order.<br/>'
        '• Colour / finish variations across production batches are inherent to the material.<br/>'
        '• GST is charged at prevailing rate; the split shown above assumes intra-state (CGST + SGST).'
    )
    story.append(Paragraph(tc, s_body_sm))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(
        '<font color="#6B7280" size="7">Vetrova Interni is a division of Vetrova Tech Services Pvt Ltd. '
        f'Quote {quote.quote_ref} · rendered {today.strftime("%d %b %Y, %H:%M UTC")}</font>',
        s_body_sm,
    ))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf
