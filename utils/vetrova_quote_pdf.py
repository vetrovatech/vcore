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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    KeepTogether,
)


# Vetrova brand palette — sourced from vetrova.in (`VIMark.tsx`) so the
# PDF matches the site exactly.
# Vetrova's own UPI QR — 8550011196@ibl. Distinct from Bathqube's
# static/images/upi-qr.jpeg (@ybl); the two brands collect on different VPAs.
_VETROVA_QR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'images', 'vetrova-upi-qr.jpeg',
)

VI_FOREST     = colors.HexColor('#0F2A22')
VI_BRASS      = colors.HexColor('#C19A4E')
VI_BRASS_DEEP = colors.HexColor('#8A6A2E')
VI_CREAM      = colors.HexColor('#F5F0E1')
VI_MUTED      = colors.HexColor('#6B7280')
VI_LIGHT      = colors.HexColor('#E5E7EB')


# ─── Unicode font registration (₹ glyph fix) ────────────────────────────────
# ReportLab's default Helvetica lacks U+20B9 (₹) and every currency cell
# rendered as a "missing glyph" black square (BD screenshot 2026-08-07).
# Fix: register DejaVuSans / DejaVuSans-Bold — installed via the
# Dockerfile's `fonts-dejavu-core` apt package — and use them as the PDF's
# base fonts. Mirrors the pattern already proven on tax_invoice_pdf.py.
# Falls back to Helvetica + 'Rs.' text prefix if the TTFs aren't on disk
# (e.g. non-Debian dev box) so the PDF still renders cleanly.
_BASE_FONT      = 'Helvetica'
_BASE_FONT_BOLD = 'Helvetica-Bold'
_RUPEE_GLYPH    = 'Rs.'   # fallback until DejaVu registers

_DEJAVU_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',           # Debian/Ubuntu
    '/usr/share/fonts/dejavu/DejaVuSans.ttf',                    # Fedora/RHEL
    '/Library/Fonts/DejaVuSans.ttf',                             # macOS
]
_DEJAVU_BOLD_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
    '/Library/Fonts/DejaVuSans-Bold.ttf',
]


def _first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _register_unicode_fonts_once():
    """Register DejaVu Sans + Bold as VetrovaSans / VetrovaSans-Bold on
    the first render. Upgrades _BASE_FONT / _BASE_FONT_BOLD / _RUPEE_GLYPH
    in-place so subsequent renders use the Unicode-covered fonts. Safe
    to call repeatedly — pdfmetrics.registerFont is idempotent for the
    same font name."""
    global _BASE_FONT, _BASE_FONT_BOLD, _RUPEE_GLYPH
    if _BASE_FONT == 'VetrovaSans':   # already registered
        return
    p_regular = _first_existing(_DEJAVU_PATHS)
    p_bold    = _first_existing(_DEJAVU_BOLD_PATHS)
    if not (p_regular and p_bold):
        return   # keep Helvetica + 'Rs.' fallback
    try:
        pdfmetrics.registerFont(TTFont('VetrovaSans',      p_regular))
        pdfmetrics.registerFont(TTFont('VetrovaSans-Bold', p_bold))
    except Exception:
        return
    _BASE_FONT      = 'VetrovaSans'
    _BASE_FONT_BOLD = 'VetrovaSans-Bold'
    _RUPEE_GLYPH    = '₹'


def _inr(v):
    """Format a value as an INR string using the current rupee glyph
    (either '₹' or the safe 'Rs.' fallback if DejaVu didn't register)."""
    try:
        return f"{_RUPEE_GLYPH}{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return f"{_RUPEE_GLYPH}0"


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


