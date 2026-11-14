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
    print("SUCCESS: All database tables created in PostgreSQL!")
    
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print(f"Total tables present: {len(tables)}")
    print("Tables:", ", ".join(tables))
