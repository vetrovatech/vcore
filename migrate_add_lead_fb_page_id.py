"""
Migration: add `fb_page_id` column to `leads`.

Backs multi-Page Facebook Lead Ads support. Until now vcore was wired to
a single Page Access Token (BathQube). With Glassy.in now connected as
an asset of the same Vcore CRM app, we need to know which Page each lead
came from — both for BD's "show me only Glassy.in leads" filter on /leads
and for routing the right Page Access Token when the webhook fires.

Columns added (nullable — every existing lead stays valid; only new
ingests stamp the value):

  leads
    + fb_page_id  VARCHAR(50)  indexed (filter selectivity)

Idempotent — re-running is a no-op.
"""

from sqlalchemy import inspect, text

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


def index_exists(name: str) -> bool:
    row = db.session.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {'n': name},
    ).first()
    return row is not None


def migrate():
    with app.app_context():
        print('=== lead fb_page_id migration ===')
        if column_exists('leads', 'fb_page_id'):
            print('  ✓ leads.fb_page_id already exists, skipping')
        else:
            print('  adding leads.fb_page_id (VARCHAR(50)) ...')
            with db.engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE leads ADD COLUMN fb_page_id VARCHAR(50)'
                ))
        if index_exists('idx_lead_fb_page_id'):
            print('  ✓ index idx_lead_fb_page_id already exists, skipping')
        else:
            print('  creating index idx_lead_fb_page_id on leads(fb_page_id) ...')
            with db.engine.begin() as conn:
                conn.execute(text(
                    'CREATE INDEX idx_lead_fb_page_id ON leads(fb_page_id)'
                ))
        inspector = inspect(db.engine)
        present = {c['name'] for c in inspector.get_columns('leads')}
        if 'fb_page_id' not in present:
            raise RuntimeError('migration finished but fb_page_id still missing')
        print('=== done ===')
        return True


if __name__ == '__main__':
    migrate()
