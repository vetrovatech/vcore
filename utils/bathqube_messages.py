"""
Customer-facing message templates for the 5 Bathqube post-purchase stages.

Each builder takes a BathqubeQuote and returns (subject, body_text, body_html).
The body is rendered into a textarea in the "Advance stage" UI so ops can
edit before sending. Use {placeholders} for values the ops user usually wants
to tweak — they're filled with current quote data on render.

# TODO from product:
#   - (b) processing-stage message body is blank — fill in once confirmed.
#   - Bank account / QR image URL / Google review URL / Instagram URL /
#     IndiaMart URL are hardcoded below. Replace via env or a settings page
#     in v2.
"""

import os

BRAND = "Bathqube"

# ---- TODO: replace these constants with real values before going live ----
BANK_DETAILS_TEXT = os.getenv(
    'BATHQUBE_BANK_DETAILS',
    "Account Name: Vetrova Tech Services Private Limited\n"
    "Bank Name: IDFC First Bank\n"
    "Account Number: 10249972220\n"
    "IFSC Code: IDFB0080158\n"
    "Account Type: Current\n"
    "UPI ID: 8550011196@ybl",
)
PAYMENT_QR_URL = os.getenv('BATHQUBE_QR_URL', 'https://bathqube.com/upi-qr.jpeg')
GOOGLE_REVIEW_URL = os.getenv('BATHQUBE_GOOGLE_URL', 'https://g.page/bathqube/review')
INSTAGRAM_URL = os.getenv('BATHQUBE_INSTAGRAM_URL', 'https://instagram.com/bathqube')
INDIAMART_URL = os.getenv('BATHQUBE_INDIAMART_URL', 'https://indiamart.com/bathqube')
SUPPORT_PHONE = os.getenv('BATHQUBE_SUPPORT_PHONE', '+91 85500 11196')


def _fmt_money(v):
    try:
        return f"₹{float(v):,.0f}"
    except Exception:
        return f"₹{v}"


def _dimensions_block(q):
    """Build a "Dimensions submitted:" multi-line block in the customer's
    original unit. Returns '' for legacy quotes (no dimensionUnit) so the
    historical email body stays exactly as it was before this feature.

    Used at the bottom of customer-facing emails where the customer wants
    to see the panel sizes echoed back in the unit they typed in.
    """
    from utils.bathqube_dimensions import get_dimension_unit, format_enclosures_email
    cfg = q.config if q else None
    unit = get_dimension_unit(cfg)
    if not unit:
        return ''
    enclosures = (cfg or {}).get('enclosures') or []
    if not enclosures:
        return ''
    block = format_enclosures_email(enclosures, unit)
    if not block:
        return ''
    return f"\n\nDimensions submitted ({unit}):\n{block}"


def _build_order_confirmation(q):
    subject = f"Thank you for your order — {q.estimate_number or ''}".strip(' —')
    body = (
        f"Hi {q.customer_name},\n\n"
        f"Thank you for shopping with {BRAND}!\n\n"
        f"We have received your order ({q.estimate_number}) for {_fmt_money(q.total)}. "
        f"Our team will reach out shortly with the next steps.\n\n"
        f"For any questions, WhatsApp us at {SUPPORT_PHONE}."
        f"{_dimensions_block(q)}\n\n"
        f"— Team {BRAND}"
    )
    return subject, body


def _build_processing(q):
    subject = f"Your {BRAND} order is now in processing — {q.estimate_number or ''}".strip(' —')
    # TODO: confirm exact wording with product team. Placeholder for now.
    body = (
        f"Hi {q.customer_name},\n\n"
        f"Your {BRAND} order ({q.estimate_number}) is now in processing. "
        f"We will share dispatch details once production is complete.\n\n"
        f"— Team {BRAND}"
    )
    return subject, body


