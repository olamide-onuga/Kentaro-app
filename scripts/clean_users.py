"""Utility script to delete all non‑test users from the database.

Run with:
    python -m scripts.clean_users
"""
import os
import sys

# Ensure the project root is on PYTHONPATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from app import create_app
from app.extensions import db
from app.models.user import User

app = create_app(os.getenv('FLASK_CONFIG', 'default'))

with app.app_context():
    # Identify test users (email ends with .test)
    test_users = User.query.filter(User.email.like('%.test')).all()
    test_ids = {u.id for u in test_users}

    # Delete all other users
    deleted = User.query.filter(~User.id.in_(test_ids)).delete(synchronize_session=False)
    db.session.commit()
    print(f"Deleted {deleted} non‑test users.")
