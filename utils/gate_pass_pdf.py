"""PDF generator for Vetrova gate passes / packing slips.

Cloned 1:1 from the Arihant Safe Glass "PACKING SLIP" reference the
BD supplied (PI No 14852, 2026-07-17). Every element in the reference
document has a counterpart here:

  ┌────────────────────────────────────────────────────────────────┐
  │ [Company block]         ┌──────────────┐        Printed On:    │
  │                         │ PACKING SLIP │        <date>         │
  │                         └──────────────┘                       │
  ├────────────────────────────────────────────────────────────────┤
  │ Customer Name : <name>                                         │
  │ Invoice No    : <inv>              Vehicle No  : <veh>         │
  │ Invoice Date  : <dt>               Transporter : <tp>          │
  ├────────────────────────────────────────────────────────────────┤
  │                    PI No : <pi_no>  (centered strip)           │
  │ ┌────┬────┬────────┬─────────┬─────────┬───┬─┬─┬──┬──┬───┬────┐│
  │ │ S  │Prd │ Work   │ ACT(MM) │ ACT(IN) │Qty│H│C│SP│BH│CSK│Sq. ││
  │ │ No │ No │ Order  │  W  H   │  W  H   │   │ │ │  │  │   │Mt  ││
  │ │    │    │ No     │         │         │   │ │ │  │  │   │    ││
  │ ├────┴────┴────────┴─────────┴─────────┴───┴─┴─┴──┴──┴───┴────┤│
  │ │ 6MM ST-136 HEAT STRENGTHED GLASS  (group span)              ││
  │ ├─┬──┬──────────┬────┬─────┬────┬──────┬─┬─┬─┬──┬──┬───┬─────┤│
  │ │1│ 1│ AWO-12307│ 990│ 1280│ 39 │50 3/8│2│ │ │  │  │   │2.672││
  │ └─┴──┴──────────┴────┴─────┴────┴──────┴─┴─┴─┴──┴──┴───┴─────┘│
  │                          Total : N        NN.NNN               │
  │                                                                │
  │            Qty : N               Total Sqmt : NN.NNN           │
  │                                                                │
  │ Signature of Authority                    Signature of Driver  │
  │ ── Powered by vcore ──                                         │
  └────────────────────────────────────────────────────────────────┘

A4 portrait. Auto-paginates the line items table. Section headers
(e.g. "6MM ST-136 Heat Strengthened Glass") are emitted whenever a
row's `material_spec` differs from the prior row's — same visual cue
Arihant uses to group by glass type.
"""

import os
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
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


# ─── formatters ──────────────────────────────────────────────────────

def _fmt_date(d):
    if not d:
        return ''
    return d.strftime('%d-%m-%Y')


def _fmt_mm(v):
    """Whole-number rendering of a millimetre value (e.g. 990). Blank on 0."""
    if v is None:
        return ''
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ''
    if f <= 0:
        return ''
    if abs(f - round(f)) < 0.005:
        return str(int(round(f)))
    return f'{f:g}'


def _fmt_in(v):
    """Inch display — pass through whatever the source stored (e.g. '50 3/8').
    Falls back to a decimal conversion from a numeric value when a fraction
    string wasn't captured upstream."""
    if v is None or v == '':
        return ''
    try:
        s = str(v).strip()
    except Exception:
        return ''
    return s


def _fmt_qty(v):
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return '0'
    if abs(f - round(f)) < 0.005:
        return str(int(round(f)))
    return f'{f:g}'


def _fmt_sqm(v):
    """3-decimal Sq.Mt display, matching Arihant's `2.672`, `26.434` style."""
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return '0.000'
    return f'{f:.3f}'


def _flag(v):
    """One-char cell for the H/C/SP/BH/CSK columns — 'Y' when true, blank."""
    return 'Y' if v else ''


# ─── header ──────────────────────────────────────────────────────────

