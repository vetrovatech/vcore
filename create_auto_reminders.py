"""
Auto-reminder script to create daily reminders for all incomplete projects
Run this twice daily via cron
"""
from app import app, db
from models import Project, User, Reminder
from datetime import datetime, timedelta

def create_auto_reminders():
    """Create automatic reminders for all incomplete projects"""
    with app.app_context():
        # Get all projects that are not completed
        incomplete_projects = Project.query.filter(
            Project.status.in_(['New', 'In Progress', 'On Hold'])
        ).all()
        
        print(f"Found {len(incomplete_projects)} incomplete projects")
        
        # Get all active users
        active_users = User.query.filter_by(is_active=True).all()
        
        # Set reminder time to 30 minutes from now
        reminder_time = datetime.utcnow() + timedelta(minutes=30)
        
        created_count = 0
        
        for project in incomplete_projects:
            # Determine who should receive the reminder
            # Priority: project owner, or all managers/admins if no owner
            recipients = []
            
            if project.owner:
                recipients = [project.owner]
            else:
                # Send to all admins and managers
                recipients = [u for u in active_users if u.role in ['Admin', 'Manager']]
            
            for user in recipients:
                # Check if a reminder already exists for this project/user in the next hour
                existing = Reminder.query.filter(
                    Reminder.project_id == project.id,
                    Reminder.user_id == user.id,
                    Reminder.status == 'pending',
                    Reminder.reminder_datetime > datetime.utcnow(),
                    Reminder.reminder_datetime < datetime.utcnow() + timedelta(hours=1)
                ).first()
                
                if not existing:
                    # Create reminder
                    reminder = Reminder(
                        reminder_type='project',
                        project_id=project.id,
                        user_id=user.id,
                        reminder_datetime=reminder_time,
                        subject=f"Daily Project Update: {project.name}",
                        message=f"This is an automated daily reminder for project: {project.name}",
                        status='pending'
                    )
                    db.session.add(reminder)
                    created_count += 1
                    print(f"✅ Created reminder for {project.name} → {user.email}")
        
        db.session.commit()
        print(f"\n✅ Created {created_count} auto-reminders")
        print(f"📧 Reminders will be sent at: {reminder_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")

if __name__ == '__main__':
    create_auto_reminders()
