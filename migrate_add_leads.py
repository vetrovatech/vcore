"""Migration: Add leads table for Leadfy lead management"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def migrate():
    with app.app_context():
        db.create_all()
        print("Migration complete: 'leads' table created (if it did not already exist).")

if __name__ == '__main__':
    migrate()
