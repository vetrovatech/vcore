from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User model for authentication and role-based access"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Promotor')  # Admin, Manager, Promotor
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    created_projects = db.relationship('Project', backref='owner', lazy=True, foreign_keys='Project.owner_id')
    assigned_tasks = db.relationship('PromotorTask', backref='promotor', lazy=True, foreign_keys='PromotorTask.promotor_id')
    created_templates = db.relationship('TaskTemplate', backref='creator', lazy=True, foreign_keys='TaskTemplate.created_by')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        """Check if user is admin"""
        return self.role == 'Admin'
    
    def is_manager_or_admin(self):
        """Check if user is manager or admin"""
        return self.role in ['Admin', 'Manager']
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Project(db.Model):
    """Project model for tracking live projects"""
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    expected_end_date = db.Column(db.Date, nullable=False)
    actual_end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Not Started', index=True)  # Not Started, In Progress, Completed, On Hold
    comments = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    tasks = db.relationship('PromotorTask', backref='project', lazy=True)
    
    def is_overdue(self):
        """Check if project is overdue"""
        if self.status != 'Completed' and self.expected_end_date:
            return datetime.now().date() > self.expected_end_date
        return False
    
    def days_remaining(self):
        """Calculate days remaining until expected end date"""
        if self.status != 'Completed' and self.expected_end_date:
            delta = self.expected_end_date - datetime.now().date()
            return delta.days
        return None
    
    def __repr__(self):
        return f'<Project {self.name} ({self.status})>'


class TaskTemplate(db.Model):
    """Task template model for reusable task definitions"""
    __tablename__ = 'task_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=True)  # Sales, Marketing, Field Work, etc.
    priority = db.Column(db.String(20), nullable=False, default='Medium')  # High, Medium, Low
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    task_instances = db.relationship('PromotorTask', backref='template', lazy=True)
    
    def __repr__(self):
        return f'<TaskTemplate {self.name} ({self.category})>'


class PromotorTask(db.Model):
    """Promotor task model for weekly task tracking"""
    __tablename__ = 'promotor_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('task_templates.id'), nullable=False)
    task_name = db.Column(db.String(200), nullable=True)  # Custom task name (optional, defaults to template name)
    promotor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    
    # Week tracking
    assigned_week = db.Column(db.Integer, nullable=False, index=True)  # Week number (1-53)
    assigned_year = db.Column(db.Integer, nullable=False, index=True)  # Year
    original_week = db.Column(db.Integer, nullable=False)  # Original week assigned (for lag calculation)
    original_year = db.Column(db.Integer, nullable=False)  # Original year assigned
    
    # Dates and status
    due_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='Pending', index=True)  # Pending, In Progress, Completed, Overdue
    completed_date = db.Column(db.DateTime, nullable=True)
    
    # Lag tracking
    lag_weeks = db.Column(db.Integer, default=0, nullable=False)  # Calculated lag in weeks
    
    # Additional fields
    priority = db.Column(db.String(20), nullable=False, default='Medium')  # High, Medium, Low
    comments = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_tasks')
    
    def calculate_lag(self):
        """Calculate lag in weeks from original assignment"""
        from datetime import datetime
        current_date = datetime.now()
        current_week = current_date.isocalendar()[1]
        current_year = current_date.isocalendar()[0]
        
        # Calculate total weeks difference
        if current_year == self.original_year:
            lag = current_week - self.original_week
        else:
            # Handle year transitions
            weeks_in_original_year = 52  # Simplified, can be 52 or 53
            lag = (weeks_in_original_year - self.original_week) + current_week
            lag += (current_year - self.original_year - 1) * 52
        
        return max(0, lag)
    
    def update_lag(self):
        """Update the lag_weeks field"""
        if self.status != 'Completed':
            self.lag_weeks = self.calculate_lag()
    
    def get_lag_badge_class(self):
        """Get Bootstrap badge class based on lag"""
        if self.lag_weeks == 0:
            return 'success'  # Green
        elif self.lag_weeks == 1:
            return 'warning'  # Yellow
        else:
            return 'danger'  # Red
    
    def __repr__(self):
        return f'<PromotorTask {self.template.name if self.template else "N/A"} - Week {self.assigned_week}/{self.assigned_year}>'


