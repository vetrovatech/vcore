# -*- coding: utf-8 -*-
"""
Migration: create purchase_invoices table.
Run once:  python migrate_add_purchase_invoices.py
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
        SELECT COUNT(*) FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'purchase_invoices'
    """, (config['database'],))

    if cursor.fetchone()[0]:
        print("[OK] Table 'purchase_invoices' already exists — nothing to do.")
    else:
        print("Creating 'purchase_invoices' table...")
        cursor.execute("""
            CREATE TABLE purchase_invoices (
                id             INT AUTO_INCREMENT PRIMARY KEY,
                serial_number  VARCHAR(20)    NOT NULL UNIQUE,
                supplier_id    INT            NOT NULL,
                project_id     INT            NOT NULL,
                bill_number    VARCHAR(100)   NOT NULL,
                bill_image_url TEXT,
                invoice_type   VARCHAR(10)    NOT NULL DEFAULT 'GST',
                invoice_amount DECIMAL(12,2),
                status         VARCHAR(10)    NOT NULL DEFAULT 'Pending',
                notes          TEXT,
                created_by     INT            NOT NULL,
                created_at     DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at     DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                CONSTRAINT fk_pi_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
                CONSTRAINT fk_pi_project  FOREIGN KEY (project_id)  REFERENCES projects(id),
                CONSTRAINT fk_pi_user     FOREIGN KEY (created_by)  REFERENCES users(id),
                INDEX idx_pi_supplier (supplier_id),
                INDEX idx_pi_project  (project_id),
                INDEX idx_pi_status   (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        connection.commit()
        print("[OK] Table created successfully.")

    cursor.close()
    connection.close()
    print("\n[OK] Migration complete.")

except Exception as e:
    print("\n[ERROR] {}".format(e))
    if 'connection' in locals():
        connection.rollback()
        connection.close()
