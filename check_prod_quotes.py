"""
Quick script to check production quote items
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.environ['DATABASE_URL'])

with engine.connect() as conn:
    quotes = conn.execute(text(
        "SELECT id, quote_number, customer_name FROM quotes ORDER BY id DESC LIMIT 5"
    )).mappings().all()
    print("Recent Quotes:")
    for q in quotes:
        print(f"  ID: {q['id']}, Number: {q['quote_number']}, Customer: {q['customer_name']}")

    if quotes:
        quote_id = quotes[0]['id']
        print(f"\nItems for Quote #{quote_id}:")
        items = conn.execute(text("""
            SELECT id, parent_id, is_group, item_number, particular,
                   actual_width, actual_height, chargeable_width, chargeable_height
            FROM quote_items
            WHERE quote_id = :qid
            ORDER BY sort_order
        """), {"qid": quote_id}).mappings().all()
        for item in items:
            print(f"  ID: {item['id']}, Parent: {item['parent_id']}, Group: {item['is_group']}, "
                  f"#: {item['item_number']}, Particular: {item['particular'][:30]}")
