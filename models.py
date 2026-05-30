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
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    start_date = db.Column(db.Date, nullable=False)
    expected_end_date = db.Column(db.Date, nullable=False)
    actual_end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Not Started', index=True)  # Not Started, In Progress, Completed, On Hold
    comments = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tasks = db.relationship('PromotorTask', backref='project', lazy=True)
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id], lazy=True)
    history = db.relationship('ProjectHistory', backref='project', lazy=True, order_by='ProjectHistory.created_at.desc()')

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


class ProjectHistory(db.Model):
    """Audit log for project changes"""
    __tablename__ = 'project_history'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # 'Created', 'Updated'
    changes = db.Column(db.Text, nullable=True)  # JSON list of {field, old, new}
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    changed_by = db.relationship('User', foreign_keys=[changed_by_id], lazy=True)

    def __repr__(self):
        return f'<ProjectHistory project={self.project_id} action={self.action}>'


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
    
    # WordPress sync tracking
    wordpress_id = db.Column(db.Integer, nullable=True, index=True)
    last_wordpress_sync = db.Column(db.DateTime, nullable=True)
    
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


class Quote(db.Model):
    """Quote model for customer quotations"""
    __tablename__ = 'quotes'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Quote identification
    quote_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    quote_date = db.Column(db.Date, nullable=False, index=True)
    expected_date = db.Column(db.Date, nullable=True)  # Expected delivery/completion date
    
    # Customer information
    customer_name = db.Column(db.String(200), nullable=False, index=True)
    customer_address = db.Column(db.Text, nullable=True)
    customer_city = db.Column(db.String(100), nullable=True)
    customer_state = db.Column(db.String(100), nullable=True)
    customer_phone = db.Column(db.String(20), nullable=True)
    customer_email = db.Column(db.String(120), nullable=True)
    customer_gst = db.Column(db.String(20), nullable=True)
    
    # Billing and shipping
    invoice_to = db.Column(db.Text, nullable=True)  # Billing address if different
    dispatch_to = db.Column(db.Text, nullable=True)  # Shipping address if different
    self_pickup = db.Column(db.Boolean, default=False, nullable=False)
    
    # Financial details
    subtotal = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    delivery_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    installation_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    freight_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    transport_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    cutout_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    holes_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    shape_cutting_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    jumbo_size_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    template_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    handling_percentage = db.Column(db.Numeric(5, 2), default=1.00, nullable=False)
    handling_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    polish_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    document_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    frosted_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    insurance_percentage = db.Column(db.Numeric(5, 2), default=0.00, nullable=False)
    insurance_charges = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    gst_percentage = db.Column(db.Numeric(5, 2), default=18.00, nullable=False)
    gst_amount = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    round_off = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    total = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    
    # Jumbo size percentage rates (editable per quote)
    jumbo_pct_tier1 = db.Column(db.Numeric(5, 2), default=10.00, nullable=False)  # 4.5–5.5 sqm
    jumbo_pct_tier2 = db.Column(db.Numeric(5, 2), default=15.00, nullable=False)  # 5.5–7 sqm
    jumbo_pct_tier3 = db.Column(db.Numeric(5, 2), default=20.00, nullable=False)  # >7 sqm

    # Terms and status
    payment_terms = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Draft', index=True)  # Draft, Sent, Accepted, Rejected, Expired
    quote_type = db.Column(db.Enum('B2B', 'B2C', name='quote_type_enum'), default='B2B', nullable=False)  # B2B or B2C quote

    # Tally / fulfillment fields
    delivery_status = db.Column(db.String(20), nullable=False, default='Pending')  # Pending, Dispatched, Delivered
    amount_received = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)   # online/bank payment received
    cash_received   = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)   # cash payment received
    misc_purchases  = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)   # extra costs (labour, transport, etc.)

    # Metadata
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    items = db.relationship('QuoteItem', backref='quote', lazy=True, cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by], backref='quotes')
    purchase_invoices = db.relationship('PurchaseInvoice', backref='quote', lazy='dynamic',
                                        foreign_keys='PurchaseInvoice.quote_id')

    @property
    def total_received(self):
        return float(self.amount_received or 0) + float(self.cash_received or 0)

    @property
    def client_payment_status(self):
        received = self.total_received
        total    = float(self.total or 0)
        if received <= 0:                        return 'Pending'
        if total > 0 and received >= total:      return 'Received'
        return 'Partial'
    
    # Indexes
    __table_args__ = (
        db.Index('idx_quote_date_status', 'quote_date', 'status'),
        db.Index('idx_customer_name', 'customer_name'),
    )
    
    def calculate_totals(self):
        """Calculate all totals based on items and charges"""
        # Calculate subtotal from items
        self.subtotal = sum(item.total for item in self.items)
        
        # Calculate taxable amount (subtotal + all charges except GST)
        taxable_amount = (
            self.subtotal + 
            self.delivery_charges + 
            self.installation_charges + 
            self.freight_charges + 
            self.transport_charges +
            self.cutout_charges +
            self.holes_charges +
            self.shape_cutting_charges +
            self.jumbo_size_charges +
            self.template_charges +
            self.handling_charges +
            self.polish_charges +
            self.document_charges +
            self.frosted_charges
        )
        
        # Calculate GST
        self.gst_amount = (taxable_amount * self.gst_percentage) / 100
        
        # Calculate total before round-off
        total_before_roundoff = taxable_amount + self.gst_amount
        
        # Calculate round-off to nearest rupee
        rounded_total = round(total_before_roundoff)
        self.round_off = rounded_total - total_before_roundoff
        self.total = rounded_total
    
    @classmethod
    def generate_quote_number(cls):
        """Generate next quote number in format GI-XXXX"""
        # Get the latest quote number
        latest_quote = cls.query.order_by(cls.id.desc()).first()
        
        if latest_quote and latest_quote.quote_number:
            # Extract number from format GI-XXXX
            try:
                last_number = int(latest_quote.quote_number.split('-')[1])
                next_number = last_number + 1
            except (IndexError, ValueError):
                next_number = 4193  # Start from sample quote number
        else:
            next_number = 4193  # Start from sample quote number
        
        return f'GI-{next_number}'
    
    def get_status_badge_class(self):
        """Get Bootstrap badge class based on status"""
        status_classes = {
            'Draft': 'secondary',
            'Sent': 'info',
            'Accepted': 'success',
            'Rejected': 'danger',
            'Expired': 'warning'
        }
        return status_classes.get(self.status, 'secondary')
    
    def __repr__(self):
        return f'<Quote {self.quote_number} - {self.customer_name}>'


