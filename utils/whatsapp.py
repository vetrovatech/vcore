"""
WhatsApp Cloud API helper.

Every send now requires a `brand` argument (Brand ORM instance from
models.py). The env-var single-tenant fallback was removed on
2026-08-04 — vcore runs multiple WABAs (Bathqube for Leadfy sends
to bathqube_campaign leads, Vtspl for every Bulk Import send and
Vetrova quotes), and letting callers omit the brand meant everything
silently routed through whatever WHATSAPP_PHONE_NUMBER_ID pointed
at. That was a real footgun: /leads bulk sends to non-Bathqube
leads landed with Bathqube branding, and non-migrated code paths
kept sending from the DEAD 1133856083153068 phone ID for weeks
without anyone noticing.

Phone-number normalization mirrors templates/leads/view.html: strip
spaces/dashes/parens/dots/+, prepend '91' if exactly 10 digits (Indian
number with no country code), otherwise use as-is.
"""

import io
import os  # kept for GRAPH_BASE override if we ever need one
import re
import requests


GRAPH_BASE = "https://graph.facebook.com"


class BrandRequired(RuntimeError):
    """Raised when a WhatsApp send helper is called without a brand.
    Kept as a distinct type so route handlers can catch it and 500
    with a specific message instead of the generic ValueError blob."""


def _brand_creds(brand):
    """Return (token, phone_id, api_ver) for a Brand or raise
    BrandRequired. Central so every send helper reports the same
    "which brand?" error text if a caller forgets to pass one."""
    if brand is None:
        raise BrandRequired(
            'WhatsApp send helper called without a brand — every callsite '
            'must resolve a Brand from models.Brand before sending.'
        )
    token    = getattr(brand, 'wa_access_token', '') or ''
    phone_id = getattr(brand, 'wa_phone_number_id', '') or ''
    api_ver  = getattr(brand, 'wa_api_version', 'v21.0') or 'v21.0'
    if not token or not phone_id:
        raise BrandRequired(
            f'Brand {getattr(brand, "slug", "?")!r} has empty '
            'wa_access_token or wa_phone_number_id — seed the row in '
            'models.Brand or update via SQL.'
        )
    return token, phone_id, api_ver


def normalize_phone(raw):
    """Return E.164-style digits (no '+') ready for the Cloud API 'to' field."""
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw)
    if len(digits) == 10:
        digits = "91" + digits
    return digits or None


def send_template(to, template_name, language="en", variables=None, brand=None):
    """
    Send an approved WhatsApp template.

    Args:
        to: recipient phone (any common format — normalised internally)
        template_name: exact template name as approved by Meta
        language: language code matching the approved template (e.g. 'en', 'en_US', 'hi')
        variables: list of strings for {{1}}, {{2}}, ... in the template body
        brand: REQUIRED. Brand instance whose WABA credentials to use.
               Passing None raises BrandRequired (never falls back to env).

    Returns:
        dict with keys:
          success (bool)
          wamid   (Meta's message id, when sent)
          error   (str, when failed)
          status  (HTTP status code from Graph API)
    """
    token, phone_id, api_ver = _brand_creds(brand)

    normalised = normalize_phone(to)
    if not normalised:
        return {"success": False, "error": f"Invalid phone number: {to!r}"}

    template_payload = {
        "name": template_name,
        "language": {"code": language},
    }
    if variables:
        template_payload["components"] = [{
            "type": "body",
            "parameters": [{"type": "text", "text": str(v)} for v in variables],
        }]

    url = f"{GRAPH_BASE}/{api_ver}/{phone_id}/messages"
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": normalised,
                "type": "template",
                "template": template_payload,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        return {"success": False, "error": f"Network error: {e}"}

    data = {}
    try:
        data = resp.json()
    except ValueError:
        pass

    if resp.status_code == 200 and data.get("messages"):
        return {
            "success": True,
            "wamid": data["messages"][0].get("id"),
            "status": resp.status_code,
        }

    err = data.get("error", {}) if isinstance(data, dict) else {}
    msg = err.get("message") or err.get("error_user_msg") or resp.text or "Unknown error"
    return {"success": False, "error": msg, "status": resp.status_code}


