from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, Response
from urllib.parse import urlparse
import csv
import io
import re
import json
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
import os
import pymysql

# Install PyMySQL as MySQLdb for MySQL compatibility
pymysql.install_as_MySQLdb()

from models import db, User, Project, ProjectHistory, TaskTemplate, PromotorTask, DailyUpdate, Product, Quote, QuoteItem, Supplier, GlassType, SupplierPricing, Reminder, PurchaseInvoice
from config import config
from forms import (LoginForm, UserForm, ProjectForm, TaskTemplateForm, 
                   TaskAssignmentForm, TaskUpdateForm, DailyUpdateForm, ProductForm)
from utils.auth import admin_required, manager_or_admin_required
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from utils.task_rollover import rollover_incomplete_tasks, get_current_week_info, get_week_date_range
from utils.s3_upload import S3Uploader
from datetime import datetime, timedelta
from sqlalchemy import text

# Initialize Flask app
app = Flask(__name__)

# Load configuration
env = os.getenv('ENVIRONMENT', 'development')
app.config.from_object(config[env])

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def _run_startup_migrations():
    """Run safe ADD COLUMN migrations on every cold start (idempotent — ignores duplicates)."""
    stmts = [
        "ALTER TABLE leads ADD COLUMN facebook_lead_id VARCHAR(50) NULL",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    pass  # Column already exists
    except Exception:
        pass  # DB not reachable yet (local dev before first request)


with app.app_context():
    _run_startup_migrations()


@app.template_filter('fromjson')
def fromjson_filter(value):
    """Parse a JSON string in Jinja2 templates."""
    try:
        return json.loads(value)
    except Exception:
        return []


@app.template_filter('to_ist')
def to_ist_filter(utc_dt):
    """Convert a UTC datetime to IST (UTC+5:30), returns datetime object."""
    if utc_dt is None:
        return None
    return utc_dt + timedelta(hours=5, minutes=30)


# Lambda-specific: Dispose connections before each request
@app.before_request
def before_request():
    """Ensure fresh database connections for each Lambda invocation"""
    try:
        db.session.execute(text('SELECT 1'))
    except Exception:
        db.session.remove()
        db.engine.dispose()


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 30 per hour")
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        # Try to find user by username or email
        user = User.query.filter(
            (User.username == form.username.data) | (User.email == form.username.data)
        ).first()

        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact an administrator.', 'danger')
                return redirect(url_for('login'))

            login_user(user, remember=form.remember_me.data)
            flash(f'Welcome back, {user.username}!', 'success')

            # Safe redirect — only allow relative paths, never external URLs
            next_page = request.args.get('next')
            if next_page:
                parsed = urlparse(next_page)
                if parsed.scheme or parsed.netloc:
                    next_page = None  # Reject absolute/external URLs
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username/email or password.', 'danger')

    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


# ============================================================================
# MAIN DASHBOARD
# ============================================================================

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard"""
    # Get statistics
    total_projects = Project.query.count()
    active_projects = Project.query.filter_by(status='In Progress').count()
    completed_projects = Project.query.filter_by(status='Completed').count()
    
    # Get current week info
    week_info = get_current_week_info()
    
    # Get tasks for current user
    if current_user.is_admin() or current_user.is_manager_or_admin():
        # Admins and managers see all tasks
        total_tasks = PromotorTask.query.filter_by(
            assigned_week=week_info['week'],
            assigned_year=week_info['year']
        ).count()
        pending_tasks = PromotorTask.query.filter_by(
            assigned_week=week_info['week'],
            assigned_year=week_info['year'],
            status='Pending'
        ).count()
        overdue_tasks = PromotorTask.query.filter_by(
            assigned_week=week_info['week'],
            assigned_year=week_info['year'],
            status='Overdue'
        ).count()
    else:
        # Users see only their tasks
        total_tasks = PromotorTask.query.filter_by(
            promotor_id=current_user.id,
            assigned_week=week_info['week'],
            assigned_year=week_info['year']
        ).count()
        pending_tasks = PromotorTask.query.filter_by(
            promotor_id=current_user.id,
            assigned_week=week_info['week'],
            assigned_year=week_info['year'],
            status='Pending'
        ).count()
        overdue_tasks = PromotorTask.query.filter_by(
            promotor_id=current_user.id,
            assigned_week=week_info['week'],
            assigned_year=week_info['year'],
            status='Overdue'
        ).count()
    
    # Get recent projects
    recent_projects = Project.query.order_by(Project.updated_at.desc()).limit(5).all()
    
    return render_template('dashboard.html',
                         total_projects=total_projects,
                         active_projects=active_projects,
                         completed_projects=completed_projects,
                         total_tasks=total_tasks,
                         pending_tasks=pending_tasks,
                         overdue_tasks=overdue_tasks,
                         recent_projects=recent_projects,
                         week_info=week_info)


# ============================================================================
# PROJECT ROUTES
# ============================================================================

@app.route('/projects')
@login_required
def projects_list():
    """List all projects"""
    status_filter = request.args.get('status', '')
    owner_filter = request.args.get('owner', '')

    query = Project.query

    if status_filter:
        query = query.filter_by(status=status_filter)
    if owner_filter:
        query = query.filter_by(owner_id=int(owner_filter))

    projects = query.order_by(Project.created_at.desc()).all()
    users = User.query.filter_by(is_active=True).all()

    return render_template('projects/list.html', projects=projects, users=users)


@app.route('/projects/<int:id>')
@login_required
def project_view(id):
    """View project details and history"""
    project = Project.query.get_or_404(id)
    return render_template('projects/view.html', project=project)


@app.route('/projects/new', methods=['GET', 'POST'])
@manager_or_admin_required
def project_new():
    """Create new project"""
    form = ProjectForm()

    all_users = User.query.filter_by(is_active=True).all()
    managers_admins = [(u.id, u.username) for u in all_users if u.role in ('Admin', 'Manager')]
    form.owner_id.choices = managers_admins
    form.assigned_to_id.choices = [(0, '— Unassigned —')] + [(u.id, u.username) for u in all_users]

    if form.validate_on_submit():
        assigned = form.assigned_to_id.data if form.assigned_to_id.data else None
        project = Project(
            name=form.name.data,
            owner_id=form.owner_id.data,
            assigned_to_id=assigned,
            start_date=form.start_date.data,
            expected_end_date=form.expected_end_date.data,
            actual_end_date=form.actual_end_date.data,
            status=form.status.data,
            comments=form.comments.data
        )
        db.session.add(project)
        db.session.flush()  # get project.id before commit

        history = ProjectHistory(
            project_id=project.id,
            changed_by_id=current_user.id,
            action='Created',
            changes=None
        )
        db.session.add(history)
        db.session.commit()
        flash(f'Project "{project.name}" created successfully!', 'success')
        return redirect(url_for('projects_list'))

    return render_template('projects/form.html', form=form, title='New Project')


@app.route('/projects/<int:id>/edit', methods=['GET', 'POST'])
@manager_or_admin_required
def project_edit(id):
    """Edit project"""
    project = Project.query.get_or_404(id)
    form = ProjectForm(obj=project)

    all_users = User.query.filter_by(is_active=True).all()
    managers_admins = [(u.id, u.username) for u in all_users if u.role in ('Admin', 'Manager')]
    form.owner_id.choices = managers_admins
    form.assigned_to_id.choices = [(0, '— Unassigned —')] + [(u.id, u.username) for u in all_users]

    if form.validate_on_submit():
        # Build a human-readable diff of what changed
        user_map = {u.id: u.username for u in all_users}
        change_list = []

        def _norm(val):
            """Normalise a value for comparison — treat None and '' as equal."""
            if val is None:
                return ''
            return str(val).strip()

        old_assigned = user_map.get(project.assigned_to_id, '') if project.assigned_to_id else ''
        new_assigned_id = form.assigned_to_id.data if form.assigned_to_id.data else None
        new_assigned = user_map.get(new_assigned_id, '') if new_assigned_id else ''

        checks = [
            ('Name', _norm(project.name), _norm(form.name.data)),
            ('Owner', user_map.get(project.owner_id, ''), user_map.get(form.owner_id.data, '')),
            ('Assigned To', old_assigned, new_assigned),
            ('Status', _norm(project.status), _norm(form.status.data)),
            ('Start Date', _norm(project.start_date), _norm(form.start_date.data)),
            ('Expected End', _norm(project.expected_end_date), _norm(form.expected_end_date.data)),
            ('Actual End', _norm(project.actual_end_date), _norm(form.actual_end_date.data)),
            ('Comments', _norm(project.comments), _norm(form.comments.data)),
        ]
        for field_label, old_val, new_val in checks:
            if old_val != new_val:
                change_list.append({'field': field_label, 'old': old_val or '—', 'new': new_val or '—'})

        project.name = form.name.data
        project.owner_id = form.owner_id.data
        project.assigned_to_id = form.assigned_to_id.data if form.assigned_to_id.data else None
        project.start_date = form.start_date.data
        project.expected_end_date = form.expected_end_date.data
        project.actual_end_date = form.actual_end_date.data
        project.status = form.status.data
        project.comments = form.comments.data
        project.updated_at = datetime.utcnow()

        if change_list:
            history = ProjectHistory(
                project_id=project.id,
                changed_by_id=current_user.id,
                action='Updated',
                changes=json.dumps(change_list)
            )
            db.session.add(history)

        db.session.commit()
        flash(f'Project "{project.name}" updated successfully!', 'success')
        return redirect(url_for('project_view', id=project.id))

    # Pre-select current assigned_to in form
    if project.assigned_to_id:
        form.assigned_to_id.data = project.assigned_to_id
    else:
        form.assigned_to_id.data = 0

    return render_template('projects/form.html', form=form, title='Edit Project', project=project)


@app.route('/projects/<int:id>/comment', methods=['POST'])
@login_required
def project_add_comment(id):
    """Add a comment to a project (saved as a history entry)"""
    project = Project.query.get_or_404(id)
    text = request.form.get('comment', '').strip()
    if text:
        history = ProjectHistory(
            project_id=project.id,
            changed_by_id=current_user.id,
            action='Comment',
            changes=json.dumps([{'field': 'Comments', 'new': text}])
        )
        db.session.add(history)
        db.session.commit()
        flash('Comment added.', 'success')
    return redirect(url_for('project_view', id=id))


@app.route('/projects/<int:id>/delete', methods=['POST'])
@admin_required
def project_delete(id):
    """Delete project"""
    project = Project.query.get_or_404(id)
    project_name = project.name
    db.session.delete(project)
    db.session.commit()
    flash(f'Project "{project_name}" deleted successfully!', 'success')
    return redirect(url_for('projects_list'))


# ============================================================================
# TASK TEMPLATE ROUTES (Admin Only)
# ============================================================================

@app.route('/task-templates')
@admin_required
def task_templates_list():
    """List all task templates"""
    templates = TaskTemplate.query.order_by(TaskTemplate.created_at.desc()).all()
    return render_template('tasks/templates.html', templates=templates)


@app.route('/task-templates/new', methods=['GET', 'POST'])
@admin_required
def task_template_new():
    """Create new task template"""
    form = TaskTemplateForm()
    
    if form.validate_on_submit():
        template = TaskTemplate(
            name=form.name.data,
            description=form.description.data,
            category=form.category.data,
            priority=form.priority.data,
            is_active=form.is_active.data,
            created_by=current_user.id
        )
        db.session.add(template)
        db.session.commit()
        flash(f'Task template "{template.name}" created successfully!', 'success')
        return redirect(url_for('task_templates_list'))
    
    return render_template('tasks/template_form.html', form=form, title='New Task Template')


@app.route('/task-templates/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def task_template_edit(id):
    """Edit task template"""
    template = TaskTemplate.query.get_or_404(id)
    form = TaskTemplateForm(obj=template)
    
    if form.validate_on_submit():
        template.name = form.name.data
        template.description = form.description.data
        template.category = form.category.data
        template.priority = form.priority.data
        template.is_active = form.is_active.data
        template.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Task template "{template.name}" updated successfully!', 'success')
        return redirect(url_for('task_templates_list'))
    
    return render_template('tasks/template_form.html', form=form, title='Edit Task Template', template=template)


@app.route('/task-templates/<int:id>/delete', methods=['POST'])
@admin_required
def task_template_delete(id):
    """Delete task template"""
    template = TaskTemplate.query.get_or_404(id)
    template_name = template.name
    db.session.delete(template)
    db.session.commit()
    flash(f'Task template "{template_name}" deleted successfully!', 'success')
    return redirect(url_for('task_templates_list'))


# ============================================================================
# PROMOTOR TASK ROUTES
# ============================================================================

@app.route('/tasks/weekly')
@login_required
def tasks_weekly():
    """Weekly task board"""
    # Get week parameter or use current week
    week = request.args.get('week', type=int)
    year = request.args.get('year', type=int)
    
    if not week or not year:
        week_info = get_current_week_info()
        week = week_info['week']
        year = week_info['year']
    
    # Get date range for the week
    date_range = get_week_date_range(week, year)
    
    # Get tasks for the week
    if current_user.is_admin() or current_user.is_manager_or_admin():
        # Admins and managers see all tasks
        tasks = PromotorTask.query.filter_by(
            assigned_week=week,
            assigned_year=year
        ).order_by(PromotorTask.status, PromotorTask.priority).all()
    else:
        # Users see only their tasks
        tasks = PromotorTask.query.filter_by(
            promotor_id=current_user.id,
            assigned_week=week,
            assigned_year=year
        ).order_by(PromotorTask.status, PromotorTask.priority).all()
    
    # Group tasks by status
    tasks_by_status = {
        'Pending': [],
        'In Progress': [],
        'Completed': [],
        'Overdue': []
    }
    
    for task in tasks:
        tasks_by_status[task.status].append(task)
    
    return render_template('tasks/weekly_board.html',
                         tasks_by_status=tasks_by_status,
                         week=week,
                         year=year,
                         date_range=date_range)


@app.route('/tasks/assign', methods=['GET', 'POST'])
@login_required
def task_assign():
    """Assign task to promotor"""
    form = TaskAssignmentForm()
    
    # Populate dropdowns
    form.template_id.choices = [(t.id, t.name) for t in TaskTemplate.query.filter_by(is_active=True).all()]
    
    # Restrict user dropdown based on role
    if current_user.is_manager_or_admin():
        # Managers and admins can assign to anyone
        form.promotor_id.choices = [(u.id, u.username) for u in User.query.filter_by(is_active=True).all()]
    else:
        # Regular users can only assign to themselves
        form.promotor_id.choices = [(current_user.id, current_user.username)]
    
    form.project_id.choices = [(0, '-- None --')] + [(p.id, p.name) for p in Project.query.filter(Project.status.in_(['Not Started', 'In Progress'])).all()]
    
    if form.validate_on_submit():
        # Get current week info
        week_info = get_current_week_info()
        
        # Create task
        task = PromotorTask(
            template_id=form.template_id.data,
            task_name=form.task_name.data if form.task_name.data else None,
            promotor_id=form.promotor_id.data,
            project_id=form.project_id.data if form.project_id.data != 0 else None,
            assigned_week=week_info['week'],
            assigned_year=week_info['year'],
            original_week=week_info['week'],
            original_year=week_info['year'],
            due_date=form.due_date.data,
            priority=form.priority.data,
            comments=form.comments.data,
            created_by=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        flash('Task assigned successfully!', 'success')
        return redirect(url_for('tasks_weekly'))
    
    return render_template('tasks/assign.html', form=form)


@app.route('/tasks/<int:id>/update', methods=['GET', 'POST'])
@login_required
def task_update(id):
    """Update task status"""
    task = PromotorTask.query.get_or_404(id)
    
    # Check permissions
    if not (current_user.is_admin() or current_user.is_manager_or_admin() or task.promotor_id == current_user.id):
        flash('You do not have permission to update this task.', 'danger')
        return redirect(url_for('tasks_weekly'))
    
    form = TaskUpdateForm(obj=task)
    
    if form.validate_on_submit():
        task.status = form.status.data
        task.comments = form.comments.data
        
        # Set completed date if status is Completed
        if form.status.data == 'Completed' and not task.completed_date:
            task.completed_date = datetime.utcnow()
        elif form.status.data != 'Completed':
            task.completed_date = None
        
        task.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Task updated successfully!', 'success')
        return redirect(url_for('tasks_weekly'))
    
    return render_template('tasks/update.html', form=form, task=task)


# ============================================================================
# USER MANAGEMENT ROUTES (Admin Only)
# ============================================================================

@app.route('/users')
@admin_required
def users_list():
    """List all users"""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('users/list.html', users=users)


@app.route('/users/new', methods=['GET', 'POST'])
@admin_required
def user_new():
    """Create new user"""
    form = UserForm()
    
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            role=form.role.data,
            is_active=form.is_active.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(f'User "{user.username}" created successfully!', 'success')
        return redirect(url_for('users_list'))
    
    return render_template('users/form.html', form=form, title='New User')


@app.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def user_edit(id):
    """Edit user"""
    user = User.query.get_or_404(id)
    form = UserForm(user_id=user.id, obj=user)
    
    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data
        user.is_active = form.is_active.data
        
        # Only update password if provided
        if form.password.data:
            user.set_password(form.password.data)
        
        user.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f'User "{user.username}" updated successfully!', 'success')
        return redirect(url_for('users_list'))
    
    return render_template('users/form.html', form=form, title='Edit User', user=user)


@app.route('/users/<int:id>/delete', methods=['POST'])
@admin_required
def user_delete(id):
    """Delete user"""
    user = User.query.get_or_404(id)
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        flash('You cannot delete your own account!', 'danger')
        return redirect(url_for('users_list'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{username}" deleted successfully!', 'success')
    return redirect(url_for('users_list'))


# ============================================================================
# DAILY UPDATE ROUTES
# ============================================================================

@app.route('/daily-updates')
@login_required
def daily_updates_list():
    """List all daily updates with filtering"""
    from datetime import date, timedelta
    from sqlalchemy import and_, or_
    
    # Get filter parameters
    date_filter = request.args.get('date', '')
    user_filter = request.args.get('user', '')
    project_filter = request.args.get('project', '')
    
    # Default to today if no date specified
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
        except ValueError:
            filter_date = date.today()
    else:
        filter_date = date.today()
    
    # Build query
    query = DailyUpdate.query.filter_by(update_date=filter_date)
    
    if user_filter:
        query = query.filter_by(user_id=int(user_filter))
    
    if project_filter:
        if project_filter == 'general':
            query = query.filter_by(is_general=True)
        else:
            query = query.filter_by(project_id=int(project_filter))
    
    # Order by created time (most recent first)
    updates = query.order_by(DailyUpdate.created_at.desc()).all()
    
    # Get all users and projects for filter dropdowns
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    projects = Project.query.filter(Project.status.in_(['Not Started', 'In Progress'])).order_by(Project.name).all()
    
    return render_template('daily_updates/list.html',
                         updates=updates,
                         users=users,
                         projects=projects,
                         filter_date=filter_date,
                         selected_user=user_filter,
                         selected_project=project_filter)


@app.route('/daily-updates/new', methods=['GET', 'POST'])
@login_required
def daily_update_new():
    """Create new daily update"""
    from datetime import date
    
    form = DailyUpdateForm()
    
    # Populate project choices - only projects user is involved with or all for managers/admins
    if current_user.is_manager_or_admin():
        # Managers and admins can update any project
        projects = Project.query.filter(Project.status.in_(['Not Started', 'In Progress'])).order_by(Project.name).all()
    else:
        # Regular users can update projects they're assigned tasks on
        user_project_ids = db.session.query(PromotorTask.project_id).filter(
            PromotorTask.promotor_id == current_user.id,
            PromotorTask.project_id.isnot(None)
        ).distinct().all()
        user_project_ids = [pid[0] for pid in user_project_ids]
        projects = Project.query.filter(Project.id.in_(user_project_ids)).order_by(Project.name).all()
    
    form.project_id.choices = [(0, '-- Select Project --')] + [(p.id, p.name) for p in projects]
    
    if form.validate_on_submit():
        # Check if update already exists for this user/project/date
        today = date.today()
        existing_update = DailyUpdate.query.filter_by(
            user_id=current_user.id,
            project_id=form.project_id.data if not form.is_general.data else None,
            update_date=today,
            is_general=form.is_general.data
        ).first()
        
        if existing_update:
            flash('You have already submitted an update for this project today. Please edit the existing update instead.', 'warning')
            return redirect(url_for('daily_update_edit', id=existing_update.id))
        
        # Create new update
        update = DailyUpdate(
            user_id=current_user.id,
            project_id=form.project_id.data if not form.is_general.data else None,
            update_date=today,
            update_text=form.update_text.data,
            is_general=form.is_general.data
        )
        db.session.add(update)
        db.session.commit()
        flash('Daily update submitted successfully!', 'success')
        return redirect(url_for('daily_updates_list'))
    
    return render_template('daily_updates/form.html', form=form, title='New Daily Update')


@app.route('/daily-updates/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def daily_update_edit(id):
    """Edit existing daily update"""
    update = DailyUpdate.query.get_or_404(id)
    
    # Check permissions
    if not update.can_edit(current_user):
        flash('You can only edit your own updates from today.', 'danger')
        return redirect(url_for('daily_updates_list'))
    
    form = DailyUpdateForm(obj=update)
    
    # Populate project choices
    if current_user.is_manager_or_admin():
        projects = Project.query.filter(Project.status.in_(['Not Started', 'In Progress'])).order_by(Project.name).all()
    else:
        user_project_ids = db.session.query(PromotorTask.project_id).filter(
            PromotorTask.promotor_id == current_user.id,
            PromotorTask.project_id.isnot(None)
        ).distinct().all()
        user_project_ids = [pid[0] for pid in user_project_ids]
        projects = Project.query.filter(Project.id.in_(user_project_ids)).order_by(Project.name).all()
    
    form.project_id.choices = [(0, '-- Select Project --')] + [(p.id, p.name) for p in projects]
    
    if form.validate_on_submit():
        update.project_id = form.project_id.data if not form.is_general.data else None
        update.update_text = form.update_text.data
        update.is_general = form.is_general.data
        update.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Daily update updated successfully!', 'success')
        return redirect(url_for('daily_updates_list'))
    
    return render_template('daily_updates/form.html', form=form, title='Edit Daily Update', update=update)


@app.route('/daily-updates/<int:id>/delete', methods=['POST'])
@login_required
def daily_update_delete(id):
    """Delete daily update"""
    update = DailyUpdate.query.get_or_404(id)
    
    # Check permissions
    if not update.can_delete(current_user):
        flash('You can only delete your own updates.', 'danger')
        return redirect(url_for('daily_updates_list'))
    
    db.session.delete(update)
    db.session.commit()
    flash('Daily update deleted successfully!', 'success')
    return redirect(url_for('daily_updates_list'))


# ============================================================================
# PRODUCT CATALOG ROUTES
# ============================================================================

@app.route('/catalog')
def catalog_list():
    """Product catalog list with filtering"""
    # Get filter parameters
    category_filter = request.args.get('category', '')
    search_query = request.args.get('search', '')
    
    # Build query
    query = Product.query.filter_by(is_active=True)
    
    if category_filter:
        query = query.filter_by(category=category_filter)
    
    if search_query:
        query = query.filter(Product.product_name.ilike(f'%{search_query}%'))
    
    # Get products
    products = query.order_by(Product.category, Product.product_name).all()
    
    # Get filter options
    categories = [cat[0] for cat in Product.get_categories()]
    
    return render_template('catalog/list.html',
                         products=products,
                         categories=categories,
                         selected_category=category_filter,
                         search_query=search_query)


@app.route('/catalog/<int:id>')
def catalog_detail(id):
    """Product detail view with previous/next navigation"""
    product = Product.query.get_or_404(id)
    
    # Get all active products ordered by category and name
    all_products = Product.query.filter_by(is_active=True).order_by(
        Product.category, Product.product_name
    ).all()
    
    # Find current product index
    current_index = next((i for i, p in enumerate(all_products) if p.id == id), None)
    
    # Get previous and next products
    prev_product = all_products[current_index - 1] if current_index and current_index > 0 else None
    next_product = all_products[current_index + 1] if current_index is not None and current_index < len(all_products) - 1 else None
    
    return render_template('catalog/detail.html', 
                         product=product,
                         prev_product=prev_product,
                         next_product=next_product)


@app.route('/catalog/new', methods=['GET', 'POST'])
@manager_or_admin_required
def catalog_new():
    """Create new product"""
    form = ProductForm()
    
    if form.validate_on_submit():
        # Initialize S3 uploader
        s3_uploader = S3Uploader()
        
        product = Product(
            category=form.category.data,
            product_name=form.product_name.data,
            product_url=form.product_url.data,
            price=form.price.data,
            image_1_url=form.image_1_url.data,
            image_2_url=form.image_2_url.data,
            image_3_url=form.image_3_url.data,
            image_4_url=form.image_4_url.data,
            availability=form.availability.data,
            description=form.description.data,
            material=form.material.data,
            brand=form.brand.data,
            usage_application=form.usage_application.data,
            thickness=form.thickness.data,
            shape=form.shape.data,
            pattern=form.pattern.data,
            is_active=form.is_active.data
        )
        
        # Handle file uploads to S3
        for i in range(1, 5):
            file_field = getattr(form, f'image_{i}_file')
            if file_field.data:
                url = s3_uploader.upload_product_image(
                    file_field.data,
                    form.category.data,
                    form.product_name.data,
                    i
                )
                if url:
                    setattr(product, f'image_{i}_url', url)
                    flash(f'Image {i} uploaded successfully!', 'success')
                else:
                    flash(f'Failed to upload image {i}', 'warning')
        
        db.session.add(product)
        db.session.commit()
        flash(f'Product "{product.product_name}" created successfully!', 'success')
        return redirect(url_for('catalog_list'))
    
    return render_template('catalog/form.html', form=form, title='New Product')


@app.route('/catalog/<int:id>/edit', methods=['GET', 'POST'])
@manager_or_admin_required
def catalog_edit(id):
    """Edit product"""
    product = Product.query.get_or_404(id)
    form = ProductForm(obj=product)
    
    if form.validate_on_submit():
        # Initialize S3 uploader
        s3_uploader = S3Uploader()
        
        product.category = form.category.data
        product.product_name = form.product_name.data
        product.product_url = form.product_url.data
        product.price = form.price.data
        product.image_1_url = form.image_1_url.data
        product.image_2_url = form.image_2_url.data
        product.image_3_url = form.image_3_url.data
        product.image_4_url = form.image_4_url.data
        product.availability = form.availability.data
        product.description = form.description.data
        product.material = form.material.data
        product.brand = form.brand.data
        product.usage_application = form.usage_application.data
        product.thickness = form.thickness.data
        product.shape = form.shape.data
        product.pattern = form.pattern.data
        product.is_active = form.is_active.data
        product.updated_at = datetime.utcnow()
        
        # Handle file uploads to S3 (replace existing images)
        for i in range(1, 5):
            file_field = getattr(form, f'image_{i}_file')
            if file_field.data:
                url = s3_uploader.upload_product_image(
                    file_field.data,
                    form.category.data,
                    form.product_name.data,
                    i
                )
                if url:
                    setattr(product, f'image_{i}_url', url)
                    flash(f'Image {i} uploaded and replaced!', 'success')
                else:
                    flash(f'Failed to upload image {i}', 'warning')
        
        db.session.commit()
        flash(f'Product "{product.product_name}" updated successfully!', 'success')
        return redirect(url_for('catalog_detail', id=product.id))
    
    return render_template('catalog/form.html', form=form, title='Edit Product', product=product)


@app.route('/catalog/<int:id>/delete', methods=['POST'])
@admin_required
def catalog_delete(id):
    """Delete product"""
    product = Product.query.get_or_404(id)
    product_name = product.product_name
    db.session.delete(product)
    db.session.commit()
    flash(f'Product "{product_name}" deleted successfully!', 'success')
    return redirect(url_for('catalog_list'))


@app.route('/catalog/export-csv')
@manager_or_admin_required
def catalog_export_csv():
    """Export all active products as a UTF-8 CSV download"""
    from datetime import date

    products = Product.query.filter_by(is_active=True).order_by(
        Product.category, Product.product_name
    ).all()

    headers = [
        'product_name', 'category', 'description', 'price', 'price_unit',
        'min_order_qty', 'unit', 'size', 'thickness', 'color', 'finish',
        'design', 'product_type',
        'photo_url_1', 'photo_url_2', 'photo_url_3', 'photo_url_4',
        'tags'
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()

    for p in products:
        specs = p.get_specifications()  # dict from JSON specifications column

        # Split stored price string (e.g. "160/sqft" or "24,999/Unit") into
        # numeric price and price_unit.
        price_val = ''
        price_unit_val = ''
        if p.price:
            m = re.match(r'^([\d,\.]+)\s*[/]?\s*(.*)', p.price.strip())
            if m:
                price_val = m.group(1).replace(',', '')
                price_unit_val = m.group(2).strip()

        def spec(*keys):
            """Return first non-empty value from specs dict for given key variants."""
            for k in keys:
                v = specs.get(k)
                if v:
                    return str(v)
            return ''

        writer.writerow({
            'product_name':  p.product_name or '',
            'category':      p.category or '',
            'description':   p.description or '',
            'price':         price_val,
            'price_unit':    spec('price_unit', 'Price Unit', 'unit_label') or price_unit_val,
            'min_order_qty': spec('min_order_qty', 'Min Order Qty', 'minimum_order_quantity', 'MOQ'),
            'unit':          spec('unit', 'Unit', 'unit_of_measurement'),
            'size':          spec('size', 'Size', 'Dimensions', 'dimensions'),
            'thickness':     p.thickness or spec('thickness', 'Thickness'),
            'color':         spec('color', 'Color', 'Colour', 'colour', 'shade', 'Shade'),
            'finish':        spec('finish', 'Finish', 'surface_finish', 'Surface Finish'),
            'design':        p.pattern or spec('design', 'Design', 'pattern', 'Pattern'),
            'product_type':  spec('product_type', 'Product Type', 'type', 'Type', 'sub_type'),
            'photo_url_1':   p.image_1_url or '',
            'photo_url_2':   p.image_2_url or '',
            'photo_url_3':   p.image_3_url or '',
            'photo_url_4':   p.image_4_url or '',
            'tags':          spec('tags', 'Tags', 'keywords', 'Keywords'),
        })

    filename = f"catalog_export_{date.today().isoformat()}.csv"
    output.seek(0)
    # utf-8-sig adds the BOM so Excel opens the file without garbled characters
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@app.route('/catalog/<int:id>/upload-image/<int:image_num>', methods=['POST'])
@manager_or_admin_required
def catalog_upload_image(id, image_num):
    """Upload/replace a single product image via AJAX"""
    try:
        product = Product.query.get_or_404(id)
        
        # Validate image number
        if image_num < 1 or image_num > 4:
            return jsonify({'success': False, 'error': 'Invalid image number'}), 400
        
        # Check if file was uploaded
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Initialize S3 uploader
        s3_uploader = S3Uploader()
        
        # Upload to S3
        url = s3_uploader.upload_product_image(
            file,
            product.category,
            product.product_name,
            image_num
        )
        
        if url:
            # Update product image URL
            setattr(product, f'image_{image_num}_url', url)
            product.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'url': url,
                'message': f'Image {image_num} uploaded successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to upload to S3'}), 500
            
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================================================
# BOM CALCULATOR ROUTES
# ============================================================================

@app.route('/bom')
@login_required
def bom_list():
    """BOM calculator list with product search"""
    search_query = request.args.get('search', '')
    
    # For now, show DGU/Insulated glass products
    products = Product.query.filter(
        Product.is_active == True
    ).filter(
        (Product.category.ilike('%insulated%')) | 
        (Product.category.ilike('%dgu%')) |
        (Product.product_name.ilike('%double glazing%'))
    ).order_by(Product.product_name).all()
    
    if search_query:
        products = [p for p in products if search_query.lower() in p.product_name.lower()]
    
    return render_template('bom/list.html', products=products, search_query=search_query)


@app.route('/bom/dgu-calculator')
@login_required
def bom_dgu_calculator():
    """DGU Glass BOM Calculator"""
    return render_template('bom/dgu_calculator.html')


# ============================================================================
# ADMIN ROLLOVER ROUTE
# ============================================================================

@app.route('/admin/rollover-tasks', methods=['POST'])
@admin_required
def admin_rollover_tasks():
    """Manually trigger task rollover"""
    try:
        result = rollover_incomplete_tasks()
        flash(f'Successfully rolled over {result["count"]} tasks to week {result["current_week"]}/{result["current_year"]}.', 'success')
    except Exception as e:
        flash(f'Error during rollover: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard'))


# ============================================================================
# HEALTH CHECK & INFO ROUTES
# ============================================================================

@app.route('/health')
def health_check():
    """Health check endpoint for AWS"""
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'service': 'vcore-api'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }), 500


# ============================================================================
# WORDPRESS SYNC ROUTES (Admin Only)
# ============================================================================

@app.route('/admin/wordpress-sync')
@admin_required
def wordpress_sync_page():
    """WordPress sync admin page"""
    from utils.wordpress_sync import WordPressSync
    
    wp_sync = WordPressSync()
    stats = wp_sync.get_sync_status(db.session)
    
    return render_template('admin/wordpress_sync.html', stats=stats)


@app.route('/api/wordpress/test-connection', methods=['POST'])
@admin_required
def wordpress_test_connection():
    """Test WordPress API connection"""
    from utils.wordpress_sync import WordPressSync
    
    wp_sync = WordPressSync()
    result = wp_sync.test_connection()
    
    return jsonify(result)


@app.route('/api/wordpress/create-categories', methods=['POST'])
@admin_required
def wordpress_create_categories():
    """Create category structure in WordPress"""
    from utils.wordpress_sync import WordPressSync
    
    wp_sync = WordPressSync()
    result = wp_sync.create_categories()
    
    return jsonify(result)


@app.route('/api/wordpress/sync-all', methods=['POST'])
@admin_required
def wordpress_sync_all():
    """Sync all products to WordPress"""
    from utils.wordpress_sync import WordPressSync
    
    # Check if incremental sync is requested (default: True)
    data = request.get_json() or {}
    incremental = data.get('incremental', True)
    
    wp_sync = WordPressSync()
    result = wp_sync.sync_all_products(db.session, incremental=incremental)
    
    return jsonify(result)


@app.route('/api/wordpress/changed-products', methods=['GET'])
@admin_required
def wordpress_changed_products():
    """Get list of products that have changed since last sync"""
    from models import Product
    
    # Get products that need syncing
    changed_products = Product.query.filter(
        Product.is_active == True,
        (Product.last_wordpress_sync == None) | 
        (Product.updated_at > Product.last_wordpress_sync)
    ).all()
    
    products_list = [{
        'id': p.id,
        'name': p.product_name,
        'category': p.category,
        'updated_at': p.updated_at.isoformat() if p.updated_at else None,
        'last_sync': p.last_wordpress_sync.isoformat() if p.last_wordpress_sync else 'Never synced'
    } for p in changed_products]
    
    return jsonify({
        'success': True,
        'count': len(products_list),
        'products': products_list
    })


@app.route('/api/wordpress/sync-product/<int:product_id>', methods=['POST'])
@admin_required
def wordpress_sync_product(product_id):
    """Sync single product to WordPress"""
    from utils.wordpress_sync import WordPressSync
    
    product = Product.query.get_or_404(product_id)
    wp_sync = WordPressSync()
    result = wp_sync.sync_single_product(product)
    
    if result.get('success'):
        db.session.commit()
    
    return jsonify(result)


@app.route('/api/wordpress/sync-batch', methods=['POST'])
@admin_required
def wordpress_sync_batch():
    """Sync a batch of products to WordPress (client-side batching)"""
    from utils.wordpress_sync import WordPressSync
    from models import Product
    
    # Get batch size from request (default: 10)
    data = request.get_json() or {}
    batch_size = data.get('batch_size', 10)
    
    # Get products that need syncing
    products = Product.query.filter(
        Product.is_active == True,
        (Product.last_wordpress_sync == None) | 
        (Product.updated_at > Product.last_wordpress_sync)
    ).limit(batch_size).all()
    
    if not products:
        return jsonify({
            'success': True,
            'message': 'All products are up to date!',
            'synced': 0,
            'remaining': 0,
            'total_pending': 0
        })
    
    # Get total pending count
    total_pending = Product.query.filter(
        Product.is_active == True,
        (Product.last_wordpress_sync == None) | 
        (Product.updated_at > Product.last_wordpress_sync)
    ).count()
    
    # Sync this batch
    wp_sync = WordPressSync()
    synced = 0
    failed = 0
    errors = []
    
    for product in products:
        result = wp_sync.sync_single_product(product)
        if result.get('success'):
            synced += 1
            db.session.commit()
        else:
            failed += 1
            errors.append({
                'product_name': product.product_name,
                'error': result.get('message', 'Unknown error')
            })
    
    remaining = total_pending - synced
    
    return jsonify({
        'success': True,
        'synced': synced,
        'failed': failed,
        'batch_size': len(products),
        'remaining': remaining,
        'total_pending': total_pending,
        'errors': errors,
        'message': f'Synced {synced} of {len(products)} products in this batch'
    })


# ============================================================================
# QUOTE MANAGEMENT ROUTES
# ============================================================================

@app.route('/quotes')
@login_required
def quotes_list():
    """List all quotes with search and filter"""
    from datetime import datetime
    
    # Get filter parameters
    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    quote_type_filter = request.args.get('quote_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Import Quote model
    from models import Quote
    
    # Build query
    query = Quote.query
    
    if search_query:
        query = query.filter(
            (Quote.customer_name.ilike(f'%{search_query}%')) |
            (Quote.quote_number.ilike(f'%{search_query}%'))
        )
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    if quote_type_filter:
        query = query.filter_by(quote_type=quote_type_filter)
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(Quote.quote_date >= from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(Quote.quote_date <= to_date)
        except ValueError:
            pass
    
    # Get quotes ordered by date then by ID (newest first)
    quotes = query.order_by(Quote.quote_date.desc(), Quote.id.desc()).all()
    
    return render_template('quotes/list.html',
                         quotes=quotes,
                         search_query=search_query,
                         status_filter=status_filter,
                         quote_type_filter=quote_type_filter,
                         date_from=date_from,
                         date_to=date_to)


@app.route('/quotes/new', methods=['GET', 'POST'])
@login_required
def quote_new():
    """Create new quote with hierarchical items"""
    from models import Quote, QuoteItem
    from datetime import date, timedelta
    
    if request.method == 'POST':
        try:
            # Get form data
            data = request.form
            
            # Generate quote number
            quote_number = Quote.generate_quote_number()
            
            # Parse dates
            quote_date = datetime.strptime(data.get('quote_date'), '%Y-%m-%d').date()
            expected_date = datetime.strptime(data.get('expected_date'), '%Y-%m-%d').date() if data.get('expected_date') else None
            
            # Create quote
            quote = Quote(
                quote_number=quote_number,
                quote_date=quote_date,
                expected_date=expected_date,
                customer_name=data.get('customer_name'),
                customer_address=data.get('customer_address'),
                customer_city=data.get('customer_city'),
                customer_state=data.get('customer_state'),
                customer_phone=data.get('customer_phone'),
                customer_email=data.get('customer_email'),
                customer_gst=data.get('customer_gst'),
                invoice_to=data.get('invoice_to'),
                dispatch_to=data.get('dispatch_to'),
                self_pickup=bool(data.get('self_pickup')),
                delivery_charges=float(data.get('delivery_charges') or 0),
                installation_charges=float(data.get('installation_charges') or 0),
                freight_charges=float(data.get('freight_charges') or 0),
                transport_charges=float(data.get('transport_charges') or 0),
                cutout_charges=float(data.get('cutout_charges') or 0),
                holes_charges=float(data.get('holes_charges') or 0),
                shape_cutting_charges=float(data.get('shape_cutting_charges') or 0),
                jumbo_size_charges=float(data.get('jumbo_size_charges') or 0),
                template_charges=float(data.get('template_charges') or 0),
                handling_percentage=float(data.get('handling_percentage') or 0),
                handling_charges=float(data.get('handling_charges') or 0),
                polish_charges=float(data.get('polish_charges') or 0),
                document_charges=float(data.get('document_charges') or 0),
                frosted_charges=float(data.get('frosted_charges') or 0),
                insurance_percentage=float(data.get('insurance_percentage') or 0),
                insurance_charges=float(data.get('insurance_charges') or 0),
                gst_percentage=float(data.get('gst_percentage') or 18),
                jumbo_pct_tier1=float(data.get('jumbo_pct_tier1') or 10),
                jumbo_pct_tier2=float(data.get('jumbo_pct_tier2') or 15),
                jumbo_pct_tier3=float(data.get('jumbo_pct_tier3') or 20),
                payment_terms=data.get('payment_terms'),
                status=data.get('status', 'Draft'),
                quote_type=data.get('quote_type', 'B2B'),
                created_by=current_user.id
            )
            
            db.session.add(quote)
            db.session.flush()  # Get quote ID

            # Save/update client record for autocomplete
            _upsert_client(data)

            # Process items - they come as items[0][field], items[1][field], etc.
            items_data = {}
            for key in data.keys():
                if key.startswith('items['):
                    # Parse items[0][particular] -> index=0, field=particular
                    import re
                    match = re.match(r'items\[(\d+)\]\[(\w+)\]', key)
                    if match:
                        index = int(match.group(1))
                        field = match.group(2)
                        if index not in items_data:
                            items_data[index] = {}
                        items_data[index][field] = data.get(key)
            
            # Create items in order, tracking parent IDs
            parent_id_map = {}  # Maps form item index to database ID
            index_to_group_id = {}  # Maps form index to group identifier (e.g., "group-1")
            
            for index in sorted(items_data.keys()):
                item_data = items_data[index]
                particular = item_data.get('particular', '')
                is_group = item_data.get('is_group') == 'true'
                
                # Skip only if it's a group without a particular (groups must have a name)
                if is_group and not particular:
                    continue
                
                parent_id_str = item_data.get('parent_id')  # This will be like "group-1", "group-2"
                
                # Determine actual parent_id by looking up the group identifier
                actual_parent_id = None
                if parent_id_str:
                    # Find which index created this group
                    for idx, group_id in index_to_group_id.items():
                        if group_id == parent_id_str:
                            actual_parent_id = parent_id_map.get(idx)
                            break
                
                # Create item
                item = QuoteItem(
                    quote_id=quote.id,
                    parent_id=actual_parent_id,
                    is_group=is_group,
                    sort_order=index,
                    item_number=int(item_data.get('item_number') or index + 1),
                    particular=particular,
                    image_s3_key=item_data.get('image_s3_key') or None,
                    actual_width=float(item_data.get('actual_width')) if item_data.get('actual_width') else None,
                    actual_height=float(item_data.get('actual_height')) if item_data.get('actual_height') else None,
                    chargeable_width=float(item_data.get('chargeable_width')) if item_data.get('chargeable_width') else None,
                    chargeable_height=float(item_data.get('chargeable_height')) if item_data.get('chargeable_height') else None,
                    unit=item_data.get('unit', 'MM'),
                    chargeable_extra=int(item_data.get('chargeable_extra') or 30),
                    quantity=int(item_data.get('quantity') or 1) if not is_group else 1,
                    rate_sqper=float(item_data.get('rate_sqper') or 0),
                    total=float(item_data.get('total') or 0) if not is_group else 0,
                    hole=int(item_data.get('hole') or 0) if not is_group else 0,
                    cutout=int(item_data.get('cutout') or 0) if not is_group else 0,
                    hole_price=float(item_data.get('hole_price') or 0),
                    cutout_price=float(item_data.get('cutout_price') or 0),
                )

                # Calculate unit square if dimensions provided
                if item.chargeable_width and item.chargeable_height:
                    item.calculate_unit_square()

                # Do NOT call item.calculate_total() here — the JS frontend
                # already calculates the correct total (including hole/cutout
                # charges). Calling it server-side would overwrite the
                # submitted value with an incorrect one because self.parent
                # is not accessible before the item is added to the session.

                db.session.add(item)
                db.session.flush()  # Get item ID

                # Store mapping: form index -> database ID
                parent_id_map[index] = item.id

                # If this is a group, also store its group identifier
                if is_group:
                    index_to_group_id[index] = f"group-{item.item_number}"

            # Calculate quote totals
            quote.subtotal = float(data.get('subtotal') or 0)
            quote.gst_amount = float(data.get('gst_amount') or 0)
            quote.round_off = float(data.get('round_off') or 0)
            quote.total = float(data.get('total') or 0)
            
            db.session.commit()
            flash(f'Quote {quote_number} created successfully!', 'success')
            return redirect(url_for('quote_view', id=quote.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating quote: {str(e)}', 'danger')
            return redirect(url_for('quote_new'))
    
    # GET request - show form
    from datetime import date, timedelta
    default_payment_terms = "For Confirmation the order need to give 100% of Quotation Value"
    
    return render_template('quotes/form.html',
                         title='New Quote',
                         quote=None,
                         default_quote_date=date.today(),
                         default_expected_date=date.today() + timedelta(days=8),
                         default_payment_terms=default_payment_terms)


@app.route('/quotes/<int:id>')
@login_required
def quote_view(id):
    """View quote details"""
    from models import Quote, QuoteComment
    quote = Quote.query.get_or_404(id)
    comments = QuoteComment.query.filter_by(quote_id=id).order_by(QuoteComment.created_at.desc()).all()
    return render_template('quotes/view.html', quote=quote, comments=comments)


@app.route('/quotes/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def quote_edit(id):
    """Edit existing quote with hierarchical items"""
    from models import Quote, QuoteItem
    
    quote = Quote.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            data = request.form
            
            # Update quote fields
            quote.quote_date = datetime.strptime(data.get('quote_date'), '%Y-%m-%d').date()
            quote.expected_date = datetime.strptime(data.get('expected_date'), '%Y-%m-%d').date() if data.get('expected_date') else None
            quote.customer_name = data.get('customer_name')
            quote.customer_address = data.get('customer_address')
            quote.customer_city = data.get('customer_city')
            quote.customer_state = data.get('customer_state')
            quote.customer_phone = data.get('customer_phone')
            quote.customer_email = data.get('customer_email')
            quote.customer_gst = data.get('customer_gst')
            quote.invoice_to = data.get('invoice_to')
            quote.dispatch_to = data.get('dispatch_to')
            quote.self_pickup = bool(data.get('self_pickup'))
            quote.delivery_charges = float(data.get('delivery_charges') or 0)
            quote.installation_charges = float(data.get('installation_charges') or 0)
            quote.freight_charges = float(data.get('freight_charges') or 0)
            quote.transport_charges = float(data.get('transport_charges') or 0)
            quote.cutout_charges = float(data.get('cutout_charges') or 0)
            quote.holes_charges = float(data.get('holes_charges') or 0)
            quote.shape_cutting_charges = float(data.get('shape_cutting_charges') or 0)
            quote.jumbo_size_charges = float(data.get('jumbo_size_charges') or 0)
            quote.template_charges = float(data.get('template_charges') or 0)
            quote.handling_percentage = float(data.get('handling_percentage') or 0)
            quote.handling_charges = float(data.get('handling_charges') or 0)
            quote.polish_charges = float(data.get('polish_charges') or 0)
            quote.document_charges = float(data.get('document_charges') or 0)
            quote.frosted_charges = float(data.get('frosted_charges') or 0)
            quote.insurance_percentage = float(data.get('insurance_percentage') or 0)
            quote.insurance_charges = float(data.get('insurance_charges') or 0)
            quote.gst_percentage = float(data.get('gst_percentage') or 18)
            quote.jumbo_pct_tier1 = float(data.get('jumbo_pct_tier1') or 10)
            quote.jumbo_pct_tier2 = float(data.get('jumbo_pct_tier2') or 15)
            quote.jumbo_pct_tier3 = float(data.get('jumbo_pct_tier3') or 20)
            quote.payment_terms = data.get('payment_terms')
            quote.status = data.get('status', 'Draft')
            quote.quote_type = data.get('quote_type', 'B2B')
            
            # Delete existing items (cascade will handle children)
            QuoteItem.query.filter_by(quote_id=quote.id).delete()
            
            # Process items - same logic as quote_new
            items_data = {}
            for key in data.keys():
                if key.startswith('items['):
                    import re
                    match = re.match(r'items\[(\d+)\]\[(\w+)\]', key)
                    if match:
                        index = int(match.group(1))
                        field = match.group(2)
                        if index not in items_data:
                            items_data[index] = {}
                        items_data[index][field] = data.get(key)
            
            # Create items in order, tracking parent IDs
            parent_id_map = {}  # Maps form item index to database ID
            index_to_group_id = {}  # Maps form index to group identifier
            
            for index in sorted(items_data.keys()):
                item_data = items_data[index]
                particular = item_data.get('particular', '')
                is_group = item_data.get('is_group') == 'true'
                
                # Skip only if it's a group without a particular (groups must have a name)
                if is_group and not particular:
                    continue
                parent_id_str = item_data.get('parent_id')
                
                # Determine actual parent_id by looking up the group identifier
                actual_parent_id = None
                if parent_id_str:
                    for idx, group_id in index_to_group_id.items():
                        if group_id == parent_id_str:
                            actual_parent_id = parent_id_map.get(idx)
                            break
                
                # Create item
                item = QuoteItem(
                    quote_id=quote.id,
                    parent_id=actual_parent_id,
                    is_group=is_group,
                    sort_order=index,
                    item_number=int(item_data.get('item_number') or index + 1),
                    particular=particular,
                    image_s3_key=item_data.get('image_s3_key') or None,
                    actual_width=float(item_data.get('actual_width')) if item_data.get('actual_width') else None,
                    actual_height=float(item_data.get('actual_height')) if item_data.get('actual_height') else None,
                    chargeable_width=float(item_data.get('chargeable_width')) if item_data.get('chargeable_width') else None,
                    chargeable_height=float(item_data.get('chargeable_height')) if item_data.get('chargeable_height') else None,
                    unit=item_data.get('unit', 'MM'),
                    chargeable_extra=int(item_data.get('chargeable_extra') or 30),
                    quantity=int(item_data.get('quantity') or 1) if not is_group else 1,
                    rate_sqper=float(item_data.get('rate_sqper') or 0),
                    total=float(item_data.get('total') or 0) if not is_group else 0,
                    hole=int(item_data.get('hole') or 0) if not is_group else 0,
                    cutout=int(item_data.get('cutout') or 0) if not is_group else 0,
                    hole_price=float(item_data.get('hole_price') or 0),
                    cutout_price=float(item_data.get('cutout_price') or 0),
                )

                # Calculate unit square if dimensions provided
                if item.chargeable_width and item.chargeable_height:
                    item.calculate_unit_square()

                # Do NOT call item.calculate_total() here — same reason as
                # quote_new: self.parent is not accessible before add/flush,
                # so hole/cutout charges would be lost.

                db.session.add(item)
                db.session.flush()

                # Store mapping: form index -> database ID
                parent_id_map[index] = item.id

                # If this is a group, also store its group identifier
                if is_group:
                    index_to_group_id[index] = f"group-{item.item_number}"

            # Update quote totals
            quote.subtotal = float(data.get('subtotal') or 0)
            quote.gst_amount = float(data.get('gst_amount') or 0)
            quote.round_off = float(data.get('round_off') or 0)
            quote.total = float(data.get('total') or 0)
            quote.updated_at = datetime.utcnow()

            # Save/update client record for autocomplete
            _upsert_client(data)

            db.session.commit()
            flash(f'Quote {quote.quote_number} updated successfully!', 'success')
            return redirect(url_for('quote_view', id=quote.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating quote: {str(e)}', 'danger')
            return redirect(url_for('quote_edit', id=id))
    
    # GET request - show form with existing data
    return render_template('quotes/form.html',
                         title='Edit Quote',
                         quote=quote)


@app.route('/quotes/<int:id>/delete', methods=['POST'])
@admin_required
def quote_delete(id):
    """Delete quote"""
    from models import Quote
    quote = Quote.query.get_or_404(id)
    quote_number = quote.quote_number
    db.session.delete(quote)
    db.session.commit()
    flash(f'Quote {quote_number} deleted successfully!', 'success')
    return redirect(url_for('quotes_list'))


# ─────────────────────────────────────────────────────────
# CLIENTS
# ─────────────────────────────────────────────────────────

def _upsert_client(data):
    """Create or update a client record from quote form data.
    Matches on name (case-insensitive). Only updates fields that are non-empty."""
    from models import Client
    name = (data.get('customer_name') or '').strip()
    if not name:
        return
    client = Client.query.filter(
        db.func.lower(Client.name) == name.lower()
    ).first()
    if not client:
        client = Client(name=name)
        db.session.add(client)
    # Update only non-empty fields so partial edits don't wipe saved data
    for src, dst in [
        ('customer_phone',   'phone'),
        ('customer_email',   'email'),
        ('customer_address', 'address'),
        ('customer_city',    'city'),
        ('customer_state',   'state'),
        ('customer_gst',     'gst_number'),
        ('dispatch_to',      'dispatch_to'),
    ]:
        val = (data.get(src) or '').strip()
        if val:
            setattr(client, dst, val)
    qt = data.get('quote_type')
    if qt in ('B2B', 'B2C'):
        client.quote_type = qt


@app.route('/api/clients/search')
@login_required
def clients_search():
    """Return up to 10 clients matching the query string (for autocomplete)."""
    from models import Client
    q = (request.args.get('q') or '').strip()
    if len(q) < 1:
        return jsonify([])
    results = Client.query.filter(
        Client.name.ilike(f'%{q}%')
    ).order_by(Client.name).limit(10).all()
    return jsonify([c.to_dict() for c in results])


@app.route('/clients')
@login_required
def clients_list():
    from models import Client
    q = request.args.get('q', '').strip()
    query = Client.query
    if q:
        query = query.filter(Client.name.ilike(f'%{q}%'))
    clients = query.order_by(Client.name).all()
    return render_template('clients/list.html', clients=clients, q=q)


@app.route('/clients/new', methods=['GET', 'POST'])
@login_required
def client_new():
    from models import Client
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Client name is required.', 'danger')
            return redirect(url_for('client_new'))
        client = Client(
            name        = name,
            phone       = request.form.get('phone',       '').strip() or None,
            email       = request.form.get('email',       '').strip() or None,
            address     = request.form.get('address',     '').strip() or None,
            city        = request.form.get('city',        '').strip() or None,
            state       = request.form.get('state',       '').strip() or None,
            gst_number  = request.form.get('gst_number',  '').strip() or None,
            dispatch_to = request.form.get('dispatch_to', '').strip() or None,
            quote_type  = request.form.get('quote_type')  or None,
            notes       = request.form.get('notes',       '').strip() or None,
        )
        db.session.add(client)
        db.session.commit()
        flash(f'Client "{client.name}" saved.', 'success')
        return redirect(url_for('clients_list'))
    return render_template('clients/form.html', client=None)


@app.route('/clients/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def client_edit(id):
    from models import Client
    client = Client.query.get_or_404(id)
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Client name is required.', 'danger')
            return redirect(url_for('client_edit', id=id))
        client.name        = name
        client.phone       = request.form.get('phone',       '').strip() or None
        client.email       = request.form.get('email',       '').strip() or None
        client.address     = request.form.get('address',     '').strip() or None
        client.city        = request.form.get('city',        '').strip() or None
        client.state       = request.form.get('state',       '').strip() or None
        client.gst_number  = request.form.get('gst_number',  '').strip() or None
        client.dispatch_to = request.form.get('dispatch_to', '').strip() or None
        client.quote_type  = request.form.get('quote_type')  or None
        client.notes       = request.form.get('notes',       '').strip() or None
        db.session.commit()
        flash(f'Client "{client.name}" updated.', 'success')
        return redirect(url_for('clients_list'))
    return render_template('clients/form.html', client=client)


@app.route('/clients/<int:id>/delete', methods=['POST'])
@login_required
def client_delete(id):
    from models import Client
    client = Client.query.get_or_404(id)
    name = client.name
    db.session.delete(client)
    db.session.commit()
    flash(f'Client "{name}" deleted.', 'success')
    return redirect(url_for('clients_list'))


# ─────────────────────────────────────────────────────────

@app.route('/quotes/<int:id>/duplicate', methods=['POST'])
@login_required
def quote_duplicate(id):
    """Duplicate an existing quote"""
    from models import Quote, QuoteItem
    from datetime import date
    
    original_quote = Quote.query.get_or_404(id)
    
    # Create new quote with same data
    new_quote = Quote(
        quote_number=Quote.generate_quote_number(),
        quote_date=date.today(),
        expected_date=original_quote.expected_date,
        customer_name=original_quote.customer_name,
        customer_address=original_quote.customer_address,
        customer_city=original_quote.customer_city,
        customer_state=original_quote.customer_state,
        customer_phone=original_quote.customer_phone,
        customer_email=original_quote.customer_email,
        invoice_to=original_quote.invoice_to,
        dispatch_to=original_quote.dispatch_to,
        self_pickup=original_quote.self_pickup,
        delivery_charges=original_quote.delivery_charges,
        installation_charges=original_quote.installation_charges,
        freight_charges=original_quote.freight_charges,
        transport_charges=original_quote.transport_charges,
        insurance_percentage=original_quote.insurance_percentage,
        insurance_charges=original_quote.insurance_charges,
        gst_percentage=original_quote.gst_percentage,
        payment_terms=original_quote.payment_terms,
        status='Draft',
        created_by=current_user.id
    )
    
    db.session.add(new_quote)
    db.session.flush()
    
    # Duplicate items
    for original_item in original_quote.items:
        new_item = QuoteItem(
            quote_id=new_quote.id,
            item_number=original_item.item_number,
            particular=original_item.particular,
            size_width=original_item.size_width,
            size_height=original_item.size_height,
            unit=original_item.unit,
            chargeable_size_width=original_item.chargeable_size_width,
            chargeable_size_height=original_item.chargeable_size_height,
            quantity=original_item.quantity,
            first_sqper=original_item.first_sqper,
            rate_sqper=original_item.rate_sqper,
            total=original_item.total
        )
        db.session.add(new_item)
    
    new_quote.calculate_totals()
    db.session.commit()
    
    flash(f'Quote duplicated as {new_quote.quote_number}!', 'success')
    return redirect(url_for('quote_edit', id=new_quote.id))


@app.route('/quotes/<int:id>/print')
@login_required
def quote_print(id):
    """Show print-friendly version of quote — auto-marks status as Sent"""
    from models import Quote
    quote = Quote.query.get_or_404(id)
    if quote.status == 'Draft':
        quote.status = 'Sent'
        db.session.commit()
    return render_template('quotes/print.html', quote=quote)


@app.route('/quotes/<int:id>/comment', methods=['POST'])
@login_required
def quote_add_comment(id):
    """Add a comment to a quote"""
    from models import Quote, QuoteComment
    quote = Quote.query.get_or_404(id)
    text = request.form.get('comment', '').strip()
    if text:
        comment = QuoteComment(quote_id=quote.id, user_id=current_user.id, comment=text)
        db.session.add(comment)
        db.session.commit()
        flash('Comment added.', 'success')
    return redirect(url_for('quote_view', id=id))


@app.route('/quotes/<int:id>/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def quote_delete_comment(id, comment_id):
    """Delete a comment (own comment or admin)"""
    from models import QuoteComment
    c = QuoteComment.query.get_or_404(comment_id)
    if c.user_id == current_user.id or current_user.is_admin():
        db.session.delete(c)
        db.session.commit()
    return redirect(url_for('quote_view', id=id))


# ============================================================================
# QUOTE API ROUTES
# ============================================================================

@app.route('/api/quotes/next-number')
@login_required
def api_quote_next_number():
    """Get next available quote number"""
    from models import Quote
    next_number = Quote.generate_quote_number()
    return jsonify({'quote_number': next_number})


@app.route('/api/quote-items/upload-image', methods=['POST'])
@login_required
def quote_item_upload_image():
    """AJAX: upload a quote item image to S3, return the s3_key and a short-lived presigned URL."""
    file = request.files.get('image')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    allowed = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in allowed:
        return jsonify({'success': False, 'error': 'Only image files are allowed'}), 400

    try:
        from utils.s3_upload import S3Uploader
        from werkzeug.utils import secure_filename
        from datetime import datetime

        uploader  = S3Uploader()
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S%f')
        filename  = f"{timestamp}_{secure_filename(file.filename)}"
        s3_key    = f"quote-items/{filename}"

        uploader.s3_client.upload_fileobj(
            file, uploader.bucket_name, s3_key,
            ExtraArgs={'ContentType': file.content_type or 'image/jpeg'}
        )

        presigned = uploader.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': uploader.bucket_name, 'Key': s3_key},
            ExpiresIn=3600
        )
        return jsonify({'success': True, 's3_key': s3_key, 'presigned_url': presigned})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.template_filter('item_image_url')
def item_image_url_filter(s3_key):
    """Jinja2 filter: convert an S3 key to a presigned URL at render time."""
    if not s3_key:
        return ''
    try:
        from utils.s3_upload import S3Uploader
        uploader = S3Uploader()
        return uploader.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': uploader.bucket_name, 'Key': s3_key},
            ExpiresIn=3600
        )
    except Exception:
        return ''


@app.route('/api/quote-items/image-url')
@login_required
def quote_item_image_url():
    """Return a fresh presigned URL for a quote item image (used by view page)."""
    s3_key = request.args.get('key', '').strip()
    if not s3_key:
        return jsonify({'error': 'No key'}), 400
    try:
        from utils.s3_upload import S3Uploader
        uploader = S3Uploader()
        url = uploader.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': uploader.bucket_name, 'Key': s3_key},
            ExpiresIn=3600
        )
        return redirect(url)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/products/search')
@login_required
def api_products_search():
    """Search products for quote (autocomplete)"""
    query = request.args.get('q', '')
    
    if len(query) < 2:
        return jsonify([])
    
    products = Product.query.filter(
        Product.is_active == True,
        Product.product_name.ilike(f'%{query}%')
    ).limit(10).all()
    
    results = [{
        'id': p.id,
        'name': p.product_name,
        'category': p.category,
        'price': p.price
    } for p in products]
    
    return jsonify(results)


@app.route('/api/glass-types')
@login_required
def api_glass_types():
    """API endpoint to get glass types with pricing for quote form"""
    glass_types = GlassType.query.filter_by(is_active=True).all()
    
    result = []
    for gt in glass_types:
        suppliers_pricing = []
        for pricing in gt.pricing:
            if pricing.is_active and pricing.is_currently_valid():
                suppliers_pricing.append({
                    'supplier_id': pricing.supplier_id,
                    'supplier_name': pricing.supplier.name,
                    'rate_per_sqm': float(pricing.rate_per_sqm),
                    'hole_price': float(pricing.hole_price),
                    'cutout_price': float(pricing.cutout_price),
                    'big_hole_price': float(pricing.big_hole_price),
                    'big_cutout_price': float(pricing.big_cutout_price),
                    'frosting_charge_per_sqm': float(pricing.frosting_charge_per_sqm),
                    'lead_time_days': pricing.lead_time_days
                })
        
        result.append({
            'id': gt.id,
            'name': gt.name,
            'category': gt.category,
            'thickness_mm': float(gt.thickness_mm) if gt.thickness_mm else None,
            'is_frosted': gt.is_frosted,
            'is_tinted': gt.is_tinted,
            'suppliers': suppliers_pricing,
            'best_price': float(gt.get_best_price()) if gt.get_best_price() else None
        })
    
    return jsonify(result)


# ============================================================================
# SUPPLIER MANAGEMENT ROUTES
# ============================================================================

@app.route('/suppliers')
@login_required
def suppliers_list():
    """List all suppliers"""
    from models import Supplier
    
    search_query = request.args.get('search', '')
    
    query = Supplier.query
    
    if search_query:
        query = query.filter(
            (Supplier.name.ilike(f'%{search_query}%')) |
            (Supplier.contact_person.ilike(f'%{search_query}%')) |
            (Supplier.city.ilike(f'%{search_query}%'))
        )
    
    suppliers = query.filter_by(is_active=True).order_by(Supplier.name).all()
    
    return render_template('suppliers/list.html',
                         suppliers=suppliers,
                         search_query=search_query)


@app.route('/suppliers/new', methods=['GET', 'POST'])
@login_required
def supplier_new():
    """Create new supplier"""
    from models import Supplier
    
    if request.method == 'POST':
        try:
            data = request.form
            if not data.get('name', '').strip():
                flash('Supplier name is required.', 'danger')
                return redirect(url_for('supplier_new'))
            if not data.get('phone', '').strip():
                flash('Phone number is required.', 'danger')
                return redirect(url_for('supplier_new'))
            if not data.get('email', '').strip():
                flash('Email is required.', 'danger')
                return redirect(url_for('supplier_new'))
            if not data.get('gstin', '').strip():
                flash('GSTIN is required.', 'danger')
                return redirect(url_for('supplier_new'))

            supplier = Supplier(
                name=data.get('name'),
                contact_person=data.get('contact_person'),
                phone=data.get('phone'),
                email=data.get('email'),
                address=data.get('address'),
                city=data.get('city'),
                state=data.get('state'),
                pincode=data.get('pincode'),
                gstin=data.get('gstin'),
                pan=data.get('pan'),
                bank_name=data.get('bank_name'),
                account_number=data.get('account_number'),
                ifsc_code=data.get('ifsc_code'),
                branch=data.get('branch'),
                payment_terms=data.get('payment_terms'),
                lead_time_days=int(data.get('lead_time_days')) if data.get('lead_time_days') else None,
                min_order_value=float(data.get('min_order_value')) if data.get('min_order_value') else None,
                notes=data.get('notes'),
                is_active=True
            )
            
            db.session.add(supplier)
            db.session.commit()
            
            flash(f'Supplier "{supplier.name}" created successfully!', 'success')
            return redirect(url_for('suppliers_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating supplier: {str(e)}', 'danger')
            return redirect(url_for('supplier_new'))
    
    return render_template('suppliers/form.html', title='New Supplier', supplier=None)


@app.route('/suppliers/<int:id>')
@login_required
def supplier_view(id):
    """View supplier details"""
    from models import Supplier
    supplier = Supplier.query.get_or_404(id)
    return render_template('suppliers/view.html', supplier=supplier)


@app.route('/suppliers/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def supplier_edit(id):
    """Edit supplier"""
    from models import Supplier
    
    supplier = Supplier.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            data = request.form
            if not data.get('name', '').strip():
                flash('Supplier name is required.', 'danger')
                return redirect(url_for('supplier_edit', id=id))
            if not data.get('phone', '').strip():
                flash('Phone number is required.', 'danger')
                return redirect(url_for('supplier_edit', id=id))
            if not data.get('email', '').strip():
                flash('Email is required.', 'danger')
                return redirect(url_for('supplier_edit', id=id))
            if not data.get('gstin', '').strip():
                flash('GSTIN is required.', 'danger')
                return redirect(url_for('supplier_edit', id=id))

            supplier.name = data.get('name')
            supplier.contact_person = data.get('contact_person')
            supplier.phone = data.get('phone')
            supplier.email = data.get('email')
            supplier.address = data.get('address')
            supplier.city = data.get('city')
            supplier.state = data.get('state')
            supplier.pincode = data.get('pincode')
            supplier.gstin = data.get('gstin')
            supplier.pan = data.get('pan')
            supplier.bank_name = data.get('bank_name')
            supplier.account_number = data.get('account_number')
            supplier.ifsc_code = data.get('ifsc_code')
            supplier.branch = data.get('branch')
            supplier.payment_terms = data.get('payment_terms')
            supplier.lead_time_days = int(data.get('lead_time_days')) if data.get('lead_time_days') else None
            supplier.min_order_value = float(data.get('min_order_value')) if data.get('min_order_value') else None
            supplier.notes = data.get('notes')
            supplier.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            flash(f'Supplier "{supplier.name}" updated successfully!', 'success')
            return redirect(url_for('supplier_view', id=supplier.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating supplier: {str(e)}', 'danger')
            return redirect(url_for('supplier_edit', id=id))
    
    return render_template('suppliers/form.html', title='Edit Supplier', supplier=supplier)


@app.route('/suppliers/<int:id>/delete', methods=['POST'])
@admin_required
def supplier_delete(id):
    """Delete supplier (soft delete)"""
    from models import Supplier
    supplier = Supplier.query.get_or_404(id)
    supplier_name = supplier.name
    supplier.is_active = False
    db.session.commit()
    flash(f'Supplier "{supplier_name}" deleted successfully!', 'success')
    return redirect(url_for('suppliers_list'))


# ============================================================================
# GLASS CATALOG ROUTES
# ============================================================================

@app.route('/glass-catalog')
@login_required
def glass_catalog_list():
    """List all glass types with pricing from all suppliers"""
    from models import GlassType, Supplier, SupplierPricing
    
    search_query = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    supplier_filter = request.args.get('supplier', '')
    
    # Get all active glass types
    query = GlassType.query.filter_by(is_active=True)
    
    if search_query:
        query = query.filter(GlassType.name.ilike(f'%{search_query}%'))
    
    if category_filter:
        query = query.filter_by(category=category_filter)
    
    glass_types = query.order_by(GlassType.category, GlassType.name).all()
    
    # Get all active suppliers for filter dropdown
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    
    # Get unique categories for filter dropdown
    categories = db.session.query(GlassType.category).filter(
        GlassType.is_active == True,
        GlassType.category.isnot(None)
    ).distinct().order_by(GlassType.category).all()
    categories = [c[0] for c in categories]
    
    # Filter pricing by supplier if selected
    if supplier_filter:
        supplier_filter = int(supplier_filter)
    
    return render_template('glass_catalog/list.html',
                         glass_types=glass_types,
                         suppliers=suppliers,
                         categories=categories,
                         search_query=search_query,
                         category_filter=category_filter,
                         supplier_filter=supplier_filter)


@app.route('/glass-catalog/new', methods=['GET', 'POST'])
@login_required
def glass_catalog_new():
    """Create new glass type"""
    from models import GlassType
    
    if request.method == 'POST':
        try:
            data = request.form
            
            glass_type = GlassType(
                name=data.get('name'),
                category=data.get('category'),
                thickness_mm=float(data.get('thickness_mm')) if data.get('thickness_mm') else None,
                description=data.get('description'),
                is_frosted=bool(data.get('is_frosted')),
                is_tinted=bool(data.get('is_tinted')),
                color=data.get('color'),
                is_active=True
            )
            
            db.session.add(glass_type)
            db.session.commit()
            
            flash(f'Glass type "{glass_type.name}" created successfully!', 'success')
            return redirect(url_for('glass_catalog_view', id=glass_type.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating glass type: {str(e)}', 'danger')
            return redirect(url_for('glass_catalog_new'))
    
    return render_template('glass_catalog/form.html', title='New Glass Type', glass_type=None)


@app.route('/glass-catalog/<int:id>')
@login_required
def glass_catalog_view(id):
    """View glass type details with all supplier pricing"""
    from models import GlassType, Supplier
    
    glass_type = GlassType.query.get_or_404(id)
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    
    return render_template('glass_catalog/view.html',
                         glass_type=glass_type,
                         suppliers=suppliers)


@app.route('/glass-catalog/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def glass_catalog_edit(id):
    """Edit glass type"""
    from models import GlassType
    
    glass_type = GlassType.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            data = request.form
            
            glass_type.name = data.get('name')
            glass_type.category = data.get('category')
            glass_type.thickness_mm = float(data.get('thickness_mm')) if data.get('thickness_mm') else None
            glass_type.description = data.get('description')
            glass_type.is_frosted = bool(data.get('is_frosted'))
            glass_type.is_tinted = bool(data.get('is_tinted'))
            glass_type.color = data.get('color')
            glass_type.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            flash(f'Glass type "{glass_type.name}" updated successfully!', 'success')
            return redirect(url_for('glass_catalog_view', id=glass_type.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating glass type: {str(e)}', 'danger')
            return redirect(url_for('glass_catalog_edit', id=id))
    
    return render_template('glass_catalog/form.html', title='Edit Glass Type', glass_type=glass_type)


@app.route('/glass-catalog/<int:id>/pricing', methods=['GET', 'POST'])
@login_required
def glass_catalog_pricing(id):
    """Manage supplier pricing for a glass type"""
    from models import GlassType, Supplier, SupplierPricing
    from datetime import date
    
    glass_type = GlassType.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            data = request.form
            supplier_id = int(data.get('supplier_id'))
            
            # Check if pricing already exists
            pricing = SupplierPricing.query.filter_by(
                supplier_id=supplier_id,
                glass_type_id=glass_type.id,
                is_active=True
            ).first()
            
            if pricing:
                # Update existing pricing
                pricing.rate_per_sqm = float(data.get('rate_per_sqm'))
                pricing.hole_price = float(data.get('hole_price', 0))
                pricing.cutout_price = float(data.get('cutout_price', 0))
                pricing.big_hole_price = float(data.get('big_hole_price', 0))
                pricing.big_cutout_price = float(data.get('big_cutout_price', 0))
                pricing.frosting_charge_per_sqm = float(data.get('frosting_charge_per_sqm', 0))
                pricing.tinting_charge_per_sqm = float(data.get('tinting_charge_per_sqm', 0))
                pricing.min_order_sqm = float(data.get('min_order_sqm')) if data.get('min_order_sqm') else None
                pricing.lead_time_days = int(data.get('lead_time_days')) if data.get('lead_time_days') else None
                pricing.notes = data.get('notes')
                pricing.updated_at = datetime.utcnow()
                
                flash('Pricing updated successfully!', 'success')
            else:
                # Create new pricing
                pricing = SupplierPricing(
                    supplier_id=supplier_id,
                    glass_type_id=glass_type.id,
                    rate_per_sqm=float(data.get('rate_per_sqm')),
                    hole_price=float(data.get('hole_price', 0)),
                    cutout_price=float(data.get('cutout_price', 0)),
                    big_hole_price=float(data.get('big_hole_price', 0)),
                    big_cutout_price=float(data.get('big_cutout_price', 0)),
                    frosting_charge_per_sqm=float(data.get('frosting_charge_per_sqm', 0)),
                    tinting_charge_per_sqm=float(data.get('tinting_charge_per_sqm', 0)),
                    min_order_sqm=float(data.get('min_order_sqm')) if data.get('min_order_sqm') else None,
                    lead_time_days=int(data.get('lead_time_days')) if data.get('lead_time_days') else None,
                    effective_from=date.today(),
                    notes=data.get('notes'),
                    is_active=True
                )
                db.session.add(pricing)
                flash('Pricing added successfully!', 'success')
            
            db.session.commit()
            return redirect(url_for('glass_catalog_view', id=glass_type.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving pricing: {str(e)}', 'danger')
            return redirect(url_for('glass_catalog_pricing', id=id))
    
    # GET request
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    
    # Check if editing existing pricing (supplier_id in query params)
    supplier_id = request.args.get('supplier_id', type=int)
    existing_pricing = None
    
    if supplier_id:
        existing_pricing = SupplierPricing.query.filter_by(
            supplier_id=supplier_id,
            glass_type_id=glass_type.id,
            is_active=True
        ).first()
    
    return render_template('glass_catalog/pricing.html',
                         glass_type=glass_type,
                         suppliers=suppliers,
                         existing_pricing=existing_pricing,
                         selected_supplier_id=supplier_id)


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500


# ============================================================================
# LAMBDA HANDLER
# ============================================================================

def lambda_handler(event, context):
    """AWS Lambda handler"""
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Use awsgi to handle Lambda event
    from awsgi import response
    return response(app, event, context)


# ============================================================================
# REMINDER ROUTES
# ============================================================================

@app.route('/reminders')
@login_required
def reminders_list():
    """List all reminders for current user"""
    if current_user.role == 'Admin':
        reminders = Reminder.query.order_by(Reminder.reminder_datetime.desc()).all()
    else:
        reminders = Reminder.query.filter_by(user_id=current_user.id).order_by(Reminder.reminder_datetime.desc()).all()
    
    return render_template('reminders/list.html', reminders=reminders)


@app.route('/reminders/new', methods=['GET', 'POST'])
@login_required
def reminder_new():
    """Create a new reminder"""
    if request.method == 'POST':
        try:
            reminder_type = request.form.get('reminder_type')
            project_id = request.form.get('project_id') if reminder_type == 'project' else None
            task_id = request.form.get('task_id') if reminder_type == 'task' else None
            user_id = request.form.get('user_id', current_user.id)
            
            reminder_date = request.form.get('reminder_date')
            reminder_time = request.form.get('reminder_time', '09:00')
            reminder_datetime = datetime.strptime(f"{reminder_date} {reminder_time}", '%Y-%m-%d %H:%M')
            
            subject = request.form.get('subject') or None
            message = request.form.get('message') or None
            is_recurring = request.form.get('is_recurring') == 'on'
            recurrence_pattern = request.form.get('recurrence_pattern') if is_recurring else None
            recurrence_end_date = request.form.get('recurrence_end_date') if is_recurring else None
            
            if recurrence_end_date:
                recurrence_end_date = datetime.strptime(recurrence_end_date, '%Y-%m-%d').date()
            
            reminder = Reminder(
                reminder_type=reminder_type,
                project_id=project_id,
                task_id=task_id,
                user_id=user_id,
                reminder_datetime=reminder_datetime,
                subject=subject,
                message=message,
                is_recurring=is_recurring,
                recurrence_pattern=recurrence_pattern,
                recurrence_end_date=recurrence_end_date,
                status='pending'
            )
            
            db.session.add(reminder)
            db.session.commit()
            
            flash('Reminder created successfully!', 'success')
            return redirect(url_for('reminders_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating reminder: {str(e)}', 'danger')
    
    if current_user.role == 'Admin':
        projects = Project.query.filter(Project.status.in_(['New', 'In Progress'])).all()
        tasks = PromotorTask.query.filter(PromotorTask.status.in_(['Pending', 'In Progress'])).all()
        users = User.query.filter_by(is_active=True).all()
    else:
        projects = Project.query.filter_by(owner_id=current_user.id).filter(
            Project.status.in_(['New', 'In Progress'])
        ).all()
        tasks = PromotorTask.query.filter_by(promotor_id=current_user.id).filter(
            PromotorTask.status.in_(['Pending', 'In Progress'])
        ).all()
        users = [current_user]
    
    return render_template('reminders/form.html', projects=projects, tasks=tasks, users=users, reminder=None)


@app.route('/reminders/<int:id>/delete', methods=['POST'])
@login_required
def reminder_delete(id):
    """Delete a reminder"""
    reminder = Reminder.query.get_or_404(id)
    
    if current_user.role != 'Admin' and reminder.user_id != current_user.id:
        flash('You do not have permission to delete this reminder.', 'danger')
        return redirect(url_for('reminders_list'))
    
    try:
        db.session.delete(reminder)
        db.session.commit()
        flash('Reminder deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting reminder: {str(e)}', 'danger')
    
    return redirect(url_for('reminders_list'))


@app.route('/api/reminders/check', methods=['GET'])
def reminders_check():
    """Cron endpoint to check and send pending reminders"""
    cron_secret = request.headers.get('X-Cron-Secret') or request.args.get('secret')
    expected_secret = os.getenv('CRON_SECRET')
    
    if not expected_secret or cron_secret != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        from utils.reminder_scheduler import ReminderScheduler
        scheduler = ReminderScheduler()
        result = scheduler.check_and_send_reminders()

        return jsonify({'success': True, 'result': result}), 200

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[reminders/check] Exception: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reminders/auto-create', methods=['GET', 'POST'])
def reminders_auto_create():
    """API endpoint to create automatic reminders for all incomplete projects"""
    # Verify secret key
    cron_secret = request.headers.get('X-Cron-Secret') or request.args.get('secret')
    expected_secret = os.getenv('CRON_SECRET')
    
    if not expected_secret or cron_secret != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get all incomplete projects
        incomplete_projects = Project.query.filter(
            Project.status.in_(['New', 'In Progress', 'On Hold'])
        ).all()
        
        # Get all active users
        active_users = User.query.filter_by(is_active=True).all()
        
        # Set reminder time to now (so the check endpoint picks them up immediately)
        reminder_time = datetime.utcnow()
        
        created_count = 0
        skipped_count = 0
        
        for project in incomplete_projects:
            # Determine recipients
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
                else:
                    skipped_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'result': {
                'projects_checked': len(incomplete_projects),
                'reminders_created': created_count,
                'reminders_skipped': skipped_count,
                'scheduled_for': reminder_time.strftime('%Y-%m-%d %H:%M:%S UTC')
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reminders/reset-failed', methods=['GET', 'POST'])
def reminders_reset_failed():
    """API endpoint to reset failed reminders to pending status"""
    # Verify secret key
    cron_secret = request.headers.get('X-Cron-Secret') or request.args.get('secret')
    expected_secret = os.getenv('CRON_SECRET')
    
    if not expected_secret or cron_secret != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get all failed reminders
        failed_reminders = Reminder.query.filter_by(status='failed').all()
        
        reset_count = 0
        for reminder in failed_reminders:
            # Reset to pending
            reminder.status = 'pending'
            reminder.error_message = None
            
            # Update reminder time to 5 minutes from now
            reminder.reminder_datetime = datetime.utcnow() + timedelta(minutes=5)
            reset_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'result': {
                'reminders_reset': reset_count,
                'scheduled_for': (datetime.utcnow() + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S UTC')
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500




# ============================================================================
# QUOTE EMAIL & FOLLOW-UP ROUTES
# ============================================================================

@app.route('/quotes/<int:id>/send-email', methods=['POST'])
@login_required
def quote_send_email(id):
    """Send quotation email to client"""
    from models import Quote
    from utils.email_service import EmailService

    quote = Quote.query.get_or_404(id)

    to_email = request.form.get('to_email', '').strip()
    custom_subject = request.form.get('subject', '').strip() or None
    custom_message = request.form.get('message', '').strip() or None

    if not to_email:
        flash('Please provide a recipient email address.', 'warning')
        return redirect(url_for('quote_view', id=id))

    email_service = EmailService()
    result = email_service.send_quote_email(
        quote,
        to_email,
        custom_subject=custom_subject,
        custom_message=custom_message
    )

    if result['success']:
        if quote.status == 'Draft':
            quote.status = 'Sent'
            db.session.commit()
        flash(f'Quotation email sent successfully to {to_email}.', 'success')
    else:
        flash(f'Failed to send email: {result.get("error", "Unknown error")}', 'danger')

    return redirect(url_for('quote_view', id=id))


@app.route('/quotes/<int:id>/schedule-followup', methods=['POST'])
@login_required
def quote_schedule_followup(id):
    """Schedule a follow-up reminder for a quote"""
    from models import Quote, Reminder
    from datetime import datetime

    quote = Quote.query.get_or_404(id)

    followup_datetime_str = request.form.get('followup_datetime', '').strip()
    custom_subject = request.form.get('subject', '').strip() or None
    custom_message = request.form.get('message', '').strip() or None

    if not followup_datetime_str:
        flash('Please select a follow-up date and time.', 'warning')
        return redirect(url_for('quote_view', id=id))

    try:
        followup_datetime = datetime.strptime(followup_datetime_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        flash('Invalid date/time format.', 'warning')
        return redirect(url_for('quote_view', id=id))

    if followup_datetime <= datetime.utcnow():
        flash('Follow-up time must be in the future.', 'warning')
        return redirect(url_for('quote_view', id=id))

    reminder = Reminder(
        reminder_type='quote',
        quote_id=quote.id,
        user_id=current_user.id,
        reminder_datetime=followup_datetime,
        subject=custom_subject or f'Follow-up: Quote {quote.quote_number} — {quote.customer_name}',
        message=custom_message,
        status='pending'
    )
    db.session.add(reminder)
    db.session.commit()

    flash(
        f'Follow-up reminder scheduled for {followup_datetime.strftime("%d %b %Y at %I:%M %p")}.',
        'success'
    )
    return redirect(url_for('quote_view', id=id))


# ============================================================================
# LEADFY - LEAD MANAGEMENT ROUTES
# ============================================================================

@app.route('/api/leads/webhook', methods=['POST'])
@limiter.limit("10 per minute; 50 per hour")
def leads_webhook():
    """Receive leads from glassy.in WordPress contact form"""
    import hmac

    # Block oversized bodies before parsing (prevent DoS via huge payloads)
    MAX_BODY = 32 * 1024  # 32 KB
    content_length = request.content_length
    if content_length and content_length > MAX_BODY:
        return jsonify({'success': False, 'error': 'Payload too large'}), 413

    # Constant-time secret comparison (prevents timing attacks)
    expected_secret = os.getenv('GLASSY_WEBHOOK_SECRET', '')
    auth_header = request.headers.get('Authorization', '')
    expected_header = f'Bearer {expected_secret}'
    if not expected_secret or not hmac.compare_digest(auth_header, expected_header):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    from models import Lead
    try:
        name       = (data.get('name') or '').strip()[:200] or None
        email      = (data.get('email') or '').strip()[:200] or None
        phone      = (data.get('phone') or '').strip()[:30] or None
        message    = (data.get('message') or '').strip()[:2000]
        source_url = (data.get('source_url') or '').strip()[:500]

        # Deduplicate: if same email submitted within the last 60 seconds, skip
        if email:
            cutoff = datetime.utcnow() - timedelta(seconds=60)
            duplicate = Lead.query.filter_by(email=email, origin='glassy.in') \
                                  .filter(Lead.created_at >= cutoff).first()
            if duplicate:
                app.logger.info(f'[Webhook] Duplicate lead skipped: {email}')
                return jsonify({'success': True}), 200

        # Compose notes from message + source URL
        notes_parts = []
        if message:
            notes_parts.append(message)
        if source_url:
            notes_parts.append(f'Source: {source_url}')
        notes = '\n'.join(notes_parts) or None

        # Find a system admin to use as created_by (required FK)
        from models import User
        admin = User.query.filter_by(role='Admin', is_active=True).first()
        if not admin:
            return jsonify({'success': False, 'error': 'Configuration error'}), 500

        lead = Lead(
            name=name,
            email=email,
            contact=phone,
            notes=notes,
            origin='glassy.in',
            stage='New Lead',
            owner_id=None,
            assigned_to_id=None,
            created_by=admin.id,
        )
        db.session.add(lead)
        db.session.commit()
        app.logger.info(f'[Webhook] New lead from glassy.in: {name} ({email})')
        return jsonify({'success': True}), 200

    except Exception as e:
        db.session.rollback()
        app.logger.error(f'[Webhook] Error saving lead: {e}')
        return jsonify({'success': False, 'error': 'Internal error'}), 500


@app.route('/leads')
@login_required
def leads_list():
    """List all leads with search and filter"""
    from models import Lead, User
    from datetime import datetime

    search_query = request.args.get('search', '')
    stage_filter = request.args.get('stage', '')
    state_filter = request.args.get('state', '')
    origin_filter = request.args.get('origin', '')
    owner_filter = request.args.get('owner', '')
    updated_from = request.args.get('updated_from', '')
    updated_to = request.args.get('updated_to', '')
    created_from = request.args.get('created_from', '')
    created_to = request.args.get('created_to', '')

    query = Lead.query

    # Non-admin/manager users only see leads assigned to them
    if not current_user.is_manager_or_admin():
        query = query.filter(Lead.assigned_to_id == current_user.id)

    lead_type_filter = request.args.get('lead_type', '')
    untouched_filter = request.args.get('untouched', '')

    if search_query:
        query = query.filter(
            (Lead.name.ilike(f'%{search_query}%')) |
            (Lead.contact.ilike(f'%{search_query}%')) |
            (Lead.company.ilike(f'%{search_query}%'))
        )
    if stage_filter:
        query = query.filter(Lead.stage == stage_filter)
    if state_filter:
        query = query.filter(Lead.state.ilike(f'%{state_filter}%'))
    if origin_filter:
        query = query.filter(Lead.origin == origin_filter)
    if lead_type_filter:
        query = query.filter(Lead.lead_type == lead_type_filter)
    if untouched_filter == '1':
        query = query.filter(Lead.is_untouched == True)
    elif untouched_filter == '0':
        query = query.filter(Lead.is_untouched == False)
    if owner_filter:
        try:
            query = query.filter(Lead.owner_id == int(owner_filter))
        except ValueError:
            pass

    if updated_from:
        try:
            query = query.filter(Lead.updated_at >= datetime.strptime(updated_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if updated_to:
        try:
            query = query.filter(Lead.updated_at <= datetime.strptime(updated_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass
    if created_from:
        try:
            query = query.filter(Lead.created_at >= datetime.strptime(created_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if created_to:
        try:
            query = query.filter(Lead.created_at <= datetime.strptime(created_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass

    PER_PAGE = 15
    page = request.args.get('page', 1, type=int)

    pagination = query.order_by(Lead.created_at.desc()).paginate(page=page, per_page=PER_PAGE, error_out=False)
    leads = pagination.items
    total_leads = Lead.query.count()
    users = User.query.filter_by(is_active=True).order_by(User.username).all()

    origins = db.session.query(Lead.origin).filter(Lead.origin.isnot(None)).distinct().order_by(Lead.origin).all()
    origins = [o[0] for o in origins]

    states = db.session.query(Lead.state).filter(Lead.state.isnot(None)).distinct().order_by(Lead.state).all()
    states = [s[0] for s in states]

    from models import IndiamartToken
    indiamart_token = IndiamartToken.query.first()
    fb_token_set = bool(os.getenv('FB_PAGE_ACCESS_TOKEN', ''))

    return render_template('leads/list.html',
                           leads=leads,
                           pagination=pagination,
                           total_leads=total_leads,
                           users=users,
                           origins=origins,
                           states=states,
                           search_query=search_query,
                           stage_filter=stage_filter,
                           state_filter=state_filter,
                           origin_filter=origin_filter,
                           owner_filter=owner_filter,
                           lead_type_filter=lead_type_filter,
                           updated_from=updated_from,
                           updated_to=updated_to,
                           created_from=created_from,
                           created_to=created_to,
                           indiamart_token=indiamart_token,
                           fb_token_set=fb_token_set)


@app.route('/leads/new', methods=['GET', 'POST'])
@login_required
def lead_new():
    """Create a new lead"""
    from models import Lead, User

    if request.method == 'POST':
        name = request.form.get('name', '').strip() or None
        owner_id = request.form.get('owner_id') or None
        contact = request.form.get('contact', '').strip() or None
        city = request.form.get('city', '').strip() or None
        state = request.form.get('state', '').strip() or None
        stage = request.form.get('stage', 'New Lead')
        origin = request.form.get('origin', '').strip() or None

        lead = Lead(
            name=name,
            owner_id=int(owner_id) if owner_id else None,
            contact=contact,
            city=city,
            state=state,
            stage=stage,
            origin=origin,
            created_by=current_user.id
        )
        db.session.add(lead)
        db.session.commit()
        flash('Lead created successfully.', 'success')
        return redirect(url_for('leads_list'))

    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    return render_template('leads/form.html', lead=None, users=users, action='new')


@app.route('/leads/<int:id>')
@login_required
def lead_view(id):
    """Lead detail page"""
    from models import Lead
    lead = Lead.query.get_or_404(id)
    history = lead.history.order_by(__import__('models').LeadHistory.created_at.desc()).all()
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    return render_template('leads/view.html', lead=lead, history=history, users=users)


@app.route('/leads/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def lead_edit(id):
    """Edit an existing lead"""
    from models import Lead, User, LeadHistory

    lead = Lead.query.get_or_404(id)

    if request.method == 'POST':
        changes = []

        # Track stage change
        new_stage = request.form.get('stage', lead.stage)
        if new_stage != lead.stage:
            changes.append(LeadHistory(lead_id=lead.id, user_id=current_user.id,
                action='stage_change',
                description=f'Stage changed from <strong>{lead.stage}</strong> to <strong>{new_stage}</strong>'))
            lead.stage = new_stage
            lead.is_untouched = False

        # Track owner change
        owner_id = request.form.get('owner_id') or None
        new_owner_id = int(owner_id) if owner_id else None
        if new_owner_id != lead.owner_id:
            old_owner = User.query.get(lead.owner_id).username if lead.owner_id else 'Unassigned'
            new_owner = User.query.get(new_owner_id).username if new_owner_id else 'Unassigned'
            changes.append(LeadHistory(lead_id=lead.id, user_id=current_user.id,
                action='field_change',
                description=f'Owner changed from <strong>{old_owner}</strong> to <strong>{new_owner}</strong>'))
            lead.owner_id = new_owner_id

        # Track assigned_to change
        assigned_to_raw = request.form.get('assigned_to_id') or None
        new_assigned_to_id = int(assigned_to_raw) if assigned_to_raw else None
        if new_assigned_to_id != lead.assigned_to_id:
            old_assignee = User.query.get(lead.assigned_to_id).username if lead.assigned_to_id else 'Unassigned'
            new_assignee = User.query.get(new_assigned_to_id).username if new_assigned_to_id else 'Unassigned'
            changes.append(LeadHistory(lead_id=lead.id, user_id=current_user.id,
                action='field_change',
                description=f'Assigned To changed from <strong>{old_assignee}</strong> to <strong>{new_assignee}</strong>'))
            lead.assigned_to_id = new_assigned_to_id

        # Track other field changes
        field_map = [
            ('name', 'name', 'Name'),
            ('contact', 'contact', 'Phone'),
            ('email', 'email', 'Email'),
            ('city', 'city', 'City'),
            ('state', 'state', 'State'),
            ('origin', 'origin', 'Origin'),
        ]
        for form_key, model_attr, label in field_map:
            new_val = request.form.get(form_key, '').strip() or None
            old_val = getattr(lead, model_attr)
            if new_val != old_val:
                changes.append(LeadHistory(lead_id=lead.id, user_id=current_user.id,
                    action='field_change',
                    description=f'{label} changed from <strong>{old_val or "—"}</strong> to <strong>{new_val or "—"}</strong>'))
                setattr(lead, model_attr, new_val)

        for ch in changes:
            db.session.add(ch)
        db.session.commit()
        return redirect(url_for('lead_view', id=lead.id))

    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    return render_template('leads/form.html', lead=lead, users=users, action='edit')


@app.route('/leads/<int:id>/delete', methods=['POST'])
@login_required
def lead_delete(id):
    """Delete a lead (admin only)"""
    if not current_user.is_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('leads_list'))

    from models import Lead
    lead = Lead.query.get_or_404(id)
    db.session.delete(lead)
    db.session.commit()
    flash('Lead deleted.', 'success')
    return redirect(url_for('leads_list'))


# ============================================================================
# INDIAMART INTEGRATION
# ============================================================================

@app.route('/leads/indiamart/save-token', methods=['POST'])
@login_required
@admin_required
def indiamart_save_token():
    """Save IndiaMart token captured from the mobile app"""
    from models import IndiamartToken
    import base64, json
    from datetime import datetime

    ak_token = request.form.get('ak_token', '').strip()
    glid = request.form.get('glid', '').strip()
    mobile = request.form.get('mobile', '').strip()
    user_ip = request.form.get('user_ip', '').strip()

    if not ak_token:
        flash('Token is required.', 'danger')
        return redirect(url_for('leads_list'))

    payload = _decode_jwt_payload(ak_token)
    expires_at = None
    refresh_token_val = None
    try:
        if payload.get('exp'):
            expires_at = datetime.utcfromtimestamp(payload['exp'])
        # Extract refresh token if IndiaMart embedded one in the JWT payload
        for key in ('refresh_token', 'rt', 'rtoken', 'refreshToken'):
            if payload.get(key):
                refresh_token_val = payload[key]
                break
    except Exception:
        pass

    token = IndiamartToken.query.first()
    if not token:
        token = IndiamartToken()
        db.session.add(token)
    token.ak_token = ak_token
    token.glid = glid
    token.mobile = mobile
    token.user_ip = user_ip
    token.expires_at = expires_at
    if refresh_token_val:
        token.refresh_token = refresh_token_val
    db.session.commit()

    flash('IndiaMart token saved successfully.', 'success')
    return redirect(url_for('leads_list'))


def _decode_jwt_payload(jwt_str):
    """Decode a JWT payload section and return the dict (no signature verification)."""
    import base64, json
    try:
        parts = jwt_str.split('.')
        if len(parts) < 2:
            return {}
        pad = parts[1] + '=' * (4 - len(parts[1]) % 4)
        return json.loads(base64.b64decode(pad))
    except Exception:
        return {}


def _save_new_ak(token, new_ak):
    """Persist a fresh AK token (and any embedded refresh_token) to the DB."""
    from datetime import datetime
    payload = _decode_jwt_payload(new_ak)
    token.ak_token = new_ak
    if payload.get('exp'):
        token.expires_at = datetime.utcfromtimestamp(payload['exp'])
    # IndiaMart sometimes embeds a long-lived refresh token in the payload
    for key in ('refresh_token', 'rt', 'rtoken', 'refreshToken'):
        if payload.get(key):
            token.refresh_token = payload[key]
            break
    db.session.commit()


def _indiamart_refresh_token(token, headers):
    """
    Try to get a fresh AK token from IndiaMart.
    Strategy 1 – checkAuth (works when current token is still valid or just expired).
    Strategy 2 – use stored refresh_token if IndiaMart returned one previously.
    Returns the current (possibly refreshed) AK string.
    """
    import requests as req_lib
    from datetime import datetime

    import logging
    log = logging.getLogger(__name__)

    datacookie = (
        f"fn=Rohit Kumar|em=vetrovaglass@gmail.com|phcc=91|iso=IN"
        f"|mb1={token.mobile}|ctid=70532|glid={token.glid}"
        f"|cmid=1|uTyp=P|utyp=P|ev=V|uv=V"
    )
    cookie_header = (
        f"ImeshVisitor=fn=Rohit Kumar|em=vetrovaglass@gmail.com|phcc=91|iso=IN"
        f"|mb1={token.mobile}|ctid=70532|glid={token.glid}"
        f"|cmid=1|uTyp=P|utyp=P|ev=V|uv=V; "
        f"im_iss=t={token.ak_token}"
    )
    base_data = {
        'APP_ACCURACY': '',
        'APP_LATITUDE': '',
        'APP_LONGITUDE': '',
        'APP_MODID': 'IOS',
        'APP_SCREEN_NAME': 'Api Request',
        'APP_USER_ID': token.glid,
        'GEOIP_COUNTRY_ISO': 'IN',
        'USER_IP': token.user_ip or '',
        'USER_IP_COUNTRY': 'India',
        'VALIDATION_GLID': token.glid,
        'VALIDATION_USERCONTACT': token.mobile,
        'VALIDATION_USER_IP': token.user_ip or '',
        'app_version_no': '13.6.4_b_4',
        'datacookie': datacookie,
        'glusrid': token.glid,
        'modid': 'IOS',
        'user_name': token.mobile,
    }
    req_headers = {**headers, 'cookie': cookie_header}

    # --- Strategy 1: checkAuth with current AK ---
    try:
        resp = req_lib.post(
            'https://mapi.indiamart.com/wservce/users/login/',
            data={**base_data,
                  'AK': token.ak_token,
                  'checkAuth': '1',
                  'im_iss': f't={token.ak_token}'},
            headers=req_headers,
            timeout=10
        )
        data = resp.json()
        log.warning(f"[IndiaMart checkAuth] HTTP {resp.status_code} | keys={list(data.keys())} | access={data.get('access')} | MSG={data.get('message','')}")
        new_ak = (data.get('jwt_token') or data.get('AK') or data.get('ak')
                  or data.get('TOKEN') or data.get('token'))
        if new_ak and data.get('access') in ('1', '2', 1, 2):
            old_exp = token.expires_at
            _save_new_ak(token, new_ak)
            # IndiaMart returns the same JWT but the server-side session is alive.
            # Extend our stored expiry by 24h from now so keepalive keeps working.
            token.expires_at = datetime.utcnow() + timedelta(hours=24)
            db.session.commit()
            log.warning(f"[IndiaMart checkAuth] Session alive, extended expiry | old_exp={old_exp} | new_exp={token.expires_at}")
            return new_ak
        else:
            log.warning(f"[IndiaMart checkAuth] No token in response. Full response: {data}")
    except Exception as e:
        log.warning(f"[IndiaMart checkAuth] Exception: {e}")

    # --- Strategy 2: use stored refresh_token (if IndiaMart ever returned one) ---
    if token.refresh_token:
        try:
            resp = req_lib.post(
                'https://mapi.indiamart.com/wservce/users/login/',
                data={**base_data,
                      'refresh_token': token.refresh_token,
                      'grant_type': 'refresh_token'},
                headers=headers,
                timeout=10
            )
            data = resp.json()
            log.warning(f"[IndiaMart refresh_token] HTTP {resp.status_code} | keys={list(data.keys())} | CODE={data.get('CODE')} | MSG={data.get('MESSAGE') or data.get('message','')}")
            new_ak = data.get('AK') or data.get('ak') or data.get('TOKEN') or data.get('token')
            if new_ak:
                _save_new_ak(token, new_ak)
                return new_ak
            else:
                log.warning(f"[IndiaMart refresh_token] No AK in response. Full response: {data}")
        except Exception as e:
            log.warning(f"[IndiaMart refresh_token] Exception: {e}")

    log.warning(f"[IndiaMart refresh] Both strategies failed. Token expires_at={token.expires_at} is_valid={token.is_valid()}")
    return token.ak_token


def _determine_lead_type(c):
    remarks = (c.get('contact_type_remarks') or '').lower()
    labels = [l.lower() for l in (c.get('label_name') or [])]
    if 'missed' in labels or 'missed' in remarks:
        return 'Missed Call'
    if c.get('is_call'):
        return 'Call'
    if 'buylead' in remarks or 'buy lead' in remarks:
        return 'Buy Lead'
    return 'Enquiry'


def _do_indiamart_sync(owner_id, created_by_id):
    """Core sync logic. Returns (new_count, skipped_count, error_msg)"""
    from models import IndiamartToken, Lead
    import requests as req_lib

    token = IndiamartToken.query.first()
    if not token:
        return 0, 0, 'No IndiaMart token saved.'

    headers = {
        'user-agent': 'IndiaMart/13.6.4 (com.indiamart.m; build:4; iOS 16.6.0) Alamofire/5.0.0-rc.2',
        'accept': '*/*',
        'accept-language': 'en-US;q=1.0',
    }

    # Attempt refresh proactively (even if expired — checkAuth may still work shortly after expiry)
    AK = _indiamart_refresh_token(token, headers)

    # Re-fetch token after potential update, then check validity
    token = IndiamartToken.query.first()
    if not token.is_valid():
        return 0, 0, 'IndiaMart token has expired and could not be auto-refreshed. Please recapture from your phone.'
    GLID = token.glid or '255155317'
    MOBILE = token.mobile or '9341980003'
    USER_IP = token.user_ip or ''

    base_params = {
        'AK': AK,
        'APP_ACCURACY': '', 'APP_LATITUDE': '', 'APP_LONGITUDE': '',
        'APP_MODID': 'IOS', 'APP_SCREEN_NAME': 'Api Request',
        'APP_USER_ID': GLID, 'VALIDATION_GLID': GLID,
        'VALIDATION_USERCONTACT': MOBILE, 'VALIDATION_USER_IP': USER_IP,
        'app_version_no': '13.6.4_b_4', 'glusrid': GLID,
        'modid': 'IOS', 'q': '*', 'rows': '50',
        'token': 'imobile@15061981', 'version': '2',
    }

    new_count = 0
    skipped_count = 0
    page = 1

    while True:
        base_params['page'] = str(page)
        try:
            resp = req_lib.get(
                'https://mapi.indiamart.com/wservce/lms/v1/search',
                params=base_params, headers=headers, timeout=15
            )
            data = resp.json()
        except Exception as e:
            return new_count, skipped_count, f'API error: {str(e)}'

        if data.get('CODE') == 429:
            return new_count, skipped_count, 'Rate limited. Try again in a minute.'

        contacts = data.get('response', {}).get('contacts', [])
        app.logger.info(f"[IndiaMart sync] page={page} contacts_returned={len(contacts)} API_CODE={data.get('CODE')} API_MSG={data.get('MESSAGE','')}")
        if not contacts:
            break

        for c in contacts:
            im_id = str(c.get('im_contact_id', ''))
            if not im_id:
                continue

            if Lead.query.filter_by(indiamart_id=im_id).first():
                skipped_count += 1
                continue

            # Parse IndiaMart dates
            def _parse_im_date(s):
                try:
                    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S') if s else None
                except Exception:
                    return None

            lead = Lead(
                name=c.get('contacts_name') or None,
                contact=c.get('contacts_mobile1') or None,
                city=c.get('contact_city') or None,
                state=c.get('contact_state') or None,
                company=c.get('contacts_company') or None,
                product_interest=c.get('contact_last_product') or None,
                product_qty=c.get('last_product_qty') or None,
                product_category=', '.join(c.get('mcat_name') or []) or None,
                lead_type=_determine_lead_type(c),
                has_whatsapp=bool(c.get('is_whatsapp')),
                is_gst_registered=bool(c.get('is_gst')),
                is_starred=bool(c.get('is_starred_lead')),
                last_message=c.get('last_message') or None,
                unread_count=int(c.get('unread_message_cnt') or 0),
                indiamart_added_date=_parse_im_date(c.get('contacts_add_date')),
                indiamart_last_contact=_parse_im_date(c.get('last_contact_date')),
                indiamart_notes=c.get('notes_v2') or None,
                indiamart_labels=', '.join(c.get('label_name') or []) or None,
                buyer_glid=c.get('contacts_glid') or None,
                is_untouched=bool(c.get('is_contact_untouched', True)),
                origin='IndiaMart',
                stage='New Lead',
                indiamart_id=im_id,
                owner_id=owner_id,
                created_by=created_by_id,
            )
            db.session.add(lead)
            new_count += 1

        db.session.commit()

        if len(contacts) < 50:
            break
        page += 1

    return new_count, skipped_count, None


@app.route('/leads/indiamart/refresh-token', methods=['POST'])
@login_required
@admin_required
def indiamart_refresh_token_route():
    """Manually trigger a token refresh attempt — useful when token is expired."""
    from models import IndiamartToken
    token = IndiamartToken.query.first()
    if not token:
        return jsonify({'success': False, 'error': 'No token saved yet.'})

    headers = {
        'user-agent': 'IndiaMart/13.6.4 (com.indiamart.m; build:4; iOS 16.6.0) Alamofire/5.0.0-rc.2',
        'accept': '*/*',
        'accept-language': 'en-US;q=1.0',
    }
    old_ak = token.ak_token
    _indiamart_refresh_token(token, headers)
    token = IndiamartToken.query.first()

    if token.ak_token != old_ak:
        return jsonify({
            'success': True,
            'message': 'Token refreshed successfully!',
            'expires_at': token.expires_at.isoformat() if token.expires_at else None,
        })
    elif token.is_valid():
        return jsonify({
            'success': True,
            'message': 'Token is still valid — no refresh needed.',
            'expires_at': token.expires_at.isoformat() if token.expires_at else None,
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Could not refresh token. IndiaMart rejected the request — please recapture via mitmproxy.',
        })


@app.route('/leads/indiamart/sync', methods=['POST'])
@login_required
def indiamart_sync():
    new_count, skipped_count, err = _do_indiamart_sync(None, current_user.id)
    if err:
        flash(err, 'warning' if 'expired' in err.lower() or 'rate' in err.lower() else 'danger')
    else:
        flash(f'IndiaMart sync complete: {new_count} new leads imported, {skipped_count} already existed.', 'success')
    return redirect(url_for('leads_list'))


@app.route('/leads/<int:id>/note', methods=['POST'])
@login_required
def lead_save_note(id):
    """Quick note save for a lead"""
    from models import Lead, LeadHistory
    lead = Lead.query.get_or_404(id)
    note_text = request.form.get('notes', '')
    if note_text != (lead.notes or ''):
        lead.notes = note_text
        lead.is_untouched = False
        if note_text:
            db.session.add(LeadHistory(lead_id=lead.id, user_id=current_user.id,
                action='note', description=note_text))
    db.session.commit()
    return jsonify({'success': True})


@app.route('/leads/<int:id>/set-customer-type', methods=['POST'])
@login_required
def lead_set_customer_type(id):
    from models import Lead
    lead = Lead.query.get_or_404(id)
    customer_type = request.form.get('customer_type', '').strip()
    lead.customer_type = customer_type if customer_type in ('B2B', 'B2C') else None
    db.session.commit()
    return jsonify({'success': True, 'customer_type': lead.customer_type})


def _do_facebook_sync(created_by_id):
    """Fetch leads from all Lead Ad forms on the Facebook Page and save new ones.
    Returns (new_count, skipped_count, error_msg).
    """
    import requests as req_lib
    from models import Lead

    access_token = os.getenv('FB_PAGE_ACCESS_TOKEN', '')
    if not access_token:
        return 0, 0, 'FB_PAGE_ACCESS_TOKEN not configured in .env'

    new_count = 0
    skipped_count = 0

    # Use FB_PAGE_ACCESS_TOKEN directly as a Page Access Token with the Page ID.
    # To generate a proper Page Access Token:
    # 1. Go to: https://developers.facebook.com/tools/explorer/
    # 2. Select your App → Generate Token → add permissions: leads_retrieval, pages_read_engagement
    # 3. Switch token type to "Page Access Token" and select your page
    # 4. Copy the token into FB_PAGE_ACCESS_TOKEN in .env
    page_id = os.getenv('FB_PAGE_ID', '')
    page_token = access_token

    if not page_id:
        return 0, 0, 'FB_PAGE_ID not set in .env. Add your Facebook Page ID.'

    # Step 2 — get all Lead Ad forms for the resolved Page
    try:
        resp = req_lib.get(
            f'https://graph.facebook.com/v19.0/{page_id}/leadgen_forms',
            params={'access_token': page_token, 'fields': 'id,name', 'limit': 100},
            timeout=15
        )
        forms_data = resp.json()
    except Exception as e:
        return 0, 0, f'Facebook API error (forms): {str(e)}'

    if 'error' in forms_data:
        msg = forms_data['error'].get('message', 'Unknown error')
        return 0, 0, f'Facebook API: {msg}'

    forms = forms_data.get('data', [])
    if not forms:
        return 0, 0, 'No Lead Ad forms found on this Page.'

    # Step 2 — for each form, paginate through all leads
    for form in forms:
        form_id = form.get('id')
        form_name = form.get('name', '')
        url = f'https://graph.facebook.com/v19.0/{form_id}/leads'
        params = {
            'access_token': page_token,
            'fields': 'id,created_time,field_data',
            'limit': 100,
        }

        while url:
            try:
                resp = req_lib.get(url, params=params, timeout=15)
                data = resp.json()
            except Exception as e:
                app.logger.error(f'[Facebook sync] Error fetching leads for form {form_id}: {e}')
                break

            if 'error' in data:
                app.logger.error(f'[Facebook sync] API error for form {form_id}: {data["error"]}')
                break

            for lead_entry in data.get('data', []):
                fb_lead_id = str(lead_entry.get('id', ''))
                if not fb_lead_id:
                    continue

                # Dedup check
                if Lead.query.filter_by(facebook_lead_id=fb_lead_id).first():
                    skipped_count += 1
                    continue

                # Parse field_data: [{"name": "full_name", "values": ["John"]}, ...]
                fields = {f['name']: (f['values'][0] if f.get('values') else '')
                          for f in lead_entry.get('field_data', [])}

                name = (fields.get('full_name') or fields.get('name') or
                        fields.get('first_name', '') + ' ' + fields.get('last_name', '')).strip() or None
                phone = (fields.get('phone_number') or fields.get('phone') or
                         fields.get('mobile') or fields.get('contact')) or None
                email = fields.get('email') or None
                city  = fields.get('city') or None
                state = fields.get('state') or None

                # Build notes from form name + any extra fields
                notes = f'Ad Form: {form_name}' if form_name else None

                lead = Lead(
                    name=name,
                    contact=phone,
                    email=email,
                    city=city,
                    state=state,
                    notes=notes,
                    origin='Facebook',
                    stage='New Lead',
                    lead_type='Enquiry',
                    facebook_lead_id=fb_lead_id,
                    owner_id=None,
                    assigned_to_id=None,
                    created_by=created_by_id,
                )
                db.session.add(lead)
                new_count += 1

            db.session.commit()

            # Follow pagination cursor
            next_page = data.get('paging', {}).get('next')
            if next_page:
                url = next_page
                params = {}  # next URL already contains all params
            else:
                break

    return new_count, skipped_count, None


@app.route('/leads/facebook/sync', methods=['POST'])
@login_required
def facebook_sync():
    """Manual sync — triggered by clicking the Sync Facebook button."""
    new_count, skipped_count, err = _do_facebook_sync(current_user.id)
    if err:
        flash(f'Facebook sync failed: {err}', 'danger')
    else:
        flash(f'Facebook sync complete: {new_count} new leads imported, {skipped_count} already existed.', 'success')
    return redirect(url_for('leads_list'))


@app.route('/api/leads/facebook-sync', methods=['GET'])
def facebook_cron_sync():
    """Cron endpoint — auto-sync Facebook leads every hour."""
    cron_secret = request.headers.get('X-Cron-Secret') or request.args.get('secret')
    expected_secret = os.getenv('CRON_SECRET')
    if not expected_secret or cron_secret != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401

    admin = User.query.filter_by(role='admin').first() or User.query.first()
    if not admin:
        return jsonify({'error': 'No users found'}), 500

    new_count, skipped_count, err = _do_facebook_sync(admin.id)
    if err:
        return jsonify({'success': False, 'error': err}), 500
    return jsonify({'success': True, 'new': new_count, 'skipped': skipped_count}), 200


@app.route('/api/leads/indiamart-sync', methods=['GET'])
def indiamart_cron_sync():
    """Cron endpoint — auto-sync IndiaMart leads every hour"""
    cron_secret = request.headers.get('X-Cron-Secret') or request.args.get('secret')
    expected_secret = os.getenv('CRON_SECRET')
    if not expected_secret or cron_secret != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401

    # Use first admin user as owner
    admin = User.query.filter_by(role='admin').first() or User.query.first()
    if not admin:
        return jsonify({'error': 'No users found'}), 500

    new_count, skipped_count, err = _do_indiamart_sync(None, admin.id)
    if err:
        return jsonify({'success': False, 'error': err}), 500
    return jsonify({'success': True, 'new': new_count, 'skipped': skipped_count}), 200


@app.route('/api/leads/indiamart-keepalive', methods=['GET'])
def indiamart_keepalive():
    """
    Cron endpoint — call every 12 hours to keep the IndiaMart token alive.
    Only refreshes the token; does NOT import leads.
    Must be called while the token is still valid (before the 24hr expiry).
    """
    cron_secret = request.headers.get('X-Cron-Secret') or request.args.get('secret')
    expected_secret = os.getenv('CRON_SECRET')
    if not expected_secret or cron_secret != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401

    from models import IndiamartToken
    token = IndiamartToken.query.first()
    if not token:
        return jsonify({'success': False, 'error': 'No token saved.'}), 400

    headers = {
        'user-agent': 'IndiaMart/13.6.4 (com.indiamart.m; build:4; iOS 16.6.0) Alamofire/5.0.0-rc.2',
        'accept': '*/*',
        'accept-language': 'en-US;q=1.0',
    }

    old_ak = token.ak_token
    _indiamart_refresh_token(token, headers)
    token = IndiamartToken.query.first()

    refreshed = token.ak_token != old_ak
    return jsonify({
        'success': True,
        'refreshed': refreshed,
        'token_valid': token.is_valid(),
        'expires_at': token.expires_at.isoformat() if token.expires_at else None,
    }), 200


# ============================================================================
# PURCHASE INVOICES
# ============================================================================

def _next_pi_serial():
    """Generate next serial number PI-001, PI-002 …"""
    last = PurchaseInvoice.query.order_by(PurchaseInvoice.id.desc()).first()
    if not last:
        return 'PI-001'
    try:
        num = int(last.serial_number.split('-')[1]) + 1
    except Exception:
        num = PurchaseInvoice.query.count() + 1
    return f'PI-{num:03d}'


@app.route('/tally')
@login_required
def tally_index():
    from models import Quote, PurchaseInvoice, Supplier, User as UserModel

    date_from       = request.args.get('date_from', '')
    date_to         = request.args.get('date_to', '')
    salesman_id     = request.args.get('salesman_id', '')
    client_name     = request.args.get('client_name', '').strip()
    supplier_id     = request.args.get('supplier_id', '')
    delivery_status = request.args.get('delivery_status', '')

    q = Quote.query.filter(Quote.status == 'Accepted')
    if date_from:
        q = q.filter(Quote.quote_date >= date_from)
    if date_to:
        q = q.filter(Quote.quote_date <= date_to)
    if salesman_id:
        q = q.filter(Quote.created_by == int(salesman_id))
    if client_name:
        q = q.filter(Quote.customer_name.ilike(f'%{client_name}%'))
    if delivery_status:
        q = q.filter(Quote.delivery_status == delivery_status)

    quotes = q.order_by(Quote.quote_date.desc()).all()

    rows = []
    for quote in quotes:
        pis = PurchaseInvoice.query.filter_by(quote_id=quote.id).all()

        if supplier_id and not any(str(pi.supplier_id) == supplier_id for pi in pis):
            continue

        sale_value    = float(quote.total or 0)
        pi_amount     = sum(float(pi.invoice_amount or 0) for pi in pis)
        pi_paid       = sum(float(pi.amount_paid    or 0) for pi in pis)
        misc          = float(quote.misc_purchases or 0)
        total_cost    = pi_amount + misc
        profit        = sale_value - total_cost
        cash_recv     = float(quote.cash_received   or 0)
        online_recv   = float(quote.amount_received or 0)
        total_recv    = cash_recv + online_recv

        rows.append({
            'quote':             quote,
            'purchase_invoices': pis,
            'sale_amount':       sale_value,
            'pi_amount':         pi_amount,
            'pi_paid':           pi_paid,
            'pi_balance':        pi_amount - pi_paid,
            'misc_purchases':    misc,
            'total_cost':        total_cost,
            'profit':            profit,
            'margin':            (profit / sale_value * 100) if sale_value > 0 else 0,
            'cash_received':     cash_recv,
            'online_received':   online_recv,
            'amount_received':   total_recv,
            'client_balance':    sale_value - total_recv,
        })

    totals = {
        'sales':             sum(r['sale_amount']     for r in rows),
        'pi_amount':         sum(r['pi_amount']       for r in rows),
        'misc':              sum(r['misc_purchases']  for r in rows),
        'total_cost':        sum(r['total_cost']      for r in rows),
        'profit':            sum(r['profit']          for r in rows),
        'pi_paid':           sum(r['pi_paid']         for r in rows),
        'pi_balance':        sum(r['pi_balance']      for r in rows),
        'cash_received':     sum(r['cash_received']   for r in rows),
        'online_received':   sum(r['online_received'] for r in rows),
        'amount_received':   sum(r['amount_received'] for r in rows),
        'client_balance':    sum(r['client_balance']  for r in rows),
        'unprocessed_count': sum(1 for r in rows if not r['purchase_invoices']),
    }

    salesmen  = UserModel.query.order_by(UserModel.username).all()
    suppliers = Supplier.query.order_by(Supplier.name).all()

    filters = {
        'date_from':       date_from,
        'date_to':         date_to,
        'salesman_id':     salesman_id,
        'client_name':     client_name,
        'supplier_id':     supplier_id,
        'delivery_status': delivery_status,
    }

    return render_template('tally/index.html', rows=rows, totals=totals,
                           salesmen=salesmen, suppliers=suppliers, filters=filters)


@app.route('/quotes/<int:id>/tally-update', methods=['POST'])
@login_required
def quote_tally_update(id):
    from models import Quote
    quote = Quote.query.get_or_404(id)
    quote.delivery_status = request.form.get('delivery_status', quote.delivery_status)
    online_recv = request.form.get('amount_received', '').strip()
    cash_recv   = request.form.get('cash_received',   '').strip()
    misc        = request.form.get('misc_purchases',  '').strip()
    quote.amount_received = float(online_recv) if online_recv else quote.amount_received
    quote.cash_received   = float(cash_recv)   if cash_recv   else quote.cash_received
    quote.misc_purchases  = float(misc)        if misc        else quote.misc_purchases
    db.session.commit()
    flash('Tally info updated.', 'success')
    return redirect(url_for('quote_view', id=id))


@app.route('/purchase-invoices')
@login_required
def purchase_invoices_list():
    supplier_filter  = request.args.get('supplier', '')
    project_filter   = request.args.get('project', '')
    type_filter      = request.args.get('invoice_type', '')
    status_filter    = request.args.get('status', '')

    query = PurchaseInvoice.query

    if supplier_filter:
        query = query.filter(PurchaseInvoice.supplier_id == supplier_filter)
    if project_filter:
        query = query.filter(PurchaseInvoice.project_id == project_filter)
    if type_filter:
        query = query.filter(PurchaseInvoice.invoice_type == type_filter)
    if status_filter:
        query = query.filter(PurchaseInvoice.status == status_filter)

    invoices  = query.order_by(PurchaseInvoice.id.desc()).all()
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    projects  = Project.query.order_by(Project.name).all()

    return render_template('purchase_invoices/list.html',
                           invoices=invoices,
                           suppliers=suppliers,
                           projects=projects,
                           supplier_filter=supplier_filter,
                           project_filter=project_filter,
                           type_filter=type_filter,
                           status_filter=status_filter)


@app.route('/purchase-invoices/new', methods=['GET', 'POST'])
@login_required
@manager_or_admin_required
def purchase_invoice_new():
    from models import Quote
    suppliers      = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    accepted_quotes = Quote.query.filter_by(status='Accepted').order_by(Quote.quote_date.desc()).all()

    if request.method == 'POST':
        supplier_id    = request.form.get('supplier_id', '').strip()
        quote_id       = request.form.get('quote_id', '').strip()
        bill_number    = request.form.get('bill_number', '').strip()
        invoice_type   = request.form.get('invoice_type', 'GST')
        invoice_amount = request.form.get('invoice_amount', '').strip()
        amount_paid    = request.form.get('amount_paid', '0').strip()
        notes          = request.form.get('notes', '').strip()
        bill_image     = request.files.get('bill_image')

        errors = []
        if not supplier_id:
            errors.append('Vendor is required.')
        if not quote_id:
            errors.append('Linked Quotation is required.')
        if not bill_number:
            errors.append('Bill Number is required.')
        if not bill_image or bill_image.filename == '':
            errors.append('Bill Image is required.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('purchase_invoices/form.html',
                                   suppliers=suppliers, accepted_quotes=accepted_quotes, invoice=None)

        bill_image_url = None
        try:
            from utils.s3_upload import S3Uploader
            from werkzeug.utils import secure_filename
            uploader  = S3Uploader()
            filename  = secure_filename(bill_image.filename)
            ext       = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            s3_key    = f"purchase-invoices/{timestamp}_{filename}"
            content_types = {'pdf': 'application/pdf', 'jpg': 'image/jpeg',
                             'jpeg': 'image/jpeg', 'png': 'image/png'}
            content_type = content_types.get(ext, 'application/octet-stream')
            uploader.s3_client.upload_fileobj(
                bill_image, uploader.bucket_name, s3_key,
                ExtraArgs={'ContentType': content_type}
            )
            bill_image_url = f"https://{uploader.bucket_name}.s3.{uploader.region}.amazonaws.com/{s3_key}"
        except Exception as e:
            flash(f'Image upload failed: {e}', 'warning')

        invoice = PurchaseInvoice(
            serial_number  = _next_pi_serial(),
            supplier_id    = int(supplier_id),
            quote_id       = int(quote_id),
            bill_number    = bill_number,
            bill_image_url = bill_image_url,
            invoice_type   = invoice_type,
            invoice_amount = float(invoice_amount) if invoice_amount else None,
            amount_paid    = float(amount_paid) if amount_paid else 0.0,
            notes          = notes or None,
            created_by     = current_user.id,
        )
        db.session.add(invoice)
        db.session.commit()
        flash(f'Purchase Invoice {invoice.serial_number} created successfully.', 'success')
        return redirect(url_for('purchase_invoices_list'))

    return render_template('purchase_invoices/form.html',
                           suppliers=suppliers, accepted_quotes=accepted_quotes, invoice=None)


@app.route('/purchase-invoices/<int:id>')
@login_required
def purchase_invoice_view(id):
    invoice = PurchaseInvoice.query.get_or_404(id)
    bill_image_presigned = None
    if invoice.bill_image_url:
        try:
            from utils.s3_upload import S3Uploader
            uploader = S3Uploader()
            s3_key = invoice.bill_image_url.split(f"{uploader.bucket_name}.s3.{uploader.region}.amazonaws.com/")[1]
            bill_image_presigned = uploader.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': uploader.bucket_name, 'Key': s3_key},
                ExpiresIn=3600
            )
        except Exception:
            bill_image_presigned = invoice.bill_image_url
    return render_template('purchase_invoices/view.html', invoice=invoice, bill_image_presigned=bill_image_presigned)


@app.route('/purchase-invoices/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@manager_or_admin_required
def purchase_invoice_edit(id):
    from models import Quote
    invoice         = PurchaseInvoice.query.get_or_404(id)
    suppliers       = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    accepted_quotes = Quote.query.filter_by(status='Accepted').order_by(Quote.quote_date.desc()).all()

    if request.method == 'POST':
        invoice.supplier_id  = int(request.form.get('supplier_id'))
        qid = request.form.get('quote_id', '').strip()
        invoice.quote_id     = int(qid) if qid else None
        invoice.bill_number  = request.form.get('bill_number', '').strip()
        invoice.invoice_type = request.form.get('invoice_type', 'GST')
        amt  = request.form.get('invoice_amount', '').strip()
        paid = request.form.get('amount_paid', '0').strip()
        invoice.invoice_amount = float(amt)  if amt  else None
        invoice.amount_paid    = float(paid) if paid else 0.0
        invoice.notes          = request.form.get('notes', '').strip() or None

        new_image = request.files.get('bill_image')
        if new_image and new_image.filename != '':
            try:
                from utils.s3_upload import S3Uploader
                from werkzeug.utils import secure_filename
                uploader  = S3Uploader()
                filename  = secure_filename(new_image.filename)
                ext       = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                s3_key    = f"purchase-invoices/{timestamp}_{filename}"
                content_types = {'pdf': 'application/pdf', 'jpg': 'image/jpeg',
                                 'jpeg': 'image/jpeg', 'png': 'image/png'}
                content_type = content_types.get(ext, 'application/octet-stream')
                uploader.s3_client.upload_fileobj(
                    new_image, uploader.bucket_name, s3_key,
                    ExtraArgs={'ContentType': content_type}
                )
                invoice.bill_image_url = f"https://{uploader.bucket_name}.s3.{uploader.region}.amazonaws.com/{s3_key}"
            except Exception as e:
                flash(f'Image upload failed: {e}', 'warning')

        db.session.commit()
        flash('Purchase Invoice updated successfully.', 'success')
        return redirect(url_for('purchase_invoice_view', id=invoice.id))

    bill_image_presigned = None
    if invoice.bill_image_url:
        try:
            from utils.s3_upload import S3Uploader
            uploader = S3Uploader()
            s3_key = invoice.bill_image_url.split(f"{uploader.bucket_name}.s3.{uploader.region}.amazonaws.com/")[1]
            bill_image_presigned = uploader.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': uploader.bucket_name, 'Key': s3_key},
                ExpiresIn=3600
            )
        except Exception:
            bill_image_presigned = invoice.bill_image_url
    return render_template('purchase_invoices/form.html',
                           suppliers=suppliers, accepted_quotes=accepted_quotes, invoice=invoice,
                           bill_image_presigned=bill_image_presigned)


@app.route('/purchase-invoices/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def purchase_invoice_delete(id):
    invoice = PurchaseInvoice.query.get_or_404(id)
    db.session.delete(invoice)
    db.session.commit()
    flash('Purchase Invoice deleted.', 'success')
    return redirect(url_for('purchase_invoices_list'))


# Quick-add vendor (inline modal)
@app.route('/api/suppliers/quick-add', methods=['POST'])
@login_required
@manager_or_admin_required
def supplier_quick_add():
    name  = request.form.get('name',  '').strip()
    phone = request.form.get('phone', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Vendor name is required.'}), 400
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number is required.'}), 400
    if Supplier.query.filter_by(name=name).first():
        return jsonify({'success': False, 'error': 'Vendor already exists.'}), 400
    supplier = Supplier(
        name=name,
        phone=phone,
        gstin=request.form.get('gstin', '').strip() or None,
        address=request.form.get('address', '').strip() or None,
        is_active=True,
    )
    db.session.add(supplier)
    db.session.commit()
    return jsonify({'success': True, 'id': supplier.id, 'name': supplier.name})


# Quick-add project (inline modal)
@app.route('/api/projects/quick-add', methods=['POST'])
@login_required
@manager_or_admin_required
def project_quick_add():
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Project name is required.'}), 400
    project = Project(
        name=name,
        status='Not Started',
        owner_id=current_user.id,
    )
    db.session.add(project)
    db.session.commit()
    return jsonify({'success': True, 'id': project.id, 'name': project.name})


# ============================================================================
# MEETINGS MODULE
# ============================================================================

MEETING_TYPES = ['Lead Visit', 'Site Survey', 'Installation', 'Follow-up', 'General']
MEETING_STATUSES = ['Scheduled', 'Checked In', 'Completed', 'Cancelled']


@app.route('/meetings')
@login_required
def meetings_list():
    """List all meetings — manager/admin see all, promotor sees own"""
    from models import Meeting, User

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    status_filter = request.args.get('status', '')
    type_filter = request.args.get('meeting_type', '')
    user_filter = request.args.get('user_id', '')

    query = Meeting.query
    if not current_user.is_manager_or_admin():
        query = query.filter(Meeting.user_id == current_user.id)
    elif user_filter:
        try:
            query = query.filter(Meeting.user_id == int(user_filter))
        except ValueError:
            pass

    if status_filter:
        query = query.filter(Meeting.status == status_filter)
    if type_filter:
        query = query.filter(Meeting.meeting_type == type_filter)
    if date_from:
        try:
            query = query.filter(Meeting.scheduled_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Meeting.scheduled_at <= datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass

    # MySQL-compatible NULL-last ordering: IS NULL sorts 0 (non-null) before 1 (null)
    meetings = query.order_by(Meeting.scheduled_at.is_(None), Meeting.scheduled_at.desc(), Meeting.created_at.desc()).all()
    users = User.query.filter_by(is_active=True).order_by(User.username).all() if current_user.is_manager_or_admin() else []

    return render_template('meetings/list.html',
                           meetings=meetings,
                           users=users,
                           meeting_types=MEETING_TYPES,
                           meeting_statuses=MEETING_STATUSES)


@app.route('/meetings/new', methods=['GET', 'POST'])
@login_required
def meeting_new():
    """Create a new meeting"""
    from models import Meeting, Lead, User

    if request.method == 'POST':
        try:
            data = request.form
            scheduled_str = data.get('scheduled_at', '').strip()
            scheduled_at = datetime.strptime(scheduled_str, '%Y-%m-%dT%H:%M') if scheduled_str else None

            lead_id = int(data.get('lead_id')) if data.get('lead_id') else None
            project_id = int(data.get('project_id')) if data.get('project_id') else None
            user_id = int(data.get('user_id')) if data.get('user_id') else current_user.id

            meeting = Meeting(
                title=data.get('title', '').strip(),
                user_id=user_id,
                created_by=current_user.id,
                lead_id=lead_id,
                project_id=project_id,
                client_name=data.get('client_name', '').strip() or None,
                client_phone=data.get('client_phone', '').strip() or None,
                client_address=data.get('client_address', '').strip() or None,
                meeting_type=data.get('meeting_type', 'Lead Visit'),
                scheduled_at=scheduled_at,
                notes=data.get('notes', '').strip() or None,
                status='Scheduled',
            )
            db.session.add(meeting)
            db.session.commit()
            flash(f'Meeting "{meeting.title}" created successfully!', 'success')
            return redirect(url_for('meeting_view', id=meeting.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating meeting: {str(e)}', 'danger')

    leads = Lead.query.order_by(Lead.name).all()
    projects = Project.query.order_by(Project.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.username).all() if current_user.is_manager_or_admin() else [current_user]
    return render_template('meetings/form.html', title='New Meeting',
                           meeting=None, leads=leads, projects=projects,
                           users=users, meeting_types=MEETING_TYPES)


@app.route('/meetings/<int:id>')
@login_required
def meeting_view(id):
    """View meeting details"""
    from models import Meeting
    meeting = Meeting.query.get_or_404(id)
    if not current_user.is_manager_or_admin() and meeting.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('meetings_list'))
    return render_template('meetings/view.html', meeting=meeting)


@app.route('/meetings/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def meeting_edit(id):
    """Edit a meeting"""
    from models import Meeting, Lead, User
    meeting = Meeting.query.get_or_404(id)

    if not current_user.is_manager_or_admin() and meeting.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('meetings_list'))

    if request.method == 'POST':
        try:
            data = request.form
            scheduled_str = data.get('scheduled_at', '').strip()
            meeting.scheduled_at = datetime.strptime(scheduled_str, '%Y-%m-%dT%H:%M') if scheduled_str else None
            meeting.title = data.get('title', '').strip()
            meeting.meeting_type = data.get('meeting_type', 'Lead Visit')
            meeting.lead_id = int(data.get('lead_id')) if data.get('lead_id') else None
            meeting.project_id = int(data.get('project_id')) if data.get('project_id') else None
            if current_user.is_manager_or_admin():
                meeting.user_id = int(data.get('user_id')) if data.get('user_id') else meeting.user_id
            meeting.client_name = data.get('client_name', '').strip() or None
            meeting.client_phone = data.get('client_phone', '').strip() or None
            meeting.client_address = data.get('client_address', '').strip() or None
            meeting.notes = data.get('notes', '').strip() or None
            meeting.outcome = data.get('outcome', '').strip() or None
            meeting.status = data.get('status', meeting.status)
            meeting.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Meeting updated successfully!', 'success')
            return redirect(url_for('meeting_view', id=meeting.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating meeting: {str(e)}', 'danger')

    leads = Lead.query.order_by(Lead.name).all()
    projects = Project.query.order_by(Project.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.username).all() if current_user.is_manager_or_admin() else [current_user]
    return render_template('meetings/form.html', title='Edit Meeting',
                           meeting=meeting, leads=leads, projects=projects,
                           users=users, meeting_types=MEETING_TYPES,
                           meeting_statuses=MEETING_STATUSES)


@app.route('/meetings/<int:id>/delete', methods=['POST'])
@login_required
def meeting_delete(id):
    """Delete a meeting"""
    from models import Meeting
    meeting = Meeting.query.get_or_404(id)
    if not current_user.is_manager_or_admin() and meeting.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('meetings_list'))
    try:
        db.session.delete(meeting)
        db.session.commit()
        flash('Meeting deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('meetings_list'))


@app.route('/meetings/<int:id>/checkin', methods=['POST'])
@login_required
def meeting_checkin(id):
    """AJAX: GPS check-in for a meeting"""
    from models import Meeting
    meeting = Meeting.query.get_or_404(id)
    if meeting.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Only the assigned person can check in'}), 403
    try:
        meeting.check_in_lat = float(request.form.get('lat'))
        meeting.check_in_lng = float(request.form.get('lng'))
        meeting.check_in_accuracy = float(request.form.get('accuracy', 0))
        meeting.check_in_address = request.form.get('address', '')[:500]
        meeting.check_in_time = datetime.utcnow()
        meeting.status = 'Checked In'
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/meetings/<int:id>/checkout', methods=['POST'])
@login_required
def meeting_checkout(id):
    """AJAX: GPS check-out for a meeting"""
    from models import Meeting
    meeting = Meeting.query.get_or_404(id)
    if meeting.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Only the assigned person can check out'}), 403
    try:
        meeting.check_out_lat = float(request.form.get('lat', 0)) or None
        meeting.check_out_lng = float(request.form.get('lng', 0)) or None
        meeting.check_out_time = datetime.utcnow()
        meeting.outcome = request.form.get('outcome', '').strip() or meeting.outcome
        meeting.status = 'Completed'
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/meetings/<int:id>/upload-photo', methods=['POST'])
@login_required
def meeting_upload_photo(id):
    """Upload a photo for a meeting"""
    from models import Meeting, MeetingPhoto
    meeting = Meeting.query.get_or_404(id)
    if not current_user.is_manager_or_admin() and meeting.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    file = request.files.get('photo')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    try:
        import boto3
        from werkzeug.utils import secure_filename
        bucket = os.getenv('AWS_BUCKET_NAME', 'glassyimages')
        region = os.getenv('AWS_REGION', 'ap-south-1')
        s3 = boto3.client('s3', region_name=region)
        filename = f"meeting_photos/{meeting.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{secure_filename(file.filename)}"
        s3.upload_fileobj(file, bucket, filename, ExtraArgs={'ContentType': file.content_type or 'image/jpeg'})
        url = f"https://{bucket}.s3.{region}.amazonaws.com/{filename}"

        photo = MeetingPhoto(
            meeting_id=meeting.id,
            photo_url=url,
            caption=request.form.get('caption', '').strip() or None,
            uploaded_by=current_user.id,
        )
        db.session.add(photo)
        db.session.commit()
        return jsonify({'success': True, 'url': url, 'photo_id': photo.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/meetings/<int:id>/delete-photo/<int:photo_id>', methods=['POST'])
@login_required
def meeting_delete_photo(id, photo_id):
    """Delete a meeting photo"""
    from models import MeetingPhoto
    photo = MeetingPhoto.query.get_or_404(photo_id)
    if photo.meeting_id != id:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    try:
        db.session.delete(photo)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/meetings/map')
@login_required
@manager_or_admin_required
def meetings_map():
    """Map view of all field visits (manager/admin only)"""
    from models import Meeting, User

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    user_filter = request.args.get('user_id', '')

    query = Meeting.query.filter(Meeting.check_in_lat.isnot(None))
    if user_filter:
        try:
            query = query.filter(Meeting.user_id == int(user_filter))
        except ValueError:
            pass
    if date_from:
        try:
            query = query.filter(Meeting.check_in_time >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Meeting.check_in_time <= datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass

    meetings = query.order_by(Meeting.check_in_time.desc()).all()
    users = User.query.filter_by(is_active=True).order_by(User.username).all()

    meetings_json = []
    for m in meetings:
        ist_time = (m.check_in_time + timedelta(hours=5, minutes=30)).strftime('%d %b %Y, %I:%M %p') if m.check_in_time else ''
        meetings_json.append({
            'id': m.id,
            'title': m.title,
            'user': m.user.username if m.user else '',
            'type': m.meeting_type,
            'client': m.client_name or (m.lead.name if m.lead else ''),
            'lat': m.check_in_lat,
            'lng': m.check_in_lng,
            'address': m.check_in_address or '',
            'time': ist_time,
            'status': m.status,
        })

    return render_template('meetings/map.html',
                           meetings_json=meetings_json,
                           users=users,
                           total=len(meetings))


# ============================================================================
# RUN APPLICATION
# ============================================================================

def _run_migrations():
    """Safe ALTER TABLE migrations for columns added after initial schema creation."""
    migrations = [
        "ALTER TABLE leads ADD COLUMN facebook_lead_id VARCHAR(50) NULL UNIQUE",
    ]
    with db.engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(db.text(sql))
                conn.commit()
            except Exception:
                pass  # Column already exists — ignore


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        _run_migrations()
    app.run(debug=True, host='0.0.0.0', port=8080)
