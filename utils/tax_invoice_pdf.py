"""PDF generator for Vetrova GST tax invoices.

Mirrors the standard Indian GST tax-invoice layout (which is legally
mandated by the Govt's GST rules — same structure every business must
use). Single page, single bordered "invoice box" with internal grid
lines dividing sections.

Structural rows of the outer invoice box (top to bottom):
  1. Header band — "GST TAX INVOICE" + "(ORIGINAL FOR RECIPIENT)" + "e-Invoice"
  2. IRN strip (only when invoice.irn is set)
  3. Parties + Metadata main band
     LEFT (60%)  — Seller block / Consignee (Ship-to) / Buyer (Bill-to)
     RIGHT (40%) — Invoice metadata grid (Invoice No, Date, e-Way Bill,
                    Mode of Payment, Dispatched through, etc.)
  4. Line items table (Sl · Description · HSN/SAC · Qty · Rate · per · Amount)
  5. Amount-in-words strip
  6. HSN-wise tax summary
  7. Tax-in-words strip
  8. Bottom triptych: PAN/Declaration · Bank · Authorised signatory
Footer below the box (small centred text):
  – SUBJECT TO BENGALURU JURISDICTION
  – This is a Computer Generated Invoice
"""

import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, LongTable,
)


# ─── Unicode font registration ──────────────────────────────────────────────
# Default ReportLab Helvetica lacks ₹ (U+20B9), so it renders as a
# black-square "missing glyph" placeholder. Register DejaVuSans/Bold
# from the system fonts directory — installed via the Dockerfile's
# `fonts-dejavu-core` apt package. Registration is idempotent + lazy:
# happens once on first import, no-op on subsequent calls.
_RUPEE_FONT = 'Helvetica-Bold'   # fallback (no ₹ — paired with `RUPEE_GLYPH`)
RUPEE_GLYPH = 'Rs.'              # safe fallback text when DejaVu unavailable
_DEJAVU_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',           # Debian/Ubuntu
    '/usr/share/fonts/dejavu/DejaVuSans.ttf',                    # Fedora/RHEL
    '/Library/Fonts/DejaVuSans.ttf',                             # mac brew
]
_DEJAVU_BOLD_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
    '/Library/Fonts/DejaVuSans-Bold.ttf',
]


def _register_rupee_font_once():
    """Register DejaVuSans-Bold under name 'RupeeBold' the first time we
    render. Upgrades _RUPEE_FONT + RUPEE_GLYPH in-place so subsequent
    callers use the Unicode font instead of the 'Rs.' fallback.
    Safe to call repeatedly — pdfmetrics.registerFont is idempotent
    given the same name."""
    global _RUPEE_FONT, RUPEE_GLYPH
    if _RUPEE_FONT != 'Helvetica-Bold':  # already registered
        return
    for path in _DEJAVU_BOLD_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('RupeeBold', path))
                _RUPEE_FONT = 'RupeeBold'
                RUPEE_GLYPH = '₹'   # actual rupee symbol
                return
            except Exception:
                continue
    # No DejaVu found — keep the 'Rs.' fallback; the PDF still renders
    # cleanly, just without the proper ₹ glyph.


# Palette — neutral black/grey, professional GST-invoice feel.
INK_DARK    = colors.HexColor('#0F0F0F')
INK_MID     = colors.HexColor('#2E2E2E')
MUTED       = colors.HexColor('#5E5E5E')
LINE_INK    = colors.HexColor('#1E1E1E')
LINE_LIGHT  = colors.HexColor('#B5B5B5')
BG_TINT     = colors.HexColor('#F1F1F1')

PAGE_BODY_WIDTH_MM = 190.0   # A4 (210mm) minus 10mm margins each side


# ─── Formatting helpers ─────────────────────────────────────────────────────

def _money(v):
    """Indian-format money. e.g. 154942.40 → '1,54,942.40'."""
    try:
        amt = float(v or 0)
    except (TypeError, ValueError):
        return '0.00'
    sign = '-' if amt < 0 else ''
    amt = abs(amt)
    int_part = int(amt)
    paise = round((amt - int_part) * 100)
    if paise == 100:
        int_part += 1
        paise = 0
    s = str(int_part)
    if len(s) <= 3:
        body = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        body = ','.join(reversed(groups)) + ',' + last3
    return f'{sign}{body}.{paise:02d}'


