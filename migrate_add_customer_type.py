"""Migration: add customer_type column to leads table"""
import os, sys
sys.path.insert(0, '/app')
from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE leads ADD COLUMN customer_type VARCHAR(10) NULL"))
            conn.commit()
            print("✓ Added customer_type column to leads table")
        except Exception as e:
            if 'duplicate' in str(e).lower() or 'already exists' in str(e).lower():
                print("✓ customer_type column already exists")
            else:
                print(f"✗ Error: {e}")
                raise
