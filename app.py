from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
import os
import pymysql

# Install PyMySQL as MySQLdb for MySQL compatibility
pymysql.install_as_MySQLdb()

from models import db, User, Project, TaskTemplate, PromotorTask, DailyUpdate, Product
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
# RUN APPLICATION
# ============================================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8080)
