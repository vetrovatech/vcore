"""
Migration: add `can_indiamart_sync` boolean column to `users`.

Per-user override for the IndiaMart sync button (2026-07-26). Managers /
Admins already qualify via role; this flag lets an admin grant sync
access to individual Promotors without also giving them the rest of
the Manager toolkit (Agent Log peer visibility, FB sync, elevated edit
permissions, etc.).

Defaults to FALSE so every existing Promotor stays where they were.
Admin toggles per-user via the user admin form.

Idempotent — no-op on re-run.
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


def migrate():
    with app.app_context():
        print('=== users.can_indiamart_sync migration ===')
        if column_exists('users', 'can_indiamart_sync'):
            print('  ok  users.can_indiamart_sync (already present)')
            return True
        print('  add users.can_indiamart_sync')
        db.session.execute(text(
            'ALTER TABLE users '
            'ADD COLUMN can_indiamart_sync BOOLEAN NOT NULL DEFAULT FALSE'
        ))
        db.session.commit()
        print('Migration completed.')
        return True


if __name__ == '__main__':
    ok = migrate()
    raise SystemExit(0 if ok else 1)