def _fmt_date(d):
    if not d:
        return ''
    try:
        return d.strftime('%d-%b-%y')
    except Exception:
        return str(d)


def _para_styles():
    """Build the small set of ParagraphStyles used throughout. Caches
    nothing — called once per render which is cheap."""
    styles = getSampleStyleSheet()
    return {
        'title':       ParagraphStyle('inv_title',  parent=styles['Normal'],
                                       fontName='Helvetica-Bold', fontSize=11,
                                       alignment=TA_CENTER, textColor=INK_DARK,
                                       leading=13),
        'subtitle':    ParagraphStyle('inv_sub',    parent=styles['Normal'],
                                       fontSize=8.5, alignment=TA_CENTER,
                                       textColor=INK_MID, leading=10),
        'einv':        ParagraphStyle('einv',       parent=styles['Normal'],
                                       fontName='Helvetica-Bold', fontSize=10,
                                       alignment=TA_RIGHT, textColor=INK_DARK,
                                       leading=12),
        'label':       ParagraphStyle('label',      parent=styles['Normal'],
                                       fontSize=7.5, textColor=MUTED, leading=9),
        'value':       ParagraphStyle('value',      parent=styles['Normal'],
                                       fontName='Helvetica-Bold', fontSize=9,
                                       textColor=INK_DARK, leading=11),
        'value_small': ParagraphStyle('value_sm',   parent=styles['Normal'],
                                       fontName='Helvetica-Bold', fontSize=8.5,
                                       textColor=INK_DARK, leading=10),
        'name':        ParagraphStyle('name',       parent=styles['Normal'],
                                       fontName='Helvetica-Bold', fontSize=10,
                                       textColor=INK_DARK, leading=12, spaceAfter=2),
        'body':        ParagraphStyle('body',       parent=styles['Normal'],
                                       fontSize=8.5, textColor=INK_DARK, leading=11),
        'body_small':  ParagraphStyle('body_sm',    parent=styles['Normal'],
                                       fontSize=8, textColor=INK_MID, leading=10),
        'body_muted':  ParagraphStyle('body_muted', parent=styles['Normal'],
                                       fontSize=8, textColor=MUTED, leading=10),
        'right':       ParagraphStyle('right',      parent=styles['Normal'],
                                       fontSize=8.5, alignment=TA_RIGHT,
                                       textColor=INK_DARK, leading=10),
        'right_bold':  ParagraphStyle('right_b',    parent=styles['Normal'],
                                       fontName='Helvetica-Bold', fontSize=9,
                                       alignment=TA_RIGHT, textColor=INK_DARK,
                                       leading=11),
        # Used only for the grand-total line that prints the ₹ symbol.
        # fontName is the registered DejaVu (or 'Helvetica-Bold' fallback
        # paired with the 'Rs.' RUPEE_GLYPH text — see registration).
        'total_money': ParagraphStyle('total_money', parent=styles['Normal'],
                                       fontName=_RUPEE_FONT, fontSize=9,
                                       alignment=TA_RIGHT, textColor=INK_DARK,
                                       leading=11),
        'center_foot': ParagraphStyle('foot',       parent=styles['Normal'],
                                       fontSize=8, alignment=TA_CENTER,
                                       textColor=MUTED, leading=10),
    }


# ─── Section builders ──────────────────────────────────────────────────────
# Each returns a flowable (a Table) that becomes one row of the outer
# invoice table.

def _build_header_band(invoice, st):
    """Row 1: centered title + e-Invoice label."""
    tbl = Table([[
        Paragraph('GST TAX INVOICE', st['title']),
        Paragraph('<i>(ORIGINAL FOR RECIPIENT)</i>', st['subtitle']),
        Paragraph('e-Invoice' if invoice.irn else '', st['einv']),
    ]], colWidths=[60 * mm, 80 * mm, 50 * mm])
    tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
    ]))
    return tbl


