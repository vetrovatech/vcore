#!/usr/bin/env python3
"""
Migration: Add hole_price and cutout_price to quote_items table
"""

from app import app, db
from sqlalchemy import text

def migrate():
    """Add hole_price and cutout_price columns to quote_items table"""
    with app.app_context():
        try:
            # Check if columns already exist
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='quote_items' 
                AND column_name IN ('hole_price', 'cutout_price')
            """))
            existing_columns = [row[0] for row in result]
            
            if 'hole_price' in existing_columns and 'cutout_price' in existing_columns:
                print("✓ Columns hole_price and cutout_price already exist in quote_items table")
                return
            
            # Add hole_price column if it doesn't exist
            if 'hole_price' not in existing_columns:
                print("Adding hole_price column to quote_items table...")
                db.session.execute(text("""
                    ALTER TABLE quote_items 
                    ADD COLUMN hole_price DECIMAL(10, 2) DEFAULT 0.00 NOT NULL
                """))
                print("✓ Added hole_price column")
            
            # Add cutout_price column if it doesn't exist
            if 'cutout_price' not in existing_columns:
                print("Adding cutout_price column to quote_items table...")
                db.session.execute(text("""
                    ALTER TABLE quote_items 
                    ADD COLUMN cutout_price DECIMAL(10, 2) DEFAULT 0.00 NOT NULL
                """))
                print("✓ Added cutout_price column")
            
            db.session.commit()
            print("✓ Migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Migration failed: {str(e)}")
            raise

if __name__ == '__main__':
    migrate()
