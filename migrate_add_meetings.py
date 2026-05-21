"""Migration: create meetings and meeting_photos tables"""
import os, sys
sys.path.insert(0, '/app')
from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        # meetings table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS meetings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    user_id INT NOT NULL,
                    created_by INT NOT NULL,
                    lead_id INT NULL,
                    project_id INT NULL,
                    client_name VARCHAR(200) NULL,
                    client_phone VARCHAR(20) NULL,
                    client_address TEXT NULL,
                    meeting_type VARCHAR(50) NOT NULL DEFAULT 'Lead Visit',
                    scheduled_at DATETIME NULL,
                    check_in_time DATETIME NULL,
                    check_in_lat DOUBLE NULL,
                    check_in_lng DOUBLE NULL,
                    check_in_accuracy DOUBLE NULL,
                    check_in_address VARCHAR(500) NULL,
                    check_out_time DATETIME NULL,
                    check_out_lat DOUBLE NULL,
                    check_out_lng DOUBLE NULL,
                    notes TEXT NULL,
                    outcome VARCHAR(200) NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'Scheduled',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_meeting_user (user_id),
                    INDEX idx_meeting_status (status),
                    INDEX idx_meeting_lead (lead_id),
                    INDEX idx_meeting_project (project_id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (created_by) REFERENCES users(id),
                    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
            print("✓ Created meetings table")
        except Exception as e:
            if 'already exists' in str(e).lower():
                print("✓ meetings table already exists")
            else:
                print(f"✗ Error creating meetings table: {e}")
                raise

        # meeting_photos table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS meeting_photos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    meeting_id INT NOT NULL,
                    photo_url TEXT NOT NULL,
                    caption VARCHAR(200) NULL,
                    uploaded_by INT NOT NULL,
                    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_mphoto_meeting (meeting_id),
                    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
                    FOREIGN KEY (uploaded_by) REFERENCES users(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
            print("✓ Created meeting_photos table")
        except Exception as e:
            if 'already exists' in str(e).lower():
                print("✓ meeting_photos table already exists")
            else:
                print(f"✗ Error creating meeting_photos table: {e}")
                raise

    print("Migration complete.")
