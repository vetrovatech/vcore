"""
Test the reminder scheduler
"""
from app import app
from utils.reminder_scheduler import ReminderScheduler

with app.app_context():
    print("=" * 60)
    print("Testing Reminder Scheduler")
    print("=" * 60)
    
    scheduler = ReminderScheduler()
    result = scheduler.check_and_send_reminders()
    
    print("\n" + "=" * 60)
    print("Scheduler Results:")
    print(f"  Total reminders checked: {result['total']}")
    print(f"  Successfully sent: {result['sent']}")
    print(f"  Failed: {result['failed']}")
    print("=" * 60)
