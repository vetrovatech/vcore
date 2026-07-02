"""
One-shot migration: collapse Leadfy's two-funnel stage system into one
canonical 11-stage funnel.

Before this migration:
  - Default funnel (IndiaMart / Website / Manual leads):
        New Lead / Contacted / Not Connected / Qualified / PI Shared /
        Closed Won / Closed Lost / Junk
  - Facebook funnel:
        Untouched / Yet to connect / Quote 1 Shared / Quote 2 Shared /
        Quote 3 Shared / Not Interested / Awaiting Payment / Payment Rcvd /
        Lost / Junk

After:
  - Single funnel — see LEAD_STAGES in models.py — 11 stages that cover
    the union of both source funnels with clean, cross-verifiable
    vocabulary.

What this script does:
  1. UPDATE leads.stage per STAGE_MAP below (identity-map for canonical
     names; rename for aliased names).
  2. String-replace stage names inside lead_history.description (HTML
     free-text) so agent logs use the new vocabulary end-to-end.
  3. Print before/after counts so you can eyeball the migration.

By default this is a DRY RUN — prints what WOULD change, writes nothing.
Pass --apply to actually write.

Idempotent — safe to run twice. Rows already on canonical stages are
untouched.

Cross-verification design note (why we rewrite history strings too):
  BD reads lead_history to reconcile "when did X move from Y to Z". If
  the strings kept old names ('Untouched' → 'Quote 1 Shared') while the
  live rows used new names ('New Lead' → 'Quote 1 Shared'), a stage
  filter on the leads list wouldn't match the log entries — the whole
  point of consolidation was to make cross-source cross-verification
  work at a single vocabulary level.
"""

import argparse
import sys
from collections import Counter

from sqlalchemy import text

from app import app, db
from models import Lead, LeadHistory


# ── Rename table ─────────────────────────────────────────────────────────────
# Old stage name → new canonical stage name. Only stages that CHANGE are
# listed; canonical stages ('New Lead', 'Contacted', 'Qualified', etc.)
# are left off intentionally so we can spot any that shouldn't have moved.
STAGE_MAP = {
    # Facebook-funnel renames
    'Untouched':        'New Lead',
    'Yet to connect':   'Not Connected',
    'Payment Rcvd':     'Closed Won',
    'Lost':             'Closed Lost',
    'Not Interested':   'Closed Lost',
    # Default-funnel renames
    'PI Shared':        'Quote 1 Shared',
}

CANONICAL_STAGES = {
    'New Lead', 'Contacted', 'Not Connected', 'Qualified',
    'Quote 1 Shared', 'Quote 2 Shared', 'Quote 3 Shared',
    'Awaiting Payment', 'Closed Won', 'Closed Lost', 'Junk',
}


def _snapshot_lead_stages():
    """Return a Counter of stage → live-lead-count."""
    rows = (db.session.query(Lead.stage, db.func.count(Lead.id))
                       .group_by(Lead.stage).all())
    return Counter({stage: n for stage, n in rows})


def _snapshot_history_stages():
    """Return a Counter of stage → occurrences in stage_change descriptions.
    Rough by design — we grep the description for each old-name substring."""
    counter = Counter()
    for old in STAGE_MAP:
        n = (db.session.query(db.func.count(LeadHistory.id))
                        .filter(LeadHistory.action == 'stage_change',
                                LeadHistory.description.like(f'%<strong>{old}</strong>%'))
                        .scalar()) or 0
        if n:
            counter[old] = n
    return counter


def _print_diff(title, before, after, expected_moves):
    """Show before → after next to expected_moves so the user can eyeball
    that the deltas match the mapping table."""
    print(f'\n── {title} ─────────────────────────────────────────────')
    all_keys = sorted(set(before) | set(after))
    for key in all_keys:
        b = before.get(key, 0)
        a = after.get(key, 0)
        delta = a - b
        arrow = '→ same' if delta == 0 else f'→ {a}  (Δ {delta:+d})'
        expected = f'  [expected: {expected_moves.get(key, 0):+d}]' if key in expected_moves else ''
        print(f'  {key:<24} {b:>6} {arrow}{expected}')


