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


def send_template(to, template_name, language="en", variables=None):
    """
    Send an approved WhatsApp template.

    Args:
        to: recipient phone (any common format — normalised internally)
        template_name: exact template name as approved by Meta
        language: language code matching the approved template (e.g. 'en', 'en_US', 'hi')
        variables: list of strings for {{1}}, {{2}}, ... in the template body

    Returns:
        dict with keys:
          success (bool)
          wamid   (Meta's message id, when sent)
          error   (str, when failed)
          status  (HTTP status code from Graph API)
    """
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
