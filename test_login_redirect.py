import os
from dotenv import load_dotenv
load_dotenv('.env')

from app import create_app
from app.models.user import User

app = create_app()

with app.app_context():
    # Ensure DB is reachable
    admin = User.query.filter_by(email='admin@kentaro.com').first()
    print('Admin exists:', bool(admin))

with app.test_client() as client:
    # Admin login test
    admin_email = 'admin@kentaro.com'
    admin_password = 'AdminPassword123!'
    res = client.post('/auth/login', data={'email': admin_email, 'password': admin_password}, follow_redirects=False)
    print('Admin login status code:', res.status_code)
    print('Admin redirect location header:', res.headers.get('Location'))

    # Coach login test (if exists)
    coach = User.query.filter_by(email='onanuga89@gmail.com').first()
    if coach:
        # Assuming coach password is known; replace with actual password if known
        coach_password = 'coachpassword'  # placeholder
        res = client.post('/auth/login', data={'email': coach.email, 'password': coach_password}, follow_redirects=False)
        print('Coach login status code:', res.status_code)
        print('Coach redirect location header:', res.headers.get('Location'))
    else:
        print('Coach user not found')
