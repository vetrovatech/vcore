"""Migration: add discount + original-config columns to bathqube_quotes.

Adds three columns (idempotent — skips any column that already exists):

  - discount_percent     NUMERIC(5,2)  NULL DEFAULT 0
        Sales person enters a percentage in the revise UI; applied to
        (enc_subtotal + extras_subtotal) BEFORE GST.

  - discount_amount      NUMERIC(12,2) NULL DEFAULT 0
        Cached computed amount = subtotal × (discount_percent / 100). Stored
        so we don't have to recompute on every view / PDF render.

  - original_config_data TEXT          NULL
        Snapshot of the customer's ORIGINAL configurator submission, captured
        the first time a sales person opens the revise screen. config_data
        becomes the working/edited version after that. This is the audit
        trail of "what the customer originally asked for vs what was sold".

Run directly with DATABASE_URL set:
    python migrate_add_bathqube_discount.py
"""

from app import app, db
from sqlalchemy import text, inspect


ALTERS = [
    "ALTER TABLE bathqube_quotes ADD COLUMN discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0",
    "ALTER TABLE bathqube_quotes ADD COLUMN discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0",
    "ALTER TABLE bathqube_quotes ADD COLUMN original_config_data TEXT NULL",
    # Flag items so the revise UI can show enclosure-derived rows vs free-form extras separately
    "ALTER TABLE bathqube_quote_items ADD COLUMN is_extra BOOLEAN NOT NULL DEFAULT FALSE",
]


def migrate():
    with app.app_context():
        with db.engine.connect() as conn:
            for sql in ALTERS:
                col_name = sql.split('ADD COLUMN ')[1].split()[0]
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    print(f"  ran:  {sql}")
                except Exception as e:
                    print(f"  skip: {col_name} — {type(e).__name__}")
                    conn.rollback()

        # Verify
        insp = inspect(db.engine)
        quote_cols = {c['name'] for c in insp.get_columns('bathqube_quotes')}
        item_cols = {c['name'] for c in insp.get_columns('bathqube_quote_items')}
        print()
        print("  bathqube_quotes columns:")
        for col in ('discount_percent', 'discount_amount', 'original_config_data'):
            print(f"    {col:24} {'ok' if col in quote_cols else 'MISSING'}")
        print("  bathqube_quote_items columns:")
        print(f"    {'is_extra':24} {'ok' if 'is_extra' in item_cols else 'MISSING'}")
        print("\nDone.")


if __name__ == '__main__':
    migrate()