def _build_irn_strip(invoice, st):
    """Row 2 (conditional): IRN + Ack No + Ack Date in a single strip."""
    rows = [[
        Paragraph('IRN', st['label']),
        Paragraph(invoice.irn, st['value_small']),
        Paragraph('Ack No.', st['label']),
        Paragraph(invoice.ack_no or '', st['value_small']),
        Paragraph('Ack Date', st['label']),
        Paragraph(_fmt_date(invoice.ack_date), st['value_small']),
    ]]
    tbl = Table(rows, colWidths=[12 * mm, 78 * mm, 16 * mm, 30 * mm, 16 * mm, 38 * mm])
    tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        ('BACKGROUND',    (0, 0), (-1, -1), BG_TINT),
    ]))
    return tbl


def _build_seller_block(invoice, st):
    """Inside the left column of the main band — seller details."""
    bits = []
    bits.append(Paragraph(invoice.seller_name, st['name']))
    bits.append(Paragraph(invoice.seller_address.replace('\n', '<br/>'), st['body_small']))
    if invoice.seller_udyam:
        bits.append(Paragraph(f"UDYAM Reg no: <b>{invoice.seller_udyam}</b>", st['body_small']))
    bits.append(Paragraph(f"GSTIN/UIN: <b>{invoice.seller_gstin}</b>", st['body_small']))
    bits.append(Paragraph(
        f"State Name: <b>{invoice.seller_state}</b>, Code: <b>{invoice.seller_state_code}</b>",
        st['body_small'],
    ))
    if invoice.seller_email:
        bits.append(Paragraph(f"E-Mail: {invoice.seller_email}", st['body_small']))
    return bits


def _build_party_block(label, name, address, gstin, state, state_code, st,
                       pan=None):
    """Consignee or Buyer block. Label small + muted, name bold, address
    smaller. Used twice per invoice. PAN is printed under GSTIN when
    present — primarily for B2C customers (who don't carry a GSTIN)
    but works for B2B too when both are filled."""
    out = [Paragraph(f"<b>{label}</b>", st['body_muted']),
           Paragraph(name or '—', st['value'])]
    if address:
        out.append(Paragraph(address.replace('\n', '<br/>'), st['body_small']))
    if gstin:
        out.append(Paragraph(f"GSTIN/UIN: <b>{gstin}</b>", st['body_small']))
    if pan:
        out.append(Paragraph(f"PAN: <b>{pan}</b>", st['body_small']))
    if state:
        sc_suffix = f', Code: <b>{state_code}</b>' if state_code else ''
        out.append(Paragraph(f"State Name: <b>{state}</b>{sc_suffix}", st['body_small']))
    return out


