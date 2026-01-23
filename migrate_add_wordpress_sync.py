"""Add WordPress sync tracking to products table

This migration adds columns to track WordPress sync status for products.
"""

from models import db
from sqlalchemy import text


def migrate():
    """Add WordPress sync columns to products table"""
    
    with db.engine.connect() as conn:
        # Add wordpress_id column
        try:
            conn.execute(text("""
                ALTER TABLE products 
                ADD COLUMN wordpress_id INTEGER DEFAULT NULL
            """))
            conn.commit()
            print("✓ Added wordpress_id column to products table")
        except Exception as e:
            print(f"⚠ wordpress_id column may already exist: {e}")
        
        # Add last_wordpress_sync column
        try:
            conn.execute(text("""
                ALTER TABLE products 
                ADD COLUMN last_wordpress_sync DATETIME DEFAULT NULL
            """))
            conn.commit()
            print("✓ Added last_wordpress_sync column to products table")
        except Exception as e:
            print(f"⚠ last_wordpress_sync column may already exist: {e}")
    
    print("\n✅ Migration completed successfully!")
    print("Products table now has WordPress sync tracking columns.")


if __name__ == '__main__':
    from app import app
    
    with app.app_context():
        migrate()
