"""
Migration: Create quote_comments table.
Run inside the container:
  docker cp migrate_add_quote_comments.py vcore-vcore-1:/app/
  docker exec vcore-vcore-1 python migrate_add_quote_comments.py
"""
import os, sys
sys.path.insert(0, '/app')

from app import app, db

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS quote_comments (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    quote_id   INT NOT NULL,
    user_id    INT NOT NULL,
    comment    TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_qc_quote_id (quote_id),
    CONSTRAINT fk_qc_quote FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE CASCADE,
    CONSTRAINT fk_qc_user  FOREIGN KEY (user_id)  REFERENCES users(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""

with app.app_context():
    conn = db.engine.connect()
    trans = conn.begin()
    try:
        print("Creating quote_comments table...")
        conn.execute(db.text(CREATE_TABLE))
        trans.commit()
        print("Done.")
    except Exception as e:
        trans.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()

print("Migration complete.")
