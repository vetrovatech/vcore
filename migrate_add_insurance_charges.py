"""
Migration: Add insurance_percentage and insurance_charges to quotes table.
Run inside the container:
  docker cp migrate_add_insurance_charges.py vcore-vcore-1:/app/
  docker exec vcore-vcore-1 python migrate_add_insurance_charges.py
"""
import os, sys
sys.path.insert(0, '/app')

from app import app, db

CHECK = """
SELECT COUNT(*) FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'quotes'
  AND column_name = 'insurance_charges'
"""

ADD_COLS = """
ALTER TABLE quotes
    ADD COLUMN insurance_percentage DECIMAL(5,2) NOT NULL DEFAULT 0.00 AFTER frosted_charges,
    ADD COLUMN insurance_charges    DECIMAL(10,2) NOT NULL DEFAULT 0.00 AFTER insurance_percentage
"""

with app.app_context():
    conn = db.engine.connect()
    trans = conn.begin()
    try:
        exists = conn.execute(db.text(CHECK)).scalar()
        if exists:
            print("insurance_charges already exists, skipping.")
        else:
            print("Adding insurance_percentage and insurance_charges to quotes...")
            conn.execute(db.text(ADD_COLS))
            print("Done.")
        trans.commit()
    except Exception as e:
        trans.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()

print("Migration complete.")