def _build_header(gp, styles):
    """Top header band — company block on the left, boxed PACKING SLIP
    title in the centre, "Printed On:" strip on the right. Mirrors the
    Arihant top band 1:1."""
    company_name = ParagraphStyle(
        'CoName', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=14, alignment=TA_LEFT,
        textColor=colors.HexColor('#B4272C'),  # deep red like Arihant
        leading=16,
    )
    company_sub = ParagraphStyle(
        'CoSub', parent=styles['Normal'],
        fontName='Helvetica', fontSize=7, alignment=TA_LEFT,
        textColor=colors.HexColor('#555'), leading=9,
    )
    title_style = ParagraphStyle(
        'PSTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=16, alignment=TA_CENTER,
        leading=20,
    )
    right_lbl = ParagraphStyle(
        'RLbl', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, alignment=TA_RIGHT,
        textColor=colors.HexColor('#555'), leading=10,
    )
    right_val = ParagraphStyle(
        'RVal', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9, alignment=TA_RIGHT,
        leading=11,
    )

    printed_on = datetime.utcnow().strftime('%d-%m-%Y')

    left_cell = [
        Paragraph('VETROVA TECH SERVICES PVT LTD', company_name),
        Paragraph('Annealed / Toughened Glass · Bengaluru', company_sub),
    ]

    # The "PACKING SLIP" title sits inside its own thin-bordered inner
    # table so the box hugs the words instead of the whole cell.
    title_box = Table([[Paragraph('GATE PASS', title_style)]],
                      colWidths=[54 * mm], rowHeights=[13 * mm])
    title_box.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.2, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))

    right_cell = [
        Paragraph('Printed On:', right_lbl),
        Paragraph(printed_on, right_val),
    ]

    outer = Table(
        [[left_cell, title_box, right_cell]],
        colWidths=[CONTENT_W * 0.42, CONTENT_W * 0.36, CONTENT_W * 0.22],
    )
    outer.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 1.0, colors.black),
    ]))
    return outer


# ─── customer / logistics strip ──────────────────────────────────────

def _build_customer_block(gp, styles):
    """Customer + Invoice + Vehicle + Transporter — plain-text visual
    mirror of the Arihant top-left block (no borders around individual
    cells; single outer rule below the strip)."""
    lbl = ParagraphStyle(
        'CLbl', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.5, alignment=TA_LEFT,
        textColor=colors.HexColor('#333'), leading=11,
    )
    val = ParagraphStyle(
        'CVal', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9.5, alignment=TA_LEFT,
        leading=12,
    )

    inv_no = gp.ref_invoice_no or ''
    inv_dt = _fmt_date(gp.ref_invoice_date)

    def kv(label, value):
        return Paragraph(
            f'<font color="#555">{label} :</font>&nbsp;&nbsp;<b>{value or "—"}</b>',
            val,
        )

    # Row 1: full-width Customer Name
    row1 = Table([[kv('Customer Name', gp.customer_name or '')]],
                 colWidths=[CONTENT_W])
    # Row 2 & 3: two columns
    row23 = Table(
        [
            [kv('Invoice No', inv_no),         kv('Vehicle No',  gp.vehicle_no or '')],
            [kv('Invoice Date', inv_dt),       kv('Transporter', gp.transporter_name or '')],
        ],
        colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45],
    )
    style = TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ])
    row1.setStyle(style)
    row23.setStyle(style)

    flow = [row1, row23]

    # Second-row extras — surfaced only if BD populated them. Reference
    # doesn't show LR / e-Way / driver, but we keep them for compliance.
    extras_bits = []
    if gp.driver_name or gp.driver_phone:
        who = gp.driver_name or ''
        if gp.driver_phone:
            who = f'{who} • {gp.driver_phone}' if who else gp.driver_phone
        extras_bits.append(('Driver', who))
    if gp.lr_number:
        extras_bits.append(('LR No', gp.lr_number))
    if gp.eway_bill_no:
        extras_bits.append(('e-Way Bill', gp.eway_bill_no))
    if gp.delivery_address:
        extras_bits.append(('Delivery', gp.delivery_address.replace('\n', ' / ')))
    if extras_bits:
        # Pack into 2-col rows so it flows naturally
        rows = []
        for i in range(0, len(extras_bits), 2):
            left  = kv(*extras_bits[i])
            right = kv(*extras_bits[i + 1]) if i + 1 < len(extras_bits) else Paragraph('', val)
            rows.append([left, right])
        extras_tbl = Table(rows, colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])
        extras_tbl.setStyle(style)
        flow.append(extras_tbl)

    # Bottom rule under the whole strip
    rule = Table([['']], colWidths=[CONTENT_W], rowHeights=[0.1])
    rule.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 0.7, colors.black),
    ]))
    flow.append(rule)

    return flow


