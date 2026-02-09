#!/usr/bin/env python3
"""
Migration script to add Supplier, GlassType, and SupplierPricing tables
Run this to create the new tables for supplier and glass catalog management
"""
from app import app, db
from models import Supplier, GlassType, SupplierPricing

def migrate():
    """Create new tables for supplier and glass catalog management"""
    with app.app_context():
        print("Creating new tables for supplier and glass catalog management...")
        
        # Create tables
        db.create_all()
        
        print("✅ Tables created successfully!")
        print("\nNew tables:")
        print("  - suppliers")
        print("  - glass_types")
        print("  - supplier_pricing")
        
        # Verify tables were created
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'suppliers' in tables and 'glass_types' in tables and 'supplier_pricing' in tables:
            print("\n✅ Migration completed successfully!")
        else:
            print("\n⚠️  Warning: Some tables may not have been created")
            print(f"Existing tables: {tables}")

if __name__ == '__main__':
    migrate()
