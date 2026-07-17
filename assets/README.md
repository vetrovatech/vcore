# vcore assets

Static files bundled with the vcore Flask app.

## `bathqube-catalog.pdf`

Bundled catalogue PDF. **Currently NOT attached** to any active WhatsApp
template — BD dropped the attachment from `general_followup` on
2026-07-17 (Meta-side template is plain body now). File kept in the
repo so a future document-header template can reference it via
`utils.lead_templates.CATALOGUE_PDF_PATH` without re-plumbing paths.

**If a document-header template is re-introduced later:**

1. Set the template's `needs_document=True` in `utils/lead_templates.py`
   and point `document_path=CATALOGUE_PDF_PATH`.
2. Replace this file if the catalogue content has changed.
3. Commit + `deploy-aws.sh`.

**Meta media IDs expire in 30 days** but the send code re-uploads on
every batch so this doesn't matter — no caching to invalidate.
