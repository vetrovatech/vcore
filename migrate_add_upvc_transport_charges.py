"""
Migration: add `transport_charges` column to `vetrova_upvc_quotes`.

BD ask 2026-07-21: on the UPVC quotation, BD wants to type an optional
Transportation Charges amount that:
  - shows on the customer PDF as its own line between Subtotal and CGST
  - is included in the taxable base (GST applies on subtotal + transport)
  - defaults to 0 so quotes with no delivery cost render unchanged

NUMERIC(10,2) matches the shape of `subtotal` / `total` / other money
columns on this table. Default 0 + NOT NULL means every existing row
gets a zero transport charge without needing a backfill statement.

Idempotent — safe to re-run.
"""

from sqlalchemy import text

from app import app, db


def column_exists(table: str, column: str) -> bool:
    row = db.session.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {'t': table, 'c': column},
    ).first()
    return row is not None


def migrate():
    with app.app_context():
        print('=== UPVC transport_charges migration ===')
        if column_exists('vetrova_upvc_quotes', 'transport_charges'):
            print('  ✓ transport_charges already exists, skipping')
        else:
            print('  adding vetrova_upvc_quotes.transport_charges …')
            with db.engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE vetrova_upvc_quotes '
                    'ADD COLUMN transport_charges NUMERIC(10,2) NOT NULL DEFAULT 0'
                ))
        print('=== done ===')
        return True


if __name__ == '__main__':
    migrate()