def _build_metadata_grid(invoice, st):
    """Right column of the main band — invoice metadata key/value pairs.

    Uses an internal 4-col layout (label · value · label · value) so the
    grid feels denser like the reference. Empty rows are omitted.
    """
    pairs = [
        ('Invoice No.',            invoice.invoice_number,       'e-Way Bill No.',      invoice.ewaybill_no or ''),
        ('Dated',                  _fmt_date(invoice.invoice_date), 'Mode/Terms of Payment', invoice.mode_of_payment or ''),
        ('Delivery Note',          invoice.delivery_note or '',  'Other References',    invoice.other_references or ''),
        ("Buyer's Order No.",      invoice.buyers_order_no or '', "Dated",              _fmt_date(invoice.buyers_order_date)),
        ('Dispatch Doc No.',       invoice.dispatch_doc_no or '', 'Delivery Note Date', _fmt_date(invoice.delivery_note_date)),
        ('Dispatched through',     invoice.dispatched_through or '', 'Destination',     invoice.destination or ''),
        ('Bill of Lading/LR-RR',   invoice.bill_of_lading or '',  'Bill of Lading Date', _fmt_date(invoice.bill_of_lading_date)),
        ('Motor Vehicle No.',      invoice.motor_vehicle_no or '', 'Terms of Delivery', invoice.terms_of_delivery or ''),
    ]
    rows = []
    for l1, v1, l2, v2 in pairs:
        # Skip a row when BOTH halves are empty
        if not (v1 or v2):
            continue
        rows.append([
            Paragraph(l1, st['label']),
            Paragraph(str(v1) if v1 else '—', st['value_small']),
            Paragraph(l2, st['label']),
            Paragraph(str(v2) if v2 else '—', st['value_small']),
        ])
    if not rows:
        rows = [[Paragraph('—', st['label']), '', '', '']]
    # Sum = 90mm to exactly match the outer band's right-column width.
    # Previously totalled 100mm (the cause of "EX OUR SITE" + the right
    # border bleeding past the page edge).
    tbl = Table(rows, colWidths=[20 * mm, 25 * mm, 20 * mm, 25 * mm])
    tbl.setStyle(TableStyle([
        ('VALIGN',         (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW',      (0, 0), (-1, -2), 0.3, LINE_LIGHT),
        ('LINEAFTER',      (1, 0), (1, -1), 0.3, LINE_LIGHT),
        ('TOPPADDING',     (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING',    (0, 0), (-1, -1), 3),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 3),
    ]))
    return tbl


def _build_parties_metadata_band(invoice, st):
    """Row 3: the big LEFT/RIGHT band. Left = seller/consignee/buyer
    stack; right = metadata grid."""
    # Left column — stack of three sub-tables so we get internal
    # dividers between seller / consignee / buyer.
    left_inner = Table([
        [_build_seller_block(invoice, st)],
        [_build_party_block('Consignee (Ship to)',
                            invoice.consignee_name, invoice.consignee_address,
                            invoice.consignee_gstin, invoice.consignee_state,
                            invoice.consignee_state_code, st)],
        [_build_party_block('Buyer (Bill to)',
                            invoice.buyer_name, invoice.buyer_address,
                            invoice.buyer_gstin, invoice.buyer_state,
                            invoice.buyer_state_code, st,
                            pan=invoice.buyer_pan)],
    ], colWidths=[100 * mm])
    left_inner.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW',     (0, 0), (-1, -2), 0.4, LINE_LIGHT),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
    ]))

    band = Table([[left_inner, _build_metadata_grid(invoice, st)]],
                 colWidths=[100 * mm, 90 * mm])
    band.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('LINEAFTER',    (0, 0), (0, -1), 0.4, LINE_INK),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
    ]))
    return band


def _build_items_table(invoice, st):
    """Row 4: line items + GST + round-off + Total — all in one bordered
    table so the column dividers run continuously top-to-bottom."""
    items = list(invoice.items or [])
    inter = invoice.is_inter_state

    rows = [[
        Paragraph('<b>Sl<br/>No.</b>',       st['label']),
        Paragraph('<b>Description of Goods / Service</b>', st['label']),
        Paragraph('<b>HSN/SAC</b>',          st['label']),
        Paragraph('<b>Quantity</b>',         st['label']),
        Paragraph('<b>Rate</b>',             st['label']),
        Paragraph('<b>per</b>',              st['label']),
        Paragraph('<b>Amount</b>',           st['label']),
    ]]

    # Product rows
    for i, it in enumerate(items, start=1):
        qty_str = f'{float(it.quantity):g} {it.unit}' if it.quantity else ''
        rows.append([
            Paragraph(str(i), st['body']),
            Paragraph(it.description, st['body']),
            Paragraph(it.hsn_code or '', st['body']),
            Paragraph(qty_str, st['right']),
            Paragraph(_money(it.rate), st['right']),
            Paragraph(it.unit or '', st['body']),
            Paragraph(_money(it.amount), st['right']),
        ])

    # GST + round-off rows (right-aligned amount, label spans description col)
    def _meta_row(label, amount):
        return [
            '',
            Paragraph(f'<i>{label}</i>', st['body']),
            '', '', '', '',
            Paragraph(_money(amount), st['right']),
        ]
    if inter:
        rows.append(_meta_row('IGST 18%', invoice.igst))
    else:
        rows.append(_meta_row('CGST 9%', invoice.cgst))
        rows.append(_meta_row('SGST 9%', invoice.sgst))
    if float(invoice.round_off or 0) != 0:
        rows.append(_meta_row('Less: Round Off', invoice.round_off))

    # Total row (bolder)
    total_qty = sum(float(it.quantity or 0) for it in items)
    rows.append([
        '',
        Paragraph('<b>Total</b>', st['body']),
        '',
        Paragraph(f'<b>{total_qty:g}</b>', st['right']),
        '',
        '',
        Paragraph(f'{RUPEE_GLYPH} {_money(invoice.total)}', st['total_money']),
    ])

    # LongTable supports auto-pagination — a plain Table can't split across
    # pages when wrapped in another flowable. Invoices with many line items
    # (we've seen 80+) used to throw `LayoutError: Flowable too large`
    # because the outer-box Table held this one as a single un-splittable
    # cell. Caller now appends this directly to the story (not nested), so
    # LongTable's row-by-row split kicks in.
    tbl = LongTable(rows,
                    colWidths=[10 * mm, 70 * mm, 22 * mm, 25 * mm, 22 * mm, 12 * mm, 29 * mm],
                    repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), BG_TINT),
        ('LINEBELOW',     (0, 0), (-1, 0), 0.5, LINE_INK),
        ('LINEBELOW',     (0, -2), (-1, -2), 0.4, LINE_INK),  # above Total
        ('LINEAFTER',     (0, 0), (-2, -1), 0.3, LINE_LIGHT), # column dividers
        ('BOX',           (0, 0), (-1, -1), 0.7, LINE_INK),   # outer border (no longer wrapped)
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    return tbl