def _esc(text):
    """Escape customer-written text for ReportLab's Paragraph mini-markup.

    Paragraph parses its input as XML-ish markup, so a bare '&' or '<' in
    free text raises and takes the WHOLE PDF down with it — which for us
    means the quote email never sends. Customer comments are the first
    genuinely free-form strings to reach these Paragraphs, so they get
    escaped here. (Pre-existing fields like customer_name are still
    unescaped upstream; worth tightening separately rather than widening
    this change.)
    """
    return (
        str(text)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


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
        # Customer's per-panel comment (BD 2026-08-18). Escaped because
        # these lines are rendered as ReportLab markup Paragraphs — an
        # unescaped "&" or "<" in customer text would break the parse.
        note = (p.get('comment') or '').strip()
        note_sfx = f" — {_esc(note)}" if note else ''
        lines.append(f"{noun} {n}: {w} × {h} {dim_unit or 'ft'}{sfx}{note_sfx}")
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

    # Lazy-register DejaVu on first render so paragraphs + table cells
    # can print the ₹ glyph. No-op on subsequent renders.
    _register_unicode_fonts_once()

    ss = getSampleStyleSheet()
    base_font = _BASE_FONT
    base_bold = _BASE_FONT_BOLD

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

        # Line-level customer comment — railings/staircase have no panels to
        # hang a note off, so it prints against the whole line (BD 2026-08-18).
        if it.customer_comment:
            desc_flow.append(Paragraph(
                f'<i>Note: {_esc(it.customer_comment)}</i>', s_body_sm))

        if it.fabric_code:
            desc_flow.append(Paragraph(f'Fabric: <b>{it.fabric_code}</b>', s_body_sm))

        # Multi-artwork bucket (Printed Glass). Falls back to a
        # single-thumbnail render when only the legacy single-image
        # field is populated via uploaded_images_parsed's fallback.
        imgs = it.uploaded_images_parsed
        if imgs:
            desc_flow.append(Spacer(1, 2))
            # Header line — "3 attached" style summary matches the BD
            # view template so both surfaces read the same.
            if len(imgs) == 1:
                desc_flow.append(Paragraph('Customer-supplied design (attached)', s_body_sm))
            else:
                desc_flow.append(Paragraph(
                    f'Customer-supplied designs ({len(imgs)} attached)',
                    s_body_sm,
                ))
            # Lay out thumbnails in a horizontal strip: up to 4 per row,
            # each 22×22 mm, labelled with gallery code (preferred) or
            # filename (fallback) or a #N marker.
            row_cells = []
            for i, a in enumerate(imgs):
                img_flow = _data_url_to_image_flowable(a.get('dataUrl'), 22, 22)
                label = a.get('galleryCode') or a.get('filename') or f'#{i + 1}'
                if len(label) > 22:
                    label = label[:20] + '…'
                if img_flow is not None:
                    cell = [img_flow, Paragraph(label, s_body_sm)]
                else:
                    cell = [Paragraph(label, s_body_sm)]
                row_cells.append(cell)
            if row_cells:
                # 4-column table so 3+ thumbs wrap neatly. Pad with blanks
                # so ReportLab's Table doesn't complain about ragged rows.
                cols_per_row = 4
                rows = []
                for j in range(0, len(row_cells), cols_per_row):
                    chunk = row_cells[j:j + cols_per_row]
                    while len(chunk) < cols_per_row:
                        chunk.append('')
                    rows.append(chunk)
                thumb_tbl = Table(
                    rows,
                    colWidths=[26 * mm] * cols_per_row,
                    hAlign='LEFT',
                )
                thumb_tbl.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING',  (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                    ('TOPPADDING',   (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
                ]))
                desc_flow.append(thumb_tbl)

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
    # Delivery charge — rule-driven, added by VetrovaQuote.recompute_totals()
    # when subtotal < ₹20,000. Renders here as its own line so the customer
    # sees why a small order costs a bit more (2026-07-27 BD rule).
    delivery = float(getattr(quote, 'delivery_charge', 0) or 0)
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
    if delivery > 0:
        tot_rows.append(['Delivery charges', _inr(delivery)])
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

    # ── Account details + UPI QR ──────────────────────────────────────
    # Printed after the T&Cs on every Vetrova quote (BD 2026-08-18).
    #
    # Vetrova collects on 8550011196@ibl; Bathqube stays on 8550011196@ybl.
    # Hence the separate asset — do NOT repoint this at
    # static/images/upi-qr.jpeg, that QR encodes Bathqube's handle and the
    # money would land on the wrong VPA.
    #
    # Wrapped in KeepTogether so a page break can never separate the QR
    # from the account number it belongs to.
    story.append(Paragraph('Account details', s_h2))
    s_bank_l = ParagraphStyle('bank_l', parent=s_body_sm, textColor=VI_MUTED)
    s_bank_v = ParagraphStyle('bank_v', parent=s_body_sm,
                              fontName=base_bold, textColor=VI_FOREST)
    bank_rows = [
        [Paragraph('Account Name', s_bank_l), Paragraph('Vetrova Tech Services Private Limited', s_bank_v)],
        [Paragraph('Bank Name', s_bank_l),    Paragraph('IDFC First Bank', s_bank_v)],
        [Paragraph('Account Number', s_bank_l), Paragraph('10249972220', s_bank_v)],
        [Paragraph('IFSC Code', s_bank_l),    Paragraph('IDFB0080158', s_bank_v)],
        [Paragraph('Account Type', s_bank_l), Paragraph('Current Account', s_bank_v)],
    ]
    bank_tbl = Table(bank_rows, colWidths=[30 * mm, 70 * mm])
    bank_tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND',    (0, 0), (-1, -1), VI_CREAM),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
    ]))

    qr_cell = []
    if os.path.exists(_VETROVA_QR_PATH):
        qr_cell.append(Image(_VETROVA_QR_PATH, width=32 * mm, height=32 * mm))
        qr_cell.append(Paragraph(
            '<font color="#6B7280" size="7">Scan to pay via UPI</font>',
            ParagraphStyle('qr_cap', parent=s_body_sm, alignment=TA_CENTER, spaceBefore=3),
        ))

    pay_block = Table([[bank_tbl, qr_cell]], colWidths=[100 * mm, 45 * mm])
    pay_block.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN',  (1, 0), (1, 0), 'CENTER'),
    ]))
    story.append(KeepTogether(pay_block))
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
