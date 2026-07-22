"""
Lead-facing WhatsApp template catalogue.

Central source of truth for which templates BD can send to leads from
/leads (single-lead "Send" button) or /leads bulk action, plus the
Bulk Send (marketing) screen.

Each entry answers:
  - what's the human-facing dropdown label?
  - what language code does Meta have this template approved in?
  - does it need a document header (catalogue PDF)?
  - how many body variables does {{1}}/{{2}}/... need?
  - how do we build those variables from a recipient object?

Add a template here → it appears in the BD dropdown automatically. Meta
still needs to approve the template on its side; this file just tells
vcore how to CALL it.
"""

from __future__ import annotations

import os
from typing import Callable, Optional


# Repo-relative path to the catalogue PDF. Bundled in vcore/assets/ so a
# vcore deploy carries it with the code. See vcore/assets/README.md for
# how to swap it. Resolved to an absolute path at send time so unit tests
# and Lambda + local both work.
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
# On-disk filename (what BD replaces to swap the catalogue).
CATALOGUE_PDF_PATH = os.path.join(_ASSETS_DIR, "bathqube-catalog.pdf")
# Customer-facing filename shown as the WhatsApp attachment title.
CATALOGUE_PDF_FILENAME = "Bathqube-Catalog.pdf"


class MissingVariable(Exception):
    """Raised by a template's var_builder when a required field is empty
    on the recipient. The bulk-send route catches this and skips the
    recipient with a per-row failure entry, rather than sending a garbage
    message with an empty {{n}} placeholder that Meta may reject
    template-side."""

    def __init__(self, field: str, recipient_id: Optional[int] = None):
        self.field = field
        self.recipient_id = recipient_id
        super().__init__(f'missing {field}')


class LeadTemplate:
    """One template BD can pick from the dropdown."""

    def __init__(
        self,
        name: str,
        label: str,
        language: str = "en",
        needs_document: bool = False,
        document_path: Optional[str] = None,
        document_filename: Optional[str] = None,
        body_var_count: int = 1,
        var_builder: Optional[Callable[[object], list[str]]] = None,
    ):
        self.name = name
        self.label = label
        self.language = language
        self.needs_document = needs_document
        self.document_path = document_path
        self.document_filename = document_filename
        # Number of body placeholders ({{1}}, {{2}}, …). Kept for
        # documentation; the actual variable list comes from var_builder.
        self.body_var_count = body_var_count
        # Optional per-template variable builder.
        #
        # Called as `var_builder(recipient)` where `recipient` duck-types
        # to whatever the callable expects (Lead / BulkContact / shim).
        # Should return a list[str] of body variables IN ORDER
        # ({{1}}, {{2}}, …). Raise MissingVariable(field) to abort the
        # send for this recipient (bulk-send treats it as a skip).
        #
        # When None, falls back to the default builder in
        # `build_body_variables()` — first-name-only, the shape every
        # legacy lead-facing template used before 2026-07-21.
        self.var_builder = var_builder

    def to_dropdown_dict(self) -> dict:
        """Serialised shape for the Jinja dropdown."""
        return {"name": self.name, "label": self.label, "needs_document": self.needs_document}


# ── Per-template variable builders ──────────────────────────────────

def _first_name_only(recipient) -> list[str]:
    """Legacy default — {{1}} = first token of the display name.
    Used by `welcome` and `general_followup`."""
    name = getattr(recipient, 'name', None) or ''
    first = name.strip().split()[0] if name.strip() else 'there'
    return [first]


def _glassy_onboarding_invite_vars(recipient) -> list[str]:
    """Body-variable builder for the Glassy India onboarding invite.
    Template text (as approved on Meta):

        Hello {{1}} 🙏  … your {{2}}⭐ Google rating.
        You can view your live listing here: {{3}}

    Vars come from the imported BulkContact:
        {{1}} = full business name (recipient.name)
        {{2}} = star rating from the directory (recipient.star_rating)
        {{3}} = the glassy.in listing URL (recipient.listing_url)

    Raises MissingVariable when any of the three is empty so the caller
    can skip cleanly (Meta rejects blank placeholders template-side)."""
    rid = getattr(recipient, 'id', None)
    name = (getattr(recipient, 'name', None) or '').strip()
    if not name:
        raise MissingVariable('name', rid)
    star = getattr(recipient, 'star_rating', None)
    if star is None or str(star).strip() in ('', '0', '0.0'):
        raise MissingVariable('star_rating', rid)
    url = (getattr(recipient, 'listing_url', None) or '').strip()
    if not url:
        raise MissingVariable('listing_url', rid)
    # Meta shows the value as-typed — a trailing `.0` on a whole number
    # (5.0 → "5.0") reads a bit unnatural but is faithful. Normalise
    # to "4.5" / "5" style: strip .0 on integers.
    try:
        f = float(star)
    except (TypeError, ValueError):
        f = 0.0
    star_str = f'{int(f)}' if abs(f - int(f)) < 0.05 else f'{f:.1f}'
    return [name, star_str, url]


# ── Registered templates, in dropdown order ─────────────────────────
LEAD_TEMPLATES: list[LeadTemplate] = [
    LeadTemplate(
        name="welcome",
        label="Welcome",
        language="en",
        needs_document=False,
        body_var_count=1,
        var_builder=_first_name_only,
    ),
    LeadTemplate(
        name="general_followup",
        label="General Followup",
        language="en",
        # 2026-07-17: BD updated the Meta-side template to plain-body
        # (no document header). Catalogue attachment removed. Keeping
        # CATALOGUE_PDF_PATH / CATALOGUE_PDF_FILENAME constants around
        # so a future document-header template can reuse them without
        # having to re-derive the path.
        needs_document=False,
        body_var_count=1,
        var_builder=_first_name_only,
    ),
    LeadTemplate(
        # Marketing template for the Glassy India directory outreach
        # campaign (2026-07-21). Sent from Bulk Send to imported
        # BulkContacts populated from the Glassy India directory Excel.
        name="glassy_onboarding_invite",
        label="Glassy Directory Invite",
        language="en",
        needs_document=False,
        body_var_count=3,
        var_builder=_glassy_onboarding_invite_vars,
    ),
]

_LOOKUP = {t.name: t for t in LEAD_TEMPLATES}


def get_lead_template(name: str) -> Optional[LeadTemplate]:
    """Return the LeadTemplate for `name`, or None if unknown."""
    return _LOOKUP.get(name)


def build_body_variables(template: LeadTemplate, recipient) -> list[str]:
    """Build the list of {{n}} body variables for a recipient + template.
    Uses the template's own var_builder when set; otherwise falls back
    to the legacy first-name-only shape. May raise MissingVariable
    (caller handles by skipping the recipient with a failure entry)."""
    if template.body_var_count == 0:
        return []
    if template.var_builder is not None:
        return template.var_builder(recipient)
    return _first_name_only(recipient)
