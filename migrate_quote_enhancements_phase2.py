"""
Migration script for Quote System Phase 2 Enhancements
- Add quote_type (B2B/B2C)
- Add chargeable_extra to quote_items
- Add 6 new additional charge fields
- Consolidate transport charges
"""

import pymysql
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

def run_migration():
    """Add new fields for quote system phase 2 enhancements"""
    
    # Parse DATABASE_URL
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    
    # Parse the URL
    url = urlparse(database_url.replace('mysql+pymysql://', 'mysql://'))
    
    # Connect to database
    connection = pymysql.connect(
        host=url.hostname,
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        database=url.path[1:],
        cursorclass=pymysql.cursors.DictCursor
    )
    
    try:
        with connection.cursor() as cursor:
            print("Starting Quote System Phase 2 migration...")
            
            # Add quote_type to quotes table
            print("\n1. Adding quote_type column...")
            try:
                cursor.execute("""
                    ALTER TABLE quotes 
                    ADD COLUMN quote_type ENUM('B2B', 'B2C') DEFAULT 'B2B' AFTER status
                """)
                print("   ✅ quote_type added")
            except pymysql.err.OperationalError as e:
                if "Duplicate column" in str(e):
                    print("   ⚠️  quote_type already exists")
                else:
                    raise
            
            # Add 6 new charge fields to quotes table
            charge_fields = [
                ('cutout_charges', 'Cutout Charges'),
                ('holes_charges', 'Holes Charges'),
                ('shape_cutting_charges', 'Shape Cutting Charges'),
                ('jumbo_size_charges', 'Jumbo Size Charges'),
                ('template_charges', 'Template Charges'),
                ('handling_charges', 'Handling Charges')
            ]
            
            print("\n2. Adding new charge fields to quotes table...")
            for field_name, display_name in charge_fields:
                try:
                    cursor.execute(f"""
                        ALTER TABLE quotes 
                        ADD COLUMN {field_name} DECIMAL(10,2) DEFAULT 0 
                        AFTER transport_charges
                    """)
                    print(f"   ✅ {display_name} added")
                except pymysql.err.OperationalError as e:
                    if "Duplicate column" in str(e):
                        print(f"   ⚠️  {display_name} already exists")
                    else:
                        raise
            
            # Add chargeable_extra to quote_items table
            print("\n3. Adding chargeable_extra to quote_items...")
            try:
                cursor.execute("""
                    ALTER TABLE quote_items 
                    ADD COLUMN chargeable_extra INT DEFAULT 30 
                    AFTER unit
                """)
                print("   ✅ chargeable_extra added")
            except pymysql.err.OperationalError as e:
                if "Duplicate column" in str(e):
                    print("   ⚠️  chargeable_extra already exists")
                else:
                    raise
            
            # Update existing items to calculate chargeable dimensions
            print("\n4. Updating existing items with chargeable dimensions...")
            cursor.execute("""
                UPDATE quote_items
                SET chargeable_width = actual_width + chargeable_extra,
                    chargeable_height = actual_height + chargeable_extra
                WHERE actual_width IS NOT NULL 
                AND actual_height IS NOT NULL
                AND chargeable_width IS NULL
            """)
            affected = cursor.rowcount
            print(f"   ✅ Updated {affected} items with chargeable dimensions")
            
            # Recalculate unit_square for existing items (convert to Sq Mtr)
            print("\n5. Recalculating unit_square in Sq Mtr...")
            cursor.execute("""
                UPDATE quote_items
                SET unit_square = (chargeable_width * chargeable_height) / 1000000
                WHERE chargeable_width IS NOT NULL 
                AND chargeable_height IS NOT NULL
                AND unit = 'MM'
            """)
            affected = cursor.rowcount
            print(f"   ✅ Recalculated {affected} items to Sq Mtr")
            
            # Commit changes
            connection.commit()
            print("\n✅ Migration completed successfully!")
            
            # Show updated table structures
            print("\n" + "="*60)
            print("Updated quotes table structure:")
            print("="*60)
            cursor.execute("DESCRIBE quotes")
            for row in cursor.fetchall():
                if row['Field'] in ['quote_type', 'cutout_charges', 'holes_charges', 
                                   'shape_cutting_charges', 'jumbo_size_charges', 
                                   'template_charges', 'handling_charges']:
                    print(f"  ✨ {row['Field']}: {row['Type']} {row['Null']} {row['Default']}")
            
            print("\n" + "="*60)
            print("Updated quote_items table structure:")
            print("="*60)
            cursor.execute("DESCRIBE quote_items")
            for row in cursor.fetchall():
                if row['Field'] in ['chargeable_extra', 'unit_square']:
                    print(f"  ✨ {row['Field']}: {row['Type']} {row['Null']} {row['Default']}")
                    
    except Exception as e:
        connection.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        connection.close()

if __name__ == '__main__':
    print("="*60)
    print("Quote System Phase 2 Enhancement Migration")
    print("="*60)
    print("\nThis will add the following to the database:")
    print("  Quotes table:")
    print("    - quote_type (B2B/B2C)")
    print("    - cutout_charges")
    print("    - holes_charges")
    print("    - shape_cutting_charges")
    print("    - jumbo_size_charges")
    print("    - template_charges")
    print("    - handling_charges")
    print("\n  Quote Items table:")
    print("    - chargeable_extra (default 30MM)")
    print("\n" + "="*60)
    
    response = input("\nProceed with migration? (yes/no): ")
    if response.lower() == 'yes':
        run_migration()
    else:
        print("Migration cancelled.")
