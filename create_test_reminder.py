"""
Quick test to create a reminder and test the scheduler
"""
from app import app, db
from models import Reminder, User, Project
from datetime import datetime, timedelta

with app.app_context():
    # Get first user
    user = User.query.first()
    print(f"User: {user.username} ({user.email})")
    
    # Get first project
    project = Project.query.first()
    if project:
        print(f"Project: {project.name}")
        
        # Create a test reminder for 5 minutes from now
        reminder_time = datetime.utcnow() + timedelta(minutes=5)
        
        reminder = Reminder(
            reminder_type='project',
            project_id=project.id,
            user_id=user.id,
            reminder_datetime=reminder_time,
            subject="Test Reminder",
            message="This is a test reminder created automatically.",
            status='pending'
        )
        
        db.session.add(reminder)
        db.session.commit()
        
        print(f"\n✅ Created test reminder #{reminder.id}")
        print(f"   Scheduled for: {reminder_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"   Will be sent to: {user.email}")
        print(f"\nTo test the scheduler, run:")
        print(f"   python3 test_scheduler.py")
    else:
        print("❌ No projects found. Create a project first.")