class QuoteComment(db.Model):
    """Comment/activity log for a quote"""
    __tablename__ = 'quote_comments'

    id         = db.Column(db.Integer, primary_key=True)
    quote_id   = db.Column(db.Integer, db.ForeignKey('quotes.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comment    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user  = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<QuoteComment quote={self.quote_id} user={self.user_id}>'


class QuoteItem(db.Model):
    """Quote item model for individual line items in a quote with hierarchical support"""
    __tablename__ = 'quote_items'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    quote_id = db.Column(db.Integer, db.ForeignKey('quotes.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('quote_items.id'), nullable=True)  # For hierarchical structure
    
    # Grouping and ordering
    is_group = db.Column(db.Boolean, default=False)  # True for parent/group items
    sort_order = db.Column(db.Integer, default=0)  # Custom ordering
    
    # Item details
    item_number = db.Column(db.Integer, nullable=False)  # Line item number (1, 2, 3...)
    particular    = db.Column(db.Text, nullable=False)
    image_s3_key  = db.Column(db.String(500), nullable=True)

    # Actual dimensions (what was measured/ordered)
    actual_width = db.Column(db.Numeric(10, 2), nullable=True)
    actual_height = db.Column(db.Numeric(10, 2), nullable=True)
    
    # Chargeable dimensions (what is billed - can differ from actual)
    chargeable_width = db.Column(db.Numeric(10, 2), nullable=True)
    chargeable_height = db.Column(db.Numeric(10, 2), nullable=True)
    
    unit = db.Column(db.String(20), nullable=True, default='MM')  # MM, sqft, etc.
    chargeable_extra = db.Column(db.Integer, default=30, nullable=False)  # Extra MM to add to chargeable dimensions
    unit_square = db.Column(db.Numeric(10, 4), nullable=True)  # Calculated area in square meters
    
    # Pricing
    quantity = db.Column(db.Integer, nullable=False, default=1)
    rate_sqper = db.Column(db.Numeric(10, 2), nullable=False)  # Rate per unit
    total = db.Column(db.Numeric(10, 2), nullable=False)  # Calculated total
    
    # Additional item details
    hole = db.Column(db.Integer, default=0, nullable=False)  # Number of holes
    cutout = db.Column(db.Integer, default=0, nullable=False)  # Number of cutouts
    hole_price = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)  # Price per hole (group level)
    cutout_price = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)  # Price per cutout (group level)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    children = db.relationship('QuoteItem', 
                              backref=db.backref('parent', remote_side=[id]),
                              cascade='all, delete-orphan',
                              order_by='QuoteItem.sort_order')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_quote_item', 'quote_id', 'item_number'),
        db.Index('idx_parent_item', 'parent_id'),
    )
    
    def calculate_unit_square(self):
        """Calculate unit square (area) from chargeable dimensions in Sq Mtr"""
        if self.chargeable_width and self.chargeable_height and self.unit == 'MM':
            # Convert MM² to M² (Sq Mtr)
            area_mm2 = float(self.chargeable_width) * float(self.chargeable_height)
            self.unit_square = area_mm2 / 1000000  # Convert to square meters
        elif self.chargeable_width and self.chargeable_height:
            # For other units, just multiply
            self.unit_square = float(self.chargeable_width) * float(self.chargeable_height)
    
    def apply_chargeable_extra(self):
        """Apply chargeable extra to actual dimensions to get chargeable dimensions"""
        if self.actual_width and self.actual_height:
            self.chargeable_width = float(self.actual_width) + float(self.chargeable_extra)
            self.chargeable_height = float(self.actual_height) + float(self.chargeable_extra)
    
    def calculate_total(self):
        """Calculate total for this line item using Area in Sq Mtr × Rate / Sq Mtr"""
        if self.is_group:
            # For group items, total is sum of children
            self.total = sum(child.total for child in self.children) if self.children else 0
        else:
            # For regular items, calculate from unit_square and rate
            base_total = 0
            if self.unit_square:
                base_total = float(self.unit_square) * float(self.rate_sqper) * self.quantity
            else:
                base_total = self.quantity * self.rate_sqper
            
            # Add hole and cutout charges from parent group
            hole_charge = 0
            cutout_charge = 0
            if self.parent:
                hole_charge = float(self.hole) * float(self.parent.hole_price)
                cutout_charge = float(self.cutout) * float(self.parent.cutout_price)
            
            self.total = base_total + hole_charge + cutout_charge
    
    def get_display_number(self, parent_number=None):
        """Get hierarchical display number (e.g., 1, 1.1, 1.2, 2, 2.1)"""
        if parent_number:
            # This is a sub-item
            siblings = [c for c in self.parent.children if c.id <= self.id]
            sub_number = len(siblings)
            return f"{parent_number}.{sub_number}"
        else:
            # This is a top-level item
            return str(self.item_number)
    
    def get_all_children(self):
        """Get all children recursively"""
        all_children = []
        for child in self.children:
            all_children.append(child)
            all_children.extend(child.get_all_children())
        return all_children
    
    def __repr__(self):
        return f'<QuoteItem {self.item_number} - {self.particular}>'


