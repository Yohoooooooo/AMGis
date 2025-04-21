from app import create_app, db
from app.models import User
import os
import sys

app = create_app()

def init_db():
    """Initialize the database and create admin/test users"""
    with app.app_context():
        try:
            # Create all tables
            db.create_all()

            # Check if admin user already exists
            admin = User.query.filter_by(username='admin').first()
            if admin is None:
                # Create admin user
                admin = User(username='admin', role='admin', is_active=True)
                admin.set_password('adminpassword')
                db.session.add(admin)
                db.session.commit()
                print("Admin account created successfully.")
            else:
                # Force update admin password to ensure it works
                admin.set_password('adminpassword')
                db.session.commit()
                print("Admin account password reset.")

            # Create a test user
            test_user = User.query.filter_by(username='test').first()
            if test_user is None:
                test_user = User(username='test', role='employee', is_active=True)
                test_user.set_password('testpassword')
                db.session.add(test_user)
                db.session.commit()
                print("Test user account created successfully.")
            else:
                # Force update test user password
                test_user.set_password('testpassword')
                db.session.commit()
                print("Test user password reset.")

            print("Database initialized successfully.")

        except Exception as e:
            print(f"Error initializing database: {e}")
            sys.exit(1)


if __name__ == '__main__':
    # Create upload directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app/static/uploads'), exist_ok=True)

    # Initialize database and create admin/employee accounts
    init_db()

    # Run the application
    app.run(debug=True)
