"""
Migration script to add bathqube_quotes + bathqube_status_events tables.

Run via docker-compose:
    docker-compose run --rm vcore python migrate_add_bathqube_quotes.py
or directly with DATABASE_URL exported:
    python migrate_add_bathqube_quotes.py
"""

from app import app, db
from models import BathqubeQuote, BathqubeStatusEvent  # noqa: F401


def migrate():
    with app.app_context():
        print("Creating bathqube_quotes + bathqube_status_events tables...")
        db.create_all()

        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        ok = True
        for t in ('bathqube_quotes', 'bathqube_status_events'):
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