def _expected_deltas():
    """Predict the per-stage delta based on STAGE_MAP + current live counts."""
    live = _snapshot_lead_stages()
    delta = Counter()
    for old, new in STAGE_MAP.items():
        n = live.get(old, 0)
        delta[old] -= n
        delta[new] += n
    return delta


def run(apply):
    with app.app_context():
        print('=' * 72)
        print(f'LEAD-STAGE CONSOLIDATION MIGRATION  ({"APPLY" if apply else "DRY RUN"})')
        print('=' * 72)

        # ── Before snapshot ─────────────────────────────────────────────
        live_before = _snapshot_lead_stages()
        hist_before = _snapshot_history_stages()
        expected_deltas = _expected_deltas()

        print(f'\nLive leads by stage (before): {sum(live_before.values()):,} total')
        for stage, n in live_before.most_common():
            marker = '  (rename)' if stage in STAGE_MAP else ('' if stage in CANONICAL_STAGES else '  (UNKNOWN!)')
            print(f'  {stage:<24} {n:>6}{marker}')

        print(f'\nHistory rows containing old stage names (before):')
        if hist_before:
            for stage, n in hist_before.most_common():
                print(f'  {stage:<24} {n:>6} log rows to rewrite')
        else:
            print('  (none — history log already clean)')

        # ── The writes ──────────────────────────────────────────────────
        if apply:
            print('\n── Writing changes ──────────────────────────────────')
            with db.engine.begin() as conn:
                for old, new in STAGE_MAP.items():
                    # 1. leads.stage
                    lead_n = conn.execute(
                        text('UPDATE leads SET stage = :new WHERE stage = :old'),
                        {'old': old, 'new': new},
                    ).rowcount
                    # 2. lead_history.description — replace the two boldened
                    #    occurrences (from_stage + to_stage tokens) in one go.
                    hist_n = conn.execute(
                        text(
                            "UPDATE lead_history "
                            "SET description = REPLACE(description, :old_tag, :new_tag) "
                            "WHERE action = 'stage_change' "
                            "  AND description LIKE :like_expr"
                        ),
                        {
                            'old_tag': f'<strong>{old}</strong>',
                            'new_tag': f'<strong>{new}</strong>',
                            'like_expr': f'%<strong>{old}</strong>%',
                        },
                    ).rowcount
                    print(f'  {old:<24} → {new:<20}  leads: {lead_n:>4}   history: {hist_n:>4}')

        # ── After snapshot ──────────────────────────────────────────────
        live_after = _snapshot_lead_stages()
        hist_after = _snapshot_history_stages()

        _print_diff('Live leads (before → after)', live_before, live_after, expected_deltas)

        print('\n── History rows still containing OLD stage names ──')
        if hist_after:
            for stage, n in hist_after.most_common():
                print(f'  {stage:<24} {n:>6}  ← NOT REWRITTEN')
            if apply:
                print('  ↑ if nonzero after --apply, something went wrong.')
        else:
            print('  (none — all history strings are on canonical vocabulary ✓)')

        # ── Unknown stages guard ─────────────────────────────────────────
        unknown = {s: n for s, n in live_after.items()
                    if s not in CANONICAL_STAGES and s not in STAGE_MAP}
        if unknown:
            print('\n⚠  Leads on UNKNOWN stages (not in the canonical set AND '
                  'not in the rename map):')
            for stage, n in sorted(unknown.items(), key=lambda x: -x[1]):
                print(f'  {stage:<24} {n:>6}')
            print('  These will not be filterable on the new leads-list UI. '
                  'Add them to STAGE_MAP or fix them manually.')

        print('\n' + ('✓ Applied.' if apply else '✓ DRY RUN complete — no writes. '
                                                  'Pass --apply to write.'))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true',
                    help='Actually write. Without this flag, dry-run only.')
    args = ap.parse_args()
    run(args.apply)
