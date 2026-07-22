"""PDF generator for Vetrova Interni UPVC quotes (KAN-67).

One document: `generate_upvc_quote_pdf(quote)` → bytes.

Design goals (per BD's directive on the ticket):
  - **Compact, space-efficient** — single-page target for ≤10 openings,
    8.5pt body, tight cell padding, no decorative whitespace.
  - **Vetrova Interni masthead** + **Vetrova Tech Services Pvt Ltd**
    legal entity block (no GSTIN per ticket answer).
  - **20-year warranty highlight strip** — green band, full-width, drawn
    above the line items so it's the first thing the customer sees.
  - Dimensions render in the unit BD picked per row (KAN-34).

ReportLab — pure Python, no headless browser. Output is bytes for both
the in-app preview/download route + the customer email attachment.
"""

import os
from io import BytesIO
from datetime import timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image,
)
from reportlab.graphics.shapes import Drawing, Polygon, Rect
from reportlab.graphics import renderPDF


# Vetrova Interni palette — atelier-aligned with vetrova.in. Sourced from
# glassyplatform/src/app/(vetrova)/vetrova/components/VIMark.tsx so the
# PDF mark matches the site exactly (same hexes, same polygon coords).
VI_FOREST    = colors.HexColor('#0F2A22')  # primary ink — dark forest
VI_BRASS     = colors.HexColor('#C19A4E')  # right facet of the V
VI_BRASS_DEEP = colors.HexColor('#8A6A2E')  # Roman I overlay on cream BG
VI_CREAM     = colors.HexColor('#F5F0E1')

# Aliases used by the rest of the document (kept so the existing styles
# below stay readable).
VI_PRIMARY = VI_FOREST
VI_ACCENT  = colors.HexColor('#E8D5A6')
VI_WARN    = colors.HexColor('#0F5132')   # 20-year warranty band — Bootstrap success green
VI_MUTED   = colors.HexColor('#6B7280')
VI_LIGHT   = colors.HexColor('#E5E7EB')

# UPI QR — same JPEG Bathqube's PDF uses. Single source of truth for
# the pay-by-UPI flow customers scan on the annex page.
_QR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'images', 'upi-qr.jpeg',
)
# Optional warranty-badge PNG. If a file exists at this path, the PDF
# uses it directly; otherwise it falls back to the hand-drawn vector
# version (_warranty_badge_drawing). Provide a transparent-background
# PNG ideally — JPEG works but loses the cut-out look.
_WARRANTY_BADGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'images', 'warranty-badge.png',
)


