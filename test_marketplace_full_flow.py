import unittest
import datetime as dt
from app import create_app, db
from app.models.user import User, Role, ClientProfile, CoachProfile, ChatMessage
from app.models.features import ClientPost, CustomProgramOffer
from app.models.coaching import ClientContract
from app.models.workout import Program

class MarketplaceFullFlowTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.client = cls.app.test_client()

        with cls.app.app_context():
            # Setup test client user
            c_role = Role.query.filter_by(name='client').first()
            if not c_role:
                c_role = Role(name='client')
                db.session.add(c_role)

            coach_role = Role.query.filter_by(name='coach').first()
            if not coach_role:
                coach_role = Role(name='coach')
                db.session.add(coach_role)
            db.session.commit()

            # Client user
            cls.test_client_user = User.query.filter_by(email='flow_client@test.com').first()
            if not cls.test_client_user:
                cls.test_client_user = User(email='flow_client@test.com', role_id=c_role.id, is_email_confirmed=True)
                cls.test_client_user.password = 'Password123!'
                db.session.add(cls.test_client_user)
                db.session.commit()
            else:
                cls.test_client_user.password = 'Password123!'
                cls.test_client_user.is_email_confirmed = True
                db.session.commit()

            cls.c_profile = ClientProfile.query.filter_by(user_id=cls.test_client_user.id).first()
            if not cls.c_profile:
                cls.c_profile = ClientProfile(user_id=cls.test_client_user.id, first_name='Flow', last_name='Athlete')
                db.session.add(cls.c_profile)
                db.session.commit()

            # Coach user
            cls.test_coach_user = User.query.filter_by(email='flow_coach@test.com').first()
            if not cls.test_coach_user:
                cls.test_coach_user = User(email='flow_coach@test.com', role_id=coach_role.id, is_email_confirmed=True)
                cls.test_coach_user.password = 'Password123!'
                db.session.add(cls.test_coach_user)
                db.session.commit()
            else:
                cls.test_coach_user.password = 'Password123!'
                cls.test_coach_user.is_email_confirmed = True
                db.session.commit()

            cls.coach_prof = CoachProfile.query.filter_by(user_id=cls.test_coach_user.id).first()
            if not cls.coach_prof:
                cls.coach_prof = CoachProfile(
                    user_id=cls.test_coach_user.id,
                    first_name='Elite',
                    last_name='Coach',
                    bio='Calisthenics & Strength Specialist',
                    specialization='Planche & Lever',
                    is_approved=True
                )
                db.session.add(cls.coach_prof)
                db.session.commit()
            else:
                cls.coach_prof.bio = 'Calisthenics & Strength Specialist'
                cls.coach_prof.specialization = 'Planche & Lever'
                cls.coach_prof.is_approved = True
                db.session.commit()

            cls.client_id = cls.c_profile.id
            cls.client_uid = cls.test_client_user.id
            cls.coach_id = cls.coach_prof.id
            cls.coach_uid = cls.test_coach_user.id

    def login_client(self):
        self.client.get('/auth/logout', follow_redirects=True)
        return self.client.post('/auth/login', data={
            'email': 'flow_client@test.com',
            'password': 'Password123!'
        }, follow_redirects=True)

    def login_coach(self):
        self.client.get('/auth/logout', follow_redirects=True)
        return self.client.post('/auth/login', data={
            'email': 'flow_coach@test.com',
            'password': 'Password123!'
        }, follow_redirects=True)

    def test_01_client_creates_marketplace_request(self):
        with self.app.app_context():
            # Clear previous posts
            ClientPost.query.filter_by(client_id=self.client_id).delete()
            # Clear previous contracts
            ClientContract.query.filter_by(client_id=self.client_id).delete()
            # Clear client's coach
            cp = db.session.get(ClientProfile, self.client_id)
            cp.coach_id = None
            db.session.commit()

        self.login_client()
        resp = self.client.post('/client/marketplace', data={
            'title': 'Need Coach for Full Planche & Straddle',
            'problem': 'Stuck on tuck planche for 4 months with wrist soreness',
            'goal': '5 second clean flat back straddle planche',
            'specialization': 'Planche & Lever',
            'skill_level': 'Intermediate',
            'experience': '1-2 Years',
            'min_budget': '75',
            'max_budget': '150',
            'currency': 'USD',
            'preferred_duration': '12 Weeks',
            'comm_preference': 'In-App Chat & Voice Notes',
            'expectations': 'Bi-weekly video critique and programming'
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            post = ClientPost.query.filter_by(client_id=self.client_id, status='active').first()
            self.assertIsNotNone(post)
            self.assertEqual(post.specialization, 'Planche & Lever')
            self.assertEqual(post.skill_level, 'Intermediate')
            self.assertEqual(post.min_budget, 75.0)
            self.assertEqual(post.max_budget, 150.0)
            self.assertEqual(post.currency, 'USD')
            self.assertIn('75', post.budget_display)

    def test_02_coach_scout_discovery(self):
        self.login_coach()
        # All requests
        resp = self.client.get('/coach/scout')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Need Coach for Full Planche', resp.data)

        # Filter by matching specialization
        resp = self.client.get('/coach/scout?specialization=Planche+%26+Lever')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Need Coach for Full Planche', resp.data)

        # Filter by non-matching specialization
        resp = self.client.get('/coach/scout?specialization=Weight+Loss')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Need Coach for Full Planche', resp.data)

    def test_03_chat_reply_and_actions(self):
        with self.app.app_context():
            # Create a message from coach to client
            m1 = ChatMessage(
                sender_id=self.coach_uid,
                receiver_id=self.client_uid,
                message="Hey Flow! I saw your Planche post and can definitely help.",
                context='marketplace'
            )
            db.session.add(m1)
            db.session.commit()
            m1_id = m1.id

            # Client replies to m1
            m2 = ChatMessage(
                sender_id=self.client_uid,
                receiver_id=self.coach_uid,
                message="That sounds amazing Coach!",
                context='marketplace',
                reply_to_id=m1_id
            )
            db.session.add(m2)
            db.session.commit()
            m2_id = m2.id

        # Verify reply relationship in DB
        with self.app.app_context():
            fetched_m2 = db.session.get(ChatMessage, m2_id)
            self.assertEqual(fetched_m2.reply_to_id, m1_id)
            self.assertIsNotNone(fetched_m2.reply_to)
            self.assertIn("saw your Planche post", fetched_m2.reply_to.message)

        # Client edits own message
        self.login_client()
        resp = self.client.post(f'/client/chat/message/{m2_id}/edit', json={
            'message': 'That sounds amazing Coach! When can we start?'
        })
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            self.assertEqual(db.session.get(ChatMessage, m2_id).is_edited, True)
            self.assertIn('When can we start?', db.session.get(ChatMessage, m2_id).message)

        # Coach attempts to delete client's message (forbidden)
        self.login_coach()
        resp = self.client.post(f'/coach/chat/message/{m2_id}/delete')
        self.assertEqual(resp.status_code, 403)

    def test_04_offer_creation_and_enrollment_workflow(self):
        with self.app.app_context():
            post = ClientPost.query.filter_by(client_id=self.client_id, status='active').first()
            self.assertIsNotNone(post)
            post_id = post.id

            # Coach creates program and offer
            prog = Program(coach_id=self.coach_id, name="Planche Mastery Protocol")
            db.session.add(prog)
            db.session.flush()

            import uuid
            offer = CustomProgramOffer(
                offer_ref=f"OFFER-TEST-{uuid.uuid4().hex[:6]}",
                coach_id=self.coach_id,
                client_id=self.client_id,
                program_id=prog.id,
                post_id=post_id,
                title="Planche Mastery Protocol",
                amount=120.0,
                currency="USD",
                duration_weeks=12,
                status="sent"
            )
            db.session.add(offer)
            db.session.commit()
            offer_id = offer.id

        # Client accepts offer
        self.login_client()
        resp = self.client.post(f'/client/marketplace/offer/{offer_id}/accept')
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            self.assertEqual(db.session.get(CustomProgramOffer, offer_id).status, 'accepted')

        # Mock payment verification
        import app.services.paystack as ps
        old_verify = ps.verify_paystack_payment
        ps.verify_paystack_payment = lambda ref: {'status': True, 'amount': 18000000, 'currency': 'NGN'}

        try:
            resp = self.client.get(f'/client/verify-program-payment/{offer_id}?reference=pstk_mock_12345', follow_redirects=True)
            self.assertEqual(resp.status_code, 200)

            with self.app.app_context():
                # Verify offer paid
                off = db.session.get(CustomProgramOffer, offer_id)
                self.assertEqual(off.status, 'paid')
                self.assertIsNotNone(off.paid_at)

                # Verify client post fulfilled
                p = db.session.get(ClientPost, post_id)
                self.assertEqual(p.status, 'fulfilled')
                self.assertEqual(p.fulfilled_coach_id, self.coach_id)

                # Verify active contract created
                contract = ClientContract.query.filter_by(client_id=self.client_id, status='active').first()
                self.assertIsNotNone(contract)
                self.assertEqual(contract.coach_id, self.coach_id)
                self.assertEqual(contract.offer_id, offer_id)

                # Verify client profile coach_id linked
                cp = db.session.get(ClientProfile, self.client_id)
                self.assertEqual(cp.coach_id, self.coach_id)

                # Verify chat messages reclassified to 'coaching'
                msgs = ChatMessage.query.filter_by(sender_id=self.coach_uid, receiver_id=self.client_uid).all()
                for m in msgs:
                    self.assertEqual(m.context, 'coaching')

        finally:
            ps.verify_paystack_payment = old_verify

        # Coach scout discovery must no longer show this fulfilled post
        self.login_coach()
        resp = self.client.get('/coach/scout')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Need Coach for Full Planche', resp.data)

if __name__ == '__main__':
    unittest.main()
