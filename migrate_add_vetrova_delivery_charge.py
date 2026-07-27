"""
Migration: add `delivery_charge` column to `vetrova_quotes` and backfill
the field on every existing quote by re-running recompute_totals().

BD rule (2026-07-27): quotes with subtotal < ₹20,000 carry a ₹2,000
delivery charge; ≥ ₹20,000 gets free delivery. The rule lives on
VetrovaQuote.recompute_totals() — this migration just backfills so
existing quotes render the correct grand total the next time they're
viewed / PDF-rendered / revised.

Idempotent — safe to re-run.
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
        print('=== vetrova_quotes.delivery_charge migration ===')
        if not column_exists('vetrova_quotes', 'delivery_charge'):
            print('  add vetrova_quotes.delivery_charge')
            db.session.execute(text(
                'ALTER TABLE vetrova_quotes '
                'ADD COLUMN delivery_charge NUMERIC(10,2) NOT NULL DEFAULT 0'
            ))
            db.session.commit()
        else:
            print('  ok  vetrova_quotes.delivery_charge (already present)')

        # Backfill: re-run recompute_totals() on every quote so the new
        # rule applies retroactively. Uses the ORM so the same code path
        # the ingest + revise use. If a quote has no items yet (edge case
        # from the pre-Phase-1 era) delivery stays at 0.
        from models import VetrovaQuote
        touched = 0
        for q in VetrovaQuote.query.all():
            q.recompute_totals()
            touched += 1
        db.session.commit()
        print(f'  ok  recomputed totals for {touched} existing quote(s)')

        # Show how many quotes now carry the delivery fee.
        with_fee = VetrovaQuote.query.filter(
            VetrovaQuote.delivery_charge > 0
        ).count()
        print(f'  ok  {with_fee} quote(s) now show delivery ₹2,000 (subtotal < ₹20,000)')
        print('Migration completed.')
        return True


if __name__ == '__main__':
    ok = migrate()
    raise SystemExit(0 if ok else 1)
