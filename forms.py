from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, DateField, TextAreaField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional, ValidationError
from models import User
from datetime import datetime


class LoginForm(FlaskForm):
    """Login form"""
    username = StringField('Username or Email', validators=[DataRequired(), Length(min=3, max=120)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')


class UserForm(FlaskForm):
    """User creation/edit form"""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[Length(min=6, max=100)])
    confirm_password = PasswordField('Confirm Password', validators=[EqualTo('password', message='Passwords must match')])
    role = SelectField('Role', choices=[('Admin', 'Admin'), ('Manager', 'Manager'), ('Promotor', 'User')], validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)
    
    def __init__(self, user_id=None, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.user_id = user_id
    
    def validate_username(self, field):
        user = User.query.filter_by(username=field.data).first()
        if user and (self.user_id is None or user.id != self.user_id):
            raise ValidationError('Username already exists.')
    
    def validate_email(self, field):
        user = User.query.filter_by(email=field.data).first()
        if user and (self.user_id is None or user.id != self.user_id):
            raise ValidationError('Email already exists.')


class ProjectForm(FlaskForm):
    """Project creation/edit form"""
    name = StringField('Project Name', validators=[DataRequired(), Length(max=200)])
    owner_id = SelectField('Project Owner', coerce=int, validators=[DataRequired()])
    start_date = DateField('Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    expected_end_date = DateField('Expected End Date', validators=[DataRequired()], format='%Y-%m-%d')
    actual_end_date = DateField('Actual End Date', validators=[Optional()], format='%Y-%m-%d')
    status = SelectField('Status', 
                        choices=[('Not Started', 'Not Started'), 
                                ('In Progress', 'In Progress'), 
                                ('Completed', 'Completed'), 
                                ('On Hold', 'On Hold')],
                        validators=[DataRequired()])
    comments = TextAreaField('Comments', validators=[Optional()])
    
    def validate_expected_end_date(self, field):
        if self.start_date.data and field.data:
            if field.data < self.start_date.data:
                raise ValidationError('Expected end date must be after start date.')
    
    def validate_actual_end_date(self, field):
        if field.data and self.start_date.data:
            if field.data < self.start_date.data:
                raise ValidationError('Actual end date must be after start date.')


class TaskTemplateForm(FlaskForm):
    """Task template creation/edit form"""
    name = StringField('Task Name', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional()])
    category = StringField('Category', validators=[Optional(), Length(max=50)])
    priority = SelectField('Priority', 
                          choices=[('High', 'High'), ('Medium', 'Medium'), ('Low', 'Low')],
                          validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)


class TaskAssignmentForm(FlaskForm):
    """Task assignment form"""
    template_id = SelectField('Task Template', coerce=int, validators=[DataRequired()])
    task_name = StringField('Task Name', validators=[Optional(), Length(max=200)])
    promotor_id = SelectField('Assign to User', coerce=int, validators=[DataRequired()])
    project_id = SelectField('Link to Project (Optional)', coerce=int, validators=[Optional()])
    due_date = DateField('Due Date', validators=[DataRequired()], format='%Y-%m-%d')
    priority = SelectField('Priority', 
                          choices=[('High', 'High'), ('Medium', 'Medium'), ('Low', 'Low')],
                          validators=[DataRequired()])
    comments = TextAreaField('Comments', validators=[Optional()])


class TaskUpdateForm(FlaskForm):
    """Task update form"""
    status = SelectField('Status', 
                        choices=[('Pending', 'Pending'), 
                                ('In Progress', 'In Progress'), 
                                ('Completed', 'Completed'),
                                ('Overdue', 'Overdue')],
                        validators=[DataRequired()])
    comments = TextAreaField('Comments', validators=[Optional()])


class DailyUpdateForm(FlaskForm):
    """Daily update form"""
    project_id = SelectField('Project', coerce=int, validators=[Optional()])
    is_general = BooleanField('General Update (not project-specific)')
    update_text = TextAreaField('Update', validators=[DataRequired(), Length(min=10, max=2000)], 
                                render_kw={"rows": 6, "placeholder": "What did you work on today? What progress did you make?"})
    
    def validate(self, extra_validators=None):
        """Custom validation to ensure either project_id or is_general is set"""
        if not super(DailyUpdateForm, self).validate(extra_validators):
            return False
        
        # If is_general is checked, project_id should be ignored
        if self.is_general.data:
            self.project_id.data = None
            return True
        
        # If is_general is not checked, project_id must be set
        if not self.project_id.data or self.project_id.data == 0:
            self.project_id.errors.append('Please select a project or check "General Update"')
            return False
        
        return True

