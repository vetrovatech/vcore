"""
Email service module for sending emails via AWS SES
"""
import boto3
from botocore.exceptions import ClientError
import os
from datetime import datetime


class EmailService:
    def __init__(self):
        """Initialize AWS SES client"""
        # In Lambda, boto3 automatically uses the IAM role
        # Locally, it will use environment variables
        region = os.getenv('AWS_REGION', 'ap-south-1')
        
        # Check if we're in Lambda (AWS_EXECUTION_ENV is set in Lambda)
        if os.getenv('AWS_EXECUTION_ENV'):
            # In Lambda - use IAM role (don't pass credentials)
            self.ses_client = boto3.client('ses', region_name=region)
        else:
            # Local development - use environment variables
            self.ses_client = boto3.client(
                'ses',
                region_name=region,
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )
        self.sender_email = os.getenv('SES_SENDER_EMAIL', 'info@glassy.in')
        self.app_url = os.getenv('APP_URL', 'http://localhost:5000')
    
    def send_email(self, to, subject, body, html=None):
        """
        Send email via AWS SES
        
        Args:
            to: Recipient email address (string)
            subject: Email subject
            body: Plain text body
            html: HTML body (optional)
        
        Returns:
            dict: Success status with message_id
        """
        try:
            # Build email body
            body_data = {'Text': {'Data': body, 'Charset': 'UTF-8'}}
            if html:
                body_data['Html'] = {'Data': html, 'Charset': 'UTF-8'}
            
            # Send email
            response = self.ses_client.send_email(
                Source=self.sender_email,
                Destination={'ToAddresses': [to]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': body_data
                }
            )
            
            return {
                'success': True,
                'message_id': response['MessageId']
            }
        except ClientError as e:
            return {
                'success': False,
                'error': e.response['Error']['Message']
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def send_project_reminder(self, project, user, custom_subject=None, custom_message=None):
        """Send project-specific reminder email via SES"""
        if not user.email:
            return {'success': False, 'error': 'User has no email address'}
        
        # Format subject
        if custom_subject:
            subject = custom_subject
        else:
            subject = f"🔔 Reminder: {project.name}"
        
        # Format message
        if custom_message:
            body = custom_message
        else:
            # Calculate status text
            status_text = ""
            days_remaining = project.days_remaining()
            if days_remaining is not None:
                if days_remaining > 0:
                    status_text = f"{days_remaining} days remaining"
                elif days_remaining == 0:
                    status_text = "Due today!"
                else:
                    status_text = f"{abs(days_remaining)} days overdue"
            else:
                status_text = "Completed"
            
            body = f"""Hello {user.username},

This is a reminder about your project:

Project: {project.name}
Status: {project.status}
Expected End Date: {project.expected_end_date.strftime('%d %B %Y') if project.expected_end_date else 'Not set'}
{status_text}

{project.comments if project.comments else ''}

Stay on track and keep up the great work!

---
VCore Project Management System
"""
        
        # Create HTML version
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                <h2 style="color: #2c3e50;">🔔 Project Reminder</h2>
                <p>Hello <strong>{user.username}</strong>,</p>
                <p>This is a reminder about your project:</p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0;">
                    <p><strong>Project:</strong> {project.name}</p>
                    <p><strong>Status:</strong> <span style="color: #007bff;">{project.status}</span></p>
                    <p><strong>Expected End Date:</strong> {project.expected_end_date.strftime('%d %B %Y')}</p>
                    <p><strong>{status_text}</strong></p>
                </div>
                
                {f'<p><em>{project.comments}</em></p>' if project.comments else ''}
                
                <p>Stay on track and keep up the great work! 💪</p>
                
                <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                <p style="font-size: 12px; color: #666;">
                    VCore Project Management System<br>
                    <a href="{self.app_url}/projects">View All Projects</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(user.email, subject, body, html)
    
    def send_task_reminder(self, task, user, custom_subject=None, custom_message=None):
        """Send task-specific reminder email via SES"""
        if not user.email:
            return {'success': False, 'error': 'User has no email address'}
        
        task_name = task.task_name or task.template.name
        project_name = task.project.name if task.project else "General"
        
        # Format subject
        if custom_subject:
            subject = custom_subject
        else:
            subject = f"🔔 Task Reminder: {task_name}"
        
        # Format message
        if custom_message:
            body = custom_message
        else:
            body = f"""Hello {user.username},

This is a reminder about your task:

Task: {task_name}
Project: {project_name}
Priority: {task.priority}
Due Date: {task.due_date.strftime('%d %B %Y')}
Status: {task.status}

{task.comments if task.comments else ''}

Time to take action! 🚀

---
VCore Project Management System
"""
        
        # Create HTML version
        priority_color = {'High': '#dc3545', 'Medium': '#ffc107', 'Low': '#28a745'}.get(task.priority, '#6c757d')
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                <h2 style="color: #2c3e50;">🔔 Task Reminder</h2>
                <p>Hello <strong>{user.username}</strong>,</p>
                <p>This is a reminder about your task:</p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid {priority_color}; margin: 20px 0;">
                    <p><strong>Task:</strong> {task_name}</p>
                    <p><strong>Project:</strong> {project_name}</p>
                    <p><strong>Priority:</strong> <span style="color: {priority_color};">{task.priority}</span></p>
                    <p><strong>Due Date:</strong> {task.due_date.strftime('%d %B %Y')}</p>
                    <p><strong>Status:</strong> {task.status}</p>
                </div>
                
                {f'<p><em>{task.comments}</em></p>' if task.comments else ''}
                
                <p>Time to take action! 🚀</p>
                
                <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                <p style="font-size: 12px; color: #666;">
                    VCore Project Management System<br>
                    <a href="{self.app_url}/tasks/weekly">View Tasks</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(user.email, subject, body, html)