def _warranty_badge_drawing(size_mm=22):
    """Hand-drawn 20-Year Warranty seal — silver palette with shiny
    metallic highlights.

    Original vector composition built from primitives. "Shine" is
    simulated by stacking lighter wedges + a specular highlight dot on
    top of the base silver tones — no gradients (ReportLab doesn't
    support them in Drawing primitives), just clever layering.

    Layered bottom-to-top:
      1. Scalloped outer ring — wavy outline
      2. Annular highlight wedge on the top arc of the outer ring
         (the catching-light look)
      3. Sunburst rays fanning from inner medallion to outer ring
      4. Embossed inner medallion (darker ring + lighter face)
      5. Upper-half shine wedge on the medallion (specular highlight)
      6. Tiny specular dot at the top-left of the medallion
      7. Five 5-pointed stars across the top arc
      8. "20" + "YEARS" centred on the medallion
      9. Silver ribbon banner with top-edge highlight + swallowtails
     10. "WARRANTY" text on ribbon
    """
    from reportlab.graphics.shapes import Drawing, Circle, String, Rect, Polygon, Wedge
    import math as _math

    # Local palette — kept inside the helper so it doesn't leak into
    # the brand-colour globals. Gold tones from creamy specular highlight
    # down to deep-gold edge; ink kept very dark so "20 / YEARS /
    # WARRANTY" stays legible on the warm gold face.
    SHINE        = colors.HexColor('#FFF1B8')   # cream-gold specular hit
    SILVER_LIGHT = colors.HexColor('#F4CE6A')   # light gold (still named
                                                 # SILVER_LIGHT below to
                                                 # avoid renaming every
                                                 # use site in this fn)
    SILVER       = colors.HexColor('#C9A14A')   # classic mid gold
    SILVER_EDGE  = colors.HexColor('#8C6720')   # deep-gold edge / shadow
    INK_DARK     = colors.HexColor('#2B1E07')   # espresso ink — legible on gold

    s = size_mm * mm
    d = Drawing(s, s)
    cx = s / 2.0
    cy = s / 2.0
    r  = s / 2.0

    # ─── 1. Scalloped outer ring ────────────────────────────────────
    # 16 alternating points between r_out_hi and r_out_lo trace a wavy
    # outline. The "scallop" depth is small (3% of radius) so the
    # outline still reads as round at small sizes.
    scallop_pts = []
    n_scallops = 16
    r_hi = r * 0.99
    r_lo = r * 0.95
    for i in range(2 * n_scallops):
        ang = (i / (2 * n_scallops)) * 2 * _math.pi - _math.pi / 2
        rad = r_hi if i % 2 == 0 else r_lo
        scallop_pts.extend([cx + rad * _math.cos(ang), cy + rad * _math.sin(ang)])
    d.add(Polygon(points=scallop_pts, fillColor=SILVER, strokeColor=SILVER_EDGE,
                  strokeWidth=0.4))

    # ─── 1b. Top-arc highlight on the scalloped ring ────────────────
    # An annular Wedge from ~40° to 140° (top section) in a lighter
    # silver — simulates light catching the top of the metallic ring.
    d.add(Wedge(cx, cy, r * 0.97, 40, 140, radius1=r * 0.86,
                fillColor=SILVER_LIGHT, strokeColor=None))

    # ─── 2. Sunburst rays ────────────────────────────────────────────
    # 24 thin radial wedges fanning between the inner medallion edge
    # and the scalloped outer ring. Built as narrow quads (4-point
    # polygons) so each ray has a definite thickness.
    n_rays = 24
    r_ray_inner = r * 0.66
    r_ray_outer = r * 0.93
    ray_half_width = 0.018   # radians — narrow ray
    for i in range(n_rays):
        ang = (i / n_rays) * 2 * _math.pi - _math.pi / 2
        c, s_ = _math.cos(ang), _math.sin(ang)
        # Tangent vector for the ray's width
        tx, ty = -s_, c
        d.add(Polygon(points=[
            cx + r_ray_inner * c - r_ray_inner * ray_half_width * tx,
            cy + r_ray_inner * s_ - r_ray_inner * ray_half_width * ty,
            cx + r_ray_outer * c - r_ray_outer * ray_half_width * tx,
            cy + r_ray_outer * s_ - r_ray_outer * ray_half_width * ty,
            cx + r_ray_outer * c + r_ray_outer * ray_half_width * tx,
            cy + r_ray_outer * s_ + r_ray_outer * ray_half_width * ty,
            cx + r_ray_inner * c + r_ray_inner * ray_half_width * tx,
            cy + r_ray_inner * s_ + r_ray_inner * ray_half_width * ty,
        ], fillColor=SILVER_EDGE, strokeColor=None))

    # ─── 3. Inner medallion — embossed darker ring + lighter face ────
    d.add(Circle(cx, cy, r * 0.68, fillColor=SILVER_EDGE, strokeColor=None))
    d.add(Circle(cx, cy, r * 0.64, fillColor=SILVER_LIGHT, strokeColor=None))

    # ─── 3b. Shine wedge across the upper half of the medallion ──────
    # Wider arc (30°→150°) in near-white to fake a specular reflection.
    # Drawn slightly inside the medallion edge so the darker ring still
    # reads as a frame.
    d.add(Wedge(cx, cy, r * 0.60, 30, 150,
                fillColor=SHINE, strokeColor=None))
    # ─── 3c. Tiny specular highlight dot at top-left of medallion ────
    d.add(Circle(cx - r * 0.22, cy + r * 0.30, r * 0.06,
                 fillColor=SHINE, strokeColor=None))

    # ─── 4. Five 5-pointed stars on the top arc inside the medallion ─
    def _star_points(scx, scy, ro, ri, rotation_rad=-_math.pi / 2):
        """Return flat point list for a 5-point star."""
        pts = []
        for i in range(10):
            a = rotation_rad + i * _math.pi / 5
            rad = ro if i % 2 == 0 else ri
            pts.extend([scx + rad * _math.cos(a), scy + rad * _math.sin(a)])
        return pts

    star_ring_r = r * 0.52
    star_outer = r * 0.045
    star_inner = star_outer * 0.45
    for angle_deg in (-55, -27.5, 0, 27.5, 55):
        ang = _math.radians(angle_deg - 90)
        scx = cx + star_ring_r * _math.cos(ang)
        scy = cy + star_ring_r * _math.sin(ang)
        d.add(Polygon(points=_star_points(scx, scy, star_outer, star_inner),
                      fillColor=INK_DARK, strokeColor=None))

    # ─── 5. "20" + "YEARS" centred on the medallion ──────────────────
    d.add(String(cx, cy - r * 0.04, "20",
                 fontSize=r * 0.50, fontName='Helvetica-Bold',
                 textAnchor='middle', fillColor=INK_DARK))
    d.add(String(cx, cy - r * 0.22, "YEARS",
                 fontSize=r * 0.13, fontName='Helvetica-Bold',
                 textAnchor='middle', fillColor=INK_DARK))

    # ─── 6. Ribbon banner across lower third ─────────────────────────
    banner_h = r * 0.30
    banner_y = cy - r * 0.55
    banner_w = r * 1.65
    # Drop-shadow underneath the ribbon for separation from the rays
    d.add(Rect(cx - banner_w / 2.0, banner_y - r * 0.025, banner_w, r * 0.025,
               fillColor=SILVER_EDGE, strokeColor=None))
    # Main ribbon face
    d.add(Rect(cx - banner_w / 2.0, banner_y, banner_w, banner_h,
               fillColor=SILVER, strokeColor=None))
    # Bright shine band across the upper third of the ribbon — fakes a
    # glossy specular reflection. Wider than the previous thin
    # highlight so the "wet metal" look reads at small zoom.
    d.add(Rect(cx - banner_w / 2.0, banner_y + banner_h * 0.62,
               banner_w, banner_h * 0.20,
               fillColor=SHINE, strokeColor=None))
    # Thin pressed-metal highlight along the very top edge
    d.add(Rect(cx - banner_w / 2.0, banner_y + banner_h - r * 0.012,
               banner_w, r * 0.012,
               fillColor=SILVER_LIGHT, strokeColor=None))
    # Darker bottom edge for the "rolled" look
    d.add(Rect(cx - banner_w / 2.0, banner_y,
               banner_w, r * 0.015,
               fillColor=SILVER_EDGE, strokeColor=None))
    # Swallowtail ends — triangular notches cut into the ribbon's far tips
    tail_drop = r * 0.10
    d.add(Polygon(points=[
        cx - banner_w / 2.0,             banner_y + banner_h,
        cx - banner_w / 2.0,             banner_y,
        cx - banner_w / 2.0 - tail_drop, banner_y + banner_h / 2.0,
    ], fillColor=SILVER_EDGE, strokeColor=None))
    d.add(Polygon(points=[
        cx + banner_w / 2.0,             banner_y + banner_h,
        cx + banner_w / 2.0,             banner_y,
        cx + banner_w / 2.0 + tail_drop, banner_y + banner_h / 2.0,
    ], fillColor=SILVER_EDGE, strokeColor=None))

    # ─── 7. "WARRANTY" text on ribbon ────────────────────────────────
    d.add(String(cx, banner_y + banner_h * 0.30, "WARRANTY",
                 fontSize=r * 0.19, fontName='Helvetica-Bold',
                 textAnchor='middle', fillColor=INK_DARK))

    return d


