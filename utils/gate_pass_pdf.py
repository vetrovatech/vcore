"""PDF generator for Vetrova gate passes / packing slips.

Mirrors the structure of the Arihant Safe Glass packing slip used as
the reference document:

  ┌──────────────────────────────────────────────────────────────┐
  │ [Logo]    VETROVA TECH SERVICES PRIVATE LIMITED              │
  │            GATE PASS / PACKING SLIP   Printed On: <date>     │
  ├──────────────────────────────────────────────────────────────┤
  │ Customer Name: ____    Invoice No: ____  Vehicle No: ____    │
  │ Invoice Date:  ____    Transporter: ____                     │
  ├──────────────────────────────────────────────────────────────┤
  │ GP No: VTS/GP/2627/0001                                      │
  │ ┌─────┬─────────┬───────┬───────┬───┬─┬─┬──┬──┬───┬──────┐  │
  │ │ S No│Work Ord │ W(mm) │ H(mm) │…  │H│C│SP│BH│CSK│Sq.Mt │  │
  │ │     │         │       │       │   │ │ │  │  │   │      │  │
  │ └─────┴─────────┴───────┴───────┴───┴─┴─┴──┴──┴───┴──────┘  │
  ├──────────────────────────────────────────────────────────────┤
  │ Total : N items   Qty: N           Total Sq.Mt: NNN.NNN      │
  │                                                              │
  │ Signature of Authority           Signature of Driver         │
  └──────────────────────────────────────────────────────────────┘

A4 portrait. Auto-paginates the line items table (Arihant ran to
page 2). Section headers (e.g. "6MM ST-136 Heat Strengthened Glass")
are emitted whenever a row's material_spec differs from the prior
row's — same visual cue used by Arihant to group lines by glass type.
"""

import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)

# Reuse the rupee font registration from tax_invoice_pdf — keeps
# DejaVu loading in one place even though we don't print ₹ here.
try:
    from utils.tax_invoice_pdf import _register_rupee_font_once
except ImportError:
    def _register_rupee_font_once():
        pass


PAGE_W, PAGE_H = A4
MARGIN_L = MARGIN_R = 10 * mm
MARGIN_T = MARGIN_B = 10 * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R


def _fmt_date(d):
    if not d:
        return ''
    return d.strftime('%d-%m-%Y')


def _fmt_mm(v):
    if v is None:
        return ''
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ''
    if f <= 0:
        return ''
    # whole if integer-ish
    if abs(f - round(f)) < 0.005:
        return str(int(round(f)))
    return f'{f:g}'


def _fmt_qty(v):
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return '0'
    if abs(f - round(f)) < 0.005:
        return str(int(round(f)))
    return f'{f:g}'


def _build_header(gp, styles):
    """Top header band — company name + GATE PASS title + printed-on."""
    title_style = ParagraphStyle(
        'GPTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=13, alignment=TA_CENTER,
        textColor=colors.HexColor('#0b3d2e'),
    )
    sub_style = ParagraphStyle(
        'GPSubtitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=11, alignment=TA_CENTER,
    )
    small_right = ParagraphStyle(
        'GPSmallRight', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, alignment=TA_RIGHT,
        textColor=colors.HexColor('#444'),
    )

    from datetime import datetime
    printed_on = datetime.utcnow().strftime('%d-%m-%Y')

    title_cell = [
        Paragraph('VETROVA TECH SERVICES PRIVATE LIMITED', title_style),
        Spacer(1, 1*mm),
        Paragraph('<b>GATE PASS / PACKING SLIP</b>', sub_style),
    ]
    right_cell = [
        Paragraph(f'Printed On:<br/><b>{printed_on}</b>', small_right),
    ]
    tbl = Table([[title_cell, right_cell]],
                colWidths=[CONTENT_W * 0.78, CONTENT_W * 0.22])
    tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return tbl


