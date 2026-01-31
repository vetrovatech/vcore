"""
Migration script to add quotes and quote_items tables
Run this script to create the necessary database tables for the quote generation system
"""

from app import app, db
from models import Quote, QuoteItem

def migrate():
    """Create quotes and quote_items tables"""
    with app.app_context():
        print("Creating quotes and quote_items tables...")
        
        # Create tables
        db.create_all()
        
        print("✓ Tables created successfully!")
        print("  - quotes")
        print("  - quote_items")
        
        # Verify tables exist
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'quotes' in tables and 'quote_items' in tables:
            print("\n✓ Migration completed successfully!")
            
            # Show table structure
            print("\nQuotes table columns:")
            for column in inspector.get_columns('quotes'):
                print(f"  - {column['name']}: {column['type']}")
            
            print("\nQuote Items table columns:")
            for column in inspector.get_columns('quote_items'):
                print(f"  - {column['name']}: {column['type']}")
        else:
            print("\n✗ Migration failed - tables not found")
            return False
        
        return True

if __name__ == '__main__':
    migrate()
