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
    # Cosmetic-only flag: when False the user is hidden from the columns of
    # /leads/agent-log but keeps every other permission (login, edit leads,
    # etc). Manager toggles this in the user admin form. False for old team
    # members who no longer need to appear in the daily activity matrix.
    show_in_agent_log = db.Column(db.Boolean, default=True, nullable=False)
    # Per-user permission override for the IndiaMart sync button (2026-07-26).
    # Managers/Admins always have access. Set this True on a Promotor to
    # grant them the sync button + POST endpoint without also giving them
    # the rest of the Manager toolkit (Agent Log peer visibility, FB sync,
    # elevated edit permissions, etc.). Least-privilege delegation.
    can_indiamart_sync = db.Column(db.Boolean, default=False, nullable=False)
    # Default owner for newly-synced IndiaMart leads (2026-07-26). Exactly
    # ONE user should have this True at a time; `_do_indiamart_sync` looks
    # up that user and assigns every new lead to them, regardless of who
    # triggered the sync (button click OR the hourly cron). If nobody has
    # the flag set, sync falls back to the pre-existing behaviour (owner
    # equals the sync trigger, or NULL for cron). Admin toggles via the
    # user admin form; when moving the flag between users the old user's
    # flag should be cleared first.
    is_indiamart_default_owner = db.Column(db.Boolean, default=False, nullable=False, index=True)
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

    def can_run_indiamart_sync(self):
        """True if this user may trigger the IndiaMart sync button.

        Managers + Admins always qualify (existing rule). Promotors qualify
        only when `can_indiamart_sync = True` — a per-user override the
        admin flips in the user admin form. Kept as a single helper so the
        route + template + agent log all check the same predicate.
        """
        return self.is_manager_or_admin() or bool(self.can_indiamart_sync)
    
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
    # Customer PAN — captured only for B2C quotes (quote_type='B2C').
    # B2B customers use the customer_gst column instead; B2C have no
    # GSTIN so PAN is the only printable tax-ID on the invoice.
    customer_pan = db.Column(db.String(15), nullable=True)
    
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


# ── Leadfy stage configuration ────────────────────────────────────────────────
# `stage` is a free-form String(50) column with no DB enum. Consolidated on
# 2026-07-02 from two per-origin funnels (Default + Facebook) into ONE
# canonical 11-stage list. Rationale: BD couldn't cross-verify agent logs
# across origins because the funnels used different vocabulary for the same
# concept ("Untouched" vs "New Lead", "Payment Rcvd" vs "Closed Won", etc.).
#
# Every historical stage has been mapped forward — see
# `migrate_reduce_lead_stages.py` for the exact rewrite table + backfill.

LEAD_STAGES = [
    'New Lead',        # untouched, needs first contact
    'Contacted',       # BD reached out, in conversation
    'Not Connected',   # tried but no response
    'Qualified',       # real interest confirmed
    'Quote 1 Shared',  # first PDF sent
    'Quote 2 Shared',  # first revision
    'Quote 3 Shared',  # second revision (practical cap)
    'Awaiting Payment',# customer accepted, waiting on money
    'Closed Won',      # paid in full
    'Closed Lost',     # customer declined / silent / not interested
    'Junk',            # spam / wrong number / duplicate
]

# Backwards-compat aliases — several routes still import these names.
# All three now point at the same single canonical list so the templates
# that render "default vs facebook" dropdowns just get the same 11 stages
# regardless of which alias they consulted.
LEAD_STAGES_DEFAULT  = LEAD_STAGES
LEAD_STAGES_FACEBOOK = LEAD_STAGES
LEAD_STAGES_ALL      = LEAD_STAGES

# Origin-specific funnel overrides — kept as an empty mapping for now so any
# imports don't break. If BD ever needs a per-origin variant again, register
# it here and update stages_for_origin() below.
LEAD_STAGES_BY_ORIGIN = {}

LEAD_STAGE_BADGE_CLASSES = {
    'New Lead':         'primary',     # blue — fresh
    'Contacted':        'info',        # light blue — engaged
    'Not Connected':    'warning',     # yellow — chase
    'Qualified':        'warning',     # yellow — action needed
    'Quote 1 Shared':   'secondary',   # grey — quote out
    'Quote 2 Shared':   'secondary',   # grey — negotiating
    'Quote 3 Shared':   'secondary',   # grey — heavier negotiation
    'Awaiting Payment': 'warning',     # yellow — money pending
    'Closed Won':       'success',     # green — paid
    'Closed Lost':      'danger',      # red — lost
    'Junk':             'dark',        # black — dead
}


def stages_for_origin(origin):
    """Return the ordered list of allowed stages. Same 11-stage funnel for
    every origin now — argument kept for signature-compat with older
    callers, but the value is ignored."""
    return LEAD_STAGES


def default_stage_for_origin(origin):
    """First stage in the funnel — used when creating leads."""
    return LEAD_STAGES[0]


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
    # Which Page the lead came from — BathQube vs Glassy.in vs future Pages.
    # NULL on legacy rows imported before multi-Page support landed; the
    # webhook + cron sync stamp it on every new ingest now.
    fb_page_id       = db.Column(db.String(50),  nullable=True, index=True)

    # FB ad-hierarchy metadata — captured from the Graph API on webhook
    # ingest (see facebook_webhook_receive in app.py). Powers the
    # Campaign / Adset / Ad filters on /leads so BD can answer "how is
    # the HSR-Showers-Lookalike creative converting?". All nullable —
    # IndiaMart / WhatsApp / manually-entered leads stay valid. Schema
    # parity in migrate_add_lead_facebook_campaign.py.
    fb_campaign_id   = db.Column(db.String(50),  nullable=True, index=True)
    fb_campaign_name = db.Column(db.String(255), nullable=True, index=True)
    fb_adset_id      = db.Column(db.String(50),  nullable=True)
    fb_adset_name    = db.Column(db.String(255), nullable=True)
    fb_ad_id         = db.Column(db.String(50),  nullable=True)
    fb_ad_name       = db.Column(db.String(255), nullable=True)
    # form_id was previously stuffed into `notes`. The name (e.g.
    # "Bathqube Shower Quote · HSR") is what BD wants to read in the list
    # — promote it to its own column. form_id stays in notes for legacy
    # parity with already-imported leads.
    fb_form_name     = db.Column(db.String(255), nullable=True)

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

    # Stage and origin. `stage` is a free-form string; the allowed set varies by
    # `origin` — Facebook leads use the funnel-style stages requested by ops
    # (Untouched → Quote 1 Shared → … → Payment Rcvd), every other origin uses
    # the generic CRM stages. See LEAD_STAGES_DEFAULT / LEAD_STAGES_FACEBOOK.
    stage = db.Column(db.String(50), nullable=False, default='New Lead', index=True)
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
        return LEAD_STAGE_BADGE_CLASSES.get(self.stage, 'secondary')

    def stage_options(self):
        """Allowed stage values for this lead, based on its origin."""
        return stages_for_origin(self.origin)

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


class Brand(db.Model):
    """One WhatsApp Business Account (WABA) per row.

    Each row holds the credentials for a specific brand's WhatsApp sender.
    Initially seeded with 'bathqube' copied from env vars; 'vetrova' and any
    future brands each add their own row with their own WABA credentials and
    phone number. The send helper looks up creds per-send, so no code change
    is needed to onboard a new brand — just insert a row + register the
    same-named template on that brand's WABA.
    """
    __tablename__ = 'brands'

    id                  = db.Column(db.Integer, primary_key=True)
    slug                = db.Column(db.String(32),  unique=True, nullable=False, index=True)
    name                = db.Column(db.String(120), nullable=False)
    wa_phone_number_id  = db.Column(db.String(64),  nullable=False)
    wa_access_token     = db.Column(db.Text,        nullable=False)
    wa_api_version      = db.Column(db.String(10),  nullable=False, default='v21.0')
    is_active           = db.Column(db.Boolean,     nullable=False, default=True)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at          = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<Brand {self.slug} phone_id={self.wa_phone_number_id}>'