def _build_customer_block(gp, styles):
    """Customer + Invoice + Vehicle + Transporter — mirrors the Arihant
    top-left block. Two columns of label/value pairs."""
    lbl = ParagraphStyle('Lbl', parent=styles['Normal'],
                          fontName='Helvetica', fontSize=8,
                          textColor=colors.HexColor('#555'))
    val = ParagraphStyle('Val', parent=styles['Normal'],
                          fontName='Helvetica-Bold', fontSize=9)

    inv_no = gp.ref_invoice_no or ''
    inv_dt = _fmt_date(gp.ref_invoice_date)

    def cell(label, value):
        return [
            Paragraph(label, lbl),
            Paragraph(value or '&nbsp;', val),
        ]

    rows = [
        [cell('Customer Name', gp.customer_name or ''),
         cell('Vehicle No', gp.vehicle_no or '')],
        [cell('Invoice No', inv_no),
         cell('Transporter', gp.transporter_name or '')],
        [cell('Invoice Date', inv_dt),
         cell('Driver', f"{gp.driver_name or ''}"
                       f"{(' • ' + gp.driver_phone) if gp.driver_phone else ''}")],
        [cell('GP No', gp.gp_number),
         cell('GP Date', _fmt_date(gp.gp_date))],
    ]
    base_tbl = Table(rows, colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])
    base_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#888')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))

    flow = [base_tbl]

    extras = []
    if gp.delivery_address:
        extras.append([Paragraph('<b>Delivery Address:</b> '
                                  + gp.delivery_address.replace('\n', ' / '), val)])
    if gp.lr_number or gp.eway_bill_no:
        bits = []
        if gp.lr_number: bits.append(f'LR: <b>{gp.lr_number}</b>')
        if gp.eway_bill_no: bits.append(f'e-Way Bill: <b>{gp.eway_bill_no}</b>')
        extras.append([Paragraph(' &nbsp; '.join(bits), val)])

    if extras:
        extra_tbl = Table(extras, colWidths=[CONTENT_W])
        extra_tbl.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        flow.append(extra_tbl)

    return flow


