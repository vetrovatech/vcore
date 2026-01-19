# -*- coding: utf-8 -*-
"""
Migration script to add task_name column to promotor_tasks table
Run this script to update the database schema
"""

import pymysql
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Parse DATABASE_URL
database_url = os.getenv('DATABASE_URL')
# Format: mysql+pymysql://user:password@host:port/database
parts = database_url.replace('mysql+pymysql://', '').split('@')
user_pass = parts[0].split(':')
host_db = parts[1].split('/')
host_port = host_db[0].split(':')

config = {
    'user': user_pass[0],
    'password': user_pass[1],
    'host': host_port[0],
    'port': int(host_port[1]),
    'database': host_db[1]
}

print("Connecting to database: {} at {}".format(config['database'], config['host']))

try:
    # Connect to database
    connection = pymysql.connect(**config)
    cursor = connection.cursor()
    
    # Check if column exists
    cursor.execute("""
        SELECT COUNT(*) 
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = %s 
        AND TABLE_NAME = 'promotor_tasks' 
        AND COLUMN_NAME = 'task_name'
    """, (config['database'],))
    
    exists = cursor.fetchone()[0]
    
    if exists:
        print("[OK] Column 'task_name' already exists in promotor_tasks table")
    else:
        print("Adding 'task_name' column to promotor_tasks table...")
        
        # Add the column
        cursor.execute("""
            ALTER TABLE promotor_tasks 
            ADD COLUMN task_name VARCHAR(200) NULL 
            AFTER template_id
        """)
        
        connection.commit()
        print("[OK] Successfully added 'task_name' column to promotor_tasks table")
    
    cursor.close()
    connection.close()
    print("\n[OK] Migration completed successfully!")
    
except Exception as e:
    print("\n[ERROR] Error: {}".format(e))
    if 'connection' in locals():
        connection.rollback()
        connection.close()