class WhatsAppMessage(db.Model):
    """Every WhatsApp event (outbound send + inbound reply + status
    update) recorded on one table.

    `direction` splits the two directions:
      - 'out' : we sent it (template send). `sent_by`, `template_name`,
                `to_number`, and `wamid` are meaningful. `status` cycles
                queued → sent → delivered → read (or failed), driven
                by the Meta webhook status updates.
      - 'in'  : the customer sent it. `from_number`, `body_text`,
                `media_url` / `media_mime` are meaningful. Rendered on
                the lead-view chat panel alongside outbound rows.

    The `sent_at` column is used for ordering in both directions — for
    inbound rows we set it to the message's `received_at`, so a single
    ORDER BY on sent_at gives us the chronological chat timeline.
    """
    __tablename__ = 'whatsapp_messages'

    id              = db.Column(db.Integer, primary_key=True)
    lead_id         = db.Column(db.Integer, db.ForeignKey('leads.id', ondelete='SET NULL'), nullable=True, index=True)
    # Marketing bulk-contact this message belongs to (Bulk Send feature).
    # Nullable — populated when the inbound `from` matches a BulkContact
    # phone (Leads take priority on collision) or when a bulk-send route
    # logs an outbound.
    bulk_contact_id = db.Column(db.Integer, db.ForeignKey('bulk_contacts.id', ondelete='SET NULL'), nullable=True, index=True)
    meeting_id      = db.Column(db.Integer, db.ForeignKey('meetings.id', ondelete='SET NULL'), nullable=True, index=True)
    # Which Bathqube quote this send belongs to (bulk-send from the Bathqube
    # inbox). Nullable for lead-only sends (single-send from lead view).
    bathqube_quote_id = db.Column(db.Integer, db.ForeignKey('bathqube_quotes.id', ondelete='SET NULL'), nullable=True, index=True)
    # Which brand's WABA sent this message. Nullable for legacy rows sent
    # before the Brand table existed (env-var single-tenant era).
    brand_id        = db.Column(db.Integer, db.ForeignKey('brands.id', ondelete='SET NULL'), nullable=True, index=True)

    # 'out' | 'in'. Defaults to 'out' so pre-webhook rows keep the right
    # semantics. See migrate_add_whatsapp_inbound.py for details.
    direction       = db.Column(db.String(3),   nullable=False, default='out', index=True)

    to_number       = db.Column(db.String(20),  nullable=True,  index=True)   # populated on outbound
    from_number     = db.Column(db.String(20),  nullable=True,  index=True)   # populated on inbound
    template_name   = db.Column(db.String(100), nullable=True)                # NULL on inbound
    language        = db.Column(db.String(10),  nullable=False, default='en')
    variables_json  = db.Column(db.Text,        nullable=True)                # JSON-encoded body params (outbound)

    # Inbound-only payload
    body_text       = db.Column(db.Text,        nullable=True)
    media_url       = db.Column(db.Text,        nullable=True)                # Meta media-download URL, short-lived
    media_mime      = db.Column(db.String(60),  nullable=True)                # image/jpeg, application/pdf, audio/ogg …
    media_caption   = db.Column(db.Text,        nullable=True)
    received_at     = db.Column(db.DateTime,    nullable=True)                # Meta's `timestamp` on the message

    wamid           = db.Column(db.String(120), nullable=True, unique=True, index=True)
    status          = db.Column(db.String(20),  nullable=False, default='queued', index=True)
                                                                 # queued | sent | delivered | read | failed | received
    error_message   = db.Column(db.Text,        nullable=True)
    sent_by         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)   # NULL on inbound
    sent_at         = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    lead            = db.relationship('Lead',    foreign_keys=[lead_id],           backref='whatsapp_messages')
    meeting         = db.relationship('Meeting', foreign_keys=[meeting_id],        backref='whatsapp_messages')
    bathqube_quote  = db.relationship('BathqubeQuote', foreign_keys=[bathqube_quote_id], backref='whatsapp_messages')
    brand           = db.relationship('Brand',   foreign_keys=[brand_id])
    sender          = db.relationship('User',    foreign_keys=[sent_by])
    bulk_contact    = db.relationship('BulkContact', foreign_keys=[bulk_contact_id], backref='whatsapp_messages')

    @property
    def is_inbound(self):
        return self.direction == 'in'

    @property
    def is_outbound(self):
        return self.direction == 'out'

    @property
    def display_body(self):
        """One-line body for chat bubble rendering. Inbound uses
        body_text (media caption if body_text empty); outbound rebuilds
        from template_name + first variable so the chat panel shows the
        gist of what was sent without a template lookup."""
        if self.direction == 'in':
            if self.body_text:
                return self.body_text
            if self.media_caption:
                return self.media_caption
            if self.media_mime:
                kind = (self.media_mime or '').split('/')[0]
                return f'[{kind} attachment]'
            return '[empty]'
        # outbound: prefer a template descriptor
        first_var = ''
        if self.variables_json:
            try:
                import json as _json
                arr = _json.loads(self.variables_json)
                if isinstance(arr, list) and arr:
                    first_var = str(arr[0])
            except Exception:
                pass
        base = f'[Template: {self.template_name}]' if self.template_name else '[Message]'
        return f'{base} {first_var}'.strip()

    def __repr__(self):
        if self.direction == 'in':
            return f'<WhatsAppMessage in {self.id} ← {self.from_number} [{self.status}]>'
        return f'<WhatsAppMessage out {self.id} {self.template_name} → {self.to_number} [{self.status}]>'


class BulkContact(db.Model):
    """One row per phone number imported for the Bulk Send marketing
    feature (name + phone Excel upload → template blast → chat replies).

    Deliberately separate from Lead: BD's marketing contacts don't need
    stage / owner / product interest fields; they need only enough to
    dispatch a template and route replies back to a chat panel.

    `campaign` is a free-text grouping tag (e.g. "Sept-promo") set at
    import time so BD can filter the list.

    `is_opted_out` flips to True when the webhook parses "STOP" /
    "unsubscribe" / "remove me" in a reply. Bulk-send routes skip
    opted-out rows silently.

    See migrate_add_bulk_contacts.py for the schema.
    """
    __tablename__ = 'bulk_contacts'

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200), nullable=False)
    phone        = db.Column(db.String(20),  nullable=False, index=True)
    campaign     = db.Column(db.String(100), nullable=True, index=True)
    is_opted_out = db.Column(db.Boolean,     nullable=False, default=False, index=True)
    imported_by  = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    imported_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Business-directory fields — populated by the Glassy India campaign
    # upload. `star_rating` + `listing_url` feed the
    # `glassy_onboarding_invite` template's {{2}} and {{3}} body vars;
    # the rest are stored for BD's cross-referencing + future filters.
    # All nullable so simple name+phone imports still work.
    star_rating       = db.Column(db.Numeric(3, 1), nullable=True)
    listing_url       = db.Column(db.Text,          nullable=True)
    business_category = db.Column(db.String(120),   nullable=True)
    location          = db.Column(db.String(200),   nullable=True)
    reviews_count     = db.Column(db.Integer,       nullable=True)
    website           = db.Column(db.String(500),   nullable=True)

    importer     = db.relationship('User', foreign_keys=[imported_by])

    def __repr__(self):
        tag = f' [{self.campaign}]' if self.campaign else ''
        opt = ' OPTED-OUT' if self.is_opted_out else ''
        return f'<BulkContact {self.id} {self.name} {self.phone}{tag}{opt}>'


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
    'draft',                 # BD-created via vcore /quotes/bathqube/new — not yet sent to customer
    'quote_generated',       # quote landed via configurator webhook OR draft flipped after Send
    'in_pipeline',           # actively working with the customer
    'revision',              # bill revised + revised PDF emailed to customer
    'awaiting_payment',      # order ready / waiting for the customer to pay
    'closed_won',            # deal closed successfully
    'junk',                  # disposition — not a real lead
    'rejected',              # disposition — lost / declined
)

