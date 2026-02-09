from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()


class Reminder(db.Model):
    """Email reminder model for projects and tasks"""
    __tablename__ = 'reminders'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Polymorphic reminder (can be for project or task)
    reminder_type = db.Column(db.String(20), nullable=False)  # 'project' or 'task'
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('promotor_tasks.id'), nullable=True, index=True)
    
    # Reminder details
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    reminder_datetime = db.Column(db.DateTime, nullable=False, index=True)
    subject = db.Column(db.String(200), nullable=True)  # Custom subject (optional)
    message = db.Column(db.Text, nullable=True)  # Custom message (optional)
    
    # Recurrence settings
    is_recurring = db.Column(db.Boolean, default=False)
    recurrence_pattern = db.Column(db.String(50), nullable=True)  # 'daily', 'weekly', 'monthly'
    recurrence_end_date = db.Column(db.Date, nullable=True)
    
    # Status tracking
    status = db.Column(db.String(20), default='pending', index=True)  # 'pending', 'sent', 'failed', 'cancelled'
    sent_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    # Email preferences
    send_email = db.Column(db.Boolean, default=True)  # Future: can add SMS, push, etc.
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='reminders', foreign_keys=[user_id])
    project = db.relationship('Project', backref='reminders', foreign_keys=[project_id])
    task = db.relationship('PromotorTask', backref='reminders', foreign_keys=[task_id])
    
    # Indexes
    __table_args__ = (
        db.Index('idx_reminder_status_datetime', 'status', 'reminder_datetime'),
        db.Index('idx_reminder_user_type', 'user_id', 'reminder_type'),
    )
    
    def __repr__(self):
        return f'<Reminder {self.id} - {self.reminder_type} - {self.status}>'
