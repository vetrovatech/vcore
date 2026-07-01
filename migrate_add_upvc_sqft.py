"""
Migration: add `sqft` column to `vetrova_upvc_quote_items`.

Follow-up to KAN-67. BD's earlier UPVC quote flow let them type a flat
"rate" per row that became the line amount as-is. Per the manager's
direction we're switching to ₹/sqft pricing where:

  sqft   = (width_in × height_in) / 144   (width/height in customer's unit,
                                           converted to inches via the
                                           UNIT_TO_INCHES table shared
                                           with the Bathqube flow)
  amount = round(quantity × sqft × rate, 2)

Storing `sqft` on the row (rather than recomputing on every read) keeps
the audit trail intact and matches what the Bathqube items table does.
NUMERIC(10,4) so a 9999.9999 sqft cap is plenty for real openings and
4dp preserves the unit-conversion precision through future reports.

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
        print('=== UPVC quote item sqft migration ===')
        if column_exists('vetrova_upvc_quote_items', 'sqft'):
            print('  ✓ sqft column already exists, skipping')
        else:
            print('  adding vetrova_upvc_quote_items.sqft (NUMERIC(10,4)) ...')
            with db.engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE vetrova_upvc_quote_items '
                    'ADD COLUMN sqft NUMERIC(10,4) NOT NULL DEFAULT 0'
                ))
        print('=== done ===')
        return True


if __name__ == '__main__':
    migrate()
