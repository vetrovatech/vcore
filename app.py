from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
import os
import pymysql

# Install PyMySQL as MySQLdb for MySQL compatibility
pymysql.install_as_MySQLdb()

from models import db, User, Project, TaskTemplate, PromotorTask, DailyUpdate, Product, Quote, QuoteItem, Supplier, GlassType, SupplierPricing, Reminder
from config import config
from forms import (LoginForm, UserForm, ProjectForm, TaskTemplateForm, 
                   TaskAssignmentForm, TaskUpdateForm, DailyUpdateForm, ProductForm)
from utils.auth import admin_required, manager_or_admin_required
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
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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
            
            # Redirect to next page or dashboard
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
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
    # Get filter parameters
    status_filter = request.args.get('status', '')
    owner_filter = request.args.get('owner', '')
    
    # Build query
    query = Project.query
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    if owner_filter:
        query = query.filter_by(owner_id=int(owner_filter))
    
    projects = query.order_by(Project.created_at.desc()).all()
    
    # Get all users for filter dropdown
    users = User.query.filter_by(is_active=True).all()
    
    return render_template('projects/list.html', projects=projects, users=users)


@app.route('/projects/new', methods=['GET', 'POST'])
@manager_or_admin_required
def project_new():
    """Create new project"""
    form = ProjectForm()
    
    # Populate owner choices with managers and admins
    form.owner_id.choices = [(u.id, u.username) for u in User.query.filter(
        User.role.in_(['Admin', 'Manager']), User.is_active == True
    ).all()]
    
    if form.validate_on_submit():
        project = Project(
            name=form.name.data,
            owner_id=form.owner_id.data,
            start_date=form.start_date.data,
            expected_end_date=form.expected_end_date.data,
            actual_end_date=form.actual_end_date.data,
            status=form.status.data,
            comments=form.comments.data
        )
        db.session.add(project)
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
    
    # Populate owner choices with managers and admins
    form.owner_id.choices = [(u.id, u.username) for u in User.query.filter(
        User.role.in_(['Admin', 'Manager']), User.is_active == True
    ).all()]
    
    if form.validate_on_submit():
        project.name = form.name.data
        project.owner_id = form.owner_id.data
        project.start_date = form.start_date.data
        project.expected_end_date = form.expected_end_date.data
        project.actual_end_date = form.actual_end_date.data
        project.status = form.status.data
        project.comments = form.comments.data
        project.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Project "{project.name}" updated successfully!', 'success')
        return redirect(url_for('projects_list'))
    
    return render_template('projects/form.html', form=form, title='Edit Project', project=project)


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
    
    # Get quotes ordered by date (newest first)
    quotes = query.order_by(Quote.quote_date.desc()).all()
    
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
                invoice_to=data.get('invoice_to'),
                dispatch_to=data.get('dispatch_to'),
                self_pickup=bool(data.get('self_pickup')),
                delivery_charges=float(data.get('delivery_charges', 0)),
                installation_charges=float(data.get('installation_charges', 0)),
                freight_charges=float(data.get('freight_charges', 0)),
                transport_charges=float(data.get('transport_charges', 0)),
                cutout_charges=float(data.get('cutout_charges', 0)),
                holes_charges=float(data.get('holes_charges', 0)),
                shape_cutting_charges=float(data.get('shape_cutting_charges', 0)),
                jumbo_size_charges=float(data.get('jumbo_size_charges', 0)),
                template_charges=float(data.get('template_charges', 0)),
                handling_charges=float(data.get('handling_charges', 0)),
                polish_charges=float(data.get('polish_charges', 0)),
                document_charges=float(data.get('document_charges', 0)),
                frosted_charges=float(data.get('frosted_charges', 0)),
                gst_percentage=float(data.get('gst_percentage', 18)),
                payment_terms=data.get('payment_terms'),
                status=data.get('status', 'Draft'),
                quote_type=data.get('quote_type', 'B2B'),
                created_by=current_user.id
            )
            
            db.session.add(quote)
            db.session.flush()  # Get quote ID
            
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
                    item_number=int(item_data.get('item_number', index + 1)),
                    particular=particular,
                    actual_width=float(item_data.get('actual_width')) if item_data.get('actual_width') else None,
                    actual_height=float(item_data.get('actual_height')) if item_data.get('actual_height') else None,
                    chargeable_width=float(item_data.get('chargeable_width')) if item_data.get('chargeable_width') else None,
                    chargeable_height=float(item_data.get('chargeable_height')) if item_data.get('chargeable_height') else None,
                    unit=item_data.get('unit', 'MM'),
                    chargeable_extra=int(item_data.get('chargeable_extra', 30)),
                    quantity=int(item_data.get('quantity', 1)) if not is_group else 1,
                    rate_sqper=float(item_data.get('rate_sqper', 0)) if not is_group else 0,
                    total=float(item_data.get('total', 0)) if not is_group else 0,
                    hole=int(item_data.get('hole', 0)) if not is_group else 0,
                    cutout=int(item_data.get('cutout', 0)) if not is_group else 0
                )
                
                # Calculate unit square if dimensions provided
                if item.chargeable_width and item.chargeable_height:
                    item.calculate_unit_square()
                
                # Calculate total if not a group
                if not is_group:
                    item.calculate_total()
                
                db.session.add(item)
                db.session.flush()  # Get item ID
                
                # Store mapping: form index -> database ID
                parent_id_map[index] = item.id
                
                # If this is a group, also store its group identifier
                if is_group:
                    # The group identifier would be in the dataset.itemId from JavaScript
                    # For now, we'll use the index as the identifier
                    index_to_group_id[index] = f"group-{item.item_number}"
            
            # Calculate quote totals
            quote.subtotal = float(data.get('subtotal', 0))
            quote.gst_amount = float(data.get('gst_amount', 0))
            quote.round_off = float(data.get('round_off', 0))
            quote.total = float(data.get('total', 0))
            
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
    from models import Quote
    quote = Quote.query.get_or_404(id)
    return render_template('quotes/view.html', quote=quote)


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
            quote.invoice_to = data.get('invoice_to')
            quote.dispatch_to = data.get('dispatch_to')
            quote.self_pickup = bool(data.get('self_pickup'))
            quote.delivery_charges = float(data.get('delivery_charges', 0))
            quote.installation_charges = float(data.get('installation_charges', 0))
            quote.freight_charges = float(data.get('freight_charges', 0))
            quote.transport_charges = float(data.get('transport_charges', 0))
            quote.cutout_charges = float(data.get('cutout_charges', 0))
            quote.holes_charges = float(data.get('holes_charges', 0))
            quote.shape_cutting_charges = float(data.get('shape_cutting_charges', 0))
            quote.jumbo_size_charges = float(data.get('jumbo_size_charges', 0))
            quote.template_charges = float(data.get('template_charges', 0))
            quote.handling_charges = float(data.get('handling_charges', 0))
            quote.polish_charges = float(data.get('polish_charges', 0))
            quote.document_charges = float(data.get('document_charges', 0))
            quote.frosted_charges = float(data.get('frosted_charges', 0))
            quote.gst_percentage = float(data.get('gst_percentage', 18))
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
                    item_number=int(item_data.get('item_number', index + 1)),
                    particular=particular,
                    actual_width=float(item_data.get('actual_width')) if item_data.get('actual_width') else None,
                    actual_height=float(item_data.get('actual_height')) if item_data.get('actual_height') else None,
                    chargeable_width=float(item_data.get('chargeable_width')) if item_data.get('chargeable_width') else None,
                    chargeable_height=float(item_data.get('chargeable_height')) if item_data.get('chargeable_height') else None,
                    unit=item_data.get('unit', 'MM'),
                    chargeable_extra=int(item_data.get('chargeable_extra', 30)),
                    quantity=int(item_data.get('quantity', 1)) if not is_group else 1,
                    rate_sqper=float(item_data.get('rate_sqper', 0)) if not is_group else 0,
                    total=float(item_data.get('total', 0)) if not is_group else 0,
                    hole=int(item_data.get('hole', 0)) if not is_group else 0,
                    cutout=int(item_data.get('cutout', 0)) if not is_group else 0
                )
                
                # Calculate unit square if dimensions provided
                if item.chargeable_width and item.chargeable_height:
                    item.calculate_unit_square()
                
                # Calculate total if not a group
                if not is_group:
                    item.calculate_total()
                
                db.session.add(item)
                db.session.flush()
                
                # Store mapping: form index -> database ID
                parent_id_map[index] = item.id
                
                # If this is a group, also store its group identifier
                if is_group:
                    index_to_group_id[index] = f"group-{item.item_number}"
            
            # Update quote totals
            quote.subtotal = float(data.get('subtotal', 0))
            quote.gst_amount = float(data.get('gst_amount', 0))
            quote.round_off = float(data.get('round_off', 0))
            quote.total = float(data.get('total', 0))
            quote.updated_at = datetime.utcnow()
            
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
    """Show print-friendly version of quote"""
    from models import Quote
    quote = Quote.query.get_or_404(id)
    return render_template('quotes/print.html', quote=quote)


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
        
        # Set reminder time to 30 minutes from now
        reminder_time = datetime.utcnow() + timedelta(minutes=30)
        
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
# RUN APPLICATION
# ============================================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8080)
