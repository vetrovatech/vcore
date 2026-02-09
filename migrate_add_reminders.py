"""
Migration script to add reminders table for email reminders
"""
from app import app, db
from sqlalchemy import text

def migrate():
    """Add reminders table"""
    with app.app_context():
        print("Creating reminders table...")
        
        # Create reminders table
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                reminder_type VARCHAR(20) NOT NULL,
                project_id INT NULL,
                task_id INT NULL,
                user_id INT NOT NULL,
                reminder_datetime DATETIME NOT NULL,
                subject VARCHAR(200) NULL,
                message TEXT NULL,
                is_recurring BOOLEAN DEFAULT FALSE,
                recurrence_pattern VARCHAR(50) NULL,
                recurrence_end_date DATE NULL,
                status VARCHAR(20) DEFAULT 'pending' NOT NULL,
                sent_at DATETIME NULL,
                error_message TEXT NULL,
                send_email BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                
                INDEX idx_reminder_status_datetime (status, reminder_datetime),
                INDEX idx_reminder_user_type (user_id, reminder_type),
                INDEX idx_project_id (project_id),
                INDEX idx_task_id (task_id),
                INDEX idx_user_id (user_id),
                
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES promotor_tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """))
        
        db.session.commit()
        print("✅ Reminders table created successfully!")
        
        # Verify table was created
        result = db.session.execute(text("SHOW TABLES LIKE 'reminders'"))
        if result.fetchone():
            print("✅ Migration completed successfully!")
        else:
            print("❌ Migration failed - table not found")

if __name__ == '__main__':
    migrate()