def _vi_mark_drawing(height_mm=10):
    """Return a ReportLab Drawing of the Vetrova Interni V·I mark.

    Hand-ported from VIMark.tsx (the non-circle inline variant):
      - viewBox 60 32 160 216 in SVG → we recreate the same polygons
        on an internal 160×216 canvas and scale to the requested mm.
      - Left facet = forest (we render on a CREAM/white PDF, so
        light=false case in the React component).
      - Right facet = brass.
      - Roman I = brass-deep.

    PDF coords have origin at BOTTOM-LEFT, SVG at TOP-LEFT — every Y is
    flipped (svg_y → canvas_h - svg_y).
    """
    # Native coords (post viewBox crop): x ∈ [60,220], y ∈ [32,248].
    # Shift so origin is at (60, 32) → x ∈ [0,160], y ∈ [0,216].
    canvas_w = 160.0
    canvas_h = 216.0

    # Aspect-preserving scale to the requested mm height.
    pt_per_mm = mm  # ReportLab unit
    h_pt = height_mm * pt_per_mm
    w_pt = h_pt * (canvas_w / canvas_h)
    sx = w_pt / canvas_w
    sy = h_pt / canvas_h

    d = Drawing(w_pt, h_pt)

    def _pt(x, y):
        """SVG (x,y) → PDF (x,y) with origin-flip + Y-axis flip + scale."""
        return ((x - 60) * sx, (canvas_h - (y - 32)) * sy)

    def _poly_pts(svg_pairs):
        out = []
        for (x, y) in svg_pairs:
            px, py = _pt(x, y)
            out.extend([px, py])
        return out

    # Left facet (forest on cream BG): 74,80  116,80  140,220  132,235  124,235
    d.add(Polygon(
        points=_poly_pts([(74, 80), (116, 80), (140, 220), (132, 235), (124, 235)]),
        fillColor=VI_FOREST, strokeColor=None,
    ))
    # Right facet (brass): 164,80  206,80  156,235  148,235  140,220
    d.add(Polygon(
        points=_poly_pts([(164, 80), (206, 80), (156, 235), (148, 235), (140, 220)]),
        fillColor=VI_BRASS, strokeColor=None,
    ))

    # Roman I — three rects in SVG-space; convert each to PDF rect.
    # SVG rect(x, y, w, h) where (x,y) is TOP-LEFT.
    def _rect_to_pdf(svg_x, svg_y, svg_w, svg_h):
        # Top-left in PDF coords is at (x, canvas_h - y); rect's PDF y is
        # bottom-left so subtract h.
        px, py_top = _pt(svg_x, svg_y)
        h_scaled = svg_h * sy
        py_bottom = py_top - h_scaled
        return Rect(px, py_bottom, svg_w * sx, h_scaled,
                    fillColor=VI_BRASS_DEEP, strokeColor=None)

    # Vertical stem:  x=137 y=62  w=6  h=178
    d.add(_rect_to_pdf(137, 62, 6, 178))
    # Top serif:      x=126 y=62  w=28 h=7
    d.add(_rect_to_pdf(126, 62, 28, 7))
    # Bottom serif:   x=126 y=233 w=28 h=7
    d.add(_rect_to_pdf(126, 233, 28, 7))

    return d