def send_document(to, media_id, filename, caption=None, brand=None):
    """Send a plain document (PDF) message referencing a media_id.
    Used when a template has no document-header slot — we send the
    document as a separate follow-up message right after the template.

    Args:
        to: recipient phone
        media_id: value from upload_media(brand=<same_brand>)
        filename: name shown to recipient
        caption: optional short caption printed under the document
        brand: REQUIRED. Brand instance — MUST match the brand used
               to upload the media_id (Meta media IDs are WABA-scoped).

    Returns:
        dict with success/wamid/error/status (same shape as send_template).
    """
    token, phone_id, api_ver = _brand_creds(brand)

    normalised = normalize_phone(to)
    if not normalised:
        return {"success": False, "error": f"Invalid phone number: {to!r}"}

    doc_payload = {"id": media_id, "filename": filename}
    if caption:
        doc_payload["caption"] = caption

    url = f"{GRAPH_BASE}/{api_ver}/{phone_id}/messages"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": normalised,
                "type": "document",
                "document": doc_payload,
            },
            timeout=30,
        )
    except requests.RequestException as e:
        return {"success": False, "error": f"Network error: {e}"}

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200 and data.get("messages"):
        return {"success": True, "wamid": data["messages"][0].get("id"), "status": 200}

    err = data.get("error", {}) if isinstance(data, dict) else {}
    msg = err.get("message") or err.get("error_user_msg") or resp.text or "Unknown error"
    return {"success": False, "error": msg, "status": resp.status_code}


def upload_media(file_bytes, filename, mime_type="application/pdf", brand=None):
    """Upload a file to Meta's media store. Returns a media_id we can
    then reference from a template's document/image header.

    Media IDs are valid for 30 days on Meta's side — plenty for a one-shot
    template send that fires seconds after upload.

    Args:
        file_bytes / filename / mime_type — the payload.
        brand: REQUIRED. Brand instance whose WABA to upload against.
               Media IDs are WABA-scoped; a media_id uploaded via Bathqube
               cannot be referenced from a Vtspl template send. Uploading
               under the WRONG brand silently fails at send time later,
               so we require the caller to pass the intended brand
               up-front.

    Returns:
        dict:
            success (bool)
            media_id (str, when uploaded)
            error (str, when failed)
            status (HTTP status code)
    """
    token, phone_id, api_ver = _brand_creds(brand)

    url = f"{GRAPH_BASE}/{api_ver}/{phone_id}/media"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (filename, io.BytesIO(file_bytes), mime_type)},
            data={"messaging_product": "whatsapp", "type": mime_type},
            timeout=30,
        )
    except requests.RequestException as e:
        return {"success": False, "error": f"Network error: {e}"}

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200 and data.get("id"):
        return {"success": True, "media_id": data["id"], "status": 200}

    err = data.get("error", {}) if isinstance(data, dict) else {}
    msg = err.get("message") or err.get("error_user_msg") or resp.text or "Unknown error"
    return {"success": False, "error": msg, "status": resp.status_code}


def send_template_with_document(to, template_name, media_id, filename,
                                 language="en", body_variables=None, brand=None):
    """Send an approved template that has a DOCUMENT header slot,
    referencing a media_id from `upload_media`.

    Args:
        to: recipient phone (any common format — normalised internally)
        template_name: exact template name as approved by Meta
        media_id: value returned from upload_media(brand=<same_brand>)
        filename: name shown to the recipient (e.g. "Bathqube-Quote.pdf")
        language: language code matching the approved template
        body_variables: list of strings for {{1}}, {{2}}, ... in the body
                        (pass None if the template body has no placeholders)
        brand: REQUIRED. Brand instance — MUST match the brand the media
               was uploaded under (Meta media IDs are WABA-scoped).

    Returns:
        Same shape as send_template().
    """
    token, phone_id, api_ver = _brand_creds(brand)

    normalised = normalize_phone(to)
    if not normalised:
        return {"success": False, "error": f"Invalid phone number: {to!r}"}

    components = [{
        "type": "header",
        "parameters": [{
            "type": "document",
            "document": {"id": media_id, "filename": filename},
        }],
    }]
    if body_variables:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(v)} for v in body_variables],
        })

    url = f"{GRAPH_BASE}/{api_ver}/{phone_id}/messages"
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": normalised,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language},
                    "components": components,
                },
            },
            timeout=30,
        )
    except requests.RequestException as e:
        return {"success": False, "error": f"Network error: {e}"}

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200 and data.get("messages"):
        return {"success": True, "wamid": data["messages"][0].get("id"), "status": 200}

    err = data.get("error", {}) if isinstance(data, dict) else {}
    msg = err.get("message") or err.get("error_user_msg") or resp.text or "Unknown error"
    return {"success": False, "error": msg, "status": resp.status_code}
