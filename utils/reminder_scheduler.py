"""
Reminder scheduler module for checking and sending pending reminders
"""
from models import db, Reminder, User
from utils.email_service import EmailService
from datetime import datetime, timedelta
import os


class ReminderScheduler:
    def __init__(self):
        self.email_service = EmailService()
    
    def check_and_send_reminders(self):
        """Check for pending reminders and send them"""
        # Get current time
        now = datetime.utcnow()
        
        # Query reminders that are due (past or upcoming in next 15 minutes)
        # This catches both overdue reminders and upcoming ones
        past_time = now - timedelta(hours=24)  # Check last 24 hours for any missed
        upcoming_time = now + timedelta(minutes=15)
        
        pending_reminders = Reminder.query.filter(
            Reminder.status == 'pending',
            Reminder.reminder_datetime >= past_time,
            Reminder.reminder_datetime <= upcoming_time
        ).all()
        
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Found {len(pending_reminders)} pending reminders to send")
        
        sent_count = 0
        failed_count = 0
        
        for reminder in pending_reminders:
            try:
                # Send reminder based on type
                if reminder.reminder_type == 'project' and reminder.project:
                    result = self.email_service.send_project_reminder(
                        reminder.project,
                        reminder.user,
                        custom_subject=reminder.subject,
                        custom_message=reminder.message
                    )
                elif reminder.reminder_type == 'task' and reminder.task:
                    result = self.email_service.send_task_reminder(
                        reminder.task,
                        reminder.user,
                        custom_subject=reminder.subject,
                        custom_message=reminder.message
                    )
                else:
                    result = {'success': False, 'error': 'Invalid reminder type or missing reference'}
                
                # Update reminder status
                if result['success']:
                    reminder.status = 'sent'
                    reminder.sent_at = datetime.utcnow()
                    sent_count += 1
                    print(f"✅ Sent reminder #{reminder.id} to {reminder.user.email}")
                    
                    # Handle recurring reminders
                    if reminder.is_recurring:
                        self.create_next_recurrence(reminder)
                else:
                    reminder.status = 'failed'
                    reminder.error_message = result.get('error', 'Unknown error')
                    failed_count += 1
                    print(f"❌ Failed to send reminder #{reminder.id}: {reminder.error_message}")
                
                db.session.commit()
                
            except Exception as e:
                print(f"❌ Error processing reminder #{reminder.id}: {str(e)}")
                reminder.status = 'failed'
                reminder.error_message = str(e)
                failed_count += 1
                db.session.commit()
        
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Completed: {sent_count} sent, {failed_count} failed")
        
        return {
            'total': len(pending_reminders),
            'sent': sent_count,
            'failed': failed_count
        }
    
    def create_next_recurrence(self, reminder):
        """Create next occurrence for recurring reminders"""
        if not reminder.is_recurring or not reminder.recurrence_pattern:
            return
        
        # Calculate next reminder datetime
        current_datetime = reminder.reminder_datetime
        
        if reminder.recurrence_pattern == 'daily':
            next_datetime = current_datetime + timedelta(days=1)
        elif reminder.recurrence_pattern == 'weekly':
            next_datetime = current_datetime + timedelta(weeks=1)
        elif reminder.recurrence_pattern == 'monthly':
            # Add approximately 30 days (simplified)
            next_datetime = current_datetime + timedelta(days=30)
        else:
            return
        
        # Check if we've reached the end date
        if reminder.recurrence_end_date and next_datetime.date() > reminder.recurrence_end_date:
            print(f"Recurrence ended for reminder #{reminder.id}")
            return
        
        # Create new reminder
        new_reminder = Reminder(
            reminder_type=reminder.reminder_type,
            project_id=reminder.project_id,
            task_id=reminder.task_id,
            user_id=reminder.user_id,
            reminder_datetime=next_datetime,
            subject=reminder.subject,
            message=reminder.message,
            is_recurring=True,
            recurrence_pattern=reminder.recurrence_pattern,
            recurrence_end_date=reminder.recurrence_end_date,
            status='pending'
        )
        
        db.session.add(new_reminder)
        print(f"✅ Created next recurrence for reminder #{reminder.id} at {next_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
