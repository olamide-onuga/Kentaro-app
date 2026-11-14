import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'), override=True)

import socket
_orig_getaddrinfo = socket.getaddrinfo
def _custom_getaddrinfo(host, port, *args, **kwargs):
    if host and 'dpg-davu8krncjis73fpdf2g-a.oregon-postgres.render.com' in host:
        return _orig_getaddrinfo('35.227.164.209', port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = _custom_getaddrinfo

from app import create_app
from app.extensions import db
from app.models.user import User, Role, CoachProfile, ClientProfile

app = create_app()

with app.app_context():
    print("--- 1. Ensuring Roles Exist ---")
    role_names = ['admin', 'coach', 'client', 'superadmin']
    roles_by_name = {}
    for r_name in role_names:
        r = Role.query.filter_by(name=r_name).first()
        if not r:
            r = Role(name=r_name)
            db.session.add(r)
            db.session.flush()
            print(f"Created role: {r_name} (id={r.id})")
        else:
            print(f"Role already exists: {r_name} (id={r.id})")
        roles_by_name[r_name] = r
    db.session.commit()

    print("\n--- 2. Fixing Existing Users Roles ---")
    users = User.query.all()
    for u in users:
        # If user has a coach profile, ensure role is coach
        if u.coach_profile and (not u.role or u.role.name != 'coach'):
            u.role = roles_by_name['coach']
            print(f"Assigned 'coach' role to user {u.email} (id={u.id})")
        # If user has a client profile, ensure role is client
        elif u.client_profile and (not u.role or u.role.name != 'client'):
            u.role = roles_by_name['client']
            print(f"Assigned 'client' role to user {u.email} (id={u.id})")
        # Ensure email is confirmed for existing test accounts
        if not u.is_email_confirmed:
            u.is_email_confirmed = True
            print(f"Marked email as confirmed for {u.email}")
    db.session.commit()

    print("\n--- 3. Creating / Updating Test Admin Account ---")
    admin_email = "admin@kentaro.com"
    admin_user = User.query.filter_by(email=admin_email).first()
    if not admin_user:
        admin_user = User(
            email=admin_email,
            role=roles_by_name['admin'],
            is_admin=True,
            is_active=True,
            is_email_confirmed=True
        )
        admin_user.password = "AdminPassword123!"
        db.session.add(admin_user)
        print(f"Created test admin user: {admin_email}")
    else:
        admin_user.role = roles_by_name['admin']
        admin_user.is_admin = True
        admin_user.is_active = True
        admin_user.is_email_confirmed = True
        admin_user.password = "AdminPassword123!"
        print(f"Updated existing test admin user: {admin_email}")
    db.session.commit()

    print("\n--- 4. Verification Summary ---")
    for u in User.query.all():
        print(f"User #{u.id}: {u.email} | role={u.role.name if u.role else None} | is_admin={u.is_admin} | is_coach={u.is_coach} | is_client={u.is_client}")

    print("\nSUCCESS: All roles and admin seeded successfully!")
