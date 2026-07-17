"""
WhatsApp Cloud API helper.

Env vars (set on Lambda):
  WHATSAPP_TOKEN            — permanent System User access token from Meta
  WHATSAPP_PHONE_NUMBER_ID  — Phone Number ID from API Setup page
  WHATSAPP_API_VERSION      — optional, defaults to v21.0

Phone-number normalization mirrors templates/leads/view.html: strip
spaces/dashes/parens/dots/+, prepend '91' if exactly 10 digits (Indian
number with no country code), otherwise use as-is.
"""

import io
import os
import re
import requests


GRAPH_BASE = "https://graph.facebook.com"


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
        brand: optional Brand instance whose WABA credentials should be used.
               When None, falls back to WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID
               env vars (single-tenant legacy path — kept for back-compat).

    Returns:
        dict with keys:
          success (bool)
          wamid   (Meta's message id, when sent)
          error   (str, when failed)
          status  (HTTP status code from Graph API)
    """
    if brand is not None:
        token = brand.wa_access_token or ""
        phone_id = brand.wa_phone_number_id or ""
        api_ver = brand.wa_api_version or "v21.0"
    else:
        token = os.getenv("WHATSAPP_TOKEN", "")
        phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        api_ver = os.getenv("WHATSAPP_API_VERSION", "v21.0")

    if not token or not phone_id:
        return {"success": False, "error": "WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID not configured"}

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


def send_document(to, media_id, filename, caption=None):
    """Send a plain document (PDF) message referencing a media_id.
    Used when a template has no document-header slot — we send the
    document as a separate follow-up message right after the template.

    Args:
        to: recipient phone
        media_id: value from upload_media()
        filename: name shown to recipient
        caption: optional short caption printed under the document

    Returns:
        dict with success/wamid/error/status (same shape as send_template).
    """
    token = os.getenv("WHATSAPP_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    api_ver = os.getenv("WHATSAPP_API_VERSION", "v21.0")

    if not token or not phone_id:
        return {"success": False, "error": "WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID not configured"}

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


def upload_media(file_bytes, filename, mime_type="application/pdf"):
    """Upload a file to Meta's media store. Returns a media_id we can
    then reference from a template's document/image header.

    Media IDs are valid for 30 days on Meta's side — plenty for a one-shot
    template send that fires seconds after upload.

    Returns:
        dict:
            success (bool)
            media_id (str, when uploaded)
            error (str, when failed)
            status (HTTP status code)
    """
    token = os.getenv("WHATSAPP_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    api_ver = os.getenv("WHATSAPP_API_VERSION", "v21.0")

    if not token or not phone_id:
        return {"success": False, "error": "WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID not configured"}

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
                                 language="en", body_variables=None):
    """Send an approved template that has a DOCUMENT header slot,
    referencing a media_id from `upload_media`.

    Args:
        to: recipient phone (any common format — normalised internally)
        template_name: exact template name as approved by Meta
        media_id: value returned from upload_media()
        filename: name shown to the recipient (e.g. "Bathqube-Quote.pdf")
        language: language code matching the approved template
        body_variables: list of strings for {{1}}, {{2}}, ... in the body
                        (pass None if the template body has no placeholders)

    Returns:
        Same shape as send_template().
    """
    token = os.getenv("WHATSAPP_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    api_ver = os.getenv("WHATSAPP_API_VERSION", "v21.0")

    if not token or not phone_id:
        return {"success": False, "error": "WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID not configured"}

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
