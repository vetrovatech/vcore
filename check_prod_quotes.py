"""
Quick script to check production quote items
"""
import pymysql
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

database_url = os.getenv('DATABASE_URL')
url = urlparse(database_url.replace('mysql+pymysql://', 'mysql://'))

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
        # Check quotes
        cursor.execute("SELECT id, quote_number, customer_name FROM quotes ORDER BY id DESC LIMIT 5")
        quotes = cursor.fetchall()
        print("Recent Quotes:")
        for q in quotes:
            print(f"  ID: {q['id']}, Number: {q['quote_number']}, Customer: {q['customer_name']}")
        
        # Check items for first quote
        if quotes:
            quote_id = quotes[0]['id']
            print(f"\nItems for Quote #{quote_id}:")
            cursor.execute("""
                SELECT id, parent_id, is_group, item_number, particular, 
                       actual_width, actual_height, chargeable_width, chargeable_height
                FROM quote_items 
                WHERE quote_id = %s
                ORDER BY sort_order
            """, (quote_id,))
            items = cursor.fetchall()
            for item in items:
                print(f"  ID: {item['id']}, Parent: {item['parent_id']}, Group: {item['is_group']}, "
                      f"#: {item['item_number']}, Particular: {item['particular'][:30]}")
finally:
    connection.close()
