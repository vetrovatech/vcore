"""
Migration — Vetrova quote items: add `uploaded_images` column.

Background: 2026-08-14, glassyplatform PDPs started letting Printed
Glass customers attach several designs to ONE line item. The wire
payload gained a `uploadedImages: [{dataUrl, filename?, source?,
galleryCode?}]` array; vcore's ingest handler was updated to persist
it, but the column doesn't exist yet on prod. This script adds it.

Idempotent — skips work if the column is already there.

Local docker DATABASE_URL points at prod Postgres — any run of this
script is a PROD change.

Run:
    docker exec -it vcore python migrate_add_uploaded_images.py
"""

from sqlalchemy import inspect, text

from app import app, db


TABLE = 'vetrova_quote_items'
COLUMN = 'uploaded_images'


def _column_exists(inspector, table, col):
    return col in {c['name'] for c in inspector.get_columns(table)}


def migrate():
    with app.app_context():
        print('Running vetrova_quote_items.uploaded_images migration…')
        engine = db.engine
        inspector = inspect(engine)

        if TABLE not in inspector.get_table_names():
            print(f'  FAIL — table {TABLE} does not exist')
            return False

        if _column_exists(inspector, TABLE, COLUMN):
            print(f'  ok  {TABLE}.{COLUMN} already exists — no-op')
            return True

        print(f'  adding {TABLE}.{COLUMN} …')
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {TABLE} ADD COLUMN {COLUMN} TEXT'))
        print(f'  ok  added {TABLE}.{COLUMN}')

        # Verify.
        inspector = inspect(engine)
        if _column_exists(inspector, TABLE, COLUMN):
            print('DONE')
            return True
        print('  FAIL — column not visible after add')
        return False


if __name__ == '__main__':
    ok = migrate()
    raise SystemExit(0 if ok else 1)
