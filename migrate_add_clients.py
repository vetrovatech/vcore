"""
Migration: Create clients table and backfill from existing quotes.
Run inside the container:
  docker cp migrate_add_clients.py vcore-vcore-1:/app/
  docker exec vcore-vcore-1 python migrate_add_clients.py
"""
import os, sys
sys.path.insert(0, '/app')

from app import app, db

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS clients (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    phone        VARCHAR(20),
    email        VARCHAR(120),
    address      TEXT,
    city         VARCHAR(100),
    state        VARCHAR(100),
    gst_number   VARCHAR(20),
    dispatch_to  TEXT,
    quote_type   ENUM('B2B','B2C'),
    notes        TEXT,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_client_name (name)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

BACKFILL = """
INSERT INTO clients (name, phone, email, address, city, state, gst_number, dispatch_to, quote_type, created_at)
SELECT
    customer_name,
    MAX(customer_phone),
    MAX(customer_email),
    MAX(customer_address),
    MAX(customer_city),
    MAX(customer_state),
    MAX(customer_gst),
    MAX(dispatch_to),
    MAX(quote_type),
    MIN(created_at)
FROM quotes
WHERE customer_name IS NOT NULL AND customer_name != ''
GROUP BY LOWER(customer_name)
ON DUPLICATE KEY UPDATE
    phone       = IF(VALUES(phone)       != '' AND VALUES(phone)       IS NOT NULL, VALUES(phone),       phone),
    email       = IF(VALUES(email)       != '' AND VALUES(email)       IS NOT NULL, VALUES(email),       email),
    address     = IF(VALUES(address)     IS NOT NULL, VALUES(address),     address),
    city        = IF(VALUES(city)        IS NOT NULL, VALUES(city),        city),
    state       = IF(VALUES(state)       IS NOT NULL, VALUES(state),       state),
    gst_number  = IF(VALUES(gst_number)  IS NOT NULL, VALUES(gst_number),  gst_number),
    dispatch_to = IF(VALUES(dispatch_to) IS NOT NULL, VALUES(dispatch_to), dispatch_to);
"""

with app.app_context():
    conn = db.engine.connect()
    trans = conn.begin()
    try:
        print("Creating clients table...")
        conn.execute(db.text(CREATE_TABLE))
        print("Backfilling from existing quotes...")
        result = conn.execute(db.text(BACKFILL))
        print(f"  → {result.rowcount} client(s) inserted/updated")
        trans.commit()
        print("Done.")
    except Exception as e:
        trans.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()