def _build_bill_revision(q):
    subject = f"Revised quote for your {BRAND} order — {q.estimate_number or ''}".strip(' —')
    salutation = f"Hello {q.customer_name}" if q.customer_name else "Hello Sir/Madam"
    body = (
        f"{salutation},\n\n"
        f"As discussed with the team, this is my offer for you.\n\n"
        f"Please find the attached quotation for your Enclosure.\n\n"
        f"Kindly review and revert in case any changes are required."
        f"{_dimensions_block(q)}\n\n"
        f"— Team {BRAND}"
    )
    return subject, body


def _build_order_ready(q):
    subject = f"Your {BRAND} order is ready for dispatch — {q.estimate_number or ''}".strip(' —')
    body = (
        f"Hi {q.customer_name},\n\n"
        f"Your order is now ready for dispatch.\n\n"
        f"Total balance payable is {_fmt_money(q.balance_payable)}. As agreed, please clear the payment.\n\n"
        f"Attaching the QR and bank details for payment:\n\n"
        f"QR: {PAYMENT_QR_URL}\n\n"
        f"{BANK_DETAILS_TEXT}\n\n"
        f"— Team {BRAND}"
    )
    return subject, body


def _build_thank_you(q):
    subject = f"Thank you from {BRAND}!"
    body = (
        f"Hi {q.customer_name},\n\n"
        f"Thank you for trusting {BRAND}. Hope you had a lovely experience.\n\n"
        f"Please rate us on:\n"
        f"  Google: {GOOGLE_REVIEW_URL}\n"
        f"  Instagram: {INSTAGRAM_URL}\n"
        f"  IndiaMart: {INDIAMART_URL}\n\n"
        f"— Team {BRAND}"
    )
    return subject, body


_BUILDERS = {
    # Active email-sending stages in the new pipeline.
    'revision':           _build_bill_revision,       # via dedicated /revise editor
    'awaiting_payment':   _build_order_ready,         # balance + QR + bank details
    # Legacy aliases preserved so historical events that reference old stage
    # names can still render their template if anyone re-opens them.
    'order_confirmation': _build_order_confirmation,
    'processing':         _build_processing,
    'bill_revision':      _build_bill_revision,
    'order_ready':        _build_order_ready,
    'thank_you':          _build_thank_you,
}

STAGE_LABELS = {
    'draft':              'Draft',
    'quote_generated':    'Quote Generated',
    'in_pipeline':        'In Pipeline',
    'revision':           'Revision',
    'awaiting_payment':   'Awaiting Payment',
    'closed_won':         'Closed Won',
    'junk':               'Junk',
    'rejected':           'Rejected',
    # Ops/fulfillment stages — driven by the ops team in /bathqube/ops.
    'measurement_scheduled':  'Measurement Scheduled',
    'measurement_done':       'Measurement Done',
    'customer_signoff':       'Customer Sign-off',
    'in_fabrication':         'In Fabrication',
    'ready_to_dispatch':      'Ready to Dispatch',
    'installation_scheduled': 'Installation Scheduled',
    'installed':              'Installed',
    'handover_complete':      'Handover Complete',
    # Legacy labels kept so historical bathqube_status_events with old stage
    # codes still render a readable label until they're migrated.
    'new':                'New',
    'order_confirmation': 'Order Confirmation',
    'processing':         'Processing',
    'bill_revision':      'Bill Revision',
    'order_ready':        'Order Ready',
    'thank_you':          'Thank You',
}


def render_stage_message(quote, stage):
    """Return (subject, body_text) for a given stage, prefilled from the quote."""
    builder = _BUILDERS.get(stage)
    if not builder:
        return ('', '')
    return builder(quote)


def next_stage(current):
    """Return the next stage in the active pipeline, or None if at the end.
    Junk and rejected are disposition states with no successor."""
    order = ['quote_generated', 'in_pipeline', 'revision', 'awaiting_payment', 'closed_won']
    try:
        i = order.index(current)
    except ValueError:
        return 'in_pipeline'
    if i + 1 >= len(order):
        return None
    return order[i + 1]
