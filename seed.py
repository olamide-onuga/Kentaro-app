import os
from app import create_app
from app.extensions import db
from app.models.user import User, Role, CoachProfile, ClientProfile

app = create_app('development')

def seed():
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Create roles
        roles = ['superadmin', 'coach', 'client']
        for r in roles:
            if not Role.query.filter_by(name=r).first():
                role = Role(name=r)
                db.session.add(role)
        db.session.commit()
        
        superadmin_role = Role.query.filter_by(name='superadmin').first()
        coach_role = Role.query.filter_by(name='coach').first()
        client_role = Role.query.filter_by(name='client').first()
        
        # Create Super Admin
        if not User.query.filter_by(email='admin@kentaro.test').first():
            admin = User(email='admin@kentaro.test', role=superadmin_role)
            admin.password = 'password'
            db.session.add(admin)
            
        # Create Demo Coach
        coach_user = User.query.filter_by(email='coach@kentaro.test').first()
        if not coach_user:
            coach_user = User(email='coach@kentaro.test', role=coach_role)
            coach_user.password = 'password'
            db.session.add(coach_user)
            db.session.commit() # Commit to get ID
            
            coach_profile = CoachProfile(
                user_id=coach_user.id,
                first_name='Demo',
                last_name='Coach',
                bio='Expert calisthenics and strength coach.',
                specialization='Calisthenics',
                experience_years=5,
                location='New York',
                timezone='UTC'
            )
            db.session.add(coach_profile)
            db.session.commit()
        else:
            coach_profile = coach_user.coach_profile
            
        # Create Demo Client
        if not User.query.filter_by(email='client@kentaro.test').first():
            client_user = User(email='client@kentaro.test', role=client_role)
            client_user.password = 'password'
            db.session.add(client_user)
            db.session.commit()
            
            client_profile = ClientProfile(
                user_id=client_user.id,
                coach_id=coach_profile.id,
                first_name='Demo',
                last_name='Client',
                timezone='UTC'
            )
            db.session.add(client_profile)
            
        db.session.commit()
        print("Database seeded successfully!")

if __name__ == '__main__':
    seed()
