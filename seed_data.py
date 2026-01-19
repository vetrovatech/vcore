"""
Database seeding script to create initial admin user and sample data
"""
from app import app, db
from models import User, Project, TaskTemplate
from datetime import datetime, timedelta

def seed_database():
    """Seed the database with initial data"""
    with app.app_context():
        # Create tables
        print("Creating database tables...")
        db.create_all()
        
        # Check if admin already exists
        admin = User.query.filter_by(username='admin').first()
        if admin:
            print("✅ Admin user already exists")
        else:
            # Create admin user
            print("Creating admin user...")
            admin = User(
                username='admin',
                email='admin@glassy.in',
                role='Admin',
                is_active=True
            )
            admin.set_password('admin123')  # Change this password!
            db.session.add(admin)
            print("✅ Admin user created (username: admin, password: admin123)")
        
        # Create sample manager
        manager = User.query.filter_by(username='manager').first()
        if not manager:
            print("Creating sample manager...")
            manager = User(
                username='manager',
                email='manager@glassy.in',
                role='Manager',
                is_active=True
            )
            manager.set_password('manager123')
            db.session.add(manager)
            print("✅ Manager user created (username: manager, password: manager123)")
        
        # Create sample promotor
        promotor = User.query.filter_by(username='promotor1').first()
        if not promotor:
            print("Creating sample promotor...")
            promotor = User(
                username='promotor1',
                email='promotor1@glassy.in',
                role='Promotor',
                is_active=True
            )
            promotor.set_password('promotor123')
            db.session.add(promotor)
            print("✅ Promotor user created (username: promotor1, password: promotor123)")
        
        db.session.commit()
        
        # Create sample task templates
        if TaskTemplate.query.count() == 0:
            print("Creating sample task templates...")
            templates = [
                TaskTemplate(
                    name='Weekly Sales Report',
                    description='Submit weekly sales report with all client interactions',
                    category='Sales',
                    priority='High',
                    is_active=True,
                    created_by=admin.id
                ),
                TaskTemplate(
                    name='Client Follow-up',
                    description='Follow up with pending clients and update status',
                    category='Sales',
                    priority='Medium',
                    is_active=True,
                    created_by=admin.id
                ),
                TaskTemplate(
                    name='Market Survey',
                    description='Conduct market survey in assigned territory',
                    category='Field Work',
                    priority='Medium',
                    is_active=True,
                    created_by=admin.id
                ),
                TaskTemplate(
                    name='Installation Verification',
                    description='Verify completed installations and collect feedback',
                    category='Field Work',
                    priority='High',
                    is_active=True,
                    created_by=admin.id
                ),
                TaskTemplate(
                    name='Social Media Updates',
                    description='Post updates on social media channels',
                    category='Marketing',
                    priority='Low',
                    is_active=True,
                    created_by=admin.id
                )
            ]
            db.session.bulk_save_objects(templates)
            print(f"✅ Created {len(templates)} task templates")
        
        # Create sample project
        if Project.query.count() == 0:
            print("Creating sample project...")
            project = Project(
                name='Corporate Office - DGU Installation',
                owner_id=admin.id,
                start_date=datetime.now().date(),
                expected_end_date=(datetime.now() + timedelta(days=30)).date(),
                status='In Progress',
                comments='High-priority corporate client project'
            )
            db.session.add(project)
            print("✅ Created sample project")
        
        db.session.commit()
        
        print("\n" + "="*50)
        print("✅ Database seeded successfully!")
        print("="*50)
        print("\nLogin credentials:")
        print("  Admin    - username: admin, password: admin123")
        print("  Manager  - username: manager, password: manager123")
        print("  Promotor - username: promotor1, password: promotor123")
        print("\n⚠️  IMPORTANT: Change these passwords in production!")
        print("="*50)

if __name__ == '__main__':
    seed_database()
