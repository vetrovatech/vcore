# -*- coding: utf-8 -*-
"""
Migration: Tally Phase 1
- Make purchase_invoices.project_id nullable
- Add quote_id FK to purchase_invoices
- Add amount_paid to purchase_invoices
- Add delivery_status, amount_received, misc_purchases to quotes

Run once: python migrate_tally_phase1.py
"""

import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv('DATABASE_URL')
parts = database_url.replace('mysql+pymysql://', '').split('@')
user_pass = parts[0].split(':')
host_db   = parts[1].split('/')
host_port = host_db[0].split(':')

config = {
    'user':     user_pass[0],
    'password': user_pass[1],
    'host':     host_port[0],
    'port':     int(host_port[1]),
    'database': host_db[1],
}

print("Connecting to {} at {}".format(config['database'], config['host']))

def col_exists(cursor, db, table, col):
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
    """, (db, table, col))
    return cursor.fetchone()[0] > 0

def index_exists(cursor, db, table, idx):
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s
    """, (db, table, idx))
    return cursor.fetchone()[0] > 0

try:
    connection = pymysql.connect(**config)
    cursor = connection.cursor()
    db = config['database']

    # 1. Make project_id nullable on purchase_invoices
    print("1. Making purchase_invoices.project_id nullable...")
    cursor.execute("""
        ALTER TABLE purchase_invoices
        MODIFY COLUMN project_id INT NULL
    """)
    print("   [OK]")

    # 2. Add quote_id to purchase_invoices
    if not col_exists(cursor, db, 'purchase_invoices', 'quote_id'):
        print("2. Adding purchase_invoices.quote_id...")
        cursor.execute("""
            ALTER TABLE purchase_invoices
            ADD COLUMN quote_id INT NULL AFTER project_id
        """)
        if not index_exists(cursor, db, 'purchase_invoices', 'idx_pi_quote'):
            cursor.execute("""
                ALTER TABLE purchase_invoices
                ADD INDEX idx_pi_quote (quote_id),
                ADD CONSTRAINT fk_pi_quote FOREIGN KEY (quote_id) REFERENCES quotes(id)
            """)
        print("   [OK]")
    else:
        print("2. quote_id already exists — skipping.")

    # 3. Add amount_paid to purchase_invoices
    if not col_exists(cursor, db, 'purchase_invoices', 'amount_paid'):
        print("3. Adding purchase_invoices.amount_paid...")
        cursor.execute("""
            ALTER TABLE purchase_invoices
            ADD COLUMN amount_paid DECIMAL(12,2) NOT NULL DEFAULT 0.00 AFTER invoice_amount
        """)
        print("   [OK]")
    else:
        print("3. amount_paid already exists — skipping.")

    # 4. Add delivery_status to quotes
    if not col_exists(cursor, db, 'quotes', 'delivery_status'):
        print("4. Adding quotes.delivery_status...")
        cursor.execute("""
            ALTER TABLE quotes
            ADD COLUMN delivery_status VARCHAR(20) NOT NULL DEFAULT 'Pending' AFTER status
        """)
        print("   [OK]")
    else:
        print("4. delivery_status already exists — skipping.")

    # 5. Add amount_received to quotes
    if not col_exists(cursor, db, 'quotes', 'amount_received'):
        print("5. Adding quotes.amount_received...")
        cursor.execute("""
            ALTER TABLE quotes
            ADD COLUMN amount_received DECIMAL(10,2) NOT NULL DEFAULT 0.00 AFTER delivery_status
        """)
        print("   [OK]")
    else:
        print("5. amount_received already exists — skipping.")

    # 6. Add misc_purchases to quotes
    if not col_exists(cursor, db, 'quotes', 'misc_purchases'):
        print("6. Adding quotes.misc_purchases...")
        cursor.execute("""
            ALTER TABLE quotes
            ADD COLUMN misc_purchases DECIMAL(10,2) NOT NULL DEFAULT 0.00 AFTER amount_received
        """)
        print("   [OK]")
    else:
        print("6. misc_purchases already exists — skipping.")

    connection.commit()
    cursor.close()
    connection.close()
    print("\n[OK] Migration complete.")

except Exception as e:
    print("\n[ERROR] {}".format(e))
    if 'connection' in locals():
        connection.rollback()
        connection.close()
