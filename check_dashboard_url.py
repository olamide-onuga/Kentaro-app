import os
from dotenv import load_dotenv
load_dotenv('.env')
from app import create_app
from app.routes.auth import _get_dashboard_url
from app.models.user import User

app = create_app()
with app.app_context():
    coach = User.query.filter_by(email='onanuga89@gmail.com').first()
    if coach:
        from flask import url_for
        # need request context for url_for
        with app.test_request_context():
            print('Dashboard URL:', _get_dashboard_url(coach))
    else:
        print('Coach not found')