def _money(v):
    try:
        return f"INR {float(v):,.2f}"
    except Exception:
        return f"INR {v}"


def _format_dim(it):
    """'1200 × 2100 mm' or '—' if either dim missing."""
    if it.width is None or it.height is None:
        return '—'
    try:
        w = float(it.width)
        h = float(it.height)
    except Exception:
        return '—'
    fmt = lambda v: f"{v:g}"
    return f"{fmt(w)} × {fmt(h)} {it.unit or ''}".strip()


def _format_type(it):
    """'Sliding · 3-track' / 'Louvers · Fixed' / 'Swing'."""
    base = (it.track_type or '').capitalize()
    sub = (it.track_system or '').strip()
    if sub and it.track_type in ('sliding', 'louvers'):
        return f"{base} · {sub.capitalize() if it.track_type == 'louvers' else sub}"
    return base


def generate_upvc_quote_pdf(quote):
    """Render the Vetrova Interni UPVC estimate PDF. Returns bytes."""
    buf = BytesIO()
    # Tight margins — the body is dense by design so the bill fits
    # one page for typical project sizes.
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"Vetrova Interni Estimate {quote.estimate_number or quote.id}",
    )

    styles = getSampleStyleSheet()
    h_brand = ParagraphStyle(
        'brand', parent=styles['Heading1'],
        textColor=VI_PRIMARY, fontSize=20, leading=22, spaceAfter=0,
    )
    h_sub = ParagraphStyle(
        'sub', parent=styles['Normal'],
        textColor=VI_MUTED, fontSize=8, leading=10,
    )
    h_section = ParagraphStyle(
        'section', parent=styles['Heading4'],
        textColor=VI_PRIMARY, fontSize=8, leading=10,
        spaceBefore=8, spaceAfter=2, textTransform='uppercase',
    )
    body = ParagraphStyle('body', parent=styles['Normal'], fontSize=8.5, leading=11)
    body_right = ParagraphStyle('body_r', parent=body, alignment=TA_RIGHT)
    estimate_tag = ParagraphStyle(
        'tag', parent=styles['Normal'],
        textColor=VI_PRIMARY, fontSize=8, alignment=TA_RIGHT,
    )

    story = []

    # ─── HEADER: V·I mark | wordmark · tagline | estimate number + date ───
    # Vector mark (recreated from VIMark.tsx) + the italicised "Interni"
    # wordmark — same lockup as the vetrova.in nav, just rendered server-
    # side as PDF primitives so we don't depend on any image file.
    mark_drawing = _vi_mark_drawing(height_mm=14)
    wordmark = ParagraphStyle(
        'wordmark', parent=styles['Heading1'],
        textColor=VI_FOREST, fontSize=20, leading=22, spaceAfter=0,
    )
    masthead_left = [[
        mark_drawing,
        [
            Paragraph(
                'Vetrova&nbsp;<i><font color="#8A6A2E">Interni</font></i>',
                wordmark,
            ),
            Paragraph(
                "AFFORDABLE GLASS INTERIORS &nbsp;·&nbsp; UPVC DOORS &amp; WINDOWS",
                ParagraphStyle('tag', parent=h_sub, textColor=VI_BRASS_DEEP,
                               fontSize=7, leading=9),
            ),
        ],
    ]]
    mark_wrap = Table(
        masthead_left,
        colWidths=[12 * mm, 96 * mm],
    )
    mark_wrap.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    issued_date = (quote.updated_at or quote.created_at).strftime('%d %b %Y')
    valid_until = (quote.created_at + timedelta(days=int(quote.validity_days or 10))).strftime('%d %b %Y')
    masthead_right = [
        Paragraph("<b>ESTIMATE</b>", estimate_tag),
        Paragraph(
            f"<font size=12><b>{quote.estimate_number or ('VI-UPVC-' + str(quote.id))}</b></font>",
            ParagraphStyle('en', parent=styles['Normal'], alignment=TA_RIGHT),
        ),
        Paragraph(f"Issued {issued_date}",
                  ParagraphStyle('iss', parent=h_sub, alignment=TA_RIGHT)),
        Paragraph(f"Valid until {valid_until}",
                  ParagraphStyle('val', parent=h_sub, alignment=TA_RIGHT)),
    ]
    header_tbl = Table([[mark_wrap, masthead_right]],
                       colWidths=[110 * mm, 70 * mm])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, VI_PRIMARY),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(header_tbl)

    # ─── CUSTOMER + 20-YEAR WARRANTY BADGE side-by-side ───
    # The badge sits to the right of the customer details so the seal
    # reads as a stamp of authenticity next to who the bill is for.
    # Replaced the earlier full-width green text band per BD's request
    # for a proper visual badge instead of flat highlight.
    story.append(Spacer(1, 6))
    story.append(Paragraph("CUSTOMER", h_section))
    cust = [['Name', quote.customer_name or '—'], ['Phone', quote.phone or '—']]
    if quote.email:        cust.append(['Email', quote.email])
    if quote.pincode:      cust.append(['Pincode', quote.pincode])
    if quote.site_address: cust.append(['Site address', quote.site_address])
    cust_tbl = Table(cust, colWidths=[26 * mm, 117 * mm])
    cust_tbl.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (0, -1), VI_MUTED),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
    ]))
    # Prefer a PNG warranty badge when one is dropped at the configured
    # path — gives BD a way to swap in a licensed designer-made seal
    # without touching code. Falls back to the hand-drawn vector if the
    # file isn't there.
    if os.path.exists(_WARRANTY_BADGE_PATH):
        badge = Image(_WARRANTY_BADGE_PATH, width=22 * mm, height=22 * mm)
    else:
        badge = _warranty_badge_drawing(size_mm=22)
    cust_badge_row = Table(
        [[cust_tbl, badge]],
        colWidths=[143 * mm, 39 * mm],
    )
    cust_badge_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (0, 0), 'TOP'),     # customer details top-left
        ('VALIGN', (1, 0), (1, 0), 'MIDDLE'),  # badge vertically centred
        ('ALIGN',  (1, 0), (1, 0), 'CENTER'),  # badge horizontally centred in its cell
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(cust_badge_row)

    # ─── LINE ITEMS ───
    story.append(Paragraph("OPENINGS", h_section))
    items = list(quote.items or [])
    if items:
        # Type cell is rendered as a Paragraph (not plain string) so long
        # values like "Sliding · 2.5-track" or "Louvers · Movable" wrap
        # cleanly inside the column instead of overflowing into Dimensions
        # — that overflow was causing words to bleed together visually.
        rows = [['#', 'Label', 'Type', 'Dimensions', 'Colour', 'Qty', 'Sqft', 'Rate/Sqft', 'Amount (INR)']]
        for i, it in enumerate(items, start=1):
            qty = float(it.quantity or 1)
            rows.append([
                str(i),
                Paragraph(it.label or '—', body),
                Paragraph(_format_type(it), body),
                Paragraph(_format_dim(it), body),
                (it.colour or '').capitalize(),
                f"{qty:g}",
                f"{float(it.sqft or 0):,.2f}",
                f"{float(it.rate or 0):,.2f}",
                f"{float(it.amount or 0):,.2f}",
            ])
        items_tbl = Table(
            rows,
            # Sum = 182 mm = page body width (A4 minus 14mm on each side).
            # Type widened from 22→26mm and Dimensions trimmed 28→24mm so
            # "Sliding · 2.5-track" fits on one line at 8.5pt, and the
            # Paragraph wrapping above catches anything still too long.
            colWidths=[7 * mm, 30 * mm, 26 * mm, 24 * mm, 18 * mm, 10 * mm,
                       17 * mm, 20 * mm, 30 * mm],
            repeatRows=1,
        )
        items_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F4EFE3')),
            ('TEXTCOLOR', (0, 0), (-1, 0), VI_PRIMARY),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 8.5),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.4, VI_LIGHT),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(items_tbl)
    else:
        story.append(Paragraph("No openings on this quote.", body))

    # ─── TOTALS (right-aligned) ───
    gst_pct = float(quote.gst_percentage or 18)
    gst_half = gst_pct / 2
    # Qty-weighted total sqft across all openings — same number the
    # view-page totals card shows + the form previewed live.
    total_sqft = sum(float(it.sqft or 0) * float(it.quantity or 1) for it in items)
    transport  = float(getattr(quote, 'transport_charges', 0) or 0)
    taxable    = float(quote.subtotal or 0) + transport
    totals_rows = [
        ['Total Sqft',                f'{total_sqft:,.2f}'],
        ['Subtotal (items)',          _money(quote.subtotal)],
    ]
    if transport > 0:
        totals_rows.append(['Transportation', _money(transport)])
        totals_rows.append(['Taxable Amount', _money(taxable)])
    totals_rows.extend([
        [f'CGST ({gst_half:g}%)',     _money(quote.cgst)],
        [f'SGST ({gst_half:g}%)',     _money(quote.sgst)],
        ['Grand Total',               _money(quote.total)],
    ])
    totals_tbl = Table(totals_rows, colWidths=[40 * mm, 40 * mm])
    totals_tbl.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (0, -2), VI_MUTED),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        # Grand total row — bold + line above
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 0.8, VI_PRIMARY),
        ('TEXTCOLOR', (0, -1), (-1, -1), VI_PRIMARY),
        ('TOPPADDING', (0, -1), (-1, -1), 4),
    ]))
    # Right-align the whole block by wrapping in a 2-col table where the
    # first column is an empty spacer.
    wrap = Table([['', totals_tbl]], colWidths=[102 * mm, 80 * mm])
    wrap.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(Spacer(1, 4))
    story.append(wrap)

    # ─── PAGE 1 footer — small reminder, full annex on page 2 ───
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<font color='#9CA3AF' size='8'>Estimate validity: "
        f"{int(quote.validity_days or 10)} days from {issued_date}. "
        f"See next page for Notes, Terms &amp; Conditions, and Bank/Payment Details.</font>",
        ParagraphStyle('p1foot', parent=body, alignment=TA_LEFT),
    ))

    # ─── PAGE 2: Notes + T&Cs + Bank/UPI annex ───
    # Mirrors the Bathqube PDF's page-2 structure so a customer browsing
    # both products sees the same payment surface. T&Cs absorb the new
    # window-install pre-requisites BD asked for, condensed into one
    # readable bullet rather than 13 tiny lines.
    story.append(PageBreak())

    note_body = ParagraphStyle('note', parent=body, fontSize=9,
                               leading=13, leftIndent=10, spaceAfter=3)

    story.append(Paragraph("NOTES", h_section))
    for line in [
        "All prices shown are inclusive of GST plus transportation, labour, and installation — no extra charges beyond what is listed.",
        "Prices may change only if additions or deletions are made to the estimate.",
        f"Estimate validity: {int(quote.validity_days or 10)} days from the date of issue.",
        "<b>Payment terms:</b> 50% on order confirmation · 50% on completion of installation.",
    ]:
        story.append(Paragraph(f"• {line}", note_body))

    story.append(Paragraph("TERMS &amp; CONDITIONS", h_section))
    for line in [
        "<b>Lead Time</b> — Installations are completed within 7&ndash;14 days in Bengaluru after order confirmation and final site measurement.",
        "<b>Final Measurement</b> — Vetrova's site measurement is taken as the actual aperture plus an additional 30 mm allowance for fit + sealing tolerance. Final dimensions are confirmed in writing before fabrication.",
        "<b>Site Pre-requisites (customer to complete before installation date)</b> — "
            "(i) walls plastered inside and outside, with inside POP complete; "
            "(ii) jams, sills, and soffits plastered; "
            "(iii) flooring complete in locations where doors are to be installed; "
            "(iv) aperture smooth, with base and top water-leveled and sides in vertical plumb; "
            "(v) sill width greater than the window width; "
            "(vi) opening accessible from inside for installation; "
            "(vii) scaffolding or bracing must not obstruct any window opening on the installation day.",
        "<b>Grills</b> &mdash; <i>Horizontal slider windows:</i> the grill must be fixed on the outer face <i>before</i> window installation. <i>Casement windows:</i> a screw-type grill is recommended <i>after</i> window installation.",
        "<b>Paint Sequencing</b> &mdash; Installation must happen before the final coat of paint. At least one base coat of paint should be completed before installation begins.",
        "<b>Cancellation</b> &mdash; 100% refund if material has not yet been sent to fabrication. Once processing begins, a 25% fee applies on the order value.",
        "<b>Liability</b> &mdash; Vetrova's liability is limited to the advance received against the order.",
        "<b>Force Majeure</b> &mdash; In cases of unavoidable cancellation by Vetrova, advances paid will be refunded in full.",
    ]:
        story.append(Paragraph(f"{line}", note_body))

    # ─── BANK & PAYMENT DETAILS ───
    story.append(Paragraph("BANK &amp; PAYMENT DETAILS", h_section))
    bank_label = ParagraphStyle('bl', parent=body, fontSize=9, textColor=VI_MUTED)
    bank_value = ParagraphStyle('bv', parent=body, fontSize=9, fontName='Helvetica-Bold')
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
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F4EFE3')),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))

    qr_cell = []
    if os.path.exists(_QR_PATH):
        qr_img = Image(_QR_PATH, width=38 * mm, height=38 * mm)
        qr_cell.append(qr_img)
        qr_cell.append(Paragraph(
            "<font color='#6B7280' size='8'>Scan to pay via UPI</font>",
            ParagraphStyle('qrl', parent=body, alignment=TA_CENTER, spaceBefore=4),
        ))

    pay_block = Table(
        [[bank_tbl, qr_cell]],
        colWidths=[115 * mm, 55 * mm],
    )
    pay_block.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(pay_block)

    # ─── LEGAL ENTITY BLOCK at the bottom of page 2 ───
    story.append(Spacer(1, 8))
    legal = Table(
        [[
            Paragraph(
                "<b>Vetrova Tech Services Private Limited</b><br/>"
                "CIN U62099KA2018PTC127405<br/>"
                "support@glassy.in",
                ParagraphStyle('legal', parent=body, fontSize=7.5, leading=10,
                               textColor=VI_PRIMARY),
            ),
            Paragraph(
                "<i>Thank you for choosing Vetrova Interni.</i>",
                ParagraphStyle('thanks', parent=body, fontSize=8, leading=10,
                               alignment=TA_RIGHT, textColor=VI_MUTED),
            ),
        ]],
        colWidths=[100 * mm, 82 * mm],
    )
    legal.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEABOVE', (0, 0), (-1, -1), 0.5, VI_LIGHT),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(legal)

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