class Supplier(db.Model):
    """Supplier model for managing glass suppliers"""
    __tablename__ = 'suppliers'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Basic information
    name = db.Column(db.String(200), nullable=False, unique=True, index=True)
    contact_person = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(200), nullable=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(20), nullable=True)
    
    # Tax and banking details
    gstin = db.Column(db.String(50), nullable=True)
    pan = db.Column(db.String(20), nullable=True)
    bank_name = db.Column(db.String(200), nullable=True)
    account_number = db.Column(db.String(50), nullable=True)
    ifsc_code = db.Column(db.String(20), nullable=True)
    branch = db.Column(db.String(200), nullable=True)
    
    # Business terms
    payment_terms = db.Column(db.Text, nullable=True)
    lead_time_days = db.Column(db.Integer, nullable=True)
    min_order_value = db.Column(db.Numeric(10, 2), nullable=True)
    
    # Status and metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    pricing = db.relationship('SupplierPricing', backref='supplier', lazy=True, cascade='all, delete-orphan')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_supplier_active', 'is_active'),
        db.Index('idx_supplier_name', 'name'),
    )
    
    def get_active_pricing(self):
        """Get all active pricing for this supplier"""
        from datetime import date
        today = date.today()
        return [p for p in self.pricing if p.is_active and 
                (p.effective_from is None or p.effective_from <= today) and
                (p.effective_to is None or p.effective_to >= today)]
    
    def __repr__(self):
        return f'<Supplier {self.name}>'


