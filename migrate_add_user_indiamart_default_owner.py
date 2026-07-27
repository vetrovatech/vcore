"""
Migration: add `is_indiamart_default_owner` boolean column to `users`.

Default owner for newly-synced IndiaMart leads (2026-07-26). When set,
`_do_indiamart_sync` assigns every new lead to that user regardless of
who triggered the sync (button click OR hourly cron). Idempotent —
no-op on re-run.

Flag is set post-migration via SQL:
    UPDATE users SET is_indiamart_default_owner = TRUE WHERE id = <sirin_id>;
Kept out of this script so re-running doesn't clobber a later
admin-side owner change.
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


def index_exists(name: str) -> bool:
    row = db.session.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {'n': name},
    ).first()
    return row is not None


def migrate():
    with app.app_context():
        print('=== users.is_indiamart_default_owner migration ===')
        if not column_exists('users', 'is_indiamart_default_owner'):
            print('  add users.is_indiamart_default_owner')
            db.session.execute(text(
                'ALTER TABLE users '
                'ADD COLUMN is_indiamart_default_owner BOOLEAN NOT NULL DEFAULT FALSE'
            ))
            db.session.commit()
        else:
            print('  ok  users.is_indiamart_default_owner (already present)')
        if not index_exists('ix_users_is_indiamart_default_owner'):
            print('  add ix_users_is_indiamart_default_owner')
            db.session.execute(text(
                'CREATE INDEX ix_users_is_indiamart_default_owner '
                'ON users (is_indiamart_default_owner)'
            ))
            db.session.commit()
        else:
            print('  ok  ix_users_is_indiamart_default_owner (already present)')
        print('Migration completed.')
        return True


if __name__ == '__main__':
    ok = migrate()
    raise SystemExit(0 if ok else 1)
