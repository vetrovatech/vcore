"""
Migration: add bathqube_quote_items table + new columns on bathqube_quotes
(gst_percentage, has_revision). Idempotent.
"""

from app import app, db
from models import BathqubeQuoteItem  # noqa: F401
from sqlalchemy import text, inspect


ALTERS = [
    "ALTER TABLE bathqube_quotes ADD COLUMN gst_percentage NUMERIC(5,2) NOT NULL DEFAULT 18",
    "ALTER TABLE bathqube_quotes ADD COLUMN has_revision BOOLEAN NOT NULL DEFAULT FALSE",
]


def migrate():
    with app.app_context():
        # New table via create_all (idempotent — only creates if missing)
        print("Creating bathqube_quote_items table if missing...")
        db.create_all()

        # ADD COLUMN — wrapped per-statement so duplicates don't kill the whole migration
        with db.engine.connect() as conn:
            for sql in ALTERS:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    print(f"  ran: {sql}")
                except Exception as e:
                    print(f"  skip: {sql.split(' ADD COLUMN ')[-1].split()[0]} — {type(e).__name__}")
                    conn.rollback()

        # Verify
        insp = inspect(db.engine)
        tables = insp.get_table_names()
        cols = {c['name'] for c in insp.get_columns('bathqube_quotes')}
        print()
        print("  bathqube_quote_items:", "ok" if "bathqube_quote_items" in tables else "MISSING")
        print("  gst_percentage col :", "ok" if "gst_percentage" in cols else "MISSING")
        print("  has_revision col   :", "ok" if "has_revision" in cols else "MISSING")
        print("\nDone.")


if __name__ == '__main__':
    migrate()
