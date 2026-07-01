"""
Migration: add `quantity` column to `vetrova_upvc_quote_items`.

Followup to the initial KAN-67 schema — BD asked for an explicit Qty
field per opening so two identical bedroom windows can sit on one row
rather than being duplicated. Defaults to 1 so every existing row stays
valid + correctly priced.

  vetrova_upvc_quote_items
    + quantity  NUMERIC(10,2)  NOT NULL DEFAULT 1

Idempotent — re-running is a no-op.
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
        print('=== UPVC quote item quantity migration ===')
        if column_exists('vetrova_upvc_quote_items', 'quantity'):
            print('  ✓ quantity column already exists, skipping')
        else:
            print('  adding vetrova_upvc_quote_items.quantity ...')
            with db.engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE vetrova_upvc_quote_items '
                    'ADD COLUMN quantity NUMERIC(10,2) NOT NULL DEFAULT 1'
                ))
        print('=== done ===')
        return True


if __name__ == '__main__':
    migrate()
