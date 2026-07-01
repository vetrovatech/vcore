"""
Migration: create `gate_passes` + `gate_pass_items` tables.

Backs the dispatch / packing-slip flow. Once a tax invoice (or quote)
is finalised, a Gate Pass is raised to track *what physically leaves
the factory* per dispatch trip. Multiple gate passes per source are
allowed (partial dispatches — exactly like the reference Arihant
packing slip where most rows show qty=0 on a given trip and only the
ones being loaded that day get a positive qty).

Source linkage is polymorphic — exactly one of `tax_invoice_id`,
`bathqube_quote_id`, `upvc_quote_id`, `lead_quote_id` is set per row.

Sequential per-FY numbering is allocated by app.py:
`_next_gate_pass_number()` → `VTS/GP/2627/0001`.

Idempotent — every CREATE uses information-schema checks so
re-running is a no-op.
"""

from sqlalchemy import inspect, text

from app import app, db


TABLES = [
    (
        'gate_passes',
        """
        CREATE TABLE gate_passes (
            id                  SERIAL PRIMARY KEY,

            gp_number           VARCHAR(40)  UNIQUE NOT NULL,
            financial_year      VARCHAR(8)   NOT NULL,
            gp_date             DATE         NOT NULL,

            -- Source (exactly one set)
            tax_invoice_id      INTEGER REFERENCES tax_invoices(id)         ON DELETE SET NULL,
            bathqube_quote_id   INTEGER REFERENCES bathqube_quotes(id)      ON DELETE SET NULL,
            upvc_quote_id       INTEGER REFERENCES vetrova_upvc_quotes(id)  ON DELETE SET NULL,
            lead_quote_id       INTEGER REFERENCES quotes(id)               ON DELETE SET NULL,

            -- Customer / delivery snapshot
            customer_name       VARCHAR(200) NOT NULL,
            delivery_address    TEXT,
            customer_gstin      VARCHAR(20),

            -- Reference back to the source invoice/quote (printed on PDF)
            ref_invoice_no      VARCHAR(60),
            ref_invoice_date    DATE,

            -- Dispatch / logistics
            vehicle_no          VARCHAR(30),
            transporter_name    VARCHAR(150),
            driver_name         VARCHAR(150),
            driver_phone        VARCHAR(30),
            lr_number           VARCHAR(60),
            eway_bill_no        VARCHAR(50),
            place_of_supply     VARCHAR(200),

            remarks             TEXT,

            -- Lifecycle
            status              VARCHAR(20)  NOT NULL DEFAULT 'draft',
            prepared_by         INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            issued_at           TIMESTAMP,
            cancelled_at        TIMESTAMP,
            cancelled_reason    TEXT
        )
        """,
    ),
    (
        'gate_pass_items',
        """
        CREATE TABLE gate_pass_items (
            id                  SERIAL PRIMARY KEY,
            gate_pass_id        INTEGER NOT NULL REFERENCES gate_passes(id) ON DELETE CASCADE,
            sort_order          INTEGER NOT NULL DEFAULT 0,

            -- Group header (printed as a bold section row like
            -- "6MM ST-136 Heat Strengthened Glass" on the Arihant slip)
            material_spec       VARCHAR(200),

            -- Free-text identifiers (BD types these in)
            ref_code            VARCHAR(60),   -- e.g. N-F-B2, E-S-G1
            work_order_no       VARCHAR(60),   -- e.g. AWO-11645

            -- Dimensions in mm + pre-formatted inch display
            width_mm            NUMERIC(10,2),
            height_mm           NUMERIC(10,2),
            width_in_display    VARCHAR(20),
            height_in_display   VARCHAR(20),

            -- Qty tracking
            qty_ordered             NUMERIC(10,2) NOT NULL DEFAULT 0,
            qty_dispatched_before   NUMERIC(10,2) NOT NULL DEFAULT 0,
            qty_this_pass           NUMERIC(10,2) NOT NULL DEFAULT 0,

            -- Area metrics (auto-computed)
            sqft                NUMERIC(12,4) NOT NULL DEFAULT 0,
            sqm                 NUMERIC(12,4) NOT NULL DEFAULT 0,

            -- Process flags (mirror Arihant H/C/SP/BH/CSK columns)
            flag_h              BOOLEAN NOT NULL DEFAULT FALSE,
            flag_c              BOOLEAN NOT NULL DEFAULT FALSE,
            flag_sp             BOOLEAN NOT NULL DEFAULT FALSE,
            flag_bh             BOOLEAN NOT NULL DEFAULT FALSE,
            flag_csk            BOOLEAN NOT NULL DEFAULT FALSE,

            -- Pointer back to the source quote line (for dispatch
            -- reconciliation). Stored as a plain int because source
            -- type varies across BQ / UPVC / Quote line tables.
            source_kind         VARCHAR(20),   -- 'bathqube' | 'upvc' | 'lead' | 'tax_invoice' | 'manual'
            source_item_id      INTEGER,

            remarks             VARCHAR(200)
        )
        """,
    ),
]


INDEXES = [
    ('idx_gate_passes_fy',          'gate_passes',     'financial_year'),
    ('idx_gate_passes_date',        'gate_passes',     'gp_date'),
    ('idx_gate_passes_status',      'gate_passes',     'status'),
    ('idx_gate_passes_tax_invoice', 'gate_passes',     'tax_invoice_id'),
    ('idx_gate_passes_bq',          'gate_passes',     'bathqube_quote_id'),
    ('idx_gate_passes_upvc',        'gate_passes',     'upvc_quote_id'),
    ('idx_gate_passes_lead',        'gate_passes',     'lead_quote_id'),
    ('idx_gate_pass_items_parent',  'gate_pass_items', 'gate_pass_id'),
    ('idx_gate_pass_items_src',     'gate_pass_items', 'source_item_id'),
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
        print('=== Gate pass tables migration ===')
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