class GlassType(db.Model):
    """Glass type model for catalog of glass products"""
    __tablename__ = 'glass_types'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Basic information
    name = db.Column(db.String(200), nullable=False, index=True)
    category = db.Column(db.String(100), nullable=True, index=True)  # Toughened, Laminated, etc.
    thickness_mm = db.Column(db.Numeric(5, 2), nullable=True)  # Glass thickness in mm
    
    # Description and specifications
    description = db.Column(db.Text, nullable=True)
    specifications = db.Column(db.Text, nullable=True)  # JSON string for additional specs
    
    # Common properties
    is_frosted = db.Column(db.Boolean, default=False)
    is_tinted = db.Column(db.Boolean, default=False)
    color = db.Column(db.String(50), nullable=True)
    
    # Status and metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    pricing = db.relationship('SupplierPricing', backref='glass_type', lazy=True, cascade='all, delete-orphan')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_glass_type_active', 'is_active'),
        db.Index('idx_glass_category', 'category', 'is_active'),
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
    
    def get_best_price(self):
        """Get the best (lowest) active price from all suppliers"""
        active_prices = [p.rate_per_sqm for p in self.pricing if p.is_active]
        return min(active_prices) if active_prices else None
    
    def get_supplier_count(self):
        """Get count of suppliers offering this glass type"""
        return len([p for p in self.pricing if p.is_active])
    
    def __repr__(self):
        return f'<GlassType {self.name}>'


class SupplierPricing(db.Model):
    """Supplier pricing model for glass type pricing by supplier"""
    __tablename__ = 'supplier_pricing'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False, index=True)
    glass_type_id = db.Column(db.Integer, db.ForeignKey('glass_types.id'), nullable=False, index=True)
    
    # Pricing details
    rate_per_sqm = db.Column(db.Numeric(10, 2), nullable=False)  # Base rate per square meter
    hole_price = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)  # Price per hole
    cutout_price = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)  # Price per cutout
    big_hole_price = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)  # Price per big hole
    big_cutout_price = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)  # Price per big cutout
    
    # Additional charges
    frosting_charge_per_sqm = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    tinting_charge_per_sqm = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    
    # Order constraints
    min_order_sqm = db.Column(db.Numeric(10, 2), nullable=True)  # Minimum order quantity
    lead_time_days = db.Column(db.Integer, nullable=True)  # Lead time in days
    
    # Validity period
    effective_from = db.Column(db.Date, nullable=True)
    effective_to = db.Column(db.Date, nullable=True)
    
    # Status and notes
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Indexes
    __table_args__ = (
        db.Index('idx_supplier_glass', 'supplier_id', 'glass_type_id'),
        db.Index('idx_pricing_active', 'is_active'),
        db.UniqueConstraint('supplier_id', 'glass_type_id', 'effective_from', name='uq_supplier_glass_date'),
    )
    
    def is_currently_valid(self):
        """Check if pricing is currently valid"""
        from datetime import date
        today = date.today()
        
        if not self.is_active:
            return False
        
        if self.effective_from and self.effective_from > today:
            return False
        
        if self.effective_to and self.effective_to < today:
            return False
        
        return True
    
    def get_total_price(self, sqm, holes=0, cutouts=0, big_holes=0, big_cutouts=0, frosted=False, tinted=False):
        """Calculate total price for given specifications"""
        total = float(self.rate_per_sqm) * sqm
        total += float(self.hole_price) * holes
        total += float(self.cutout_price) * cutouts
        total += float(self.big_hole_price) * big_holes
        total += float(self.big_cutout_price) * big_cutouts
        
        if frosted:
            total += float(self.frosting_charge_per_sqm) * sqm
        
        if tinted:
            total += float(self.tinting_charge_per_sqm) * sqm
        
        return total
    
    def __repr__(self):
        return f'<SupplierPricing {self.supplier.name if self.supplier else "N/A"} - {self.glass_type.name if self.glass_type else "N/A"}>'


