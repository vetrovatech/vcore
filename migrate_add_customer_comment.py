"""migrate_add_customer_comment.py

Adds `vetrova_quote_items.customer_comment` (TEXT, nullable).

WHY: BD 2026-08-18 asked for "option to add comment along with every panel
across every category", visible on the generated quote and in vcore when BD
edits. Panel-based categories carry their note inside the existing
`panels` JSON (one `comment` key per panel — no schema change needed there,
the column is free-form JSON text). But railings and staircase are priced
per running foot and have NO panels, so their single line-level note has
nowhere to live. Hence this column.

DELIBERATELY NOT `notes`: that column already exists and is documented as
"BD's private note on this line". Customer-written text must not land in a
field BD treats as internal — they'd be indistinguishable in the revise
form, and BD notes are not meant to be echoed back to the customer.

Idempotent: checks information_schema first, so re-running is a no-op.

⚠️ Runs against whatever DATABASE_URL points at — which locally is PROD.
"""
import os
import re
import sys

import psycopg2


def _database_url():
    url = os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_URI')
    if not url:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        try:
            for line in open(env_path):
                m = re.match(r'^\s*(DATABASE_URL|DATABASE_URI)\s*=\s*(.*?)\s*$', line)
                if m:
                    url = m.group(2).strip('"\'')
                    break
        except OSError:
            pass
    if not url:
        sys.exit('No DATABASE_URL / DATABASE_URI found')
    # SQLAlchemy-style driver prefix is not a valid libpq DSN.
    return url.replace('postgresql+psycopg2://', 'postgresql://')


def main():
    conn = psycopg2.connect(_database_url())
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(
        """SELECT 1 FROM information_schema.columns
            WHERE table_name = 'vetrova_quote_items'
              AND column_name = 'customer_comment'"""
    )
    if cur.fetchone():
        print('customer_comment already exists — nothing to do')
        conn.close()
        return

    print('adding vetrova_quote_items.customer_comment …')
    cur.execute('ALTER TABLE vetrova_quote_items ADD COLUMN customer_comment TEXT')
    conn.commit()

    cur.execute(
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_name = 'vetrova_quote_items'
              AND column_name = 'customer_comment'"""
    )
    print('  ->', cur.fetchone())
    conn.close()
    print('done')


if __name__ == '__main__':
    main()