# Stages that are "active" (shown by default in the list view). Junk + rejected
# are disposition states that get filtered out unless the user explicitly opts in.
# Draft is included so BD can see their in-progress drafts in the main list.
BATHQUBE_ACTIVE_STAGES = ('draft', 'quote_generated', 'in_pipeline', 'revision', 'awaiting_payment', 'closed_won')

# Ops/fulfillment stages — run AFTER closed_won. Sales hands the order off to
# the ops team who drives the order through manufacturing + installation.
# These are stored in the same bathqube_quotes.stage column as the sales
# stages — kept separate here so the sales list view and the ops list view
# can each show only their own slice.
BATHQUBE_OPS_STAGES = (
    'measurement_scheduled',   # site visit booked
    'measurement_done',        # dimensions captured + photos uploaded
    'customer_signoff',        # customer confirmed dimensions via WhatsApp
    'in_fabrication',          # glass cutting + toughening
    'ready_to_dispatch',       # boxed + hardware bundled
    'installation_scheduled',  # installer + date locked
    'installed',               # installer signed off on site
    'handover_complete',       # final invoice + warranty card sent
)

# Ops stages that the ops list shows by default. handover_complete is the
# terminal state — filtered out unless the user opts in (mirrors how junk +
# rejected are handled on the sales list).
BATHQUBE_OPS_ACTIVE_STAGES = (
    'closed_won',  # included so freshly-won orders surface for ops to pick up
    'measurement_scheduled', 'measurement_done', 'customer_signoff',
    'in_fabrication', 'ready_to_dispatch',
    'installation_scheduled', 'installed',
)

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
    # Bathqube is B2C — customer doesn't have GSTIN, so PAN is the only
    # tax-ID we can print on the invoice. BD captures it during the
    # revise step (or later when invoicing).
    customer_pan = db.Column(db.String(15), nullable=True)

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
    def paid_via_receipts(self):
        """Sum of all BathqubePaymentReceipt rows on this quote — the
        UTR-audited running total. Use this for any new code; the legacy
        `amount_received` field is left in place for Tally back-compat
        but should be considered deprecated for sales-side flows."""
        rows = getattr(self, 'payment_receipts', None) or []
        return sum(float(r.amount or 0) for r in rows)

    @property
    def paid_to_date(self):
        """The effective amount-received: receipts sum if any exist,
        else the legacy flat field. Lets new receipt-based code and
        legacy quotes coexist without breaking either."""
        receipts_sum = self.paid_via_receipts
        if receipts_sum > 0:
            return receipts_sum
        return float(self.amount_received or 0)

    @property
    def balance_payable(self):
        effective_total = float(self.revised_total if self.revised_total is not None else self.total or 0)
        return max(0.0, effective_total - self.paid_to_date)

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


class BathqubeWorkOrder(db.Model):
    """Ops-side fulfillment record for a Bathqube quote.

    Created lazily the first time a quote transitions out of closed_won into
    an ops stage (or when an ops user opens it for the first time). One row
    per quote — see the uselist=False backref on BathqubeQuote.

    Holds the data the ops team needs but the sales-side quote does not:
    the ops owner, scheduling dates, and free-form ops notes. Stage itself
    stays on BathqubeQuote so the audit log via BathqubeStatusEvent is
    unified.

    Single ops_assignee_id today (one person handles measurement +
    fabrication + installation). When the team splits roles, add
    measurement_assignee_id / installer_assignee_id columns and migrate.
    """
    __tablename__ = 'bathqube_work_orders'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('bathqube_quotes.id', ondelete='CASCADE'),
                         unique=True, nullable=False, index=True)

    ops_assignee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Structured scheduling fields. Cheap to add now, expensive to retro-fit
    # once ops is using free-text notes for the same thing.
    measurement_scheduled_at  = db.Column(db.DateTime, nullable=True)
    installation_scheduled_at = db.Column(db.DateTime, nullable=True)
    delivery_eta              = db.Column(db.Date, nullable=True)

    ops_notes = db.Column(db.Text, nullable=True)
    # Workshop-floor instructions printed on the Work Order PDF that goes
    # to the glass cutters. Distinct from `ops_notes` (which is broader
    # internal scheduling / customer-side notes); cutting_notes is what
    # the worker actually reads on the printed sheet. Free-form text:
    # "Saturday install only", "use 10mm not 8mm for the door panel",
    # "spare 600×1900 piece needed", etc. Editable by BD before
    # generating the PDF.
    cutting_notes = db.Column(db.Text, nullable=True)
    # Workshop scheduling priority. Drives a visual badge on the WO PDF
    # so the floor team can pull urgent jobs to the front of the queue.
    # `normal` = standard turnaround; `urgent` = jump-the-queue.
    # `low` = backfill when there's downtime.
    priority = db.Column(db.String(10), nullable=False, default='normal')

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    quote = db.relationship('BathqubeQuote', backref=db.backref('work_order', uselist=False,
                                                                cascade='all, delete-orphan'))
    ops_assignee = db.relationship('User', foreign_keys=[ops_assignee_id])

    def __repr__(self):
        return f'<BathqubeWorkOrder q={self.quote_id}>'


class BathqubeStageAttachment(db.Model):
    """File/photo uploaded against a specific ops stage of a Bathqube quote.

    Multiple per stage. Used for: measurement photos, signed dimension
    sheets, fabrication-vendor POs, installation before/after shots,
    customer handover signature.
    """
    __tablename__ = 'bathqube_stage_attachments'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('bathqube_quotes.id', ondelete='CASCADE'),
                         nullable=False, index=True)
    # Which stage this attachment belongs to — string, not FK, since stages
    # are an enum-ish constant rather than a table.
    stage = db.Column(db.String(32), nullable=False, index=True)
    kind  = db.Column(db.String(20), nullable=False, default='photo')  # photo | document | signature

    file_url = db.Column(db.Text, nullable=False)
    caption  = db.Column(db.String(255), nullable=True)

    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    quote    = db.relationship('BathqubeQuote', backref=db.backref('stage_attachments', lazy=True,
                                                                   cascade='all, delete-orphan',
                                                                   order_by='BathqubeStageAttachment.created_at.desc()'))
    uploader = db.relationship('User', foreign_keys=[uploaded_by])

    def __repr__(self):
        return f'<BathqubeStageAttachment q={self.quote_id} stage={self.stage} kind={self.kind}>'


