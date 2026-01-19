# -*- coding: utf-8 -*-
"""
Migration script to add daily_updates table to the database
Run this script to add the DailyUpdate feature to VCore
"""
import os
import sys
import pymysql
from datetime import datetime

# Install PyMySQL as MySQLdb
pymysql.install_as_MySQLdb()

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import DailyUpdate


def migrate():
    """Add daily_updates table to database"""
    with app.app_context():
        print("Starting migration: Adding daily_updates table...")
        
        try:
            # Create the daily_updates table
            db.create_all()
            print("✓ Successfully created daily_updates table")
            
            # Verify table was created
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'daily_updates' in tables:
                print("✓ Verified daily_updates table exists")
                
                # Show table columns
                columns = inspector.get_columns('daily_updates')
                print("\nTable columns:")
                for col in columns:
                    print(f"  - {col['name']}: {col['type']}")
                
                # Show indexes
                indexes = inspector.get_indexes('daily_updates')
                print("\nTable indexes:")
                for idx in indexes:
                    print(f"  - {idx['name']}: {idx['column_names']}")
                
                print("\n✓ Migration completed successfully!")
            else:
                print("✗ Error: daily_updates table was not created")
                return False
                
        except Exception as e:
            print(f"✗ Migration failed: {str(e)}")
            db.session.rollback()
            return False
    
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("VCore Database Migration: Add Daily Updates")
    print("=" * 60)
    print()
    
    success = migrate()
    
    if success:
        print("\n" + "=" * 60)
        print("Migration completed successfully!")
        print("You can now use the Daily Updates feature.")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("Migration failed. Please check the errors above.")
        print("=" * 60)
        sys.exit(1)