# ─── items table ─────────────────────────────────────────────────────

# 15 physical columns:
#   0 S     6mm   ┐ under "S No" span
#   1 Prd   6mm   ┘
#   2 WO   26mm   Work Order No
#   3 Wmm  15mm   ┐ under "ACT(MM)" span
#   4 Hmm  15mm   ┘
#   5 Win  20mm   ┐ under "ACT(IN)" span
#   6 Hin  20mm   ┘
#   7 Qty  10mm
#   8 H     6mm
#   9 C     6mm
#  10 SP    6mm
#  11 BH    6mm
#  12 CSK   6mm
#  13 Sq.Mt 14mm
#  14 Remarks 28mm
COL_WIDTHS_MM = [6, 6, 26, 15, 15, 20, 20, 10, 6, 6, 6, 6, 6, 14, 28]


def _build_items_table(gp, styles):
    col_widths = [w * mm for w in COL_WIDTHS_MM]
    assert abs(sum(col_widths) - CONTENT_W) < 1, \
        f'col width sum {sum(col_widths)/mm:.1f}mm != content {CONTENT_W/mm:.1f}mm'
    NC = len(col_widths)

    # ── styles
    hdr = ParagraphStyle('TblHdr', parent=styles['Normal'],
                          fontName='Helvetica-Bold', fontSize=8,
                          alignment=TA_CENTER, leading=9.5)
    hdr_small = ParagraphStyle('TblHdrSm', parent=styles['Normal'],
                                fontName='Helvetica-Bold', fontSize=7,
                                alignment=TA_CENTER, leading=9)
    cell_l  = ParagraphStyle('TblCell', parent=styles['Normal'],
                              fontName='Helvetica', fontSize=8,
                              alignment=TA_LEFT, leading=10)
    cell_c  = ParagraphStyle('TblCellC', parent=cell_l, alignment=TA_CENTER)
    cell_r  = ParagraphStyle('TblCellR', parent=cell_l, alignment=TA_RIGHT)
    group_h = ParagraphStyle('GroupHdr', parent=styles['Normal'],
                              fontName='Helvetica-Bold', fontSize=9,
                              alignment=TA_LEFT, leading=11,
                              textColor=colors.HexColor('#0b3d2e'))
    pi_style = ParagraphStyle('PIStrip', parent=styles['Normal'],
                               fontName='Helvetica-Bold', fontSize=9.5,
                               alignment=TA_CENTER, leading=12)
    total_lbl = ParagraphStyle('TotLbl', parent=styles['Normal'],
                                fontName='Helvetica-Bold', fontSize=9,
                                alignment=TA_RIGHT, leading=11)
    total_val = ParagraphStyle('TotVal', parent=styles['Normal'],
                                fontName='Helvetica-Bold', fontSize=9,
                                alignment=TA_RIGHT, leading=11)

    data = []
    style_cmds = []
    row = 0

    # ── PI No strip (spans all columns)
    pi_no = gp.ref_invoice_no or gp.gp_number
    data.append([Paragraph(f'PI No : {pi_no}', pi_style)] + [''] * (NC - 1))
    style_cmds.append(('SPAN', (0, row), (NC - 1, row)))
    style_cmds.append(('BACKGROUND', (0, row), (NC - 1, row), colors.HexColor('#F0F0EA')))
    style_cmds.append(('TOPPADDING', (0, row), (-1, row), 4))
    style_cmds.append(('BOTTOMPADDING', (0, row), (-1, row), 4))
    row += 1

    # ── Column headers, two-row stacked layout matching Arihant.
    # Row A: super-headers  |  Row B: sub-headers
    #   S No spans (0-1) rowA; single-cell "S No" and "Prd No" in rowB.
    #   Work Order No spans rowA+B as one tall cell.
    #   ACT(MM) spans (3-4) rowA; "Width"/"Height" in rowB.
    #   ACT(IN) spans (5-6) rowA; "Width"/"Height" in rowB.
    #   Qty / H / C / SP / BH / CSK / Sq.Mt / Remarks all span rowA+B.
    header_rowA = [
        Paragraph('S No', hdr), '',                       # 0-1 span
        Paragraph('Work Order<br/>No', hdr),              # 2 (spans down)
        Paragraph('ACT (MM)', hdr), '',                   # 3-4 span
        Paragraph('ACT (IN)', hdr), '',                   # 5-6 span
        Paragraph('Qty', hdr),
        Paragraph('H', hdr),
        Paragraph('C', hdr),
        Paragraph('SP', hdr),
        Paragraph('BH', hdr),
        Paragraph('CSK', hdr),
        Paragraph('Sq.Mt', hdr),
        Paragraph('Remarks / Ref', hdr),
    ]
    header_rowB = [
        Paragraph('S No', hdr_small),
        Paragraph('Prd No', hdr_small),
        '',                                                # spanned from A
        Paragraph('Width', hdr_small),
        Paragraph('Height', hdr_small),
        Paragraph('Width', hdr_small),
        Paragraph('Height', hdr_small),
        '', '', '', '', '', '', '', '',                    # spanned from A
    ]
    header_row_idx_A = row
    header_row_idx_B = row + 1
    data.append(header_rowA)
    data.append(header_rowB)

    # Horizontal spans in rowA
    style_cmds.append(('SPAN', (0, header_row_idx_A), (1, header_row_idx_A)))       # S No
    style_cmds.append(('SPAN', (3, header_row_idx_A), (4, header_row_idx_A)))       # ACT(MM)
    style_cmds.append(('SPAN', (5, header_row_idx_A), (6, header_row_idx_A)))       # ACT(IN)
    # Vertical spans (rowA extending into rowB) for single-label headers
    for c in (2, 7, 8, 9, 10, 11, 12, 13, 14):
        style_cmds.append(('SPAN', (c, header_row_idx_A), (c, header_row_idx_B)))
    # Header formatting
    style_cmds.append(('BACKGROUND', (0, header_row_idx_A), (NC - 1, header_row_idx_B), colors.HexColor('#EAEEE9')))
    style_cmds.append(('VALIGN', (0, header_row_idx_A), (NC - 1, header_row_idx_B), 'MIDDLE'))
    style_cmds.append(('TOPPADDING', (0, header_row_idx_A), (-1, header_row_idx_B), 4))
    style_cmds.append(('BOTTOMPADDING', (0, header_row_idx_A), (-1, header_row_idx_B), 4))
    row += 2

    # ── Item rows, grouped by material_spec
    current_spec = None
    sl = 0
    prd = 0
    total_qty = 0.0
    total_sqm = 0.0

    for it in gp.items:
        spec = (it.material_spec or '').strip()
        # New group header row whenever material_spec changes.
        if spec and spec != current_spec:
            data.append([Paragraph(spec.upper(), group_h)] + [''] * (NC - 1))
            style_cmds.append(('SPAN', (0, row), (NC - 1, row)))
            style_cmds.append(('BACKGROUND', (0, row), (NC - 1, row), colors.HexColor('#F7F4E9')))
            style_cmds.append(('TOPPADDING', (0, row), (-1, row), 4))
            style_cmds.append(('BOTTOMPADDING', (0, row), (-1, row), 4))
            current_spec = spec
            row += 1

        sl += 1
        prd += 1
        qty = float(it.qty_this_pass or 0)
        sqm = float(it.sqm or 0)
        total_qty += qty
        total_sqm += sqm

        data.append([
            Paragraph(str(sl),  cell_c),
            Paragraph(str(prd), cell_c),
            Paragraph(it.work_order_no or '',                    cell_c),
            Paragraph(_fmt_mm(it.width_mm),                       cell_r),
            Paragraph(_fmt_mm(it.height_mm),                      cell_r),
            Paragraph(_fmt_in(it.width_in_display),               cell_r),
            Paragraph(_fmt_in(it.height_in_display),              cell_r),
            Paragraph(_fmt_qty(qty),                              cell_c),
            Paragraph(_flag(it.flag_h),   cell_c),
            Paragraph(_flag(it.flag_c),   cell_c),
            Paragraph(_flag(it.flag_sp),  cell_c),
            Paragraph(_flag(it.flag_bh),  cell_c),
            Paragraph(_flag(it.flag_csk), cell_c),
            Paragraph(_fmt_sqm(sqm),      cell_r),
            Paragraph(it.remarks or '',   cell_l),
        ])
        row += 1

    # ── Total row: "Total : N" spans cols 0..12 (under S No through
    #    CSK), Sq.Mt total sits in its own col 13, Remarks col 14 blank.
    tot_row = row
    data.append([
        Paragraph(f'<b>Total : {_fmt_qty(total_qty)}</b>', total_lbl),
        '', '', '', '', '', '', '', '', '', '', '', '',
        Paragraph(f'<b>{_fmt_sqm(total_sqm)}</b>', total_val),
        '',
    ])
    style_cmds.append(('SPAN', (0, tot_row), (12, tot_row)))   # "Total : N" label
    style_cmds.append(('LINEABOVE',    (0, tot_row), (-1, tot_row), 0.6, colors.black))
    style_cmds.append(('TOPPADDING',   (0, tot_row), (-1, tot_row), 4))
    style_cmds.append(('BOTTOMPADDING',(0, tot_row), (-1, tot_row), 4))
    row += 1

    # ── Global grid + typography
    style_cmds.append(('GRID',   (0, 0), (NC - 1, tot_row), 0.35, colors.HexColor('#333')))
    style_cmds.append(('BOX',    (0, 0), (NC - 1, tot_row), 0.9,  colors.black))
    style_cmds.append(('VALIGN', (0, 0), (NC - 1, tot_row), 'MIDDLE'))
    style_cmds.append(('LEFTPADDING',  (0, 0), (-1, -1), 2))
    style_cmds.append(('RIGHTPADDING', (0, 0), (-1, -1), 2))

    tbl = Table(data, colWidths=col_widths, repeatRows=3)  # PI strip + 2 header rows
    tbl.setStyle(TableStyle(style_cmds))
    return tbl, total_qty, total_sqm


