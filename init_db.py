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
    
    from app.models.user import Role
    for r_name in ['admin', 'coach', 'client', 'superadmin']:
        if not Role.query.filter_by(name=r_name).first():
            db.session.add(Role(name=r_name))
    db.session.commit()
    print("SUCCESS: Standard roles initialized!")
    
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print(f"Total tables present: {len(tables)}")
    print("Tables:", ", ".join(tables))