def _build_items_table(gp, styles):
    """Godown-friendly 4-column loading checklist.

    Layout:
        S No · Description · Qty · ✓ Loaded
                                    └─ empty box, loader hand-ticks on the truck
        ─────────────────────────────────
        TOTAL ITEMS LEAVING GODOWN: N
        ─────────────────────────────────

    The view/form intentionally hide the per-line reconciliation columns
    (qty_ordered / qty_dispatched_before) — those are office concerns,
    not what the godown person needs at loading time. They still live
    in the schema and are preserved on every save, so the office can
    surface them via a different report later.
    """
    # Cols: S | Description | W (mm) | H (mm) | Qty | ✓ Loaded
    col_widths_mm = [10, 92, 24, 24, 18, 22]
    col_widths = [w*mm for w in col_widths_mm]
    assert abs(sum(col_widths) - CONTENT_W) < 1, \
        f'col width sum {sum(col_widths)/mm:.1f}mm != content {CONTENT_W/mm:.1f}mm'

    header_style = ParagraphStyle('TblHdr', parent=styles['Normal'],
                                   fontName='Helvetica-Bold', fontSize=9.5,
                                   alignment=TA_CENTER, leading=12)
    cell_style = ParagraphStyle('TblCell', parent=styles['Normal'],
                                 fontName='Helvetica', fontSize=9,
                                 alignment=TA_LEFT, leading=12)
    cell_center = ParagraphStyle('TblCellC', parent=cell_style, alignment=TA_CENTER)
    cell_right = ParagraphStyle('TblCellR', parent=cell_style, alignment=TA_RIGHT)

    header_row = [
        Paragraph('S No', header_style),
        Paragraph('Description', header_style),
        Paragraph('Width<br/>(mm)', header_style),
        Paragraph('Height<br/>(mm)', header_style),
        Paragraph('Qty', header_style),
        Paragraph('Loaded ✓', header_style),
    ]
    data = [header_row]
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef4f0')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#444')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]

    sl = 0
    total_qty = 0.0

    for it in gp.items:
        sl += 1
        qty_now = float(it.qty_this_pass or 0)
        total_qty += qty_now
        w_mm = float(it.width_mm) if it.width_mm else 0
        h_mm = float(it.height_mm) if it.height_mm else 0
        data.append([
            Paragraph(str(sl), cell_center),
            Paragraph((it.material_spec or '—'), cell_style),
            Paragraph(f'{w_mm:g}' if w_mm else '—', cell_right),
            Paragraph(f'{h_mm:g}' if h_mm else '—', cell_right),
            Paragraph(f'<b>{_fmt_qty(qty_now)}</b>', cell_right),
            # Empty cell — the godown person hand-ticks here as they load
            Paragraph('', cell_center),
        ])

    # Big bold TOTAL footer row (godown person + security gate sees this)
    total_row_idx = len(data)
    total_style = ParagraphStyle('GdTotal', parent=styles['Normal'],
                                  fontName='Helvetica-Bold', fontSize=11,
                                  alignment=TA_RIGHT, leading=14,
                                  textColor=colors.HexColor('#0b3d2e'))
    total_qty_style = ParagraphStyle('GdTotalQty', parent=styles['Normal'],
                                      fontName='Helvetica-Bold', fontSize=13,
                                      alignment=TA_RIGHT, leading=15,
                                      textColor=colors.HexColor('#0b3d2e'))
    data.append([
        Paragraph('TOTAL ITEMS LEAVING GODOWN', total_style),
        '', '', '',
        Paragraph(f'<b>{_fmt_qty(total_qty)}</b>', total_qty_style),
        Paragraph('', cell_center),
    ])
    style_cmds.append(('SPAN', (0, total_row_idx), (3, total_row_idx)))
    style_cmds.append(('BACKGROUND', (0, total_row_idx), (-1, total_row_idx),
                       colors.HexColor('#d6efdf')))
    style_cmds.append(('LINEABOVE', (0, total_row_idx), (-1, total_row_idx),
                       1.0, colors.black))
    style_cmds.append(('TOPPADDING', (0, total_row_idx), (-1, total_row_idx), 8))
    style_cmds.append(('BOTTOMPADDING', (0, total_row_idx), (-1, total_row_idx), 8))

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _build_signature_strip(gp, styles):
    sig_style = ParagraphStyle('Sig', parent=styles['Normal'],
                                fontName='Helvetica', fontSize=8,
                                alignment=TA_CENTER, leading=10)
    rows = [
        ['', ''],
        [Paragraph('________________________<br/>Signature of Authority', sig_style),
         Paragraph('________________________<br/>Signature of Driver', sig_style)],
    ]
    tbl = Table(rows, colWidths=[CONTENT_W/2, CONTENT_W/2], rowHeights=[12*mm, 14*mm])
    tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return tbl


def _build_footer_strip(gp, styles):
    foot = ParagraphStyle('Foot', parent=styles['Normal'],
                          fontName='Helvetica-Oblique', fontSize=7,
                          alignment=TA_CENTER, textColor=colors.HexColor('#666'))
    return Paragraph(
        'This is a computer-generated dispatch document. '
        'Subject to verification at site.', foot)


def generate_gate_pass_pdf(gp):
    """Render a GatePass to PDF bytes."""
    _register_rupee_font_once()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title=f'Gate Pass {gp.gp_number}',
    )
    styles = getSampleStyleSheet()

    story = []
    story.append(_build_header(gp, styles))
    story.append(Spacer(1, 2*mm))
    for el in _build_customer_block(gp, styles):
        story.append(el)
    story.append(Spacer(1, 2*mm))
    story.append(_build_items_table(gp, styles))
    story.append(Spacer(1, 3*mm))
    story.append(_build_signature_strip(gp, styles))
    story.append(Spacer(1, 1*mm))
    story.append(_build_footer_strip(gp, styles))

    doc.build(story)
    return buf.getvalue()
