"""Migration: Add quote_id column to reminders table"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from sqlalchemy import text


def migrate():
    with app.app_context():
        with db.engine.connect() as conn:
            # Check if column already exists
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'reminders' "
                "AND column_name = 'quote_id'"
            ))
            exists = result.scalar()

            if exists:
                print("Column 'quote_id' already exists in reminders table. Skipping.")
            else:
                conn.execute(text(
                    "ALTER TABLE reminders "
                    "ADD COLUMN quote_id INT NULL, "
                    "ADD INDEX idx_reminder_quote (quote_id), "
                    "ADD CONSTRAINT fk_reminder_quote FOREIGN KEY (quote_id) REFERENCES quotes(id)"
                ))
                conn.commit()
                print("Migration complete: 'quote_id' column added to reminders table.")


if __name__ == '__main__':
    migrate()
