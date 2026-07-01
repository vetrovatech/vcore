"""
Migration: create `tax_invoices` + `tax_invoice_items` tables.

Backs the GST tax-invoice generation flow. When a quote reaches
`closed_won` and the deal goes to Tally, BD can "Generate Tax Invoice"
to produce a properly-formatted GST invoice (matches the reference
Arihant invoice layout). The invoice freezes a snapshot of the line
items at generation time so the source quote stays mutable but the
invoice does not.

Source quote linkage is polymorphic — exactly one of
`bathqube_quote_id`, `upvc_quote_id`, `lead_quote_id` is set per row
(matches the `PurchaseInvoice` pattern already in this codebase).

Sequential per-FY numbering (`VTS/2627/0001`) is allocated by the
`_next_tax_invoice_number()` helper in app.py — DB enforces uniqueness
via the unique index on `invoice_number`.

Idempotent — every CREATE uses `IF NOT EXISTS` / information-schema
checks so re-running is a no-op.
"""

from sqlalchemy import inspect, text

from app import app, db


TABLES = [
    (
        'tax_invoices',
        """
        CREATE TABLE tax_invoices (
            id                  SERIAL PRIMARY KEY,

            -- Invoice identity (sequential per FY)
            invoice_number      VARCHAR(40)   UNIQUE NOT NULL,
            financial_year      VARCHAR(8)    NOT NULL,
            invoice_date        DATE          NOT NULL,

            -- Source quote (exactly one set; the others NULL)
            bathqube_quote_id   INTEGER REFERENCES bathqube_quotes(id)        ON DELETE SET NULL,
            upvc_quote_id       INTEGER REFERENCES vetrova_upvc_quotes(id)    ON DELETE SET NULL,
            lead_quote_id       INTEGER REFERENCES quotes(id)                 ON DELETE SET NULL,

            -- Seller snapshot (defaults from settings; frozen here so
            -- changing settings later doesn't rewrite history)
            seller_name         VARCHAR(200)  NOT NULL,
            seller_address      TEXT          NOT NULL,
            seller_gstin        VARCHAR(20)   NOT NULL,
            seller_state        VARCHAR(50)   NOT NULL,
            seller_state_code   VARCHAR(4)    NOT NULL,
            seller_pan          VARCHAR(20),
            seller_udyam        VARCHAR(40),
            seller_email        VARCHAR(200),
            seller_cin          VARCHAR(40),

            -- Buyer (Bill-to)
            buyer_name          VARCHAR(200)  NOT NULL,
            buyer_address       TEXT          NOT NULL,
            buyer_gstin         VARCHAR(20),
            buyer_state         VARCHAR(50),
            buyer_state_code    VARCHAR(4),

            -- Consignee (Ship-to). Defaults to buyer when same site.
            consignee_name      VARCHAR(200)  NOT NULL,
            consignee_address   TEXT          NOT NULL,
            consignee_gstin     VARCHAR(20),
            consignee_state     VARCHAR(50),
            consignee_state_code VARCHAR(4),

            -- Invoice metadata (BD enters; defaults applied where sensible)
            buyers_order_no     VARCHAR(100),
            buyers_order_date   DATE,
            delivery_note       VARCHAR(100),
            delivery_note_date  DATE,
            dispatch_doc_no     VARCHAR(100),
            mode_of_payment     VARCHAR(50)   DEFAULT 'PROMPT',
            other_references    VARCHAR(255),
            dispatched_through  VARCHAR(50)   DEFAULT 'ROAD',
            destination         VARCHAR(200),
            terms_of_delivery   VARCHAR(255)  DEFAULT 'EX OUR SITE',
            bill_of_lading      VARCHAR(100),
            bill_of_lading_date DATE,
            motor_vehicle_no    VARCHAR(20),
            ewaybill_no         VARCHAR(50),

            -- e-Invoice fields — BD pastes manually after IRP gen.
            -- Rendered on the PDF only when irn is set.
            irn                 VARCHAR(80),
            ack_no              VARCHAR(40),
            ack_date            DATE,

            -- Money (computed from items)
            subtotal            NUMERIC(14,2) NOT NULL DEFAULT 0,
            cgst                NUMERIC(12,2) NOT NULL DEFAULT 0,
            sgst                NUMERIC(12,2) NOT NULL DEFAULT 0,
            igst                NUMERIC(12,2) NOT NULL DEFAULT 0,
            round_off           NUMERIC(6,2)  NOT NULL DEFAULT 0,
            total               NUMERIC(14,2) NOT NULL DEFAULT 0,
            amount_in_words     VARCHAR(500),

            -- Bank details snapshot (mirrors what's printed in the PDF)
            bank_account_name   VARCHAR(200),
            bank_name           VARCHAR(100),
            bank_account_no     VARCHAR(40),
            bank_ifsc           VARCHAR(20),
            bank_branch         VARCHAR(100),
            upi_id              VARCHAR(60),

            declaration         TEXT,

            -- Lifecycle
            status              VARCHAR(20)   NOT NULL DEFAULT 'draft',
            created_by          INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            issued_at           TIMESTAMP,
            cancelled_at        TIMESTAMP,
            cancelled_reason    TEXT
        )
        """,
    ),
    (
        'tax_invoice_items',
        """
        CREATE TABLE tax_invoice_items (
            id            SERIAL PRIMARY KEY,
            invoice_id    INTEGER NOT NULL REFERENCES tax_invoices(id) ON DELETE CASCADE,
            sort_order    INTEGER NOT NULL DEFAULT 0,

            description   VARCHAR(500) NOT NULL,
            hsn_code      VARCHAR(10),
            quantity      NUMERIC(12,4) NOT NULL DEFAULT 1,
            unit          VARCHAR(20)   DEFAULT 'nos',
            rate          NUMERIC(12,2) NOT NULL DEFAULT 0,
            amount        NUMERIC(14,2) NOT NULL DEFAULT 0,

            -- True for non-product lines (transportation, installation,
            -- manual discount). PDF renders them after the product rows.
            is_extra      BOOLEAN NOT NULL DEFAULT FALSE
        )
        """,
    ),
]


INDEXES = [
    ('idx_tax_invoices_fy',         'tax_invoices',      'financial_year'),
    ('idx_tax_invoices_date',       'tax_invoices',      'invoice_date'),
    ('idx_tax_invoices_status',     'tax_invoices',      'status'),
    ('idx_tax_invoices_bq',         'tax_invoices',      'bathqube_quote_id'),
    ('idx_tax_invoices_upvc',       'tax_invoices',      'upvc_quote_id'),
    ('idx_tax_invoices_lead',       'tax_invoices',      'lead_quote_id'),
    ('idx_tax_invoice_items_invoice','tax_invoice_items','invoice_id'),
    ('idx_tax_invoice_items_hsn',   'tax_invoice_items','hsn_code'),
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
        print('=== Tax invoice tables migration ===')
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