def _build_words_strip(invoice, st):
    """Row 5: amount-in-words + 'E. & O.E' on the right."""
    rows = [
        [Paragraph('Amount Chargeable (in words)', st['label']),
         Paragraph('<i>E. &amp; O.E</i>', st['right'])],
        [Paragraph(f'<b>{invoice.amount_in_words or ""}</b>', st['value']), ''],
    ]
    tbl = Table(rows, colWidths=[155 * mm, 35 * mm])
    tbl.setStyle(TableStyle([
        ('SPAN',          (0, 1), (1, 1)),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
    ]))
    return tbl


def _build_hsn_summary(invoice, st):
    """Row 6: HSN-wise tax summary table."""
    inter = invoice.is_inter_state
    # Aggregate items by HSN
    agg = {}
    for it in invoice.items:
        hsn = it.hsn_code or '—'
        agg.setdefault(hsn, 0.0)
        agg[hsn] += float(it.amount or 0)
    if not agg:
        return None

    if inter:
        rows = [[
            Paragraph('<b>HSN/SAC</b>',         st['label']),
            Paragraph('<b>Taxable Value</b>',   st['label']),
            Paragraph('<b>IGST Rate</b>',       st['label']),
            Paragraph('<b>IGST Amount</b>',     st['label']),
            Paragraph('<b>Total Tax Amount</b>', st['label']),
        ]]
        sum_taxable = 0.0
        sum_tax = 0.0
        for hsn, taxable in sorted(agg.items()):
            igst_amt = round(taxable * 18.0 / 100, 2)
            rows.append([
                Paragraph(hsn, st['body']),
                Paragraph(_money(taxable), st['right']),
                Paragraph('18%', st['right']),
                Paragraph(_money(igst_amt), st['right']),
                Paragraph(_money(igst_amt), st['right']),
            ])
            sum_taxable += taxable
            sum_tax += igst_amt
        rows.append([
            Paragraph('<b>Total</b>', st['body']),
            Paragraph(f'<b>{_money(sum_taxable)}</b>', st['right_bold']),
            '',
            Paragraph(f'<b>{_money(sum_tax)}</b>', st['right_bold']),
            Paragraph(f'<b>{_money(sum_tax)}</b>', st['right_bold']),
        ])
        col_widths = [30 * mm, 50 * mm, 25 * mm, 40 * mm, 45 * mm]
    else:
        rows = [[
            Paragraph('<b>HSN/SAC</b>',       st['label']),
            Paragraph('<b>Taxable Value</b>', st['label']),
            Paragraph('<b>CGST Rate</b>',     st['label']),
            Paragraph('<b>CGST Amount</b>',   st['label']),
            Paragraph('<b>SGST Rate</b>',     st['label']),
            Paragraph('<b>SGST Amount</b>',   st['label']),
            Paragraph('<b>Total Tax</b>',     st['label']),
        ]]
        sum_taxable = 0.0
        sum_cgst = 0.0
        sum_sgst = 0.0
        for hsn, taxable in sorted(agg.items()):
            cgst_amt = round(taxable * 9.0 / 100, 2)
            sgst_amt = cgst_amt
            rows.append([
                Paragraph(hsn, st['body']),
                Paragraph(_money(taxable), st['right']),
                Paragraph('9%', st['right']),
                Paragraph(_money(cgst_amt), st['right']),
                Paragraph('9%', st['right']),
                Paragraph(_money(sgst_amt), st['right']),
                Paragraph(_money(cgst_amt + sgst_amt), st['right']),
            ])
            sum_taxable += taxable
            sum_cgst += cgst_amt
            sum_sgst += sgst_amt
        rows.append([
            Paragraph('<b>Total</b>', st['body']),
            Paragraph(f'<b>{_money(sum_taxable)}</b>', st['right_bold']),
            '',
            Paragraph(f'<b>{_money(sum_cgst)}</b>', st['right_bold']),
            '',
            Paragraph(f'<b>{_money(sum_sgst)}</b>', st['right_bold']),
            Paragraph(f'<b>{_money(sum_cgst + sum_sgst)}</b>', st['right_bold']),
        ])
        col_widths = [22 * mm, 30 * mm, 18 * mm, 30 * mm, 18 * mm, 30 * mm, 42 * mm]

    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, 0), BG_TINT),
        ('LINEBELOW',      (0, 0), (-1, 0), 0.4, LINE_INK),
        ('LINEABOVE',      (0, -1), (-1, -1), 0.4, LINE_INK),
        ('LINEAFTER',      (0, 0), (-2, -1), 0.3, LINE_LIGHT),
        ('VALIGN',         (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',     (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 3),
        ('LEFTPADDING',    (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 4),
    ]))
    return tbl


