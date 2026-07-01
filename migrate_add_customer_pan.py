"""
Migration: add `customer_pan` to the three quote tables + `buyer_pan`
to `tax_invoices`.

Bathqube + UPVC are B2C — they carry no GSTIN, so PAN is the only
ID we can print on the tax invoice. For regular Quotes the field is
also present but should only be filled when quote_type='B2C'; B2B
quotes use the existing `customer_gst` column instead.

Columns added (all VARCHAR(15) nullable — Indian PAN is exactly 10
chars in AAAAA9999A format; the extra 5 chars of headroom catches
data-entry mistakes without truncating):

  bathqube_quotes        + customer_pan
  vetrova_upvc_quotes    + customer_pan
  quotes                 + customer_pan
  tax_invoices           + buyer_pan

Idempotent — every ADD COLUMN uses information_schema check so
re-running is a no-op.
"""

from sqlalchemy import text

from app import app, db


ADDITIONS = [
    ('bathqube_quotes',      'customer_pan'),
    ('vetrova_upvc_quotes',  'customer_pan'),
    ('quotes',               'customer_pan'),
    ('tax_invoices',         'buyer_pan'),
]


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
        print('=== Customer PAN columns migration ===')
        for table, col in ADDITIONS:
            if column_exists(table, col):
                print(f'  ✓ {table}.{col} already exists, skipping')
                continue
            print(f'  adding {table}.{col} (VARCHAR(15)) ...')
            with db.engine.begin() as conn:
                conn.execute(text(
                    f'ALTER TABLE {table} ADD COLUMN {col} VARCHAR(15)'
                ))
        print('=== done ===')
        return True


if __name__ == '__main__':
    migrate()
