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
    "Account Name: Bathqube\nBank: TBD\nA/C: TBD\nIFSC: TBD",
)
PAYMENT_QR_URL = os.getenv('BATHQUBE_QR_URL', 'https://bathqube.com/pay/qr.png')
GOOGLE_REVIEW_URL = os.getenv('BATHQUBE_GOOGLE_URL', 'https://g.page/bathqube/review')
INSTAGRAM_URL = os.getenv('BATHQUBE_INSTAGRAM_URL', 'https://instagram.com/bathqube')
INDIAMART_URL = os.getenv('BATHQUBE_INDIAMART_URL', 'https://indiamart.com/bathqube')
SUPPORT_PHONE = os.getenv('BATHQUBE_SUPPORT_PHONE', '+91 85500 11196')


def _fmt_money(v):
    try:
        return f"₹{float(v):,.0f}"
    except Exception:
        return f"₹{v}"


def _build_order_confirmation(q):
    subject = f"Thank you for your order — {q.estimate_number or ''}".strip(' —')
    body = (
        f"Hi {q.customer_name},\n\n"
        f"Thank you for shopping with {BRAND}!\n\n"
        f"We have received your order ({q.estimate_number}) for {_fmt_money(q.total)}. "
        f"Our team will reach out shortly with the next steps.\n\n"
        f"For any questions, WhatsApp us at {SUPPORT_PHONE}.\n\n"
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
        f"Kindly review and revert in case any changes are required.\n\n"
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
    'order_confirmation': _build_order_confirmation,
    'processing':         _build_processing,
    'bill_revision':      _build_bill_revision,
    'order_ready':        _build_order_ready,
    'thank_you':          _build_thank_you,
}

STAGE_LABELS = {
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
    """Return the next stage in the lifecycle, or None if at the end."""
    order = ['new', 'order_confirmation', 'processing', 'bill_revision', 'order_ready', 'thank_you']
    try:
        i = order.index(current)
    except ValueError:
        return 'order_confirmation'
    if i + 1 >= len(order):
        return None
    return order[i + 1]
