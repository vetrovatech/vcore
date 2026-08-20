"""backfill_vetrova_quote_leads.py

Mirror historic vetrova.in quotations into Leadfy.

Rules (BD 2026-08-19), identical to the live ingest hook in app.py:
  * ONE LEAD PER CUSTOMER, matched on the last 10 phone digits.
    64 quotes came from 20 numbers; a lead-per-quote would show BD 64 rows
    for 20 people.
  * A customer already in Leadfy (Facebook / IndiaMart / …) keeps their
    existing lead, origin and assignee, and gains a history note. Rewriting
    their origin would destroy campaign attribution; a second row would
    split the conversation.
  * New leads get origin 'vetrova.in', stage 'New Lead', unassigned.

TEST DATA IS EXCLUDED. 47 of the 60 website quotes came from four internal
numbers — the dev's own handset, two obvious debug numbers, and the company's
published phone. Importing those would create leads called "Test Debug" and
"Debug 3" and pile 29 notes onto one lead. Pass --include-test to override.

Raw psycopg2 ON PURPOSE: importing app.py runs module-level bootstrap
(brand upserts, CREATE TABLE IF NOT EXISTS, ALTER TABLE attempts) against
production. A dry run must not do that.

⚠️ WRITES TO PRODUCTION. Dry-run by default; --commit applies.
"""
import re
import sys

import psycopg2

COMMIT = '--commit' in sys.argv
INCLUDE_TEST = '--include-test' in sys.argv
ACTOR = 'ansar'          # lead_history.user_id is NOT NULL

# Internal / test handsets — see the module docstring.
TEST_PHONES = {
    '8197618457',   # developer's own number, 29 quotes ("ansar", "ann", …)
    '9999999999',   # "Debug 3", "Legacy Test", "Multi-run Test"
    '1234567890',   # "Test Debug", "Debug V4"
    '8550011196',   # the company's published phone (vetrova.in footer)
}


def last10(phone):
    return re.sub(r'\D', '', str(phone or ''))[-10:]


def db():
    env = {}
    for line in open('.env'):
        m = re.match(r'^\s*([A-Z_0-9]+)\s*=\s*(.*?)\s*$', line)
        if m:
            env[m.group(1)] = m.group(2).strip('"\'')
    url = env.get('DATABASE_URL') or env.get('DATABASE_URI')
    return psycopg2.connect(url.replace('postgresql+psycopg2://', 'postgresql://'))


conn = db()
conn.autocommit = False
cur = conn.cursor()

cur.execute("SELECT id FROM users WHERE username = %s", (ACTOR,))
row = cur.fetchone()
if not row:
    sys.exit(f'No user {ACTOR!r} to attribute history rows to')
actor_id = row[0]

cur.execute("""SELECT id, quote_ref, customer_name, phone, email, category_label,
                      COALESCE(grand_total, total, 0), created_at
                 FROM vetrova_quotes
                WHERE source = 'ingest'
                ORDER BY created_at ASC""")
quotes = cur.fetchall()

print(f"=== vetrova.in quotes → Leadfy {'(COMMIT)' if COMMIT else '(DRY RUN)'} ===")
print(f"  {len(quotes)} website quote(s); test numbers "
      f"{'INCLUDED' if INCLUDE_TEST else 'excluded'}\n")

created = notes = skipped_test = skipped_nophone = 0
handled = {}

for qid, ref, name, phone, email, cat, total, created_at in quotes:
    digits = last10(phone)
    if not digits:
        skipped_nophone += 1
        continue
    if digits in TEST_PHONES and not INCLUDE_TEST:
        skipped_test += 1
        continue

    blurb = f'Quote {ref} · {cat} · ₹{float(total):,.0f}'

    cur.execute("""SELECT id, origin FROM leads
                    WHERE right(regexp_replace(contact, '[^0-9]', '', 'g'), 10) = %s
                    ORDER BY created_at ASC LIMIT 1""", (digits,))
    existing = cur.fetchone()

    if existing:
        lead_id, origin = existing
        notes += 1
        where = handled.get(digits) or f'existing lead #{lead_id} (origin {origin})'
        print(f"  {ref:16s} {str(name)[:20]:20s} note → {where}")
        if COMMIT:
            cur.execute("""INSERT INTO lead_history (lead_id, user_id, action, description, created_at)
                           VALUES (%s, %s, 'note', %s, NOW())""",
                        (lead_id, actor_id,
                         f'Generated a quotation on vetrova.in — {blurb}'))
        handled.setdefault(digits, f'lead #{lead_id}')
        continue

    created += 1
    print(f"  {ref:16s} {str(name)[:20]:20s} NEW lead (origin vetrova.in)")
    if COMMIT:
        cur.execute("""INSERT INTO leads
                         (name, contact, email, origin, stage, lead_type,
                          product_interest, notes, owner_id, assigned_to_id,
                          created_by, created_at, updated_at, is_untouched)
                       VALUES (%s,%s,%s,%s,'New Lead','Enquiry',%s,%s,NULL,NULL,%s,NOW(),NOW(),TRUE)
                       RETURNING id""",
                    (name or None, phone or None, email or None,
                     'vetrova.in', cat or None, blurb, actor_id))
        lead_id = cur.fetchone()[0]
        cur.execute("""INSERT INTO lead_history (lead_id, user_id, action, description, created_at)
                       VALUES (%s, %s, 'created', %s, NOW())""",
                    (lead_id, actor_id,
                     f'Lead created from a vetrova.in quotation — {blurb}'))
        handled[digits] = f'lead #{lead_id}'
    else:
        handled[digits] = 'the lead created above'

print(f"\n  new leads: {created}   notes on existing: {notes}   "
      f"skipped(test): {skipped_test}   skipped(no phone): {skipped_nophone}")

if COMMIT:
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM leads WHERE origin = 'vetrova.in'")
    print(f"  ✓ committed — leads with origin 'vetrova.in': {cur.fetchone()[0]}")
else:
    conn.rollback()
    print("  rolled back — re-run with --commit to apply")
conn.close()
