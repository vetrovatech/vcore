#!/usr/bin/env python3
"""
Migration: Add assigned_to_id to projects table and create project_history table
"""

from app import app, db
from sqlalchemy import text


def migrate():
    with app.app_context():
        try:
            # 1. Add assigned_to_id column to projects
            result = db.session.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='projects' AND column_name='assigned_to_id'
            """))
            if not result.fetchone():
                print("Adding assigned_to_id to projects...")
                db.session.execute(text("""
                    ALTER TABLE projects
                    ADD COLUMN assigned_to_id INT NULL,
                    ADD CONSTRAINT fk_projects_assigned_to
                        FOREIGN KEY (assigned_to_id) REFERENCES users(id)
                        ON DELETE SET NULL
                """))
                print("Added assigned_to_id to projects.")
            else:
                print("assigned_to_id already exists in projects.")

            # 2. Create project_history table
            result = db.session.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name='project_history'
            """))
            if not result.fetchone():
                print("Creating project_history table...")
                db.session.execute(text("""
                    CREATE TABLE project_history (
                        id INT NOT NULL AUTO_INCREMENT,
                        project_id INT NOT NULL,
                        changed_by_id INT NOT NULL,
                        action VARCHAR(50) NOT NULL,
                        changes TEXT NULL,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (id),
                        INDEX ix_project_history_project_id (project_id),
                        CONSTRAINT fk_ph_project FOREIGN KEY (project_id)
                            REFERENCES projects(id) ON DELETE CASCADE,
                        CONSTRAINT fk_ph_user FOREIGN KEY (changed_by_id)
                            REFERENCES users(id)
                    )
                """))
                print("Created project_history table.")
            else:
                print("project_history table already exists.")

            db.session.commit()
            print("Migration completed successfully!")

        except Exception as e:
            db.session.rollback()
            print(f"Migration failed: {str(e)}")
            raise


if __name__ == '__main__':
    migrate()
