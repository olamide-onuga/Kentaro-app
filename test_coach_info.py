import os
from dotenv import load_dotenv
load_dotenv('.env')
from app import create_app
from app.models.user import User

app = create_app()
with app.app_context():
    coach = User.query.filter_by(email='onanuga89@gmail.com').first()
    if not coach:
        print('Coach not found')
    else:
        print('Email:', coach.email)
        print('Role name:', coach.role.name if coach.role else 'None')
        print('is_admin:', coach.is_admin)
        print('is_coach property:', coach.is_coach)
        print('coach_profile exists:', bool(coach.coach_profile))
        print('is_client property:', coach.is_client)
        print('client_profile exists:', bool(coach.client_profile))
