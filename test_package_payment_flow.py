import os
import sys
import unittest
import uuid
import datetime as dt

sys.path.insert(0, r"C:\Users\Kentaro\.gemini\antigravity\scratch\kentaro")

from app import create_app, db
from app.models.user import User, Role, CoachProfile, ClientProfile
from app.models.coaching import CoachingPackage, ClientContract
from app.models.features import ClientPost

class PackagePaymentFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            # Coach role
            coach_role = Role.query.filter_by(name='coach').first()
            if not coach_role:
                coach_role = Role(name='coach')
                db.session.add(coach_role)

            client_role = Role.query.filter_by(name='client').first()
            if not client_role:
                client_role = Role(name='client')
                db.session.add(client_role)
            db.session.commit()

            # Create test coach
            self.coach_email = f"pkg_coach_{uuid.uuid4().hex[:6]}@test.com"
            c_user = User(
                email=self.coach_email,
                role=coach_role,
                is_active=True,
                is_email_confirmed=True
            )
            c_user.password = "Password123!"
            db.session.add(c_user)
            db.session.flush()

            coach_prof = CoachProfile(
                user_id=c_user.id,
                first_name="Marcus",
                last_name="Vance",
                bio="Elite Calisthenics Master with 10 years experience",
                specialization="Calisthenics & Strength",
                experience_years=10,
                currency="USD",
                payment_link="https://paystack.com/pay/coach-marcus"
            )
            db.session.add(coach_prof)
            db.session.flush()

            # Create coaching package with package-level payment link
            pkg = CoachingPackage(
                coach_id=coach_prof.id,
                name="12-Week Calisthenics Mastery",
                price=250.0,
                renewal_monthly_price=120.0,
                duration_weeks=12,
                currency="USD",
                payment_link="https://paystack.com/pay/marcus-12week-mastery",
                features="Custom workout plan\nWeekly video check-in\nDirect chat access",
                is_active=True
            )
            db.session.add(pkg)
            db.session.flush()
            self.package_id = pkg.id
            self.coach_profile_id = coach_prof.id

            # Create test client
            self.client_email = f"pkg_client_{uuid.uuid4().hex[:6]}@test.com"
            cl_user = User(
                email=self.client_email,
                role=client_role,
                is_active=True,
                is_email_confirmed=True
            )
            cl_user.password = "Password123!"
            db.session.add(cl_user)
            db.session.flush()

            cl_prof = ClientProfile(
                user_id=cl_user.id,
                first_name="Alex",
                last_name="Rivers"
            )
            db.session.add(cl_prof)
            db.session.flush()
            self.client_profile_id = cl_prof.id

            db.session.commit()

    def test_package_checkout_and_payment_verification(self):
        # 1. Log in as client
        login_resp = self.client.post('/auth/login', data={
            'email': self.client_email,
            'password': 'Password123!'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)

        # 2. View package checkout page
        checkout_resp = self.client.get(f'/client/select-package/{self.package_id}')
        self.assertEqual(checkout_resp.status_code, 200)
        html = checkout_resp.get_data(as_text=True)
        self.assertIn("12-Week Calisthenics Mastery", html)
        self.assertIn("Marcus", html)
        self.assertIn("https://paystack.com/pay/marcus-12week-mastery", html)
        self.assertIn("Pay with Paystack", html)

        # 3. Verify payment via test mock reference
        mock_ref = f"pstk_test_mock_pkg_{uuid.uuid4().hex[:8]}"
        verify_resp = self.client.post(
            f'/client/verify-package-payment/{self.package_id}',
            data={'reference': mock_ref},
            follow_redirects=True
        )
        self.assertEqual(verify_resp.status_code, 200)

        # 4. Check that contract is active and client is enrolled
        with self.app.app_context():
            contract = ClientContract.query.filter_by(
                client_id=self.client_profile_id,
                package_id=self.package_id,
                status='active'
            ).first()
            self.assertIsNotNone(contract)
            self.assertEqual(contract.coach_id, self.coach_profile_id)
            self.assertEqual(contract.monthly_renewal_price, 250.0)

            client_p = ClientProfile.query.get(self.client_profile_id)
            self.assertEqual(client_p.coach_id, self.coach_profile_id)
            self.assertEqual(client_p.active_package_id, self.package_id)

if __name__ == '__main__':
    unittest.main()