class Lead(db.Model):
    """Lead model for Leadfy lead management"""
    __tablename__ = 'leads'

    id = db.Column(db.Integer, primary_key=True)

    # Lead information
    name = db.Column(db.String(200), nullable=True)  # nullable for unknown leads
    contact = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)

    # Facebook Lead Ads integration
    facebook_lead_id = db.Column(db.String(50), nullable=True, unique=True, index=True)

    # IndiaMart integration
    indiamart_id = db.Column(db.String(50), nullable=True, unique=True, index=True)
    buyer_glid = db.Column(db.String(50), nullable=True)
    company = db.Column(db.String(200), nullable=True)
    product_interest = db.Column(db.String(200), nullable=True)
    product_qty = db.Column(db.String(100), nullable=True)
    product_category = db.Column(db.String(200), nullable=True)
    lead_type = db.Column(db.String(50), nullable=True)
    customer_type = db.Column(db.String(10), nullable=True)  # B2B or B2C
    has_whatsapp = db.Column(db.Boolean, default=False)
    is_gst_registered = db.Column(db.Boolean, default=False)
    is_starred = db.Column(db.Boolean, default=False)
    last_message = db.Column(db.Text, nullable=True)
    unread_count = db.Column(db.Integer, default=0)
    indiamart_added_date = db.Column(db.DateTime, nullable=True)
    indiamart_last_contact = db.Column(db.DateTime, nullable=True)
    indiamart_notes = db.Column(db.Text, nullable=True)
    indiamart_labels = db.Column(db.String(500), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_untouched = db.Column(db.Boolean, default=True)

    # Stage and origin
    stage = db.Column(db.String(50), nullable=False, default='New Lead', index=True)
    # New Lead, Contacted, Not Connected, Qualified, PI Shared, Closed Won, Closed Lost, Junk
    origin = db.Column(db.String(100), nullable=True, index=True)

    # Ownership
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_leads')
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id], backref='assigned_leads')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_leads')

    # Indexes
    __table_args__ = (
        db.Index('idx_lead_stage', 'stage'),
        db.Index('idx_lead_owner', 'owner_id'),
        db.Index('idx_lead_assigned_to', 'assigned_to_id'),
        db.Index('idx_lead_created_at', 'created_at'),
        db.Index('idx_lead_updated_at', 'updated_at'),
    )

    def get_stage_badge_class(self):
        """Get Bootstrap badge class based on stage"""
        stage_classes = {
            'New Lead': 'primary',
            'Contacted': 'info',
            'Not Connected': 'warning',
            'Qualified': 'warning',
            'PI Shared': 'secondary',
            'Closed Won': 'success',
            'Closed Lost': 'danger',
            'Junk': 'dark',
        }
        return stage_classes.get(self.stage, 'secondary')

    def get_initials(self):
        """Get initials from name"""
        if not self.name:
            return '?'
        parts = self.name.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return parts[0][0].upper() if parts else '?'

    def get_age_days(self):
        return (datetime.utcnow() - self.created_at).days

    def __repr__(self):
        return f'<Lead {self.name or "Unknown"} ({self.stage})>'


class LeadHistory(db.Model):
    """Tracks all changes made to a lead"""
    __tablename__ = 'lead_history'

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('leads.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)   # stage_change, note, field_change, created
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    lead = db.relationship('Lead', backref=db.backref('history', lazy='dynamic', cascade='all, delete-orphan'))
    user = db.relationship('User', foreign_keys=[user_id])


class IndiamartToken(db.Model):
    """Stores IndiaMart API session token"""
    __tablename__ = 'indiamart_tokens'

    id = db.Column(db.Integer, primary_key=True)
    ak_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)   # extracted from JWT payload if present
    glid = db.Column(db.String(50), nullable=True)
    mobile = db.Column(db.String(20), nullable=True)
    user_ip = db.Column(db.String(50), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def is_valid(self):
        if not self.expires_at:
            return False
        return datetime.utcnow() < self.expires_at

    def expires_soon(self, minutes=120):
        """True if token expires within the given number of minutes."""
        if not self.expires_at:
            return True
        from datetime import timedelta
        return datetime.utcnow() >= (self.expires_at - timedelta(minutes=minutes))


class PurchaseInvoice(db.Model):
    """Purchase Invoice model — tracks bills received from suppliers"""
    __tablename__ = 'purchase_invoices'

    id = db.Column(db.Integer, primary_key=True)
    serial_number = db.Column(db.String(20), nullable=False, unique=True, index=True)  # PI-001

    # Relationships
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False, index=True)
    project_id  = db.Column(db.Integer, db.ForeignKey('projects.id'),  nullable=True,  index=True)  # legacy, nullable
    quote_id    = db.Column(db.Integer, db.ForeignKey('quotes.id'),    nullable=True,  index=True)
    # Allow a PI to link to either a regular Quote OR a BathqubeQuote.
    # Exactly one of (quote_id, bathqube_quote_id) should be set in practice.
    bathqube_quote_id = db.Column(db.Integer, db.ForeignKey('bathqube_quotes.id'), nullable=True, index=True)

    # Bill details
    bill_number    = db.Column(db.String(100), nullable=False)
    bill_image_url = db.Column(db.Text, nullable=True)
    invoice_type   = db.Column(db.String(10), nullable=False, default='GST')  # GST / Non-GST
    invoice_amount = db.Column(db.Numeric(12, 2), nullable=True)
    amount_paid    = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)

    # Metadata
    notes      = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ORM relationships
    supplier = db.relationship('Supplier', backref=db.backref('purchase_invoices', lazy='dynamic'))
    project  = db.relationship('Project',  backref=db.backref('purchase_invoices', lazy='dynamic'))
    creator  = db.relationship('User',     foreign_keys=[created_by])
    bathqube_quote = db.relationship('BathqubeQuote', backref=db.backref('purchase_invoices', lazy='dynamic'))

    @property
    def vendor_payment_status(self):
        paid  = float(self.amount_paid or 0)
        total = float(self.invoice_amount or 0)
        if paid <= 0:                      return 'Pending'
        if total > 0 and paid >= total:    return 'Paid'
        return 'Partial'

    def __repr__(self):
        return f'<PurchaseInvoice {self.serial_number}>'


