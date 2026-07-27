"""
Migration — Vetrova quotes Phase 1: add line-items table + billing columns.

Adds:
  - `vetrova_quote_items` table (mirrors the wire runs[] shape)
  - `vetrova_quotes.subtotal / transport_charges / cgst / sgst /
     gst_percentage / grand_total / amount_received / revision_count /
     validity_days` columns

Backfills existing single-row VetrovaQuote rows into one item each so
the /quotes/vetrova/<id> view keeps working without re-ingest.

Local docker DATABASE_URL points at prod Postgres — any run of this
script is a PROD change. Safe to re-run (idempotent).
"""

from decimal import Decimal
import json
from sqlalchemy import inspect, text

from app import app, db
from models import VetrovaQuote, VetrovaQuoteItem  # noqa: F401


def _column_exists(inspector, table, col):
    return col in {c['name'] for c in inspector.get_columns(table)}


def migrate():
    with app.app_context():
        print("Running Vetrova quotes Phase-1 migration...")
        engine = db.engine
        inspector = inspect(engine)

        # 1) Create vetrova_quote_items (no-op if already present).
        print("Creating vetrova_quote_items table (if missing)...")
        db.create_all()

        tables = set(inspector.get_table_names())
        if 'vetrova_quote_items' not in tables:
            print("  FAIL — vetrova_quote_items not created")
            return False
        print("  ok  vetrova_quote_items")

        # 2) Add new columns to vetrova_quotes.
        new_cols = [
            ('subtotal',          'NUMERIC(12,2) NOT NULL DEFAULT 0'),
            ('transport_charges', 'NUMERIC(10,2) NOT NULL DEFAULT 0'),
            ('cgst',              'NUMERIC(12,2) NOT NULL DEFAULT 0'),
            ('sgst',              'NUMERIC(12,2) NOT NULL DEFAULT 0'),
            ('gst_percentage',    'NUMERIC(5,2)  NOT NULL DEFAULT 18'),
            ('grand_total',       'NUMERIC(12,2) NOT NULL DEFAULT 0'),
            ('amount_received',   'NUMERIC(12,2) NOT NULL DEFAULT 0'),
            ('revision_count',    'INTEGER       NOT NULL DEFAULT 0'),
            ('validity_days',     'INTEGER       NOT NULL DEFAULT 10'),
        ]
        with engine.begin() as conn:
            existing = {c['name'] for c in inspector.get_columns('vetrova_quotes')}
            for col, ddl in new_cols:
                if col in existing:
                    print(f"  ok  vetrova_quotes.{col} (already present)")
                    continue
                print(f"  add vetrova_quotes.{col}")
                conn.execute(text(f'ALTER TABLE vetrova_quotes ADD COLUMN {col} {ddl}'))

        # 3) Backfill: for every VetrovaQuote that has NO items yet, create
        # one item from the parent's legacy fields. Grand-total mirrors
        # the pre-tax `total` the customer saw; recompute_totals() then
        # derives GST + grand_total consistently.
        print("Backfilling legacy quotes into items...")
        backfilled = 0
        # Refresh inspector after adding columns so the ORM sees them.
        db.session.close()
        for q in VetrovaQuote.query.all():
            if q.items:
                continue
            item = VetrovaQuoteItem(
                quote_id=q.id,
                sort_order=1,
                category_slug=q.category_slug,
                category_label=q.category_label,
                selections=q.selections,
                dimension_kind='running_feet' if q.category_slug in
                    ('balcony', 'staircase', 'railings', 'storage', 'folding-glass') else 'square_feet',
                dimension_unit='ft',
                running_ft=q.running_ft or 0,
                quantity=q.quantity or 1,
                panels=None,
                fabric_code=None,
                uploaded_image_data_url=None,
                rate_per_unit=Decimal('0'),
                subtotal=q.total or 0,
                notes=None,
            )
            db.session.add(item)
            q.recompute_totals()
            backfilled += 1
        db.session.commit()
        print(f"  ok  backfilled {backfilled} legacy quote(s) into single items")

        print("\nMigration completed.")
        return True


if __name__ == '__main__':
    ok = migrate()
    raise SystemExit(0 if ok else 1)
