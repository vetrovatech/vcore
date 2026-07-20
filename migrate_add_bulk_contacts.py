"""
Migration: create `bulk_contacts` table for the Bulk Send marketing feature +
add `whatsapp_messages.bulk_contact_id` FK so inbound replies can attach to
either a Lead or a BulkContact.

Bulk Send is a standalone marketing feature — BD downloads an Excel
template, fills in name + phone rows for a campaign, uploads, selects
recipients, picks a marketing WhatsApp template, and sends. Replies land
on the webhook, get matched to a BulkContact by phone, and render on the
contact detail page's chat panel (same layout as the Leads chat).

Contacts are separate from Leads on purpose:
  - BD explicitly asked for a dedicated "Bulk Send" menu, not a leads
    filter (previously discussed and rejected).
  - Different lifecycle — marketing lists get imported, blasted,
    opted-out. Leads have stages, owners, meetings.
  - Kept minimal (name, phone, campaign, opt-out) — no room for the
    per-lead fields that don't apply (product_interest, stage, etc).

Idempotent — every DDL guards existence.
"""

from sqlalchemy import text

from app import app, db


def table_exists(name: str) -> bool:
    row = db.session.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = :n"),
        {'n': name},
    ).first()
    return row is not None


def column_exists(table: str, column: str) -> bool:
    row = db.session.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {'t': table, 'c': column},
    ).first()
    return row is not None


def index_exists(index_name: str) -> bool:
    row = db.session.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {'n': index_name},
    ).first()
    return row is not None


def migrate():
    with app.app_context():
        print('=== bulk_contacts migration ===')

        if not table_exists('bulk_contacts'):
            print('  creating bulk_contacts …')
            with db.engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE bulk_contacts (
                        id           SERIAL PRIMARY KEY,
                        name         VARCHAR(200) NOT NULL,
                        phone        VARCHAR(20)  NOT NULL,
                        campaign     VARCHAR(100),
                        is_opted_out BOOLEAN      NOT NULL DEFAULT FALSE,
                        imported_by  INTEGER      REFERENCES users(id) ON DELETE SET NULL,
                        imported_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
        else:
            print('  ✓ bulk_contacts already exists')

        # Indexes — phone is the main lookup key (webhook match, dedup),
        # campaign for filter chips, is_opted_out to skip on send.
        for idx_name, ddl in [
            ('idx_bulk_contacts_phone',        'CREATE INDEX idx_bulk_contacts_phone ON bulk_contacts(phone)'),
            ('idx_bulk_contacts_campaign',     'CREATE INDEX idx_bulk_contacts_campaign ON bulk_contacts(campaign)'),
            ('idx_bulk_contacts_opted_out',    'CREATE INDEX idx_bulk_contacts_opted_out ON bulk_contacts(is_opted_out)'),
        ]:
            if not index_exists(idx_name):
                print(f'  adding {idx_name} …')
                with db.engine.begin() as conn:
                    conn.execute(text(ddl))

        # whatsapp_messages.bulk_contact_id — inbound replies from a
        # bulk contact attach here; NULL when the reply is from a Lead
        # or unmatched.
        if not column_exists('whatsapp_messages', 'bulk_contact_id'):
            print('  adding whatsapp_messages.bulk_contact_id …')
            with db.engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE whatsapp_messages '
                    'ADD COLUMN bulk_contact_id INTEGER '
                    'REFERENCES bulk_contacts(id) ON DELETE SET NULL'
                ))
        else:
            print('  ✓ whatsapp_messages.bulk_contact_id already exists')

        # Index for the chat panel query (all messages for a bulk contact).
        if not index_exists('idx_wam_bulk_contact_time'):
            print('  adding idx_wam_bulk_contact_time …')
            with db.engine.begin() as conn:
                conn.execute(text(
                    'CREATE INDEX idx_wam_bulk_contact_time '
                    'ON whatsapp_messages (bulk_contact_id, sent_at)'
                ))

        print('=== done ===')
        return True


if __name__ == '__main__':
    migrate()