class BathqubePaymentReceipt(db.Model):
    """One payment receipt against a Bathqube quote.

    Customers typically pay in instalments — 10–30% advance, the rest on
    install. Each row is ONE inflow: amount + UTR + date. The downloadable
    receipt PDF for this row shows the cumulative summary as of this
    receipt's date (previous payments + this one + balance due).

    `BathqubeQuote.amount_received` was a single flat ₹ field; from now on
    the source of truth is the SUM of these receipts. The legacy field is
    still on the model for back-compat with existing rows (and for the
    Tally screen which is not tied to UTR-level audit), but new payments
    should always be recorded as receipts.

    Permanent log — never UPDATE or DELETE an existing row even if BD
    typed wrong. Instead create a corrective receipt with a negative
    amount or refund-mode flag. That keeps the audit trail intact.
    """
    __tablename__ = 'bathqube_payment_receipts'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('bathqube_quotes.id', ondelete='CASCADE'),
                         nullable=False, index=True)

    # Human-readable receipt id, e.g. "BQ-RCP-2026-0042". Unique across
    # all receipts so it can be the printed reference number the
    # customer quotes back. Auto-assigned at create time.
    receipt_number = db.Column(db.String(32), unique=True, nullable=False, index=True)

    # When the money actually hit our account (typed by BD on the form,
    # defaults to today). NOT the same as created_at — BD may record a
    # payment a day or two after the inflow.
    received_at = db.Column(db.Date, nullable=False, default=datetime.utcnow)

    amount = db.Column(db.Numeric(12, 2), nullable=False)

    # bank_transfer | upi | cash | cheque — drives which reference field
    # is mandatory and how the PDF describes the payment.
    payment_method = db.Column(db.String(20), nullable=False, default='bank_transfer')

    # Banking refs — at most one of these is filled in per row depending
    # on payment_method. We don't enforce a check constraint because BD
    # may legitimately have neither (cash receipts).
    utr_number = db.Column(db.String(40), nullable=True)
    cheque_number = db.Column(db.String(40), nullable=True)

    # Optional free-form (e.g. "10% advance per WO signed", "balance after
    # install — site 8th floor delay, see WhatsApp"). Printed in small
    # text on the PDF.
    notes = db.Column(db.String(500), nullable=True)

    # Audit
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    quote = db.relationship('BathqubeQuote', backref=db.backref('payment_receipts', lazy=True,
                                                                cascade='all, delete-orphan',
                                                                order_by='BathqubePaymentReceipt.received_at.desc(), BathqubePaymentReceipt.id.desc()'))
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<BathqubePaymentReceipt {self.receipt_number} q={self.quote_id} amt={self.amount}>'


# ============================================================================
# VETROVA INTERNI · UPVC QUOTES (KAN-67)
# ============================================================================
# UPVC quotation flow for Vetrova Interni. Mirrors the Bathqube model shape
# but leaner — no public configurator (BD types each line), no workshop
# work-order (vendor fabricates), no UPI/receipts table yet. BD picks track
# type + system + dimensions + colour per line and writes the price himself;
# the price is the TAXABLE amount, GST is added on top. Invoice issues
# under "Vetrova Tech Services Private Limited" with Vetrova Interni
# masthead + a prominent 20-year warranty highlight strip.

# Sales lifecycle. Shorter than Bathqube because there's no public
# configurator entry point (no `quote_generated` from a webhook). BD
# manually creates the quote in vcore, then walks it through the funnel.
UPVC_STAGES = (
    'draft',              # being built — not yet sent to customer
    'sent',               # estimate PDF emailed to the customer
    'revision',           # bill revised + revised PDF re-emailed
    'awaiting_payment',   # customer has accepted; waiting on money
    'closed_won',         # paid in full
    'rejected',           # customer declined
    'junk',               # bad lead / spam
)
UPVC_ACTIVE_STAGES = ('draft', 'sent', 'revision', 'awaiting_payment', 'closed_won')


class UpvcQuote(db.Model):
    """Vetrova Interni UPVC quote (KAN-67).

    BD-created, mirrors `BathqubeQuote` shape but simpler — no
    configurator snapshot, no work-order, no receipts table yet (will
    reuse the same payment-receipt pattern when needed). Each line is a
    track/opening configured + priced by the BD.
    """
    __tablename__ = 'vetrova_upvc_quotes'

    id = db.Column(db.Integer, primary_key=True)

    # Human-readable estimate number stamped on the PDF, e.g. "VI-UPVC-2026-0042".
    # Auto-assigned at create time; unique so it can be the printed
    # reference the customer quotes back.
    estimate_number = db.Column(db.String(32), unique=True, nullable=True, index=True)

    # Customer — typed by BD on the create form. No upstream Lead FK yet
    # (UPVC enquiries currently come through phone / referral, not a form);
    # if/when we wire UPVC to a lead funnel we'll add lead_id here.
    customer_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(32), nullable=False, index=True)
    email = db.Column(db.String(200), nullable=True, index=True)
    pincode = db.Column(db.String(12), nullable=True)
    site_address = db.Column(db.Text, nullable=True)
    # UPVC is B2C — PAN captured for tax invoice rendering.
    customer_pan = db.Column(db.String(15), nullable=True)

    # Money. BD's per-line price is the TAXABLE amount; subtotal is the
    # sum of line amounts; GST applies on top per the directive that
    # "whatever he writes is taxable, tax is calculated after that value".
    subtotal = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    # Optional BD-typed transport/delivery charge — added to the taxable
    # base BEFORE GST. Shown as a separate line on the customer PDF
    # between Subtotal and CGST. Defaults 0 so old quotes read fine.
    transport_charges = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    cgst = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    sgst = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    gst_percentage = db.Column(db.Numeric(5, 2), default=18, nullable=False)
    amount_received = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    # Validity in days (KAN-67 answer #4 — fixed at 10). Stored per-row
    # so a future BD-typed override per quote is a config change, not a
    # schema change.
    validity_days = db.Column(db.Integer, default=10, nullable=False)

    # Bumped on every successful save in the revise UI. 0 = the original
    # quote BD typed; revisions[0] is the FIRST revise; etc.
    revision_count = db.Column(db.Integer, default=0, nullable=False)

    # Lifecycle (UPVC_STAGES above)
    stage = db.Column(db.String(32), nullable=False, default='draft', index=True)
    notes = db.Column(db.Text, nullable=True)

    # Audit
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    purchased_at = db.Column(db.DateTime, nullable=True)

    # Backrefs
    items = db.relationship('UpvcQuoteItem', backref='quote', lazy=True,
                            cascade='all, delete-orphan',
                            order_by='UpvcQuoteItem.sort_order')
    events = db.relationship('UpvcStatusEvent', backref='quote', lazy=True,
                             cascade='all, delete-orphan',
                             order_by='UpvcStatusEvent.created_at.desc()')
    revisions = db.relationship('UpvcQuoteRevision', backref='quote', lazy=True,
                                cascade='all, delete-orphan',
                                order_by='UpvcQuoteRevision.revision_number.desc()')
    creator = db.relationship('User', foreign_keys=[created_by])

    @property
    def balance_payable(self):
        return max(0.0, float(self.total or 0) - float(self.amount_received or 0))

    @property
    def valid_until(self):
        """created_at + validity_days. Used by the PDF + email template."""
        from datetime import timedelta
        if not self.created_at:
            return None
        return self.created_at + timedelta(days=int(self.validity_days or 10))

    def __repr__(self):
        return f'<UpvcQuote {self.estimate_number or self.id} {self.customer_name} {self.stage}>'


