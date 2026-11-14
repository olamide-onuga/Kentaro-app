import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'), override=True)

from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    print(f"Connecting to database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    db.create_all()
    print("SUCCESS: All database tables created!")
    
    from app.models.user import User, Role
    roles_map = {}
    for r_name in ['admin', 'coach', 'client', 'superadmin']:
        r = Role.query.filter_by(name=r_name).first()
        if not r:
            r = Role(name=r_name)
            db.session.add(r)
            db.session.flush()
        roles_map[r_name] = r
    db.session.commit()
    print("SUCCESS: Standard roles initialized!")
    
    admin_user_exists = User.query.join(Role).filter(Role.name.in_(['superadmin', 'admin'])).first()
    default_admin_email = os.environ.get('SUPERADMIN_EMAIL', 'admin@kentaro.com').strip().lower()
    default_admin_pass = os.environ.get('SUPERADMIN_PASSWORD', 'AdminPassword123!')

    existing_default = User.query.filter(db.func.lower(User.email) == default_admin_email).first()
    if existing_default:
        existing_default.role = roles_map['superadmin']
        existing_default.is_admin = True
        existing_default.is_active = True
        existing_default.is_email_confirmed = True
        existing_default.admin_status = 'active'
        db.session.commit()
        print(f"SUCCESS: Superadmin active for '{default_admin_email}'")
    elif not admin_user_exists:
        superadmin = User(
            email=default_admin_email,
            role=roles_map['superadmin'],
            is_admin=True,
            is_active=True,
            is_email_confirmed=True,
            admin_status='active',
            display_name='Super Admin'
        )
        superadmin.password = default_admin_pass
        db.session.add(superadmin)
        db.session.commit()
        print(f"SUCCESS: Default Superadmin account initialized: {default_admin_email}")
    
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print(f"Total tables present: {len(tables)}")
    print("Tables:", ", ".join(tables))
