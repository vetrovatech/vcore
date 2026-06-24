"""
Backfill: fetch Meta campaign / adset / ad / form names for existing
Facebook leads that pre-date the webhook-side capture in
facebook_webhook_receive.

For every Lead row where:
  origin = 'Facebook'  AND  facebook_lead_id IS NOT NULL  AND
  fb_campaign_id IS NULL   (i.e. ingested before the schema landed)

we hit Graph API:
  GET /<facebook_lead_id>?fields=ad_id,adset_id,campaign_id,
                                 campaign_name,adset_name,ad_name,form_name
and stamp the row.

Rate limits — Meta caps lead-form API at ~200 calls / hour per page. We
sleep 200ms between calls (5 req/s) which keeps us well under that for
realistic backfill sizes (~few thousand leads). Set BACKFILL_LIMIT=N to
process at most N rows per run; re-run later for the rest. Re-running
is safe: rows already filled in are skipped via the `fb_campaign_id IS
NULL` predicate.

Idempotent. No-op on a fresh prod that has no FB leads to backfill.

Usage:
    docker-compose run --rm vcore python backfill_lead_facebook_campaign.py
    BACKFILL_LIMIT=500 docker-compose run --rm vcore python backfill_lead_facebook_campaign.py
    DRY_RUN=1 docker-compose run --rm vcore python backfill_lead_facebook_campaign.py
"""

import os
import sys
import time

import requests

from app import app, db
from models import Lead


GRAPH_VERSION = 'v19.0'
THROTTLE_SEC = 0.20  # 5 req/s — well below Meta's lead-form quota


def backfill():
    page_token = os.getenv('FB_PAGE_ACCESS_TOKEN', '')
    if not page_token:
        print('FB_PAGE_ACCESS_TOKEN not set in env — cannot backfill', file=sys.stderr)
        return False

    dry_run = os.getenv('DRY_RUN', '').strip() in ('1', 'true', 'yes')
    limit_env = os.getenv('BACKFILL_LIMIT', '').strip()
    try:
        limit = int(limit_env) if limit_env else None
    except ValueError:
        limit = None

    with app.app_context():
        q = (
            Lead.query
            .filter(Lead.origin == 'Facebook')
            .filter(Lead.facebook_lead_id.isnot(None))
            .filter(Lead.fb_campaign_id.is_(None))
            .order_by(Lead.id)
        )
        if limit:
            q = q.limit(limit)
        leads = q.all()
        total = len(leads)
        if total == 0:
            print('Nothing to backfill — every Facebook lead already has fb_campaign_id set.')
            return True

        print(f'Backfilling {total} Facebook lead(s){"  [DRY RUN]" if dry_run else ""} …')

        ok = 0
        skipped = 0
        errors = 0
        for i, lead in enumerate(leads, start=1):
            try:
                resp = requests.get(
                    f'https://graph.facebook.com/{GRAPH_VERSION}/{lead.facebook_lead_id}',
                    params={
                        'access_token': page_token,
                        # form_name is NOT a leadgen-edge field (error #100).
                        # Form_id is already in notes — skip form_name.
                        'fields': (
                            'ad_id,adset_id,campaign_id,'
                            'campaign_name,adset_name,ad_name'
                        ),
                    },
                    timeout=10,
                )
                data = resp.json()
            except Exception as e:
                errors += 1
                print(f'  [{i}/{total}] #{lead.id} {lead.facebook_lead_id} :: fetch failed: {e}')
                continue

            if 'error' in data:
                err = data['error'].get('message', '')
                # Old / archived leads sometimes return "this lead has been
                # deleted" — not an error, just an absent record. Tag it
                # as skipped so the run summary stays clean.
                if 'deleted' in err.lower() or 'unsupported' in err.lower():
                    skipped += 1
                else:
                    errors += 1
                print(f'  [{i}/{total}] #{lead.id} {lead.facebook_lead_id} :: graph error: {err}')
                continue

            updates = {
                'fb_campaign_id':   data.get('campaign_id'),
                'fb_campaign_name': data.get('campaign_name'),
                'fb_adset_id':      data.get('adset_id'),
                'fb_adset_name':    data.get('adset_name'),
                'fb_ad_id':         data.get('ad_id'),
                'fb_ad_name':       data.get('ad_name'),
                # form_name not requested (see fields list above).
            }
            if not any(v for v in updates.values()):
                skipped += 1
                print(f'  [{i}/{total}] #{lead.id} :: no campaign data in response, skipped')
            else:
                if not dry_run:
                    for k, v in updates.items():
                        if v:
                            setattr(lead, k, v)
                ok += 1
                campaign = updates.get('fb_campaign_name') or updates.get('campaign_id') or '—'
                print(f'  [{i}/{total}] #{lead.id} ✓ {campaign}')

            # Stay polite with Meta's rate limit.
            time.sleep(THROTTLE_SEC)

        if not dry_run:
            try:
                db.session.commit()
                print(f'Committed {ok} updates.')
            except Exception as e:
                db.session.rollback()
                print(f'COMMIT FAILED: {e}', file=sys.stderr)
                return False

        print(f'=== done — updated {ok}, skipped {skipped}, errors {errors} of {total} ===')
        return True


if __name__ == '__main__':
    backfill()
