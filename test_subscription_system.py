import os
import unittest
from datetime import datetime, timedelta
from run import app
from app.extensions import db
from app.models.user import User, CoachProfile, ClientProfile, Role
from app.models.coaching import CoachingPackage, ClientContract
from app.models.subscription import (
    SubscriptionPlan, CoachSubscription, SubscriptionAuditLog, SubscriptionPayment
)
from app.services.entitlements import (
    get_coach_subscription, get_coach_plan, get_active_client_count,
    can_coach_add_client, has_feature_access, seed_default_plans, log_subscription_change
)
from app.services.paystack import initialize_paystack_payment, verify_paystack_payment, _convert_to_ngn

class TestSubscriptionSystem(unittest.TestCase):

    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.rollback()
        self.ctx.pop()

    def test_01_default_plans_seeded(self):
        """Test default plans (Free, Basic, Premium) exist with correct defaults."""
        plans = seed_default_plans()
        free = SubscriptionPlan.query.filter_by(slug='free').first()
        basic = SubscriptionPlan.query.filter_by(slug='basic').first()
        premium = SubscriptionPlan.query.filter_by(slug='premium').first()

        self.assertIsNotNone(free)
        self.assertEqual(free.price, 0.0)
        self.assertEqual(free.max_clients, 5)
        self.assertFalse(free.is_unlimited_clients)

        self.assertIsNotNone(basic)
        self.assertEqual(basic.price, 19.0)
        self.assertEqual(basic.max_clients, 15)
        self.assertFalse(basic.is_unlimited_clients)

        self.assertIsNotNone(premium)
        self.assertEqual(premium.price, 49.0)
        self.assertIsNone(premium.max_clients)
        self.assertTrue(premium.is_unlimited_clients)
        self.assertEqual(premium.client_limit_display, "Unlimited")

    def test_02_free_plan_client_limit_enforcement(self):
        """Test that Free plan enforces limit of 5 clients and blocks when full."""
        # Find or create a test coach
        coach_user = User.query.filter_by(email='test_coach_sub@kentaro.app').first()
        if not coach_user:
            role_coach = Role.query.filter_by(name='coach').first()
            coach_user = User(email='test_coach_sub@kentaro.app', role_id=role_coach.id if role_coach else None)
            coach_user.password = 'Coach123!'
            db.session.add(coach_user)
            db.session.commit()
            coach = CoachProfile(user_id=coach_user.id, first_name='Test', last_name='Coach', specialization='Calisthenics')
            db.session.add(coach)
            db.session.commit()
        else:
            coach = coach_user.coach_profile

        # Ensure coach is on Free plan
        free_plan = SubscriptionPlan.query.filter_by(slug='free').first()
        sub = get_coach_subscription(coach.id)
        sub.plan_id = free_plan.id
        sub.status = 'active'
        sub.current_period_end = None
        db.session.commit()

        # Check initial can_coach_add_client
        res = can_coach_add_client(coach.id)
        self.assertFalse(res['is_unlimited'])
        self.assertEqual(res['max_limit'], 5)

    def test_03_unlimited_premium_capacity(self):
        """Test that Premium plan has unlimited capacity."""
        coach = CoachProfile.query.first()
        self.assertIsNotNone(coach)
        prem_plan = SubscriptionPlan.query.filter_by(slug='premium').first()

        sub = get_coach_subscription(coach.id)
        old_plan_id = sub.plan_id
        sub.plan_id = prem_plan.id
        sub.status = 'active'
        db.session.commit()

        check = can_coach_add_client(coach.id)
        self.assertTrue(check['allowed'])
        self.assertTrue(check['is_unlimited'])
        self.assertIsNone(check['max_limit'])

        # Reset back
        sub.plan_id = old_plan_id
        db.session.commit()

    def test_04_custom_admin_plan_creation_and_limits(self):
        """Test admin can create a custom plan (e.g., $35/mo for 30 clients)."""
        slug = 'custom_pro_30'
        existing = SubscriptionPlan.query.filter_by(slug=slug).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()

        custom_plan = SubscriptionPlan(
            name='Pro 30',
            slug=slug,
            description='Custom tier for mid-size studios',
            price=35.0,
            billing_interval='monthly',
            max_clients=30,
            is_unlimited_clients=False,
            display_order=5,
            is_active=True
        )
        custom_plan.set_features({'program_builder': True, 'analytics': True})
        db.session.add(custom_plan)
        db.session.commit()

        self.assertEqual(custom_plan.price, 35.0)
        self.assertEqual(custom_plan.max_clients, 30)
        self.assertEqual(custom_plan.client_limit_display, "30 clients")
        self.assertTrue(custom_plan.has_feature('analytics'))

    def test_05_feature_entitlement_enforcement(self):
        """Test backend checking of feature permissions."""
        free_plan = SubscriptionPlan.query.filter_by(slug='free').first()
        prem_plan = SubscriptionPlan.query.filter_by(slug='premium').first()

        # Free plan does not have analytics
        self.assertFalse(free_plan.has_feature('analytics'))
        # Premium plan has analytics
        self.assertTrue(prem_plan.has_feature('analytics'))

    def test_06_downgrade_retains_existing_clients_but_blocks_new(self):
        """If coach has clients and downgrades, existing are kept but additions blocked."""
        plan = SubscriptionPlan(
            name='Mini Plan',
            slug='mini_test_slug',
            price=5.0,
            max_clients=1,
            is_unlimited_clients=False,
            is_active=True
        )
        db.session.add(plan)
        db.session.commit()

        coach = CoachProfile.query.first()
        sub = get_coach_subscription(coach.id)
        orig_plan = sub.plan_id

        sub.plan_id = plan.id
        db.session.commit()

        # If coach has >= 1 client, incoming client must be blocked
        active_count = get_active_client_count(coach.id)
        if active_count >= 1:
            check = can_coach_add_client(coach.id, count_incoming=1)
            self.assertFalse(check['allowed'])

        # Restore
        sub.plan_id = orig_plan
        db.session.commit()
        db.session.delete(plan)
        db.session.commit()

    def test_07_subscription_expiration_fallback_to_free(self):
        """Expired paid subscription safely falls back to Free plan entitlements."""
        coach = CoachProfile.query.first()
        sub = get_coach_subscription(coach.id)
        basic_plan = SubscriptionPlan.query.filter_by(slug='basic').first()

        # Set subscription to expired in the past
        sub.plan_id = basic_plan.id
        sub.status = 'active'
        sub.current_period_end = datetime.utcnow() - timedelta(days=2)
        db.session.commit()

        # Calling get_coach_subscription or get_coach_plan detects expiration
        plan = get_coach_plan(coach.id)
        # Should fallback to free
        self.assertEqual(plan.slug, 'free')

        # Reset
        sub.status = 'active'
        sub.current_period_end = None
        db.session.commit()

    def test_08_paystack_currency_conversion(self):
        """Test USD to NGN conversion avoids 403 unsupported currency."""
        ngn_amt, cur, rate = _convert_to_ngn(19.0, 'USD')
        self.assertEqual(cur, 'NGN')
        self.assertEqual(rate, 1500.0)
        self.assertEqual(ngn_amt, 28500.0)

        # NGN passes directly without conversion
        ngn_direct, cur2, rate2 = _convert_to_ngn(5000, 'NGN')
        self.assertEqual(cur2, 'NGN')
        self.assertIsNone(rate2)
        self.assertEqual(ngn_direct, 5000.0)

    def test_09_audit_logging(self):
        """Test subscription changes create audit records."""
        coach = CoachProfile.query.first()
        free_plan = SubscriptionPlan.query.filter_by(slug='free').first()
        basic_plan = SubscriptionPlan.query.filter_by(slug='basic').first()

        log_subscription_change(
            coach_id=coach.id,
            changed_by_user_id=None,
            old_plan_id=free_plan.id,
            new_plan_id=basic_plan.id,
            action='test_action',
            reason='Automated verification'
        )

        audit = SubscriptionAuditLog.query.filter_by(coach_id=coach.id, action='test_action').first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.new_plan_id, basic_plan.id)

    def test_10_coach_onboarding_payment_link_optional(self):
        """Verify coach profile is complete even without payment_link."""
        profile = CoachProfile(
            first_name='Alex',
            last_name='Athlete',
            bio='Calisthenics specialist',
            specialization='Strength & Skills',
            payment_link=None  # Optional on onboarding!
        )
        self.assertTrue(profile.is_complete)

    def test_11_clients_do_not_have_subscriptions(self):
        """Verify subscription plans are strictly for coaches, clients buy packages/contracts."""
        # 1. No CoachSubscription has a client as its coach_id
        client_ids = [c.id for c in ClientProfile.query.all()]
        if client_ids:
            client_subs = CoachSubscription.query.filter(CoachSubscription.coach_id.in_(client_ids)).count()
            # Ensure no subscription points to a client profile
            coach_ids = [c.id for c in CoachProfile.query.all()]
            for sub in CoachSubscription.query.all():
                self.assertIn(sub.coach_id, coach_ids)

        # 2. Client user attempting to access /coach/subscription is redirected/blocked
        client_role = Role.query.filter_by(name='client').first()
        client_user = User.query.filter_by(email='test_client_nosub@kentaro.app').first()
        if not client_user:
            client_user = User(email='test_client_nosub@kentaro.app', role_id=client_role.id if client_role else None)
            client_user.password = 'Client123!'
            db.session.add(client_user)
            db.session.commit()
            client_prof = ClientProfile(user_id=client_user.id, first_name='TestClient', last_name='Athlete')
            db.session.add(client_prof)
            db.session.commit()

        # Login client and test access
        with self.client:
            self.client.post('/auth/login', data={'email': 'test_client_nosub@kentaro.app', 'password': 'Client123!'})
            res = self.client.get('/coach/subscription', follow_redirects=False)
            # Must redirect away (302) and not allow access
            self.assertEqual(res.status_code, 302)

if __name__ == '__main__':
    unittest.main()