def _build_tax_words_strip(invoice, st):
    """Row 7: tax amount in words."""
    inter = invoice.is_inter_state
    tax_total = float(invoice.igst or 0) if inter else (float(invoice.cgst or 0) + float(invoice.sgst or 0))
    try:
        from app import _amount_in_words_inr
        words = _amount_in_words_inr(tax_total)
    except Exception:
        words = ''
    tbl = Table([[
        Paragraph(f'<b>Tax Amount (in words):</b> {words}', st['body']),
    ]], colWidths=[190 * mm])
    tbl.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
    ]))
    return tbl


def _build_bottom_triptych(invoice, st):
    """Row 8: 3-col footer band — PAN+Declaration | Bank details | Authorised signatory."""
    # Left — PAN + declaration
    left = []
    if invoice.seller_pan:
        left.append(Paragraph(f"Company's PAN : <b>{invoice.seller_pan}</b>", st['body']))
    left.append(Paragraph('<b>Declaration</b>', ParagraphStyle(
        'decl_h', parent=st['body_muted'], spaceBefore=4)))
    if invoice.declaration:
        left.append(Paragraph(invoice.declaration, st['body_small']))

    # Middle — Bank details (label / value pairs in a sub-table)
    bank_label = ParagraphStyle('bk_lbl', parent=st['label'], fontSize=8)
    bank_value = ParagraphStyle('bk_val', parent=st['value_small'], fontSize=8.5)
    bank_rows = [[Paragraph("<b>Company's Bank Details</b>", st['body_muted']), '']]
    if invoice.bank_account_name:
        bank_rows.append([Paragraph("A/c Holder's Name", bank_label),
                          Paragraph(invoice.bank_account_name, bank_value)])
    if invoice.bank_name:
        bank_rows.append([Paragraph('Bank Name', bank_label),
                          Paragraph(invoice.bank_name, bank_value)])
    if invoice.bank_account_no:
        bank_rows.append([Paragraph('A/c No.', bank_label),
                          Paragraph(invoice.bank_account_no, bank_value)])
    if invoice.bank_ifsc:
        branch_ifsc = f"{invoice.bank_branch} &amp; {invoice.bank_ifsc}" if invoice.bank_branch else invoice.bank_ifsc
        bank_rows.append([Paragraph('Branch &amp; IFS Code', bank_label),
                          Paragraph(branch_ifsc, bank_value)])
    if invoice.upi_id:
        bank_rows.append([Paragraph('UPI ID', bank_label),
                          Paragraph(invoice.upi_id, bank_value)])
    middle = Table(bank_rows, colWidths=[24 * mm, 50 * mm])
    middle.setStyle(TableStyle([
        ('SPAN',          (0, 0), (1, 0)),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))

    # Right — Authorised signatory area
    right = [
        Paragraph(f"for <b>{invoice.seller_name}</b>",
                  ParagraphStyle('sig_co', parent=st['body_small'],
                                  alignment=TA_RIGHT, fontSize=8)),
        Spacer(1, 22),
        Paragraph('<b>Authorised Signatory</b>',
                  ParagraphStyle('sig_label', parent=st['body_small'],
                                  alignment=TA_RIGHT, fontSize=8.5,
                                  textColor=INK_DARK)),
    ]

    band = Table([[left, middle, right]],
                 colWidths=[62 * mm, 82 * mm, 46 * mm])
    band.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('LINEAFTER',    (0, 0), (0, -1), 0.4, LINE_INK),
        ('LINEAFTER',    (1, 0), (1, -1), 0.4, LINE_INK),
        ('LEFTPADDING',  (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING',   (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
    ]))
    return band


