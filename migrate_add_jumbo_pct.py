#!/usr/bin/env python3
"""
Migration: Add jumbo percentage tier columns to quotes table
"""

from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        try:
            result = db.session.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='quotes'
                AND column_name IN ('jumbo_pct_tier1', 'jumbo_pct_tier2', 'jumbo_pct_tier3')
            """))
            existing = [row[0] for row in result]

            for col, default in [('jumbo_pct_tier1', 10), ('jumbo_pct_tier2', 15), ('jumbo_pct_tier3', 20)]:
                if col not in existing:
                    print(f"Adding {col}...")
                    db.session.execute(text(f"""
                        ALTER TABLE quotes
                        ADD COLUMN {col} DECIMAL(5,2) NOT NULL DEFAULT {default}
                    """))
                    print(f"Added {col}")
                else:
                    print(f"{col} already exists")

            db.session.commit()
            print("Migration completed!")

        except Exception as e:
            db.session.rollback()
            print(f"Migration failed: {str(e)}")
            raise

if __name__ == '__main__':
    migrate()