class Meeting(db.Model):
    """Meeting / field visit record with GPS check-in"""
    __tablename__ = 'meetings'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)

    # Assigned salesman
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Optional links
    lead_id = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True, index=True)

    # Client details (free text — filled even without a linked lead)
    client_name = db.Column(db.String(200), nullable=True)
    client_phone = db.Column(db.String(20), nullable=True)
    client_address = db.Column(db.Text, nullable=True)

    # Type and schedule
    meeting_type = db.Column(db.String(50), nullable=False, default='Lead Visit')
    # Lead Visit | Site Survey | Installation | Follow-up | General
    scheduled_at = db.Column(db.DateTime, nullable=True)

    # GPS check-in
    check_in_time = db.Column(db.DateTime, nullable=True)
    check_in_lat = db.Column(db.Float, nullable=True)
    check_in_lng = db.Column(db.Float, nullable=True)
    check_in_accuracy = db.Column(db.Float, nullable=True)   # metres
    check_in_address = db.Column(db.String(500), nullable=True)

    # GPS check-out
    check_out_time = db.Column(db.DateTime, nullable=True)
    check_out_lat = db.Column(db.Float, nullable=True)
    check_out_lng = db.Column(db.Float, nullable=True)

    # Outcome
    notes = db.Column(db.Text, nullable=True)
    outcome = db.Column(db.String(200), nullable=True)

    # Status: Scheduled | Checked In | Completed | Cancelled
    status = db.Column(db.String(20), nullable=False, default='Scheduled', index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='meetings')
    creator_user = db.relationship('User', foreign_keys=[created_by], backref='created_meetings')
    lead = db.relationship('Lead', foreign_keys=[lead_id], backref='meetings')
    project = db.relationship('Project', foreign_keys=[project_id], backref='meetings')
    photos = db.relationship('MeetingPhoto', backref='meeting', lazy=True,
                              cascade='all, delete-orphan')

    def duration_minutes(self):
        if self.check_in_time and self.check_out_time:
            return int((self.check_out_time - self.check_in_time).total_seconds() / 60)
        return None

    def __repr__(self):
        return f'<Meeting {self.id} - {self.title}>'


class MeetingPhoto(db.Model):
    """Photos attached to a meeting visit"""
    __tablename__ = 'meeting_photos'

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meetings.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    photo_url = db.Column(db.Text, nullable=False)
    caption = db.Column(db.String(200), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    uploader = db.relationship('User', foreign_keys=[uploaded_by])

    def __repr__(self):
        return f'<MeetingPhoto {self.id} for meeting {self.meeting_id}>'


class Client(db.Model):
    """Saved client/customer details for quote autocomplete"""
    __tablename__ = 'clients'

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200), nullable=False, index=True)
    phone        = db.Column(db.String(20),  nullable=True)
    email        = db.Column(db.String(120), nullable=True)
    address      = db.Column(db.Text,        nullable=True)
    city         = db.Column(db.String(100), nullable=True)
    state        = db.Column(db.String(100), nullable=True)
    gst_number   = db.Column(db.String(20),  nullable=True)
    dispatch_to  = db.Column(db.Text,        nullable=True)
    quote_type   = db.Column(db.Enum('B2B', 'B2C', name='client_quote_type_enum'), nullable=True)  # preferred type
    notes        = db.Column(db.Text,        nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_client_name', 'name'),
    )

    def to_dict(self):
        return {
            'id':          self.id,
            'name':        self.name,
            'phone':       self.phone  or '',
            'email':       self.email  or '',
            'address':     self.address or '',
            'city':        self.city   or '',
            'state':       self.state  or '',
            'gst_number':  self.gst_number or '',
            'dispatch_to': self.dispatch_to or '',
            'quote_type':  self.quote_type or '',
            'notes':       self.notes  or '',
        }


class Reminder(db.Model):
    """Email reminder model for projects and tasks"""
    __tablename__ = 'reminders'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Polymorphic reminder (can be for project, task, or quote)
    reminder_type = db.Column(db.String(20), nullable=False)  # 'project', 'task', or 'quote'
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('promotor_tasks.id'), nullable=True, index=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('quotes.id'), nullable=True, index=True)
    
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
    quote = db.relationship('Quote', backref='reminders', foreign_keys=[quote_id])
    
    # Indexes
    __table_args__ = (
        db.Index('idx_reminder_status_datetime', 'status', 'reminder_datetime'),
        db.Index('idx_reminder_user_type', 'user_id', 'reminder_type'),
    )
    
    def __repr__(self):
        return f'<Reminder {self.id} - {self.reminder_type} - {self.status}>'


