"""
One-shot migration: hide 4 team members from /leads/agent-log and
reassign one of them's owned leads to Unowned.

Manager's ask (2026-07-02):
  * Remove `sumit`, `ansar`, `shekar`, `rahul` from the agent-log matrix.
    Their accounts stay active — they can still log in, edit leads,
    everything. They just don't get a column on /leads/agent-log any more.
  * Reassign every lead currently owned by `ansar` (182 rows) to Unowned
    (owner_id = NULL) so it shows up under the Unowned column instead of
    a defunct one.

What this script does:
  1. Adds `show_in_agent_log BOOLEAN NOT NULL DEFAULT TRUE` to `users`
     (idempotent — ALTER wrapped in DO $$ EXCEPTION WHEN duplicate_column).
  2. UPDATE users SET show_in_agent_log = FALSE WHERE username IN (...).
  3. UPDATE leads SET owner_id = NULL WHERE owner_id = (SELECT id FROM users
     WHERE username = 'ansar').
  4. Prints before / after counts so you can eyeball.

Dry-run by default (writes nothing). Pass --apply to write.

Idempotent — safe to re-run.
"""

import argparse

from sqlalchemy import text

from app import app, db
from models import Lead, User


HIDDEN_USERNAMES = ['sumit', 'ansar', 'Shekar', 'rahul']
UNOWNED_SOURCE   = 'ansar'  # only this user's leads flip to owner_id=NULL


def _snapshot():
    """Read the current relevant state via raw SQL — avoids SELECTing the new
    show_in_agent_log column before it exists in the DB (which would blow up
    the pre-migration dry-run since the ORM includes every mapped column in
    every SELECT). Returns a lightweight dict per hidden user."""
    col_exists = _has_column()
    if col_exists:
        rows = db.session.execute(text(
            "SELECT id, username, is_active, show_in_agent_log "
            "FROM users WHERE username = ANY(:names)"
        ), {'names': HIDDEN_USERNAMES}).mappings().all()
    else:
        rows = db.session.execute(text(
            "SELECT id, username, is_active, NULL::boolean AS show_in_agent_log "
            "FROM users WHERE username = ANY(:names)"
        ), {'names': HIDDEN_USERNAMES}).mappings().all()
    by_username = {r['username']: dict(r) for r in rows}
    owned_counts = {}
    for uname in HIDDEN_USERNAMES:
        u = by_username.get(uname)
        if u:
            owned_counts[uname] = db.session.execute(
                text("SELECT count(*) FROM leads WHERE owner_id = :oid"),
                {'oid': u['id']},
            ).scalar() or 0
        else:
            owned_counts[uname] = 0
    unowned_total = db.session.execute(
        text("SELECT count(*) FROM leads WHERE owner_id IS NULL")
    ).scalar() or 0
    return by_username, owned_counts, unowned_total


def _has_column():
    row = db.session.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'users' AND column_name = 'show_in_agent_log'"
    )).first()
    return row is not None


def run(apply):
    with app.app_context():
        print('=' * 72)
        print(f'AGENT-LOG HIDE MIGRATION  ({"APPLY" if apply else "DRY RUN"})')
        print('=' * 72)

        # ── Before ─────────────────────────────────────────────────────
        by_username, owned_before, unowned_before = _snapshot()
        col_exists = _has_column()

        print(f'\nColumn `users.show_in_agent_log` present before: {col_exists}')
        print(f'\nTarget users (owned lead counts BEFORE):')
        for uname in HIDDEN_USERNAMES:
            u = by_username.get(uname)
            if not u:
                print(f'  {uname:<10} ✗ not found in DB (skipping)')
                continue
            flag = u.get('show_in_agent_log') if col_exists else '(no col yet)'
            print(f'  {uname:<10} id={u["id"]:<4} active={u["is_active"]}  show_in_agent_log={flag}  owned={owned_before[uname]:>4}')
        print(f'\nCurrent Unowned lead total: {unowned_before}')

        # ── Writes ─────────────────────────────────────────────────────
        if apply:
            print('\n── Writing changes ──────────────────────────────────')

            # 1. Column
            if not col_exists:
                print('  adding column users.show_in_agent_log (default TRUE)...')
                with db.engine.begin() as conn:
                    conn.execute(text(
                        "ALTER TABLE users ADD COLUMN show_in_agent_log "
                        "BOOLEAN NOT NULL DEFAULT TRUE"
                    ))
            else:
                print('  column users.show_in_agent_log already present, skipping ADD.')

            # 2. Hide the 4 usernames
            n_hidden = db.session.execute(
                text('UPDATE users SET show_in_agent_log = FALSE '
                     'WHERE username IN :names AND show_in_agent_log = TRUE'),
                {'names': tuple(HIDDEN_USERNAMES)},
            ).rowcount
            print(f'  flipped {n_hidden} users to show_in_agent_log = FALSE')

            # 3. Reassign ansar's leads → Unowned
            src = by_username.get(UNOWNED_SOURCE)
            if src:
                n_unowned = db.session.execute(
                    text('UPDATE leads SET owner_id = NULL WHERE owner_id = :src_id'),
                    {'src_id': src['id']},
                ).rowcount
                print(f'  reassigned {n_unowned} leads from `{UNOWNED_SOURCE}` (id={src["id"]}) → owner_id=NULL')
            else:
                print(f'  ⚠ user `{UNOWNED_SOURCE}` not found — no lead reassignment done')

            db.session.commit()

        # ── After ──────────────────────────────────────────────────────
        db.session.expire_all()
        by_username_after, owned_after, unowned_after = _snapshot()
        col_exists_after = _has_column()

        print('\n── After ────────────────────────────────────────────────')
        print(f'Column `users.show_in_agent_log` present: {col_exists_after}')
        print(f'\nTarget users (owned lead counts AFTER):')
        for uname in HIDDEN_USERNAMES:
            u = by_username_after.get(uname)
            if not u: continue
            flag = u.get('show_in_agent_log') if col_exists_after else '(no col yet)'
            delta = owned_after[uname] - owned_before[uname]
            print(f'  {uname:<10} id={u["id"]:<4} show_in_agent_log={flag}  owned={owned_after[uname]:>4}  (Δ {delta:+d})')
        print(f'\nUnowned lead total: {unowned_before} → {unowned_after}  (Δ {unowned_after - unowned_before:+d})')

        print('\n' + ('✓ Applied.' if apply else '✓ DRY RUN complete — no writes. Pass --apply to write.'))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true',
                    help='Actually write. Without this flag, dry-run only.')
    args = ap.parse_args()
    run(args.apply)
