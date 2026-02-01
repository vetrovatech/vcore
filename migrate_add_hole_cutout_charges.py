#!/usr/bin/env python3
"""
Migration script to add hole/cutout fields to quote_items
and polish/document/frosted charges to quotes table
"""

from app import app, db
from sqlalchemy import text

def run_migration():
    with app.app_context():
        print("Starting migration...")
        
        try:
            # Add hole and cutout to quote_items
            print("Adding hole and cutout columns to quote_items...")
            try:
                db.session.execute(text('ALTER TABLE quote_items ADD COLUMN hole INTEGER DEFAULT 0 NOT NULL'))
                print("  ✓ Added hole column")
            except Exception as e:
                if 'Duplicate column name' in str(e):
                    print("  - hole column already exists")
                else:
                    raise
            
            try:
                db.session.execute(text('ALTER TABLE quote_items ADD COLUMN cutout INTEGER DEFAULT 0 NOT NULL'))
                print("  ✓ Added cutout column")
            except Exception as e:
                if 'Duplicate column name' in str(e):
                    print("  - cutout column already exists")
                else:
                    raise
            
            # Add new charges to quotes
            print("Adding polish_charges, document_charges, frosted_charges to quotes...")
            try:
                db.session.execute(text('ALTER TABLE quotes ADD COLUMN polish_charges NUMERIC(10, 2) DEFAULT 0.00 NOT NULL'))
                print("  ✓ Added polish_charges column")
            except Exception as e:
                if 'Duplicate column name' in str(e):
                    print("  - polish_charges column already exists")
                else:
                    raise
            
            try:
                db.session.execute(text('ALTER TABLE quotes ADD COLUMN document_charges NUMERIC(10, 2) DEFAULT 0.00 NOT NULL'))
                print("  ✓ Added document_charges column")
            except Exception as e:
                if 'Duplicate column name' in str(e):
                    print("  - document_charges column already exists")
                else:
                    raise
            
            try:
                db.session.execute(text('ALTER TABLE quotes ADD COLUMN frosted_charges NUMERIC(10, 2) DEFAULT 0.00 NOT NULL'))
                print("  ✓ Added frosted_charges column")
            except Exception as e:
                if 'Duplicate column name' in str(e):
                    print("  - frosted_charges column already exists")
                else:
                    raise
            
            db.session.commit()
            print("\n✅ Migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Migration failed: {str(e)}")
            raise

if __name__ == '__main__':
    run_migration()
