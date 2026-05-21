# -*- coding: utf-8 -*-
"""
Migration: add refresh_token column to indiamart_tokens table.
Run once:  python migrate_add_indiamart_refresh_token.py
"""

import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv('DATABASE_URL')
parts = database_url.replace('mysql+pymysql://', '').split('@')
user_pass = parts[0].split(':')
host_db = parts[1].split('/')
host_port = host_db[0].split(':')

config = {
    'user': user_pass[0],
    'password': user_pass[1],
    'host': host_port[0],
    'port': int(host_port[1]),
    'database': host_db[1],
}

print("Connecting to {} at {}".format(config['database'], config['host']))

try:
    connection = pymysql.connect(**config)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = 'indiamart_tokens'
          AND COLUMN_NAME = 'refresh_token'
    """, (config['database'],))

    if cursor.fetchone()[0]:
        print("[OK] Column 'refresh_token' already exists in indiamart_tokens — nothing to do.")
    else:
        print("Adding 'refresh_token' column to indiamart_tokens...")
        cursor.execute("""
            ALTER TABLE indiamart_tokens
            ADD COLUMN refresh_token TEXT NULL AFTER ak_token
        """)
        connection.commit()
        print("[OK] Column added successfully.")

    cursor.close()
    connection.close()
    print("\n[OK] Migration complete.")

except Exception as e:
    print("\n[ERROR] {}".format(e))
    if 'connection' in locals():
        connection.rollback()
        connection.close()
