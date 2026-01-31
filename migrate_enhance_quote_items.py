"""
Migration script to enhance quote_items table with hierarchical structure
and detailed size specifications to match sample quote format.
"""

import pymysql
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

def run_migration():
    """Add new fields to quote_items table for enhanced quote system"""
    
    # Parse DATABASE_URL
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    
    # Parse the URL (format: mysql+pymysql://user:password@host:port/database)
    url = urlparse(database_url.replace('mysql+pymysql://', 'mysql://'))
    
    # Connect to database
    connection = pymysql.connect(
        host=url.hostname,
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        database=url.path[1:],  # Remove leading /
        cursorclass=pymysql.cursors.DictCursor
    )
    
    try:
        with connection.cursor() as cursor:
            print("Starting quote_items table enhancement migration...")
            
            # Add parent_id for hierarchical structure
            print("Adding parent_id column...")
            cursor.execute("""
                ALTER TABLE quote_items 
                ADD COLUMN parent_id INT NULL AFTER quote_id,
                ADD FOREIGN KEY (parent_id) REFERENCES quote_items(id) ON DELETE CASCADE
            """)
            
            # Add is_group flag
            print("Adding is_group column...")
            cursor.execute("""
                ALTER TABLE quote_items 
                ADD COLUMN is_group BOOLEAN DEFAULT FALSE AFTER parent_id
            """)
            
            # Add sort_order for custom ordering
            print("Adding sort_order column...")
            cursor.execute("""
                ALTER TABLE quote_items 
                ADD COLUMN sort_order INT DEFAULT 0 AFTER is_group
            """)
            
            # Rename existing size fields to actual_size
            print("Renaming size_width to actual_width...")
            cursor.execute("""
                ALTER TABLE quote_items 
                CHANGE COLUMN size_width actual_width DECIMAL(10,2) NULL
            """)
            
            print("Renaming size_height to actual_height...")
            cursor.execute("""
                ALTER TABLE quote_items 
                CHANGE COLUMN size_height actual_height DECIMAL(10,2) NULL
            """)
            
            # Add chargeable size fields
            print("Adding chargeable_width column...")
            cursor.execute("""
                ALTER TABLE quote_items 
                ADD COLUMN chargeable_width DECIMAL(10,2) NULL AFTER actual_height
            """)
            
            print("Adding chargeable_height column...")
            cursor.execute("""
                ALTER TABLE quote_items 
                ADD COLUMN chargeable_height DECIMAL(10,2) NULL AFTER chargeable_width
            """)
            
            # Add unit_square for calculated area
            print("Adding unit_square column...")
            cursor.execute("""
                ALTER TABLE quote_items 
                ADD COLUMN unit_square DECIMAL(10,4) NULL AFTER chargeable_height
            """)
            
            # Migrate existing data: copy actual size to chargeable size
            print("Migrating existing data...")
            cursor.execute("""
                UPDATE quote_items 
                SET chargeable_width = actual_width,
                    chargeable_height = actual_height
                WHERE actual_width IS NOT NULL AND actual_height IS NOT NULL
            """)
            
            # Calculate unit_square for existing items
            print("Calculating unit_square for existing items...")
            cursor.execute("""
                UPDATE quote_items 
                SET unit_square = (chargeable_width * chargeable_height) / 1000000
                WHERE chargeable_width IS NOT NULL 
                AND chargeable_height IS NOT NULL
                AND unit = 'MM'
            """)
            
            # Commit changes
            connection.commit()
            print("✅ Migration completed successfully!")
            
            # Show updated table structure
            print("\nUpdated table structure:")
            cursor.execute("DESCRIBE quote_items")
            for row in cursor.fetchall():
                print(f"  {row['Field']}: {row['Type']} {row['Null']} {row['Key']}")
                
    except Exception as e:
        connection.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        connection.close()

if __name__ == '__main__':
    print("=" * 60)
    print("Quote Items Table Enhancement Migration")
    print("=" * 60)
    print("\nThis will add the following to quote_items table:")
    print("  - parent_id (for hierarchical structure)")
    print("  - is_group (flag for parent items)")
    print("  - sort_order (custom ordering)")
    print("  - Rename size_width/height to actual_width/height")
    print("  - chargeable_width/height (can differ from actual)")
    print("  - unit_square (calculated area)")
    print("\n" + "=" * 60)
    
    response = input("\nProceed with migration? (yes/no): ")
    if response.lower() == 'yes':
        run_migration()
    else:
        print("Migration cancelled.")