class UpvcQuoteItem(db.Model):
    """One opening / track on a UPVC quote.

    BD configures: track type, sliding-system (if applicable), dimensions
    (W × H + unit), colour, optional label, and a free-typed price. The
    price is the line-level taxable amount; GST is added at the quote
    level. Quantity is implicit (1 per row) — if BD wants two identical
    openings he adds two rows so the line item table stays scannable
    on the PDF.
    """
    __tablename__ = 'vetrova_upvc_quote_items'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('vetrova_upvc_quotes.id', ondelete='CASCADE'),
                         nullable=False, index=True)

    sort_order = db.Column(db.Integer, default=0, nullable=False)

    # Optional human label — "Master bedroom — North window" etc. Helps
    # the customer identify which opening is which in the PDF.
    label = db.Column(db.String(200), nullable=True)

    # Configurator fields (KAN-67)
    track_type = db.Column(db.String(20), nullable=False)              # 'swing' | 'sliding'
    track_system = db.Column(db.String(20), nullable=True)             # '2-track' | '2.5-track' | '3-track' — NULL for swing
    width = db.Column(db.Numeric(10, 2), nullable=True)
    height = db.Column(db.Numeric(10, 2), nullable=True)
    unit = db.Column(db.String(8), nullable=False, default='ft')       # mm | cm | m | ft | in — KAN-34
    colour = db.Column(db.String(20), nullable=False)                  # 'white' | 'black' | 'wooden'

    # Quantity of this opening at the given spec/price. Defaults to 1.
    # BD bumps it when the customer wants N identical openings without
    # duplicating the row (e.g. two identical bedroom windows).
    quantity = db.Column(db.Numeric(10, 2), default=1, nullable=False)
    # Square-feet computed from width × height using the unit-aware
    # to_inches() table (mirrors the Bathqube formula). Persisted so the
    # audit trail captures what was computed at save time even if the
    # to_inches table ever changes. NUMERIC(10,4) keeps 4dp precision
    # which is sufficient for any realistic opening.
    sqft = db.Column(db.Numeric(10, 4), default=0, nullable=False)
    # BD-typed PER-SQUARE-FOOT price (taxable). The semantics shift was
    # made on 2026-06-27 — earlier rows had `rate` as a flat per-line
    # price, but those rows were wiped before the migration. From now on
    # rate is ALWAYS ₹/sqft.
    rate = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    # Snapshot of quantity*sqft*rate at save time. The recompute helper
    # always rewrites this so divergence between (qty, sqft, rate) and
    # amount can only come from a bug.
    amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    def __repr__(self):
        dim = f'{self.width}x{self.height}{self.unit}' if self.width and self.height else 'no-dim'
        return f'<UpvcQuoteItem q={self.quote_id} {self.track_type}/{self.colour} {dim} {self.amount}>'


class UpvcQuoteRevision(db.Model):
    """One row per Save in the UPVC revise UI. Internal audit log."""
    __tablename__ = 'vetrova_upvc_quote_revisions'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('vetrova_upvc_quotes.id', ondelete='CASCADE'),
                         nullable=False, index=True)
    revision_number = db.Column(db.Integer, nullable=False)
    prev_subtotal = db.Column(db.Numeric(12, 2), nullable=True)
    new_subtotal = db.Column(db.Numeric(12, 2), nullable=True)
    prev_total = db.Column(db.Numeric(12, 2), nullable=True)
    new_total = db.Column(db.Numeric(12, 2), nullable=True)
    snapshot = db.Column(db.Text, nullable=True)  # JSON: {items, customer}
    triggered_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', foreign_keys=[triggered_by])

    @property
    def total_delta(self):
        try:
            return float(self.new_total or 0) - float(self.prev_total or 0)
        except Exception:
            return 0

    def __repr__(self):
        return f'<UpvcQuoteRevision q={self.quote_id} #{self.revision_number} {self.prev_total}->{self.new_total}>'


class UpvcStatusEvent(db.Model):
    """Audit log of stage transitions + emails sent for a UPVC quote.
    Same shape as BathqubeStatusEvent so the view template can re-use
    the same activity-timeline component."""
    __tablename__ = 'vetrova_upvc_status_events'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('vetrova_upvc_quotes.id', ondelete='CASCADE'),
                         nullable=False, index=True)

    from_stage = db.Column(db.String(32), nullable=True)
    to_stage = db.Column(db.String(32), nullable=False)

    channel = db.Column(db.String(20), nullable=False, default='email')  # email | none
    subject = db.Column(db.String(255), nullable=True)
    message = db.Column(db.Text, nullable=True)

    send_status = db.Column(db.String(20), nullable=False, default='pending')  # pending|sent|failed|skipped
    send_error = db.Column(db.Text, nullable=True)
    provider_message_id = db.Column(db.String(128), nullable=True)

    triggered_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', foreign_keys=[triggered_by])

    def __repr__(self):
        return f'<UpvcStatusEvent q={self.quote_id} {self.from_stage}->{self.to_stage} {self.send_status}>'


# ============================================================================
# TAX INVOICES — GST-compliant invoice generation
# ============================================================================
# When a quote reaches `closed_won` and BD pushes it through Tally, they
# can "Generate Tax Invoice" to produce a properly-formatted GST invoice.
# The invoice freezes a snapshot of the line items at gen time — the
# source quote stays mutable but the invoice does not.

# Statuses for the invoice lifecycle
TAX_INVOICE_STATUSES = ('draft', 'issued', 'cancelled')


