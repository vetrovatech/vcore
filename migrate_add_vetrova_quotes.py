"""
Migration script to add vetrova_quotes + vetrova_status_events tables.

Run via docker-compose:
    docker-compose run --rm vcore python migrate_add_vetrova_quotes.py
or directly with DATABASE_URL exported:
    python migrate_add_vetrova_quotes.py
"""

from app import app, db
from models import VetrovaQuote, VetrovaStatusEvent  # noqa: F401


def migrate():
    with app.app_context():
        print("Creating vetrova_quotes + vetrova_status_events tables...")
        db.create_all()

        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        ok = True
        for t in ('vetrova_quotes', 'vetrova_status_events'):
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