# ============================================================================
# BATHQUBE QUOTATIONS
# ----------------------------------------------------------------------------
# Mirror of glassyplatform's `bathspace-quotes` Payload collection. Glassy
# pushes a quote here over HMAC-signed webhook after the configurator submits.
# Vcore owns the post-purchase lifecycle (5 stages, each with a customer
# message). Glassy stays the source of truth for the original configurator
# snapshot; vcore owns edits + revised totals + stage transitions.
# ============================================================================

BATHQUBE_STAGES = (
    'quote_generated',       # default — quote just landed via webhook
    'in_pipeline',           # actively working with the customer
    'revision',              # bill revised + revised PDF emailed to customer
    'awaiting_payment',      # order ready / waiting for the customer to pay
    'closed_won',            # deal closed successfully
    'junk',                  # disposition — not a real lead
    'rejected',              # disposition — lost / declined
)

# Stages that are "active" (shown by default in the list view). Junk + rejected
# are disposition states that get filtered out unless the user explicitly opts in.
BATHQUBE_ACTIVE_STAGES = ('quote_generated', 'in_pipeline', 'revision', 'awaiting_payment', 'closed_won')

# Legacy → new stage map for the one-shot data migration. Keep this around in
# case anyone needs to re-run the migration against new data that may have
# slipped in with an old stage value.
BATHQUBE_LEGACY_STAGE_MAP = {
    'new':                'quote_generated',
    'order_confirmation': 'in_pipeline',
    'processing':         'in_pipeline',
    'bill_revision':      'revision',
    'order_ready':        'awaiting_payment',
    'thank_you':          'closed_won',
}


class BathqubeQuote(db.Model):
    """Bathqube configurator quote, mirrored from glassyplatform."""
    __tablename__ = 'bathqube_quotes'

    id = db.Column(db.Integer, primary_key=True)

    # Link back to the glassyplatform Payload record
    external_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    estimate_number = db.Column(db.String(32), unique=True, nullable=True, index=True)

    # Customer
    customer_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(32), nullable=False, index=True)
    email = db.Column(db.String(200), nullable=True, index=True)
    pincode = db.Column(db.String(12), nullable=True)
    site_address = db.Column(db.Text, nullable=True)

    # Where the quote came from on bathqube.com
    source_path = db.Column(db.String(255), nullable=True)
    variant_size = db.Column(db.String(120), nullable=True)
    variant_material = db.Column(db.String(120), nullable=True)

    # Full configurator snapshot (panels, finishes, prices) as JSON string.
    # After the first revise, this holds the sales-person's EDITED version.
    config_data = db.Column(db.Text, nullable=True)

    # Snapshot of the customer's ORIGINAL submission, captured the first time
    # someone opens the revise screen. Read-only audit trail of "what they
    # asked for vs what was sold". Null until first revise.
    original_config_data = db.Column(db.Text, nullable=True)

    # Money — copied from configurator, editable in vcore after bill_revision
    subtotal = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    cgst = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    sgst = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    revised_total = db.Column(db.Numeric(12, 2), nullable=True)
    amount_received = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    # Tally-only fields (parallel to Quote — same semantics, same dashboard).
    # Populated/edited from /tally once stage is 'closed_won'.
    cash_received    = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    misc_purchases   = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    delivery_status  = db.Column(db.String(20), default='Pending', nullable=False)
    gst_percentage = db.Column(db.Numeric(5, 2), default=18, nullable=False)
    has_revision = db.Column(db.Boolean, default=False, nullable=False)
    # Discount as % of pre-tax subtotal — applied BEFORE GST.
    discount_percent = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    discount_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    # How many times the sales person has saved a revision (0 = customer's original).
    # Bumped in app.py on every successful save; matches len(revisions).
    revision_count = db.Column(db.Integer, default=0, nullable=False)

    # Lifecycle
    stage = db.Column(db.String(32), nullable=False, default='quote_generated', index=True)
    notes = db.Column(db.Text, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    purchased_at = db.Column(db.DateTime, nullable=True)

    # Audit log of stage transitions
    events = db.relationship('BathqubeStatusEvent', backref='quote', lazy=True,
                             cascade='all, delete-orphan',
                             order_by='BathqubeStatusEvent.created_at.desc()')

    # Editable line items (created on first revision, then persisted)
    items = db.relationship('BathqubeQuoteItem', backref='quote', lazy=True,
                            cascade='all, delete-orphan',
                            order_by='BathqubeQuoteItem.sort_order')

    # Audit log: one row per Save in the revise UI. Used by the view page's
    # "Revision history" card. Customer never sees these — internal only.
    revisions = db.relationship('BathqubeQuoteRevision', backref='quote', lazy=True,
                                cascade='all, delete-orphan',
                                order_by='BathqubeQuoteRevision.revision_number.desc()')

    @property
    def balance_payable(self):
        effective_total = float(self.revised_total if self.revised_total is not None else self.total or 0)
        return max(0.0, effective_total - float(self.amount_received or 0))

    @property
    def config(self):
        """Parsed configData JSON; returns {} if missing/invalid."""
        if not self.config_data:
            return {}
        try:
            return json.loads(self.config_data)
        except Exception:
            return {}

    def __repr__(self):
        return f'<BathqubeQuote {self.estimate_number or self.id} {self.customer_name} {self.stage}>'


class BathqubeStatusEvent(db.Model):
    """Audit log of every stage transition + message sent."""
    __tablename__ = 'bathqube_status_events'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('bathqube_quotes.id', ondelete='CASCADE'),
                         nullable=False, index=True)

    from_stage = db.Column(db.String(32), nullable=True)
    to_stage = db.Column(db.String(32), nullable=False)

    channel = db.Column(db.String(20), nullable=False, default='email')  # email | whatsapp | none
    subject = db.Column(db.String(255), nullable=True)
    message = db.Column(db.Text, nullable=True)

    send_status = db.Column(db.String(20), nullable=False, default='pending')  # pending|sent|failed|skipped
    send_error = db.Column(db.Text, nullable=True)
    provider_message_id = db.Column(db.String(128), nullable=True)

    triggered_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', foreign_keys=[triggered_by])

    def __repr__(self):
        return f'<BathqubeStatusEvent q={self.quote_id} {self.from_stage}->{self.to_stage} {self.send_status}>'


