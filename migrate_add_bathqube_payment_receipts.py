"""
Migration: add bathqube_payment_receipts table + cutting_notes column.

Backs the new fulfillment paperwork features on the Bathqube quote flow:
  - bathqube_payment_receipts  — one row per inflow (UTR-level audit).
                                 Sales records 4 partial payments → 4 rows,
                                 each printable as its own receipt PDF.
  - bathqube_work_orders.cutting_notes — workshop-specific free-text
                                         instructions printed on the
                                         glass-cutting WO PDF.

Idempotent:
  - db.create_all() creates the new table only if missing.
  - The ADD COLUMN uses information_schema to no-op on re-run.
Existing rows on bathqube_quotes / bathqube_work_orders are untouched.

Run via docker-compose:
    docker-compose run --rm vcore python migrate_add_bathqube_payment_receipts.py
or directly with DATABASE_URL exported:
    python migrate_add_bathqube_payment_receipts.py
"""

from sqlalchemy import inspect, text

from app import app, db
from models import BathqubePaymentReceipt, BathqubeWorkOrder  # noqa: F401


def migrate():
    with app.app_context():
        print("Creating bathqube_payment_receipts table (if missing)...")
        db.create_all()

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        ok = True

        # 1) New table check
        if 'bathqube_payment_receipts' in tables:
            print("  ok  bathqube_payment_receipts")
        else:
            print("  FAIL bathqube_payment_receipts not created")
            ok = False

        # 2) cutting_notes column on bathqube_work_orders. db.create_all()
        # doesn't add columns to existing tables, so we ALTER manually
        # only if missing.
        cols = {c['name'] for c in inspector.get_columns('bathqube_work_orders')}
        if 'cutting_notes' in cols:
            print("  ok  bathqube_work_orders.cutting_notes (already exists)")
        else:
            print("  adding bathqube_work_orders.cutting_notes ...")
            with db.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE bathqube_work_orders ADD COLUMN cutting_notes TEXT"
                ))
            print("  ok  bathqube_work_orders.cutting_notes")

        if ok:
            print("\nMigration completed.")
        else:
            print("\nMigration failed.")
        return ok


if __name__ == '__main__':
    migrate()
