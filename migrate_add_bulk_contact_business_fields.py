"""
Migration: extend `bulk_contacts` with business-directory fields for the
`glassy_onboarding_invite` template campaign.

BD's outreach list comes from the Glassy India directory as a CSV/Excel
sheet with:
    business name, category, phone, location, star rating, reviews,
    website, glassy listing URL

The `glassy_onboarding_invite` WhatsApp template needs 3 body variables:
    {{1}} = business name (contact.name)
    {{2}} = star rating   (contact.star_rating)
    {{3}} = listing URL   (contact.listing_url)

Those three are the minimum for a send. The other columns
(category / location / reviews / website) are stored for BD's benefit —
filtering, cross-referencing, future campaigns — with no per-send cost.

All columns nullable so existing rows (name + phone only) stay valid.

Idempotent — every ALTER guards with an information_schema.columns check.
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


NEW_COLUMNS = [
    ('star_rating',       'NUMERIC(3,1)'),
    ('listing_url',       'TEXT'),
    ('business_category', 'VARCHAR(120)'),
    ('location',          'VARCHAR(200)'),
    ('reviews_count',     'INTEGER'),
    ('website',           'VARCHAR(500)'),
]


def migrate():
    with app.app_context():
        print('=== bulk_contacts business-fields migration ===')
        for col, ddl in NEW_COLUMNS:
            if column_exists('bulk_contacts', col):
                print(f'  ✓ {col} already exists, skipping')
                continue
            print(f'  adding bulk_contacts.{col} …')
            with db.engine.begin() as conn:
                conn.execute(text(
                    f'ALTER TABLE bulk_contacts ADD COLUMN {col} {ddl}'
                ))
        print('=== done ===')
        return True


if __name__ == '__main__':
    migrate()