class BathqubeQuoteItem(db.Model):
    """Line item on a revised Bathqube quote. Discounts = negative-amount rows."""
    __tablename__ = 'bathqube_quote_items'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('bathqube_quotes.id', ondelete='CASCADE'),
                         nullable=False, index=True)

    sort_order = db.Column(db.Integer, default=0, nullable=False)
    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), default=1, nullable=False)
    # True for free-form 'extras' added in the revise UI (installation, trim,
    # manual discounts). False = generated from an enclosure's panel and
    # regenerated on every save (so don't edit these directly).
    is_extra = db.Column(db.Boolean, default=False, nullable=False)
    rate = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)  # snapshot of qty*rate at save time

    def __repr__(self):
        return f'<BathqubeQuoteItem q={self.quote_id} "{self.description[:30]}" {self.amount}>'


class BathqubeQuoteRevision(db.Model):
    """One row per Save in the revise UI. Internal audit log — customer never sees this.

    Captures before/after totals plus a full JSON snapshot of items + enclosures at
    the moment of save, so the team can reconstruct what the bill looked like at any
    point in its history.
    """
    __tablename__ = 'bathqube_quote_revisions'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('bathqube_quotes.id', ondelete='CASCADE'),
                         nullable=False, index=True)
    revision_number = db.Column(db.Integer, nullable=False)  # 1, 2, 3, ...
    prev_subtotal = db.Column(db.Numeric(12, 2), nullable=True)
    new_subtotal = db.Column(db.Numeric(12, 2), nullable=True)
    prev_total = db.Column(db.Numeric(12, 2), nullable=True)
    new_total = db.Column(db.Numeric(12, 2), nullable=True)
    discount_percent = db.Column(db.Numeric(5, 2), nullable=True)
    snapshot = db.Column(db.Text, nullable=True)  # JSON: {enclosures, items, customer}
    triggered_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', foreign_keys=[triggered_by])

    @property
    def snapshot_parsed(self):
        """JSON-parsed snapshot; returns {} if missing/invalid."""
        if not self.snapshot:
            return {}
        try:
            return json.loads(self.snapshot)
        except Exception:
            return {}

    @property
    def total_delta(self):
        """new_total - prev_total. Positive = bill went up, negative = went down."""
        try:
            return float(self.new_total or 0) - float(self.prev_total or 0)
        except Exception:
            return 0

    def __repr__(self):
        return f'<BathqubeQuoteRevision q={self.quote_id} #{self.revision_number} {self.prev_total}->{self.new_total}>'

