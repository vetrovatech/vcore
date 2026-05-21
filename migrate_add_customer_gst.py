"""Migration: Add customer_gst column to quotes table"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        with db.engine.connect() as conn:
            # Check if column already exists (MySQL)
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'quotes' "
                "AND column_name = 'customer_gst'"
            ))
            exists = result.scalar()

            if not exists:
                conn.execute(text("ALTER TABLE quotes ADD COLUMN customer_gst VARCHAR(20)"))
                conn.commit()
                print("✓ Added customer_gst column to quotes table")
            else:
                print("✓ customer_gst column already exists — skipping")

if __name__ == '__main__':
    migrate()
