# VCore - Glassy Project Tracking System

A comprehensive project and promotor task tracking system for Glassy, built with Flask and deployed as an AWS Lambda application.

## Features

### Project Management
- Create, edit, and track live projects
- Track start date, expected end date, and actual end date
- Project owner assignment
- Status tracking (Not Started, In Progress, Completed, On Hold)
- Comments and notes

### Promotor Task Tracking
- Admin-managed task templates
- Weekly task assignment to promotors
- Automatic lag calculation for overdue tasks
- Manual rollover of incomplete tasks to next week
- Kanban-style weekly task board
- Task status tracking (Pending, In Progress, Completed, Overdue)

### User Management
- Role-based access control (Admin, Manager, Promotor)
- Admin can create and manage users
- Secure authentication with password hashing

## Technology Stack

- **Backend**: Flask, SQLAlchemy, Flask-Login
- **Frontend**: Jinja2 templates, Bootstrap 5
- **Database**: MySQL on AWS RDS
- **Deployment**: AWS Lambda (planned)

## Local Development

### Prerequisites
- Python 3.8+
- MySQL database access

### Setup

1. **Clone the repository**
```bash
cd /Users/montygupta/My/personal/bin/azure/vetrova/github/vcore
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
The `.env` file is already configured with your database credentials.

5. **Initialize database**
```bash
python seed_data.py
```

6. **Run the application**
```bash
python app.py
```

The application will be available at `http://localhost:5000`

### Default Login Credentials

After running `seed_data.py`, use these credentials:

- **Admin**: username: `admin`, password: `admin123`
- **Manager**: username: `manager`, password: `manager123`
- **Promotor**: username: `promotor1`, password: `promotor123`

⚠️ **IMPORTANT**: Change these passwords in production!

## Project Structure

```
vcore/
├── app.py                  # Main Flask application
├── models.py               # Database models
├── forms.py                # WTForms
├── config.py               # Configuration
├── seed_data.py            # Database seeding script
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables
├── utils/
│   ├── auth.py            # Authentication decorators
│   └── task_rollover.py   # Task rollover logic
└── templates/
    ├── base.html          # Base template
    ├── login.html         # Login page
    ├── dashboard.html     # Dashboard
    ├── projects/          # Project templates
    ├── tasks/             # Task templates
    ├── users/             # User management templates
    └── errors/            # Error pages
```

## Key Features Explained

### Weekly Task Rollover
- Incomplete tasks automatically move to the current week
- Lag calculation shows how many weeks a task is delayed
- Color-coded badges: Green (on-time), Yellow (1 week lag), Red (2+ weeks lag)
- Manual trigger by admin via dashboard button

### Role-Based Access
- **Admin**: Full access to all features, user management, task templates
- **Manager**: Can create projects, assign tasks, view all tasks
- **Promotor**: Can view and update their own tasks, view projects

### Project Tracking
- Track multiple projects simultaneously
- Overdue indicators for projects past expected end date
- Days remaining calculation
- Link tasks to projects (optional)

## Database Schema

### Users Table
- id, username, email, password_hash, role, is_active, created_at, updated_at

### Projects Table
- id, name, owner_id, start_date, expected_end_date, actual_end_date, status, comments, created_at, updated_at

### Task Templates Table
- id, name, description, category, priority, is_active, created_by, created_at, updated_at

### Promotor Tasks Table
- id, template_id, promotor_id, project_id, assigned_week, assigned_year, original_week, original_year, due_date, status, completed_date, lag_weeks, priority, comments, created_by, created_at, updated_at

## AWS Deployment (Planned)

The application is designed to be deployed as an AWS Lambda function with:
- API Gateway for HTTP routing
- RDS MySQL for database
- Custom domain: vcore.glassy.in

## License

© 2026 Glassy India. All rights reserved.
