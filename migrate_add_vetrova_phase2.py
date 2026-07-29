"""
Migration — Vetrova quotes Phase 2: full-lifecycle edit foundation.

Adds:
  1. `vetrova_quote_revisions` table (mirror of BathqubeQuoteRevision) —
     one snapshot per BD save of the revise editor. Enables the audit
     trail + view-only history panel.
  2. VetrovaStatusEvent gains channel/subject/message/send_status/
     send_error/provider_message_id columns so we can log WhatsApp +
     email sends per stage (parity with BathqubeStatusEvent).
  3. VetrovaQuote gains customer_pan, discount_percent, discount_amount —
     needed for tax invoice B2C compliance + revise discount UI.
  4. VetrovaQuoteItem gains is_extra bool — separates BD-added extras/
     discounts (negative-amount rows) from configurator-generated rows
     so they survive the wipe-and-recreate on every revise save.

Local docker DATABASE_URL points at prod Postgres — any run of this
script is a PROD change. Safe to re-run (idempotent).
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


def table_exists(table: str) -> bool:
    row = db.session.execute(
        text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
        ),
        {'t': table},
    ).first()
    return row is not None


def migrate():
    with app.app_context():
        print('=== Vetrova quotes Phase 2 migration ===')

        # ── 1. vetrova_quote_revisions table ─────────────────────────
        if not table_exists('vetrova_quote_revisions'):
            print('  add table vetrova_quote_revisions')
            db.session.execute(text("""
                CREATE TABLE vetrova_quote_revisions (
                    id                SERIAL PRIMARY KEY,
                    quote_id          INTEGER NOT NULL REFERENCES vetrova_quotes(id) ON DELETE CASCADE,
                    revision_number   INTEGER NOT NULL,
                    prev_subtotal     NUMERIC(12, 2),
                    new_subtotal      NUMERIC(12, 2),
                    prev_total        NUMERIC(12, 2),
                    new_total         NUMERIC(12, 2),
                    discount_percent  NUMERIC(5, 2),
                    snapshot          TEXT,
                    triggered_by      INTEGER REFERENCES users(id),
                    note              TEXT,
                    created_at        TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """))
            db.session.execute(text(
                'CREATE INDEX IF NOT EXISTS vetrova_quote_revisions_quote_id_idx '
                'ON vetrova_quote_revisions (quote_id)'
            ))
            db.session.execute(text(
                'CREATE INDEX IF NOT EXISTS vetrova_quote_revisions_created_at_idx '
                'ON vetrova_quote_revisions (created_at)'
            ))
            db.session.commit()
        else:
            print('  ok  vetrova_quote_revisions (already exists)')

        # ── 2. vetrova_status_events — send/channel columns ──────────
        status_cols = [
            # (column, ddl fragment)
            ('channel',              "VARCHAR(20) NOT NULL DEFAULT 'email'"),
            ('subject',              "VARCHAR(255)"),
            ('message',              "TEXT"),
            ('send_status',          "VARCHAR(20) NOT NULL DEFAULT 'skipped'"),
            ('send_error',           "TEXT"),
            ('provider_message_id',  "VARCHAR(128)"),
        ]
        for col, ddl in status_cols:
            if not column_exists('vetrova_status_events', col):
                print(f'  add vetrova_status_events.{col}')
                db.session.execute(text(
                    f'ALTER TABLE vetrova_status_events ADD COLUMN {col} {ddl}'
                ))
                db.session.commit()
            else:
                print(f'  ok  vetrova_status_events.{col} (already present)')

        # ── 3. vetrova_quotes — customer_pan, discount fields ────────
        quote_cols = [
            ('customer_pan',      "VARCHAR(20)"),
            ('discount_percent',  "NUMERIC(5, 2) NOT NULL DEFAULT 0"),
            ('discount_amount',   "NUMERIC(12, 2) NOT NULL DEFAULT 0"),
        ]
        for col, ddl in quote_cols:
            if not column_exists('vetrova_quotes', col):
                print(f'  add vetrova_quotes.{col}')
                db.session.execute(text(
                    f'ALTER TABLE vetrova_quotes ADD COLUMN {col} {ddl}'
                ))
                db.session.commit()
            else:
                print(f'  ok  vetrova_quotes.{col} (already present)')

        # ── 4. vetrova_quote_items — is_extra flag ───────────────────
        if not column_exists('vetrova_quote_items', 'is_extra'):
            print('  add vetrova_quote_items.is_extra')
            db.session.execute(text(
                'ALTER TABLE vetrova_quote_items '
                'ADD COLUMN is_extra BOOLEAN NOT NULL DEFAULT FALSE'
            ))
            db.session.commit()
        else:
            print('  ok  vetrova_quote_items.is_extra (already present)')

        print('Migration completed.')
        return True


if __name__ == '__main__':
    ok = migrate()
    raise SystemExit(0 if ok else 1)