# ─── Main entry ─────────────────────────────────────────────────────────────

def generate_tax_invoice_pdf(invoice):
    """Render a GST tax-invoice PDF. Returns bytes.

    Composes the page from section builders, wrapped in a single outer
    Table so the entire invoice gets a continuous border with internal
    dividers — matches the reference layout's look.
    """
    # Register the Unicode font with ₹ support before building styles.
    # No-op on subsequent calls; falls back to Helvetica-Bold + "Rs."
    # if DejaVu isn't installed (graceful degradation).
    _register_rupee_font_once()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
        title=f'Tax Invoice {invoice.invoice_number}',
    )
    st = _para_styles()
    story = []

    # Layout split into THREE independent flowables so a long line-items
    # table can paginate naturally:
    #
    #   1) Top box     — header + IRN + parties/metadata band
    #   2) Items table — standalone LongTable (auto-splits across pages,
    #                    header row repeats — see _build_items_table)
    #   3) Bottom box  — amount-in-words + HSN summary + tax words + triptych
    #
    # Earlier this all sat inside ONE outer Table; that threw `LayoutError:
    # Flowable too large` once an invoice grew past one page because Tables
    # can't split mid-row. Splitting into three Tables loses the continuous
    # outer border, but it's the cleanest way to support invoices of any
    # length without per-line PDF babysitting.
    top_rows = [[_build_header_band(invoice, st)]]
    if invoice.irn:
        top_rows.append([_build_irn_strip(invoice, st)])
    top_rows.append([_build_parties_metadata_band(invoice, st)])

    top_box = Table(top_rows, colWidths=[PAGE_BODY_WIDTH_MM * mm])
    top_box.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 0.7, LINE_INK),
        ('LINEBELOW',     (0, 0), (-1, -2), 0.45, LINE_INK),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    bottom_rows = []
    if invoice.amount_in_words:
        bottom_rows.append([_build_words_strip(invoice, st)])
    hsn = _build_hsn_summary(invoice, st)
    if hsn is not None:
        bottom_rows.append([hsn])
    bottom_rows.append([_build_tax_words_strip(invoice, st)])
    bottom_rows.append([_build_bottom_triptych(invoice, st)])

    bottom_box = Table(bottom_rows, colWidths=[PAGE_BODY_WIDTH_MM * mm])
    bottom_box.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 0.7, LINE_INK),
        ('LINEBELOW',     (0, 0), (-1, -2), 0.45, LINE_INK),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    story.append(top_box)
    story.append(_build_items_table(invoice, st))
    story.append(bottom_box)

    # Footer text — small + centred + outside the bordered box
    story.append(Spacer(1, 4))
    story.append(Paragraph('SUBJECT TO BENGALURU JURISDICTION', st['center_foot']))
    story.append(Paragraph('This is a Computer Generated Invoice', st['center_foot']))

    doc.build(story)
    out = buf.getvalue()
    buf.close()
    return out
