"""One-shot migration: switch bathqube quotes to the new sales-pipeline model.

Behaviour:
  1. bathqube_quotes.stage — blanket reset every row to 'quote_generated'.
     The sales team is restarting the pipeline from scratch under the new
     stage model, so old production-lifecycle classifications are dropped.
  2. bathqube_status_events.{from,to}_stage — granular map per old code so
     the historical audit trail still renders meaningful labels.

Idempotent — safe to re-run. Anything already in the new stage codes is left
alone.

Run from inside the container (DATABASE_URL is read from env):
    python migrate_bathqube_stages.py
"""
from app import app, db
from models import BATHQUBE_LEGACY_STAGE_MAP


def run():
    with app.app_context():
        print('=== bathqube stage migration ===')
        print()

        # 1. Blanket reset current stage on all quotes to 'quote_generated'.
        print('Step 1 — reset bathqube_quotes.stage to "quote_generated" for all rows')
        r = db.session.execute(
            db.text("UPDATE bathqube_quotes SET stage = 'quote_generated' WHERE stage != 'quote_generated'")
        )
        print(f'  rows updated: {r.rowcount}')
        print()

        # 2. Preserve audit-trail accuracy by mapping historical events per old code.
        print('Step 2 — remap historical bathqube_status_events stages (granular)')
        for old, new in BATHQUBE_LEGACY_STAGE_MAP.items():
            r2 = db.session.execute(
                db.text('UPDATE bathqube_status_events SET to_stage = :new WHERE to_stage = :old'),
                {'old': old, 'new': new},
            )
            r3 = db.session.execute(
                db.text('UPDATE bathqube_status_events SET from_stage = :new WHERE from_stage = :old'),
                {'old': old, 'new': new},
            )
            print(f'  {old:<22} -> {new:<20} | to_stage={r2.rowcount}  from_stage={r3.rowcount}')

        db.session.commit()
        print()
        print('=== resulting stage distribution on bathqube_quotes ===')
        rows = db.session.execute(
            db.text('SELECT stage, COUNT(*) AS n FROM bathqube_quotes GROUP BY stage ORDER BY n DESC')
        ).all()
        for r in rows:
            print(f'  {r.stage:<22} {r.n}')


if __name__ == '__main__':
    run()