# ─── totals + signatures + footer ────────────────────────────────────

def _build_totals_below(total_qty, total_sqm, styles):
    """Right-aligned "Qty : N   Total Sqmt : NN.NNN" strip that sits
    just below the items table (like Arihant's dotted-line summary)."""
    body = ParagraphStyle('TotBelow', parent=styles['Normal'],
                           fontName='Helvetica-Bold', fontSize=10,
                           alignment=TA_RIGHT, leading=13)
    tbl = Table([[
        Paragraph(
            f'<font color="#555">Qty :</font> <b>{_fmt_qty(total_qty)}</b>'
            f'&nbsp;&nbsp;&nbsp;&nbsp;'
            f'<font color="#555">Total Sqmt :</font> <b>{_fmt_sqm(total_sqm)}</b>',
            body,
        ),
    ]], colWidths=[CONTENT_W])
    tbl.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEABOVE', (0, 0), (-1, -1), 0.4, colors.HexColor('#888')),
    ]))
    return tbl


def _build_signature_strip(gp, styles):
    """Bottom-of-page signature block — Authority left, Driver right."""
    sig = ParagraphStyle('Sig', parent=styles['Normal'],
                          fontName='Helvetica-Bold', fontSize=9,
                          alignment=TA_LEFT, leading=11)
    sig_right = ParagraphStyle('SigR', parent=sig, alignment=TA_RIGHT)
    tbl = Table(
        [[
            Paragraph('Signature of Authority', sig),
            Paragraph('Signature of Driver', sig_right),
        ]],
        colWidths=[CONTENT_W / 2, CONTENT_W / 2],
        rowHeights=[18 * mm],
    )
    tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return tbl


def _build_footer_strip(gp, styles):
    foot = ParagraphStyle('Foot', parent=styles['Normal'],
                          fontName='Helvetica-Oblique', fontSize=7,
                          alignment=TA_LEFT, textColor=colors.HexColor('#888'))
    return Paragraph('Powered by vcore', foot)


# ─── entry point ─────────────────────────────────────────────────────

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
    story.append(Spacer(1, 3 * mm))
    for el in _build_customer_block(gp, styles):
        story.append(el)
    story.append(Spacer(1, 3 * mm))
    items_tbl, total_qty, total_sqm = _build_items_table(gp, styles)
    story.append(items_tbl)
    story.append(Spacer(1, 3 * mm))
    story.append(_build_totals_below(total_qty, total_sqm, styles))
    story.append(Spacer(1, 6 * mm))
    story.append(_build_signature_strip(gp, styles))
    story.append(Spacer(1, 2 * mm))
    story.append(_build_footer_strip(gp, styles))

    doc.build(story)
    return buf.getvalue()
