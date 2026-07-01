"""
Migration: create Vetrova Interni UPVC quote tables (KAN-67).

Adds four parallel tables that back the new UPVC quotation flow:

  vetrova_upvc_quotes            — header (customer + totals + stage)
  vetrova_upvc_quote_items       — line items (one per opening / track)
  vetrova_upvc_quote_revisions   — internal audit log of revise-Saves
  vetrova_upvc_status_events     — stage-transition + email-send audit log

Mirrors the Bathqube quote schema shape (so the existing view-page
component patterns reuse), minus the work-order + payment-receipt tables
since UPVC fabrication is outsourced and BD's first cut doesn't need
UTR-level receipt tracking.

Idempotent — every CREATE TABLE / CREATE INDEX uses information_schema
checks so re-running is a no-op.
"""

from sqlalchemy import inspect, text

from app import app, db


TABLES = [
    # (table_name, ddl)
    (
        'vetrova_upvc_quotes',
        """
        CREATE TABLE vetrova_upvc_quotes (
            id              SERIAL PRIMARY KEY,
            estimate_number VARCHAR(32) UNIQUE,
            customer_name   VARCHAR(200)  NOT NULL,
            phone           VARCHAR(32)   NOT NULL,
            email           VARCHAR(200),
            pincode         VARCHAR(12),
            site_address    TEXT,
            subtotal        NUMERIC(12,2) NOT NULL DEFAULT 0,
            cgst            NUMERIC(12,2) NOT NULL DEFAULT 0,
            sgst            NUMERIC(12,2) NOT NULL DEFAULT 0,
            total           NUMERIC(12,2) NOT NULL DEFAULT 0,
            gst_percentage  NUMERIC(5,2)  NOT NULL DEFAULT 18,
            amount_received NUMERIC(12,2) NOT NULL DEFAULT 0,
            validity_days   INTEGER       NOT NULL DEFAULT 10,
            revision_count  INTEGER       NOT NULL DEFAULT 0,
            stage           VARCHAR(32)   NOT NULL DEFAULT 'draft',
            notes           TEXT,
            created_by      INTEGER REFERENCES users(id),
            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            purchased_at    TIMESTAMP
        )
        """,
    ),
    (
        'vetrova_upvc_quote_items',
        """
        CREATE TABLE vetrova_upvc_quote_items (
            id           SERIAL PRIMARY KEY,
            quote_id     INTEGER       NOT NULL REFERENCES vetrova_upvc_quotes(id) ON DELETE CASCADE,
            sort_order   INTEGER       NOT NULL DEFAULT 0,
            label        VARCHAR(200),
            track_type   VARCHAR(20)   NOT NULL,
            track_system VARCHAR(20),
            width        NUMERIC(10,2),
            height       NUMERIC(10,2),
            unit         VARCHAR(8)    NOT NULL DEFAULT 'ft',
            colour       VARCHAR(20)   NOT NULL,
            rate         NUMERIC(12,2) NOT NULL DEFAULT 0,
            amount       NUMERIC(12,2) NOT NULL DEFAULT 0
        )
        """,
    ),
    (
        'vetrova_upvc_quote_revisions',
        """
        CREATE TABLE vetrova_upvc_quote_revisions (
            id              SERIAL PRIMARY KEY,
            quote_id        INTEGER NOT NULL REFERENCES vetrova_upvc_quotes(id) ON DELETE CASCADE,
            revision_number INTEGER NOT NULL,
            prev_subtotal   NUMERIC(12,2),
            new_subtotal    NUMERIC(12,2),
            prev_total      NUMERIC(12,2),
            new_total       NUMERIC(12,2),
            snapshot        TEXT,
            triggered_by    INTEGER REFERENCES users(id),
            created_at      TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
    ),
    (
        'vetrova_upvc_status_events',
        """
        CREATE TABLE vetrova_upvc_status_events (
            id                  SERIAL PRIMARY KEY,
            quote_id            INTEGER NOT NULL REFERENCES vetrova_upvc_quotes(id) ON DELETE CASCADE,
            from_stage          VARCHAR(32),
            to_stage            VARCHAR(32) NOT NULL,
            channel             VARCHAR(20) NOT NULL DEFAULT 'email',
            subject             VARCHAR(255),
            message             TEXT,
            send_status         VARCHAR(20) NOT NULL DEFAULT 'pending',
            send_error          TEXT,
            provider_message_id VARCHAR(128),
            triggered_by        INTEGER REFERENCES users(id),
            created_at          TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
    ),
]


INDEXES = [
    # (index_name, table, column)
    ('idx_upvc_quotes_phone',          'vetrova_upvc_quotes',        'phone'),
    ('idx_upvc_quotes_email',          'vetrova_upvc_quotes',        'email'),
    ('idx_upvc_quotes_stage',          'vetrova_upvc_quotes',        'stage'),
    ('idx_upvc_quotes_created_at',     'vetrova_upvc_quotes',        'created_at'),
    ('idx_upvc_items_quote',           'vetrova_upvc_quote_items',   'quote_id'),
    ('idx_upvc_revisions_quote',       'vetrova_upvc_quote_revisions','quote_id'),
    ('idx_upvc_status_events_quote',   'vetrova_upvc_status_events', 'quote_id'),
    ('idx_upvc_status_events_created', 'vetrova_upvc_status_events', 'created_at'),
]


def table_exists(name: str) -> bool:
    row = db.session.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = :n AND table_schema = 'public'"
        ),
        {'n': name},
    ).first()
    return row is not None


def index_exists(name: str) -> bool:
    row = db.session.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {'n': name},
    ).first()
    return row is not None


def migrate():
    with app.app_context():
        print('=== Vetrova Interni UPVC quote migration ===')

        for name, ddl in TABLES:
            if table_exists(name):
                print(f'  ✓ table {name} already exists, skipping')
                continue
            print(f'  creating table {name} ...')
            with db.engine.begin() as conn:
                conn.execute(text(ddl))

        for index_name, table, column in INDEXES:
            if index_exists(index_name):
                print(f'  ✓ index {index_name} already exists, skipping')
                continue
            print(f'  creating index {index_name} on {table}({column}) ...')
            with db.engine.begin() as conn:
                conn.execute(text(
                    f'CREATE INDEX {index_name} ON {table}({column})'
                ))

        inspector = inspect(db.engine)
        existing = set(inspector.get_table_names())
        missing = [t for t, _ in TABLES if t not in existing]
        if missing:
            raise RuntimeError(f'migration finished but tables still missing: {missing}')
        print('=== done ===')
        return True


if __name__ == '__main__':
    migrate()