class DailyUpdate(db.Model):
    """Daily update model for tracking daily progress on projects"""
    __tablename__ = 'daily_updates'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True, index=True)
    update_date = db.Column(db.Date, nullable=False, index=True)
    update_text = db.Column(db.Text, nullable=False)
    is_general = db.Column(db.Boolean, default=False, nullable=False)  # True for general updates
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='daily_updates', foreign_keys=[user_id])
    project = db.relationship('Project', backref='daily_updates', foreign_keys=[project_id])
    
    # Unique constraint: one update per user per project per day
    __table_args__ = (
        db.UniqueConstraint('user_id', 'project_id', 'update_date', name='uq_user_project_date'),
        db.Index('idx_update_date_user', 'update_date', 'user_id'),
    )
    
    def can_edit(self, user):
        """Check if user can edit this update"""
        from datetime import date
        # Can edit if: (1) it's your update AND (2) it's from today OR (3) you're an admin
        is_today = self.update_date == date.today()
        is_owner = self.user_id == user.id
        is_admin = user.is_admin()
        return (is_owner and is_today) or is_admin
    
    def can_delete(self, user):
        """Check if user can delete this update"""
        # Can delete if: (1) it's your update OR (2) you're an admin
        return self.user_id == user.id or user.is_admin()
    
    def __repr__(self):
        project_name = self.project.name if self.project else "General"
        return f'<DailyUpdate {self.user.username} - {project_name} - {self.update_date}>'


class Product(db.Model):
    """Product model for catalog management"""
    __tablename__ = 'products'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Core fields (always present - 80+ rows populated)
    category = db.Column(db.String(100), nullable=False, index=True)
    product_name = db.Column(db.String(300), nullable=False, index=True)
    product_url = db.Column(db.String(500), nullable=True)
    price = db.Column(db.String(100), nullable=True)  # Varies: "160/sqft", "24,999/Unit"
    
    # Images (S3 URLs)
    image_1_url = db.Column(db.String(500), nullable=True)
    image_2_url = db.Column(db.String(500), nullable=True)
    image_3_url = db.Column(db.String(500), nullable=True)
    image_4_url = db.Column(db.String(500), nullable=True)
    
    # Common fields
    availability = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    
    # Common specification fields (20+ rows populated)
    material = db.Column(db.String(200), nullable=True)
    brand = db.Column(db.String(100), nullable=True, index=True)
    usage_application = db.Column(db.String(200), nullable=True)
    thickness = db.Column(db.String(100), nullable=True)
    shape = db.Column(db.String(100), nullable=True)
    pattern = db.Column(db.String(100), nullable=True)
    
    # Additional specifications stored as JSON
    # Stores sparse fields like: Color, Glass Type, Door Type, Frame Material, etc.
    specifications = db.Column(db.Text, nullable=True)  # JSON string
    
    # Metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Indexes for better query performance
    __table_args__ = (
        db.Index('idx_category_active', 'category', 'is_active'),
        db.Index('idx_brand_active', 'brand', 'is_active'),
    )
    
    def get_specifications(self):
        """Get specifications as a dictionary"""
        if self.specifications:
            try:
                return json.loads(self.specifications)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def set_specifications(self, specs_dict):
        """Set specifications from a dictionary"""
        if specs_dict:
            self.specifications = json.dumps(specs_dict)
        else:
            self.specifications = None
    
    def get_all_images(self):
        """Get list of all non-empty image URLs"""
        images = []
        for i in range(1, 5):
            url = getattr(self, f'image_{i}_url', None)
            if url:
                images.append(url)
        return images
    
    def get_primary_image(self):
        """Get the first available image URL or a placeholder"""
        return self.image_1_url or '/static/images/no-product-image.png'
    
    def get_formatted_price(self):
        """Get formatted price string"""
        if self.price:
            return self.price
        return 'Price on request'
    
    @classmethod
    def search(cls, query, category=None, brand=None):
        """Search products by name, category, or brand"""
        filters = [cls.is_active == True]
        
        if query:
            filters.append(cls.product_name.ilike(f'%{query}%'))
        
        if category:
            filters.append(cls.category == category)
        
        if brand:
            filters.append(cls.brand == brand)
        
        return cls.query.filter(*filters).order_by(cls.product_name)
    
    @classmethod
    def get_categories(cls):
        """Get list of unique categories"""
        return db.session.query(cls.category).filter(cls.is_active == True).distinct().order_by(cls.category).all()
    
    @classmethod
    def get_brands(cls):
        """Get list of unique brands"""
        return db.session.query(cls.brand).filter(cls.is_active == True, cls.brand.isnot(None)).distinct().order_by(cls.brand).all()
    
    def __repr__(self):
        return f'<Product {self.product_name} ({self.category})>'


