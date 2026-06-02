"""Dimension formatting for Bathqube quotes.

Two output modes, one source of truth:
- format_for_display(): the staff-facing view (vcore web UI, ops dashboard,
  internal PDF). ALWAYS renders in inches, regardless of what the customer
  typed, so the team has one consistent unit to think in.
- format_for_email(): outbound customer mail (initial confirmation, every
  revision). Renders in the unit the customer chose on the configurator,
  so what they see in their inbox matches what they typed on the form.

Legacy quotes (no dimensionUnit on configData) are treated as feet — that's
what the configurator used before this feature shipped. Those quotes keep
rendering exactly as they did pre-feature: "Wft x Hft".

All conversions anchor on inches so sqft (= in x in / 144) is exact.
"""

# Inches per source unit. 'ft' is the legacy default for grandfathered quotes.
_TO_INCHES = {
    'mm': 1.0 / 25.4,
    'cm': 1.0 / 2.54,
    'in': 1.0,
    'm':  39.37007874015748,
    'ft': 12.0,
}

_SUPPORTED_UNITS = ('mm', 'cm', 'in', 'm', 'ft')


def to_inches(value, unit):
    """Convert a numeric width/height in `unit` to inches. Returns 0 on
    bad input — we never want a dimension formatter to raise mid-template."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    factor = _TO_INCHES.get(unit)
    if factor is None:
        return 0.0
    return v * factor


def _fmt_num(v):
    """Two-decimal stringifier that strips a trailing '.00' so integers stay
    clean ('1200', not '1200.00') while non-integers show two decimals
    ('47.24'). Matches the precision the user agreed to."""
    s = f"{v:.2f}"
    return s[:-3] if s.endswith('.00') else s


def format_panel_display(width, height, unit):
    """Render ONE panel for the in-vcore display, always in inches.

    Example: format_panel_display(1200, 2100, 'mm') -> '47.24" x 82.68"'
    """
    w_in = to_inches(width, unit)
    h_in = to_inches(height, unit)
    return f'{_fmt_num(w_in)}" x {_fmt_num(h_in)}"'


def format_panel_email(width, height, unit):
    """Render ONE panel for a customer-facing email, in the customer's unit.

    Example: format_panel_email(1200, 2100, 'mm') -> '1200 mm x 2100 mm'
    Legacy 'ft' quotes -> '4 ft x 7 ft'.
    """
    if unit not in _SUPPORTED_UNITS:
        unit = 'ft'  # legacy default — quotes before the unit picker shipped
    return f'{_fmt_num(_safe_float(width))} {unit} x {_fmt_num(_safe_float(height))} {unit}'


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def get_dimension_unit(config_data):
    """Read `dimensionUnit` off a parsed config_data dict. Returns one of
    ('mm','cm','in','m') if present and valid, else None (caller should
    treat None as 'legacy quote — feet, no conversion needed for emails')."""
    if not isinstance(config_data, dict):
        return None
    u = config_data.get('dimensionUnit')
    if u in ('mm', 'cm', 'in', 'm'):
        return u
    return None


def format_enclosures_display(enclosures, unit):
    """Render all panels across all enclosures as a single inches string,
    suitable for the vcore quote view. Returns a list of strings — one per
    enclosure — so the template can wrap each in its own row.

    `unit` may be 'mm'/'cm'/'in'/'m' for new quotes, or None for legacy
    (which falls back to 'ft' rendering without conversion — matches the
    pre-feature template).
    """
    out = []
    for enc in (enclosures or []):
        panels = enc.get('glassPanels') or []
        if unit is None:
            # Legacy path: render as the customer typed (feet), with "ft" suffix.
            parts = [f"{p.get('width')}x{p.get('height')}ft" for p in panels]
        else:
            parts = [format_panel_display(p.get('width'), p.get('height'), unit) for p in panels]
        out.append(', '.join(parts))
    return out


def format_enclosures_email(enclosures, unit):
    """Render all panels across all enclosures as an email-ready multi-line
    block, in the customer's chosen unit. Used inside the email body and
    inside the PDF attachment.

    Returns a single string ready to drop into a textarea/PDF section.
    """
    lines = []
    for ei, enc in enumerate(enclosures or [], start=1):
        name = enc.get('name') or f'Enclosure {ei}'
        type_label = enc.get('typeLabel') or ''
        header = f"{ei}. {name}" + (f" - {type_label}" if type_label else "")
        lines.append(header)
        panels = enc.get('glassPanels') or []
        for pi, p in enumerate(panels, start=1):
            lines.append(
                f"   Panel {pi}: {format_panel_email(p.get('width'), p.get('height'), unit)}"
            )
    return '\n'.join(lines)
