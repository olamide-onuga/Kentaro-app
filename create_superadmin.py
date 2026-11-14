import os
import sys
import argparse
import getpass
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'), override=True)

from app import create_app
from app.extensions import db
from app.models.user import User, Role

def create_superadmin(email=None, password=None, display_name=None):
    app = create_app()
    with app.app_context():
        # Ensure database tables exist
        db.create_all()

        # Ensure all standard roles exist
        roles = {}
        for r_name in ['admin', 'coach', 'client', 'superadmin']:
            r = Role.query.filter_by(name=r_name).first()
            if not r:
                r = Role(name=r_name)
                db.session.add(r)
                db.session.flush()
            roles[r_name] = r
        db.session.commit()

        # Interactive prompts if arguments not provided
        if not email:
            try:
                email = input("Enter superadmin email: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled.")
                return False
        
        email = email.strip().lower()
        if not email or '@' not in email:
            print("Error: A valid email address is required.")
            return False

        if not password:
            try:
                password = getpass.getpass("Enter password: ").strip()
                confirm = getpass.getpass("Confirm password: ").strip()
                if password != confirm:
                    print("Error: Passwords do not match.")
                    return False
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled.")
                return False

        if not password or len(password) < 6:
            print("Error: Password must be at least 6 characters long.")
            return False

        if not display_name:
            display_name = "Super Admin"

        # Check if user already exists
        user = User.query.filter_by(email=email).first()
        if user:
            user.role = roles['superadmin']
            user.is_admin = True
            user.is_active = True
            user.is_email_confirmed = True
            user.admin_status = 'active'
            user.display_name = display_name
            user.password = password
            db.session.commit()
            print(f"\n[SUCCESS] Existing user '{email}' has been promoted to SUPERADMIN!")
        else:
            user = User(
                email=email,
                role=roles['superadmin'],
                is_admin=True,
                is_active=True,
                is_email_confirmed=True,
                admin_status='active',
                display_name=display_name
            )
            user.password = password
            db.session.add(user)
            db.session.commit()
            print(f"\n[SUCCESS] New SUPERADMIN user created: '{email}'!")

        print(f"Details:")
        print(f" - Email:        {user.email}")
        print(f" - Role:         {user.role.name}")
        print(f" - Superadmin:   {user.is_superadmin}")
        print(f" - Is Admin:     {user.is_admin}")
        print(f" - Login URL:    /auth/login")
        print(f" - Superadmin:   /superadmin/dashboard")
        return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Create or promote a Super Admin user.")
    parser.add_argument('--email', '-e', help="Superadmin email address")
    parser.add_argument('--password', '-p', help="Superadmin password")
    parser.add_argument('--name', '-n', help="Display name (default: Super Admin)")
    
    args = parser.parse_args()
    success = create_superadmin(email=args.email, password=args.password, display_name=args.name)
    sys.exit(0 if success else 1)
