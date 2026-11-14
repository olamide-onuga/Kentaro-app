import sys, os
# Ensure the project root is on PYTHONPATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()

create_sql = """
CREATE TABLE IF NOT EXISTS appointments (
    id SERIAL PRIMARY KEY,
    coach_id INTEGER NOT NULL REFERENCES coach_profiles(id),
    client_id INTEGER NOT NULL REFERENCES client_profiles(id),
    date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    title VARCHAR(128) DEFAULT '1-on-1 Coaching Call',
    client_notes TEXT,
    meeting_platform VARCHAR(32) DEFAULT 'in_app',
    meeting_url VARCHAR(255),
    status VARCHAR(32) DEFAULT 'scheduled',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

with app.app_context():
    db.session.execute(text(create_sql))
    db.session.commit()
    print('appointments table ensured')
