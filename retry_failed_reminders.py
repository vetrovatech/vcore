#!/usr/bin/env python3
"""
Script to retry failed reminders by resetting them to pending status
"""
from app import app, db
from models import Reminder
from datetime import datetime, timedelta

def retry_failed_reminders():
    """Reset failed reminders to pending status"""
    with app.app_context():
        # Get all failed reminders
        failed_reminders = Reminder.query.filter_by(status='failed').all()
        
        print(f"📊 Found {len(failed_reminders)} failed reminders")
        print()
        
        if not failed_reminders:
            print("✅ No failed reminders to retry!")
            return
        
        for reminder in failed_reminders:
            # Reset to pending
            reminder.status = 'pending'
            reminder.error_message = None
            
            # Update reminder time to 5 minutes from now
            reminder.reminder_datetime = datetime.utcnow() + timedelta(minutes=5)
            
            print(f"✅ Reset reminder #{reminder.id}: {reminder.subject}")
        
        db.session.commit()
        print()
        print(f"🎉 Successfully reset {len(failed_reminders)} reminders to pending")
        print(f"⏰ Reminders will be sent at: {(datetime.utcnow() + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')} UTC")

if __name__ == '__main__':
    retry_failed_reminders()
