"""
Migration: extend `whatsapp_messages` to carry inbound replies and delivery
receipts as well as outbound sends.

Before this migration the table was outbound-only (one row per template
send, `status` cycling queued → sent → delivered → read / failed). Meta's
webhook feeds us TWO new streams we want in the same timeline:

  1. Inbound messages — replies the customer sends back on WhatsApp.
     Text, media (image/PDF/voice), or interactive replies.
  2. Delivery / read receipts — `wamid`-scoped status updates for our
     own outbound rows (already handled by the existing `status` column,
     but we've never wired the webhook to actually flip it — this
     migration is the prerequisite for that too).

Approach: additive columns on the existing table so the message timeline
is a single ORDER BY on one table (no UNIONs, no schema fork). Old
outbound rows implicitly get `direction='out'` via the column default.

New columns:
  direction    VARCHAR(3)   NOT NULL DEFAULT 'out'
               'out' for BD sends, 'in' for customer replies. Indexed
               so the lead-view chat panel can pull inbound + outbound
               with one query.
  from_number  VARCHAR(20)  NULL   — customer phone on inbound rows.
  body_text    TEXT         NULL   — plain-text customer message body.
  media_url    TEXT         NULL   — Meta media-download URL (short-lived).
  media_mime   VARCHAR(60)  NULL   — image/jpeg, application/pdf, audio/ogg…
  media_caption TEXT        NULL   — caption customers attach to media.
  received_at  TIMESTAMP    NULL   — Meta's message timestamp on inbound.
                                     (Outbound rows keep using sent_at.)

Idempotent — every ALTER guards with an information_schema.columns check,
so re-running is a no-op.
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


def index_exists(index_name: str) -> bool:
    row = db.session.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {'n': index_name},
    ).first()
    return row is not None


NEW_COLUMNS = [
    # (column, DDL fragment)
    ('direction',     "VARCHAR(3) NOT NULL DEFAULT 'out'"),
    ('from_number',   'VARCHAR(20)'),
    ('body_text',     'TEXT'),
    ('media_url',     'TEXT'),
    ('media_mime',    'VARCHAR(60)'),
    ('media_caption', 'TEXT'),
    ('received_at',   'TIMESTAMP'),
]


def migrate():
    with app.app_context():
        print('=== WhatsApp inbound migration ===')

        for col, ddl in NEW_COLUMNS:
            if column_exists('whatsapp_messages', col):
                print(f'  ✓ {col} already exists, skipping')
                continue
            print(f'  adding whatsapp_messages.{col} ...')
            with db.engine.begin() as conn:
                conn.execute(text(
                    f'ALTER TABLE whatsapp_messages ADD COLUMN {col} {ddl}'
                ))

        # Index for the lead-view timeline: pull inbound + outbound
        # for a single lead, ordered by time. `direction` participates
        # so we can render out/in bubbles without a second lookup.
        idx = 'idx_wam_lead_time'
        if not index_exists(idx):
            print(f'  adding {idx} …')
            with db.engine.begin() as conn:
                conn.execute(text(
                    f'CREATE INDEX {idx} ON whatsapp_messages '
                    '(lead_id, sent_at)'
                ))

        # Index for wamid-based status lookups (webhook status handler).
        # `wamid` was already unique+indexed on the outbound send path;
        # this is just a note that the existing index covers it.
        print('=== done ===')
        return True


if __name__ == '__main__':
    migrate()
