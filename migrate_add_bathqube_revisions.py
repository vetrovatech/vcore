"""Migration: add revision audit log for Bathqube quotes.

Adds:
  - bathqube_quotes.revision_count   INT NOT NULL DEFAULT 0
        Fast lookup for "how many times has this bill been revised". Bumped
        each time the sales person clicks Save in the revise UI.

  - bathqube_quote_revisions TABLE
        Audit trail. One row per revision, captures before/after totals plus
        a JSON snapshot of items + enclosures at the moment of save. Used by
        the view page's "Revision history" card.

Run directly with DATABASE_URL set:
    python migrate_add_bathqube_revisions.py
"""

import os
import psycopg2
from psycopg2 import errors as pg_errors


COLUMN_ALTERS = [
    ("bathqube_quotes", "revision_count", "INTEGER NOT NULL DEFAULT 0"),
]

CREATE_TABLES = [
    ("bathqube_quote_revisions", """
        CREATE TABLE IF NOT EXISTS bathqube_quote_revisions (
            id                SERIAL PRIMARY KEY,
            quote_id          INTEGER NOT NULL REFERENCES bathqube_quotes(id) ON DELETE CASCADE,
            revision_number   INTEGER NOT NULL,
            prev_subtotal     NUMERIC(12,2),
            new_subtotal      NUMERIC(12,2),
            prev_total        NUMERIC(12,2),
            new_total         NUMERIC(12,2),
            discount_percent  NUMERIC(5,2),
            snapshot          TEXT,
            triggered_by      INTEGER REFERENCES users(id),
            created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """),
]

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_bathqube_quote_revisions_quote_id ON bathqube_quote_revisions(quote_id)",
    "CREATE INDEX IF NOT EXISTS idx_bathqube_quote_revisions_created ON bathqube_quote_revisions(created_at DESC)",
]


def migrate():
    url = os.environ['DATABASE_URL'].replace('+psycopg2', '')
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    print("=== Add columns ===")
    for table, col, decl in COLUMN_ALTERS:
        try:
            cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} {decl}')
            print(f"  ✅ ran:  ALTER {table} ADD {col}")
        except pg_errors.DuplicateColumn:
            print(f"  ↪ skip: {table}.{col} already exists")
        except Exception as e:
            print(f"  ❌ FAIL: {table}.{col} — {type(e).__name__}: {e}")

    print()
    print("=== Create tables ===")
    for table, ddl in CREATE_TABLES:
        try:
            cur.execute(ddl)
            print(f"  ✅ ran:  CREATE TABLE IF NOT EXISTS {table}")
        except Exception as e:
            print(f"  ❌ FAIL: {table} — {type(e).__name__}: {e}")

    print()
    print("=== Create indexes ===")
    for ddl in CREATE_INDEXES:
        try:
            cur.execute(ddl)
            print(f"  ✅ ran:  {ddl.split('IF NOT EXISTS ')[1].split(' ')[0]}")
        except Exception as e:
            print(f"  ❌ FAIL: {type(e).__name__}: {e}")

    print()
    print("=== Verify ===")
    cur.execute("""
        SELECT data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name='bathqube_quotes' AND column_name='revision_count'
    """)
    row = cur.fetchone()
    if row:
        print(f"  ✅ bathqube_quotes.revision_count  type={row[0]} nullable={row[1]} default={row[2]}")
    else:
        print(f"  ❌ bathqube_quotes.revision_count  MISSING")

    cur.execute("""
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_name='bathqube_quote_revisions' ORDER BY ordinal_position
    """)
    cols = cur.fetchall()
    if cols:
        print(f"  ✅ bathqube_quote_revisions table — {len(cols)} columns:")
        for name, dtype in cols:
            print(f"      {name:20} {dtype}")
    else:
        print(f"  ❌ bathqube_quote_revisions table MISSING")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == '__main__':
    migrate()