class TaxInvoice(db.Model):
    """GST tax invoice issued by Vetrova Tech Services to a customer.

    Polymorphic source: exactly one of (`bathqube_quote_id`,
    `upvc_quote_id`, `lead_quote_id`) is set per row — mirrors the
    `PurchaseInvoice` pattern already in this codebase.

    Once `status='issued'`, money fields + line items are immutable
    (the route layer enforces this); only soft fields (vehicle no,
    e-Way Bill no, IRN paste-in, terms of delivery, etc.) may still
    be edited. Cancellation creates a credit-note flow in a future
    phase — for now we just mark `status='cancelled'`.
    """
    __tablename__ = 'tax_invoices'

    id = db.Column(db.Integer, primary_key=True)

    # Sequential per-FY: e.g. VTS/2627/0001
    invoice_number  = db.Column(db.String(40), unique=True, nullable=False, index=True)
    financial_year  = db.Column(db.String(8),  nullable=False, index=True)
    invoice_date    = db.Column(db.Date,       nullable=False, default=datetime.utcnow, index=True)

    # Source quote — exactly one set
    bathqube_quote_id = db.Column(db.Integer, db.ForeignKey('bathqube_quotes.id'),     nullable=True, index=True)
    upvc_quote_id     = db.Column(db.Integer, db.ForeignKey('vetrova_upvc_quotes.id'), nullable=True, index=True)
    lead_quote_id     = db.Column(db.Integer, db.ForeignKey('quotes.id'),              nullable=True, index=True)

    # Seller snapshot (frozen — changing global settings later doesn't
    # rewrite historical invoices)
    seller_name        = db.Column(db.String(200), nullable=False)
    seller_address     = db.Column(db.Text,        nullable=False)
    seller_gstin       = db.Column(db.String(20),  nullable=False)
    seller_state       = db.Column(db.String(50),  nullable=False)
    seller_state_code  = db.Column(db.String(4),   nullable=False)
    seller_pan         = db.Column(db.String(20),  nullable=True)
    seller_udyam       = db.Column(db.String(40),  nullable=True)
    seller_email       = db.Column(db.String(200), nullable=True)
    seller_cin         = db.Column(db.String(40),  nullable=True)

    # Buyer (Bill-to)
    buyer_name         = db.Column(db.String(200), nullable=False)
    buyer_address      = db.Column(db.Text,        nullable=False)
    buyer_gstin        = db.Column(db.String(20),  nullable=True)
    # Buyer PAN — printed on the invoice for B2C customers who don't
    # carry a GSTIN. Either buyer_gstin or buyer_pan (or neither) is
    # typically filled; both can coexist if the customer is B2B with a
    # voluntarily-shared PAN.
    buyer_pan          = db.Column(db.String(15),  nullable=True)
    buyer_state        = db.Column(db.String(50),  nullable=True)
    buyer_state_code   = db.Column(db.String(4),   nullable=True)

    # Consignee (Ship-to). Defaults to buyer when same site.
    consignee_name        = db.Column(db.String(200), nullable=False)
    consignee_address     = db.Column(db.Text,        nullable=False)
    consignee_gstin       = db.Column(db.String(20),  nullable=True)
    consignee_state       = db.Column(db.String(50),  nullable=True)
    consignee_state_code  = db.Column(db.String(4),   nullable=True)

    # Invoice metadata — BD enters these on the "generate invoice" form.
    # Some have sensible defaults applied at row-create time.
    buyers_order_no    = db.Column(db.String(100), nullable=True)
    buyers_order_date  = db.Column(db.Date,        nullable=True)
    delivery_note      = db.Column(db.String(100), nullable=True)
    delivery_note_date = db.Column(db.Date,        nullable=True)
    dispatch_doc_no    = db.Column(db.String(100), nullable=True)
    mode_of_payment    = db.Column(db.String(50),  default='PROMPT')
    other_references   = db.Column(db.String(255), nullable=True)
    dispatched_through = db.Column(db.String(50),  default='ROAD')
    destination        = db.Column(db.String(200), nullable=True)
    terms_of_delivery  = db.Column(db.String(255), default='EX OUR SITE')
    bill_of_lading     = db.Column(db.String(100), nullable=True)
    bill_of_lading_date = db.Column(db.Date,       nullable=True)
    motor_vehicle_no   = db.Column(db.String(20),  nullable=True)
    ewaybill_no        = db.Column(db.String(50),  nullable=True)

    # e-Invoice fields — BD pastes manually after generating on the IRP
    # portal. PDF renders the IRN block only when irn is set; otherwise
    # the block is omitted entirely so a non-e-invoice document still
    # prints clean.
    irn      = db.Column(db.String(80), nullable=True)
    ack_no   = db.Column(db.String(40), nullable=True)
    ack_date = db.Column(db.Date,       nullable=True)

    # Computed totals
    subtotal        = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    cgst            = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    sgst            = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    igst            = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    round_off       = db.Column(db.Numeric(6, 2),  nullable=False, default=0)
    total           = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    amount_in_words = db.Column(db.String(500),    nullable=True)

    # Bank snapshot (so changing the global bank later doesn't rewrite
    # what was printed on a past invoice)
    bank_account_name = db.Column(db.String(200), nullable=True)
    bank_name         = db.Column(db.String(100), nullable=True)
    bank_account_no   = db.Column(db.String(40),  nullable=True)
    bank_ifsc         = db.Column(db.String(20),  nullable=True)
    bank_branch       = db.Column(db.String(100), nullable=True)
    upi_id            = db.Column(db.String(60),  nullable=True)

    declaration = db.Column(db.Text, nullable=True)

    status         = db.Column(db.String(20), nullable=False, default='draft', index=True)
    created_by     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    issued_at      = db.Column(db.DateTime, nullable=True)
    cancelled_at   = db.Column(db.DateTime, nullable=True)
    cancelled_reason = db.Column(db.Text, nullable=True)

    # Relationships
    items = db.relationship('TaxInvoiceItem', backref='invoice', lazy=True,
                            cascade='all, delete-orphan',
                            order_by='TaxInvoiceItem.sort_order')
    bathqube_quote = db.relationship('BathqubeQuote', foreign_keys=[bathqube_quote_id])
    upvc_quote     = db.relationship('UpvcQuote',     foreign_keys=[upvc_quote_id])
    lead_quote     = db.relationship('Quote',         foreign_keys=[lead_quote_id])
    creator        = db.relationship('User',          foreign_keys=[created_by])

    @property
    def is_inter_state(self):
        """True when buyer's state differs from seller's — drives
        IGST vs CGST+SGST treatment."""
        if not self.buyer_state_code or not self.seller_state_code:
            return False
        return self.buyer_state_code != self.seller_state_code

    @property
    def is_editable(self):
        """Soft-edit gate: status='issued' invoices lock money fields +
        line items (the route enforces this; this property is for the
        view template's button visibility)."""
        return self.status == 'draft'

    def __repr__(self):
        return f'<TaxInvoice {self.invoice_number} {self.buyer_name} {self.status} ₹{self.total}>'


