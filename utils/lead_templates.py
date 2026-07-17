"""
Lead-facing WhatsApp template catalogue.

Central source of truth for which templates BD can send to leads from
/leads (single-lead "Send" button) or /leads bulk action.

Each entry answers:
  - what's the human-facing dropdown label?
  - what language code does Meta have this template approved in?
  - does it need a document header (catalogue PDF)?
  - how many body variables does {{1}}/{{2}}/... need?

Add a template here → it appears in the BD dropdown automatically. Meta
still needs to approve the template on its side; this file just tells
vcore how to CALL it.
"""

from __future__ import annotations

import os
from typing import Optional


# Repo-relative path to the catalogue PDF. Bundled in vcore/assets/ so a
# vcore deploy carries it with the code. See vcore/assets/README.md for
# how to swap it. Resolved to an absolute path at send time so unit tests
# and Lambda + local both work.
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
# On-disk filename (what BD replaces to swap the catalogue).
CATALOGUE_PDF_PATH = os.path.join(_ASSETS_DIR, "bathqube-catalog.pdf")
# Customer-facing filename shown as the WhatsApp attachment title.
CATALOGUE_PDF_FILENAME = "Bathqube-Catalog.pdf"


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
    ):
        self.name = name
        self.label = label
        self.language = language
        self.needs_document = needs_document
        self.document_path = document_path
        self.document_filename = document_filename
        # Number of body placeholders ({{1}}, {{2}}, …). For lead-facing
        # templates we currently only pass first_name as {{1}}, so 0 or 1
        # covers every case. Higher counts would need per-template logic.
        self.body_var_count = body_var_count

    def to_dropdown_dict(self) -> dict:
        """Serialised shape for the Jinja dropdown."""
        return {"name": self.name, "label": self.label, "needs_document": self.needs_document}


# Registered templates, in dropdown order.
LEAD_TEMPLATES: list[LeadTemplate] = [
    LeadTemplate(
        name="welcome",
        label="Welcome",
        language="en",
        needs_document=False,
        body_var_count=1,
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
    ),
]

_LOOKUP = {t.name: t for t in LEAD_TEMPLATES}


def get_lead_template(name: str) -> Optional[LeadTemplate]:
    """Return the LeadTemplate for `name`, or None if unknown."""
    return _LOOKUP.get(name)


def build_body_variables(template: LeadTemplate, lead) -> list[str]:
    """Build the list of {{n}} body variables for a lead + template pair.

    Currently only maps `first_name` (the recipient's first token of their
    display name), matching every existing lead-facing template. If a new
    template needs different vars, extend this function per template.
    """
    if template.body_var_count == 0:
        return []
    first_name = (lead.name or "there").strip().split()[0] if lead.name else "there"
    return [first_name]
