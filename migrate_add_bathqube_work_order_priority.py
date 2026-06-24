"""
Migration: add priority column to bathqube_work_orders.

Drives the workshop-floor priority badge on the Work Order PDF
('normal' / 'urgent' / 'low'). NOT NULL with a default, so existing
rows pick up 'normal' automatically without a backfill.

Idempotent — the ADD COLUMN is gated by an information_schema check;
re-running is a no-op.
"""

from sqlalchemy import inspect, text

from app import app, db


def migrate():
    with app.app_context():
        inspector = inspect(db.engine)
        cols = {c['name'] for c in inspector.get_columns('bathqube_work_orders')}
        if 'priority' in cols:
            print("ok  bathqube_work_orders.priority (already exists)")
            return True
        print("adding bathqube_work_orders.priority ...")
        with db.engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE bathqube_work_orders "
                "ADD COLUMN priority VARCHAR(10) NOT NULL DEFAULT 'normal'"
            ))
        print("ok  bathqube_work_orders.priority")
        return True


if __name__ == '__main__':
    migrate()
