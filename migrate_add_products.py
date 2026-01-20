"""
Migration script to add products table to the database
Run this script to create the products table
"""
from app import app
from models import db, Product
from sqlalchemy import text

def create_products_table():
    """Create the products table"""
    with app.app_context():
        print("Creating products table...")
        
        # Create the table
        db.create_all()
        
        # Verify table was created
        inspector = db.inspect(db.engine)
        if 'products' in inspector.get_table_names():
            print("✓ Products table created successfully!")
            
            # Show table structure
            columns = inspector.get_columns('products')
            print("\nTable structure:")
            for col in columns:
                print(f"  - {col['name']}: {col['type']}")
            
            return True
        else:
            print("✗ Failed to create products table")
            return False

if __name__ == '__main__':
    create_products_table()
