"""backfill_kashif_leads.py

One-off: assign to Kashif the leads that should already have been his.

Two groups, both invisible to him today because non-managers only see
leads where assigned_to_id == their own id:

  A. Printed_glass campaign leads that arrived before the auto-routing
     rule existed and were never bulk-assigned (the 61 others were, by
     hand, one batch at a time).
  B. Leads Kashif created himself before lead_new() started honouring
     the "Assign To" field — born unassigned, so he could not see the
     lead he had just filed.

Writes a lead_history row per lead in the SAME shape the revise handler
writes, so the change is auditable and does not look like it happened by
magic. user_id is the admin running the backfill (lead_history.user_id is
NOT NULL, so it needs a real user).

Only touches leads that are still unassigned — never reassigns anyone.

⚠️ WRITES TO PRODUCTION. Dry-run by default; --commit applies.
"""
import re
import sys

import psycopg2

COMMIT = '--commit' in sys.argv
ASSIGNEE = 'Kashif'
ACTOR = 'ansar'          # admin on whose behalf the backfill is recorded


def db():
    env = {}
    for line in open('.env'):
        m = re.match(r'^\s*([A-Z_0-9]+)\s*=\s*(.*?)\s*$', line)
        if m:
            env[m.group(1)] = m.group(2).strip('"\'')
    url = (env.get('DATABASE_URL') or env.get('DATABASE_URI'))
    return psycopg2.connect(url.replace('postgresql+psycopg2://', 'postgresql://'))


conn = db()
conn.autocommit = False
cur = conn.cursor()

cur.execute("SELECT id FROM users WHERE username = %s AND is_active", (ASSIGNEE,))
row = cur.fetchone()
if not row:
    sys.exit(f'No active user {ASSIGNEE!r}')
assignee_id = row[0]

cur.execute("SELECT id FROM users WHERE username = %s", (ACTOR,))
row = cur.fetchone()
if not row:
    sys.exit(f'No user {ACTOR!r} to attribute the history row to')
actor_id = row[0]

cur.execute(
    """SELECT l.id, l.name, l.fb_campaign_name, u.username AS creator, l.created_at
         FROM leads l LEFT JOIN users u ON u.id = l.created_by
        WHERE l.assigned_to_id IS NULL
          AND ( l.fb_campaign_name = 'Printed_glass'
                OR u.username = %s )
        ORDER BY l.created_at""", (ASSIGNEE,))
targets = cur.fetchall()

print(f"=== backfill → {ASSIGNEE} (id {assignee_id}) {'(COMMIT)' if COMMIT else '(DRY RUN)'} ===")
if not targets:
    print('  nothing to do')
    conn.close()
    sys.exit(0)

for lid, name, campaign, creator, created in targets:
    why = 'Printed_glass campaign' if campaign == 'Printed_glass' else f'created by {creator}'
    print(f"  lead {lid:5d}  {str(name)[:22]:22s}  {created:%Y-%m-%d %H:%M}  ({why})")
    if COMMIT:
        cur.execute("UPDATE leads SET assigned_to_id = %s WHERE id = %s AND assigned_to_id IS NULL",
                    (assignee_id, lid))
        cur.execute(
            """INSERT INTO lead_history (lead_id, user_id, action, description, created_at)
               VALUES (%s, %s, 'field_change', %s, NOW())""",
            (lid, actor_id,
             f'Assigned To changed from <strong>Unassigned</strong> to '
             f'<strong>{ASSIGNEE}</strong> (backfill)'))

if COMMIT:
    conn.commit()
    cur.execute("""SELECT COUNT(*) FROM leads l LEFT JOIN users u ON u.id = l.created_by
                    WHERE l.assigned_to_id IS NULL
                      AND (l.fb_campaign_name = 'Printed_glass' OR u.username = %s)""", (ASSIGNEE,))
    print(f"\n  ✓ {len(targets)} lead(s) assigned. Still unassigned in these groups: {cur.fetchone()[0]}")
else:
    print(f"\n  {len(targets)} lead(s) would be assigned. Re-run with --commit.")
conn.close()
