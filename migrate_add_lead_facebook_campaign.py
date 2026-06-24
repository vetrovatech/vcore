"""
Migration: add Facebook ad-hierarchy columns to `leads`.

Backs the per-campaign / per-adset / per-ad lead segmentation BD asked
for. When a Meta Lead Ads webhook lands, the ingest path now also
fetches campaign{id,name}, adset{id,name}, ad{id,name} and form{id,name}
via the Graph API and stamps the result onto the lead row. The list
page gets a Campaign filter dropdown so BD can answer "how is the
HSR-Showers-Lookalike campaign converting?".

Columns added (all nullable — existing IndiaMart / WhatsApp / manual
leads stay valid):

  leads
    + fb_campaign_id    VARCHAR(50)   indexed (filter selectivity)
    + fb_campaign_name  VARCHAR(255)
    + fb_adset_id       VARCHAR(50)
    + fb_adset_name     VARCHAR(255)
    + fb_ad_id          VARCHAR(50)
    + fb_ad_name        VARCHAR(255)
    + fb_form_name      VARCHAR(255)  -- form_id already lived in notes;
                                         promote the human-readable name
                                         to its own column so the UI can
                                         show it without re-parsing

Idempotent — every ADD COLUMN / CREATE INDEX uses information_schema
checks so re-running is a no-op.
"""

from sqlalchemy import inspect, text

from app import app, db


ADDITIONS = [
    ('fb_campaign_id',   'VARCHAR(50)'),
    ('fb_campaign_name', 'VARCHAR(255)'),
    ('fb_adset_id',      'VARCHAR(50)'),
    ('fb_adset_name',    'VARCHAR(255)'),
    ('fb_ad_id',         'VARCHAR(50)'),
    ('fb_ad_name',       'VARCHAR(255)'),
    ('fb_form_name',     'VARCHAR(255)'),
]

# Only fb_campaign_id is indexed by default — the list page filters on
# that selectivity-friendly value. Names are indexed too so the dropdown
# DISTINCT query stays fast as the table grows.
INDEXES = [
    ('idx_lead_fb_campaign_id',   'fb_campaign_id'),
    ('idx_lead_fb_campaign_name', 'fb_campaign_name'),
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


def index_exists(name: str) -> bool:
    row = db.session.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {'n': name},
    ).first()
    return row is not None


def migrate():
    with app.app_context():
        print('=== lead facebook campaign migration ===')
        for column, defn in ADDITIONS:
            if column_exists('leads', column):
                print(f'  ✓ leads.{column} already exists, skipping')
                continue
            print(f'  adding leads.{column} ({defn}) ...')
            with db.engine.begin() as conn:
                conn.execute(text(
                    f'ALTER TABLE leads ADD COLUMN {column} {defn}'
                ))
        for index_name, column in INDEXES:
            if index_exists(index_name):
                print(f'  ✓ index {index_name} already exists, skipping')
                continue
            print(f'  creating index {index_name} on leads({column}) ...')
            with db.engine.begin() as conn:
                conn.execute(text(
                    f'CREATE INDEX {index_name} ON leads({column})'
                ))
        # Sanity: confirm columns present
        inspector = inspect(db.engine)
        present = {c['name'] for c in inspector.get_columns('leads')}
        missing = [c for c, _ in ADDITIONS if c not in present]
        if missing:
            raise RuntimeError(f'migration finished but columns still missing: {missing}')
        print('=== done ===')
        return True


if __name__ == '__main__':
    migrate()
