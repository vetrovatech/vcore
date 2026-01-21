"""
Import updated product descriptions from CSV
"""
import pymysql
import csv
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def parse_database_url(url):
    """Parse MySQL database URL"""
    url = url.replace('mysql+pymysql://', '')
    auth, rest = url.split('@')
    user, password = auth.split(':')
    host_port, database = rest.split('/')
    host, port = host_port.split(':')
    return {
        'host': host,
        'user': user,
        'password': password,
        'database': database,
        'port': int(port)
    }

def main():
    csv_filename = 'new_product_descriptions.csv'
    
    if not os.path.exists(csv_filename):
        print(f"❌ CSV file not found: {csv_filename}")
        print("   Run generate_product_descriptions.py first")
        return
    
    # Get database connection details
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("❌ DATABASE_URL not found in .env file")
        return
    
    db_config = parse_database_url(db_url)
    
    print("🔗 Connecting to database...")
    connection = pymysql.connect(**db_config)
    
    try:
        with connection.cursor() as cursor:
            # Read CSV
            with open(csv_filename, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                updated_count = 0
                
                for row in reader:
                    product_id = int(row['product_id'])
                    new_description = row['new_description']
                    
                    # Update product description
                    update_query = """
                        UPDATE products
                        SET description = %s
                        WHERE id = %s
                    """
                    cursor.execute(update_query, (new_description, product_id))
                    updated_count += 1
                    
                    print(f"   ✅ Updated product {product_id}: {new_description}")
            
            # Commit changes
            connection.commit()
            
            print(f"\n✅ Successfully updated {updated_count} product descriptions!")
            
    except Exception as e:
        connection.rollback()
        print(f"❌ Error: {e}")
        
    finally:
        connection.close()

if __name__ == "__main__":
    print("\n⚠️  WARNING: This will update product descriptions in the database")
    confirm = input("Continue? (yes/no): ").strip().lower()
    
    if confirm == 'yes':
        main()
    else:
        print("❌ Import cancelled")
