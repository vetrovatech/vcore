"""
Migration: Add assigned_to_id column to leads table.
Run inside the container:
  docker cp migrate_add_lead_assigned_to.py vcore-vcore-1:/app/
  docker exec vcore-vcore-1 python migrate_add_lead_assigned_to.py
"""
import os, sys
sys.path.insert(0, '/app')

from app import app, db

ADD_COLUMN = """
ALTER TABLE leads
    ADD COLUMN assigned_to_id INT NULL AFTER owner_id,
    ADD INDEX idx_lead_assigned_to (assigned_to_id),
    ADD CONSTRAINT fk_lead_assigned_to
        FOREIGN KEY (assigned_to_id) REFERENCES users(id)
        ON DELETE SET NULL
"""

CHECK_COLUMN = """
SELECT COUNT(*) FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'leads'
  AND column_name = 'assigned_to_id'
"""

with app.app_context():
    conn = db.engine.connect()
    trans = conn.begin()
    try:
        result = conn.execute(db.text(CHECK_COLUMN))
        exists = result.scalar()
        if exists:
            print("assigned_to_id column already exists, skipping.")
        else:
            print("Adding assigned_to_id column to leads table...")
            conn.execute(db.text(ADD_COLUMN))
            print("Done.")
        trans.commit()
    except Exception as e:
        trans.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()

print("Migration complete.")
