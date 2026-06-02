"""
Migration: add bathqube_work_orders + bathqube_stage_attachments tables.

Backs the ops-team fulfillment flow for Bathqube orders (post closed_won):
  - bathqube_work_orders        — one row per quote, per-stage assignees +
                                  scheduling + fabrication vendor + ops notes
  - bathqube_stage_attachments  — many rows per quote, photos/files keyed
                                  to the ops stage they belong to

Idempotent — db.create_all() only creates tables that don't exist yet, so
re-running is safe. Existing bathqube_quotes / bathqube_status_events rows
are not touched.

Run via docker-compose:
    docker-compose run --rm vcore python migrate_add_bathqube_work_orders.py
or directly with DATABASE_URL exported:
    python migrate_add_bathqube_work_orders.py
"""

from app import app, db
from models import BathqubeWorkOrder, BathqubeStageAttachment  # noqa: F401


def migrate():
    with app.app_context():
        print("Creating bathqube_work_orders + bathqube_stage_attachments tables...")
        db.create_all()

        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        ok = True
        for t in ('bathqube_work_orders', 'bathqube_stage_attachments'):
            if t in tables:
                print(f"  ok  {t}")
            else:
                print(f"  FAIL {t} not created")
                ok = False

        if ok:
            print("\nMigration completed.")
        else:
            print("\nMigration failed.")
        return ok


if __name__ == '__main__':
    migrate()