class TaxInvoiceItem(db.Model):
    """One line on a tax invoice — frozen at issue time."""
    __tablename__ = 'tax_invoice_items'

    id         = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('tax_invoices.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    description = db.Column(db.String(500), nullable=False)
    hsn_code    = db.Column(db.String(10),  nullable=True, index=True)
    quantity    = db.Column(db.Numeric(12, 4), nullable=False, default=1)
    unit        = db.Column(db.String(20),  nullable=False, default='nos')
    rate        = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    amount      = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    # Transportation / installation / discount lines — PDF places these
    # after the product rows for visual grouping.
    is_extra = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f'<TaxInvoiceItem inv={self.invoice_id} HSN={self.hsn_code} {self.description[:30]} {self.amount}>'


class GatePass(db.Model):
    """Dispatch document — tracks material physically leaving the
    factory. Modelled on the Arihant packing slip: customer + invoice
    + vehicle + transporter on top, line items (qty + dimensions +
    process flags) in the middle, totals + signatures at the bottom.

    Polymorphic source: exactly one of `tax_invoice_id`,
    `bathqube_quote_id`, `upvc_quote_id`, `lead_quote_id` is set per
    row. Multiple gate passes per source are allowed — supports
    partial dispatches across multiple trips.

    Once `status='issued'`, qty fields are immutable (the route layer
    enforces this); only logistics fields (vehicle, driver, LR, e-Way
    Bill no) stay editable so BD can keep the document fresh without
    breaking dispatch reconciliation.
    """
    __tablename__ = 'gate_passes'

    id = db.Column(db.Integer, primary_key=True)

    # Sequential per-FY: VTS/GP/2627/0001
    gp_number       = db.Column(db.String(40), unique=True, nullable=False, index=True)
    financial_year  = db.Column(db.String(8),  nullable=False, index=True)
    gp_date         = db.Column(db.Date,       nullable=False, default=datetime.utcnow, index=True)

    # Source — exactly one set
    tax_invoice_id    = db.Column(db.Integer, db.ForeignKey('tax_invoices.id'),         nullable=True, index=True)
    bathqube_quote_id = db.Column(db.Integer, db.ForeignKey('bathqube_quotes.id'),      nullable=True, index=True)
    upvc_quote_id     = db.Column(db.Integer, db.ForeignKey('vetrova_upvc_quotes.id'),  nullable=True, index=True)
    lead_quote_id     = db.Column(db.Integer, db.ForeignKey('quotes.id'),               nullable=True, index=True)

    # Customer / delivery snapshot
    customer_name    = db.Column(db.String(200), nullable=False)
    delivery_address = db.Column(db.Text,        nullable=True)
    customer_gstin   = db.Column(db.String(20),  nullable=True)

    # Reference back to source invoice/quote (printed on PDF)
    ref_invoice_no   = db.Column(db.String(60), nullable=True)
    ref_invoice_date = db.Column(db.Date,       nullable=True)

    # Logistics
    vehicle_no       = db.Column(db.String(30),  nullable=True)
    transporter_name = db.Column(db.String(150), nullable=True)
    driver_name      = db.Column(db.String(150), nullable=True)
    driver_phone     = db.Column(db.String(30),  nullable=True)
    lr_number        = db.Column(db.String(60),  nullable=True)
    eway_bill_no     = db.Column(db.String(50),  nullable=True)
    place_of_supply  = db.Column(db.String(200), nullable=True)

    remarks = db.Column(db.Text, nullable=True)

    status         = db.Column(db.String(20), nullable=False, default='draft', index=True)
    prepared_by    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    issued_at      = db.Column(db.DateTime, nullable=True)
    cancelled_at   = db.Column(db.DateTime, nullable=True)
    cancelled_reason = db.Column(db.Text, nullable=True)

    # Relationships
    items = db.relationship('GatePassItem', backref='gate_pass', lazy=True,
                            cascade='all, delete-orphan',
                            order_by='GatePassItem.sort_order')
    tax_invoice    = db.relationship('TaxInvoice',    foreign_keys=[tax_invoice_id])
    bathqube_quote = db.relationship('BathqubeQuote', foreign_keys=[bathqube_quote_id])
    upvc_quote     = db.relationship('UpvcQuote',     foreign_keys=[upvc_quote_id])
    lead_quote     = db.relationship('Quote',         foreign_keys=[lead_quote_id])
    preparer       = db.relationship('User',          foreign_keys=[prepared_by])

    @property
    def is_editable(self):
        """Qty fields are mutable only while draft."""
        return self.status == 'draft'

    @property
    def total_qty(self):
        return sum(float(it.qty_this_pass or 0) for it in self.items)

    @property
    def total_sqft(self):
        return sum(float(it.sqft or 0) for it in self.items)

    @property
    def total_sqm(self):
        return sum(float(it.sqm or 0) for it in self.items)

    @property
    def source_label(self):
        if self.tax_invoice_id:
            return f'Tax Invoice #{self.tax_invoice_id}'
        if self.bathqube_quote_id:
            return f'Bathqube #{self.bathqube_quote_id}'
        if self.upvc_quote_id:
            return f'UPVC #{self.upvc_quote_id}'
        if self.lead_quote_id:
            return f'Quote #{self.lead_quote_id}'
        return '—'

    def __repr__(self):
        return f'<GatePass {self.gp_number} {self.customer_name} {self.status}>'


class GatePassItem(db.Model):
    """One dispatched line. Mirrors a row in the Arihant packing slip."""
    __tablename__ = 'gate_pass_items'

    id           = db.Column(db.Integer, primary_key=True)
    gate_pass_id = db.Column(db.Integer, db.ForeignKey('gate_passes.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    sort_order   = db.Column(db.Integer, nullable=False, default=0)

    material_spec     = db.Column(db.String(200), nullable=True)
    ref_code          = db.Column(db.String(60),  nullable=True)
    work_order_no     = db.Column(db.String(60),  nullable=True)

    width_mm          = db.Column(db.Numeric(10, 2), nullable=True)
    height_mm         = db.Column(db.Numeric(10, 2), nullable=True)
    width_in_display  = db.Column(db.String(20),  nullable=True)
    height_in_display = db.Column(db.String(20),  nullable=True)

    qty_ordered           = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    qty_dispatched_before = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    qty_this_pass         = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    sqft = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    sqm  = db.Column(db.Numeric(12, 4), nullable=False, default=0)

    # Process flags — mirror Arihant H/C/SP/BH/CSK columns
    # H=Heat-soaked, C=Coated, SP=Polished, BH=Bevel/Hole, CSK=Countersink
    flag_h   = db.Column(db.Boolean, nullable=False, default=False)
    flag_c   = db.Column(db.Boolean, nullable=False, default=False)
    flag_sp  = db.Column(db.Boolean, nullable=False, default=False)
    flag_bh  = db.Column(db.Boolean, nullable=False, default=False)
    flag_csk = db.Column(db.Boolean, nullable=False, default=False)

    source_kind    = db.Column(db.String(20), nullable=True)
    source_item_id = db.Column(db.Integer, nullable=True)

    remarks = db.Column(db.String(200), nullable=True)

    def __repr__(self):
        return f'<GatePassItem gp={self.gate_pass_id} ref={self.ref_code} qty={self.qty_this_pass}>'


# ============================================================================
# Vetrova Quotes (KAN — 2026-07-08)
# ============================================================================
# Customer fills a per-category configurator on vetrova.in (balcony,
# staircase, pergola, …) and clicks "Get quote on WhatsApp". Glassyplatform
# HMAC-forwards the payload to `POST /api/vetrova/quotes/ingest` here. BD
# then works the lead through the same 5-stage funnel as Bathqube. Category
# lives on the row so BD can filter (Balcony / Staircase / Pergola / …).
# ============================================================================

VETROVA_STAGES = (
    'quote_generated',       # landed from vetrova.in configurator
    'in_pipeline',           # BD actively working
    'revision',              # revised quote sent
    'awaiting_payment',      # order ready / waiting for payment
    'closed_won',            # deal closed
    'junk',                  # not a real lead
    'rejected',              # lost / declined
)

VETROVA_ACTIVE_STAGES = ('quote_generated', 'in_pipeline', 'revision', 'awaiting_payment', 'closed_won')

VETROVA_STAGE_LABELS = {
    'quote_generated':  'Quote Generated',
    'in_pipeline':      'In Pipeline',
    'revision':         'Revision',
    'awaiting_payment': 'Awaiting Payment',
    'closed_won':       'Closed Won',
    'junk':             'Junk',
    'rejected':         'Rejected',
}

# Canonical category enum shared with glassyplatform. Slugs match
# `categorySlug` on the POST payload. Labels are what BD sees in the filter
# dropdown and the list-view column. Keep alphabetical after 'balcony' —
# the three current railings-family categories first.
VETROVA_CATEGORIES = (
    ('balcony',           'Balcony'),
    ('staircase',         'Staircase'),
    ('pergola',           'Pergola'),
    ('railings',          'Railings'),
    ('partitions',        'Partitions'),
    ('office-cubicles',   'Office Cubicles'),
    ('doors-and-windows', 'Doors & Windows'),
    ('printed-glass',     'Printed Glass'),
    ('laminated-glass',   'Laminated Glass'),
    ('backsplash',        'Backsplash'),
    ('feature-walls',     'Feature Walls'),
    ('storage',           'Storage'),
    ('smartglass',        'Smart Glass'),
    ('pool-mosaics',      'Pool Mosaics'),
    ('wardrobes',         'Wardrobes'),
    ('folding-glass',     'Folding Glass'),
    ('upvc',              'UPVC'),
)
VETROVA_CATEGORY_LABELS = dict(VETROVA_CATEGORIES)


class VetrovaQuote(db.Model):
    """Configurator quote from vetrova.in — parent row per submission.

    Line items live on `VetrovaQuoteItem` (one per configured category
    run — customers can add multiple configurations in one basket). The
    legacy per-quote fields (category_slug, selections, running_ft,
    quantity) are kept for the SINGLE-run case + back-compat with pre-
    KAN Phase-1 rows; new ingests populate `items` and leave these
    fields set to the first run's summary for the list view.
    """
    __tablename__ = 'vetrova_quotes'

    id = db.Column(db.Integer, primary_key=True)

    # Compact reference minted by glassyplatform (VQ-BAL-1234).
    quote_ref = db.Column(db.String(32), unique=True, nullable=False, index=True)
    # Distinct from quote_ref so future glassyplatform-side persistence can
    # link back independently. Optional today (glassyplatform's endpoint is
    # still stateless), so it may equal quote_ref for now.
    external_id = db.Column(db.String(64), unique=True, nullable=True, index=True)

    # Primary category label — for multi-run quotes it's the FIRST run's
    # category (or "Multi-configuration" when categories differ). Kept for
    # the list view; the actual per-item categories live on `items`.
    category_slug = db.Column(db.String(32), nullable=False, index=True)
    category_label = db.Column(db.String(64), nullable=False)

    # Customer
    customer_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(32), nullable=False, index=True)
    email = db.Column(db.String(200), nullable=True, index=True)
    pincode = db.Column(db.String(12), nullable=True)
    site_address = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # ── Legacy single-run snapshot (populated ONLY when the quote has
    # exactly one item; kept for back-compat with UI/reports that still
    # read these top-level fields). Multi-run quotes leave these as the
    # first run's values so the list view still reads sensibly. ────
    selections = db.Column(db.Text, nullable=True)
    running_ft = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)

    # ── Money — computed as Σ(items.subtotal) via recompute_totals(). ────
    # `total` is the customer-facing subtotal EXCLUSIVE of tax (what the
    # customer saw on the configurator PDF). Retained for back-compat;
    # new callers should prefer `subtotal`.
    total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    transport_charges = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    cgst = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    sgst = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    gst_percentage = db.Column(db.Numeric(5, 2), default=18, nullable=False)
    grand_total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    # BD's revised total override — usually NULL (grand_total is authoritative).
    # Populated when BD wants to negotiate a lump-sum discount without
    # touching per-item rates.
    revised_total = db.Column(db.Numeric(12, 2), nullable=True)
    amount_received = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    # Revision bookkeeping — bumped on every save via the revise editor.
    revision_count = db.Column(db.Integer, default=0, nullable=False)
    # Validity in days — mirrors UPVC quote (KAN-67).
    validity_days = db.Column(db.Integer, default=10, nullable=False)

    stage = db.Column(db.String(32), nullable=False, default='quote_generated', index=True)
    stage_notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items = db.relationship('VetrovaQuoteItem', backref='quote', lazy=True,
                            cascade='all, delete-orphan',
                            order_by='VetrovaQuoteItem.sort_order')
    events = db.relationship('VetrovaStatusEvent', backref='quote', lazy=True,
                             cascade='all, delete-orphan',
                             order_by='VetrovaStatusEvent.created_at.desc()')

    @property
    def selections_parsed(self):
        if not self.selections:
            return {}
        try:
            return json.loads(self.selections)
        except Exception:
            return {}

    @property
    def balance_payable(self):
        target = float(self.revised_total if self.revised_total is not None else self.grand_total or 0)
        return max(0.0, target - float(self.amount_received or 0))

    @property
    def valid_until(self):
        """created_at + validity_days. Used by the PDF + email template."""
        from datetime import timedelta
        if not self.created_at:
            return None
        return self.created_at + timedelta(days=int(self.validity_days or 10))

    def recompute_totals(self):
        """Recalculate subtotal + GST + grand_total from the current items.

        Called by the ingest handler + the revise-save handler so any time
        items change, the parent's money fields stay in sync. Uses whole
        rupees to match the customer-facing PDF (which never shows paise).
        """
        subtotal = sum(float(i.subtotal or 0) for i in (self.items or []))
        transport = float(self.transport_charges or 0)
        gst_pct = float(self.gst_percentage or 18)
        taxable = subtotal + transport
        # Split GST evenly across CGST/SGST for intra-state (default).
        cgst = round(taxable * (gst_pct / 200), 2)
        sgst = round(taxable * (gst_pct / 200), 2)
        self.subtotal = round(subtotal, 2)
        self.cgst = cgst
        self.sgst = sgst
        self.grand_total = round(taxable + cgst + sgst, 2)
        # Keep `total` (pre-GST subtotal) in sync — used by legacy list view
        # + the configurator PDF that customers already have.
        self.total = round(subtotal, 2)

    def __repr__(self):
        return f'<VetrovaQuote {self.quote_ref} {self.category_slug} {self.customer_name} {self.stage}>'


class VetrovaQuoteItem(db.Model):
    """One configured run on a VetrovaQuote.

    A single customer submission from vetrova.in can carry N runs — one
    per configured category. Each run becomes one row here, mirroring
    the wire payload shape:

      { categorySlug, selections{...}, runningFt, quantity, panels[],
        fabricCode, uploadedImageDataUrl, dimensionKind, dimensionUnit,
        subtotal }

    BD edits each item's rate/qty/selections/panels via the revise
    route; the parent VetrovaQuote's subtotal is Σ(item.subtotal).
    """
    __tablename__ = 'vetrova_quote_items'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('vetrova_quotes.id', ondelete='CASCADE'),
                         nullable=False, index=True)

    sort_order = db.Column(db.Integer, default=0, nullable=False)

    # Category this run configures (partitions / laminated-glass / …).
    category_slug = db.Column(db.String(32), nullable=False)
    category_label = db.Column(db.String(64), nullable=False)

    # Optional BD-typed label for the line (e.g. "Master bedroom partition").
    label = db.Column(db.String(200), nullable=True)

    # Swatch picks per axis. JSON dict {axisKey: valueSlug} (matches
    # glassyplatform's selection shape). BD edits via the revise form —
    # values are free-form text since the axis catalog is
    # category-dependent and lives on glassyplatform.
    selections = db.Column(db.Text, nullable=True)

    # Dimension shape at commit time.
    dimension_kind = db.Column(db.String(16), nullable=True)  # 'square_feet' | 'running_feet' | ...
    dimension_unit = db.Column(db.String(4), nullable=True)   # 'ft' | 'in' (only meaningful for panels)

    # Total chargeable area — sqft for square_feet, ft for running_feet.
    # For panelsMode items this is Σ(panel W × panel H × panel qty).
    running_ft = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    quantity = db.Column(db.Numeric(10, 2), default=1, nullable=False)

    # Per-panel (+ per-door) breakdown as JSON array:
    #   [{ widthFt: 4, heightFt: 6, qty: 2, kind: 'panel'|'door' }, …]
    # None → single-row item (running_ft × quantity is the entire spec).
    panels = db.Column(db.Text, nullable=True)

    # Category-specific extras.
    fabric_code = db.Column(db.String(32), nullable=True)
    # Full data URL (base64) as sent from the client. Persisted so BD can
    # eyeball the customer's requested artwork; PDF regen embeds it.
    uploaded_image_data_url = db.Column(db.Text, nullable=True)

    # Money — BD-editable via revise.
    rate_per_unit = db.Column(db.Numeric(12, 2), default=0, nullable=False)  # ₹/sqft or ₹/ft
    subtotal = db.Column(db.Numeric(12, 2), default=0, nullable=False)       # ₹, line-level pre-tax
    notes = db.Column(db.Text, nullable=True)                                # BD's private note on this line

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def selections_parsed(self):
        if not self.selections:
            return {}
        try:
            return json.loads(self.selections)
        except Exception:
            return {}

    @property
    def panels_parsed(self):
        if not self.panels:
            return []
        try:
            v = json.loads(self.panels)
            return v if isinstance(v, list) else []
        except Exception:
            return []

    @property
    def is_sqft(self):
        return (self.dimension_kind or '') == 'square_feet'

    def __repr__(self):
        return f'<VetrovaQuoteItem q={self.quote_id} {self.category_slug} {self.subtotal}>'


class VetrovaStatusEvent(db.Model):
    """Audit log of stage transitions on a VetrovaQuote."""
    __tablename__ = 'vetrova_status_events'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('vetrova_quotes.id', ondelete='CASCADE'),
                         nullable=False, index=True)

    from_stage = db.Column(db.String(32), nullable=True)
    to_stage = db.Column(db.String(32), nullable=False)
    note = db.Column(db.Text, nullable=True)

    triggered_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', foreign_keys=[triggered_by])

    def __repr__(self):
        return f'<VetrovaStatusEvent q={self.quote_id} {self.from_stage}->{self.to_stage}>'

