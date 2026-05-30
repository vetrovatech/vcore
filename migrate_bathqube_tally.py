"""Add the Tally-related columns + PurchaseInvoice link for bathqube quotes.

When a BathqubeQuote is moved to stage 'closed_won', it should show up in the
Tally dashboard alongside regular Accepted quotes — same row structure, same
editable financial fields, same ability to attach purchase invoices.

This migration adds:

  bathqube_quotes
    + cash_received     NUMERIC(12,2)  default 0
    + misc_purchases    NUMERIC(12,2)  default 0
    + delivery_status   VARCHAR(20)    default 'Pending'

  purchase_invoices
    + bathqube_quote_id INTEGER  NULL  FK -> bathqube_quotes.id

Idempotent — safe to re-run. Existing quote_id column on purchase_invoices is
untouched, so regular Quote → PurchaseInvoice links continue to work.

Run from inside the container:
    python migrate_bathqube_tally.py
"""
from app import app, db


ADDITIONS = [
    ("bathqube_quotes", "cash_received",     "NUMERIC(12,2) NOT NULL DEFAULT 0"),
    ("bathqube_quotes", "misc_purchases",    "NUMERIC(12,2) NOT NULL DEFAULT 0"),
    ("bathqube_quotes", "delivery_status",   "VARCHAR(20)   NOT NULL DEFAULT 'Pending'"),
    ("purchase_invoices", "bathqube_quote_id", "INTEGER NULL REFERENCES bathqube_quotes(id)"),
]


def column_exists(table: str, column: str) -> bool:
    row = db.session.execute(
        db.text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
        """),
        {"t": table, "c": column},
    ).first()
    return row is not None


def run():
    with app.app_context():
        print('=== bathqube tally migration ===')
        for table, column, defn in ADDITIONS:
            if column_exists(table, column):
                print(f'  ✓ {table}.{column} already exists, skipping')
                continue
            sql = f'ALTER TABLE {table} ADD COLUMN {column} {defn}'
            print(f'  + {sql}')
            db.session.execute(db.text(sql))
        db.session.commit()
        print()
        print('Done.')


if __name__ == '__main__':
    run()
