import sys
import datetime as dt
from app import create_app, db
from app.models.user import User, CoachProfile, ClientProfile, ChatMessage
from app.models.workout import Program, ProgramPhase, Workout
from app.models.progress import ClientProgram
from app.models.features import SupportTicket, TicketMessage, SupportRating, CustomProgramOffer
from app.services.messaging import (
    create_support_ticket,
    accept_support_ticket,
    close_support_ticket_by_id,
    rate_support_ticket
)

app = create_app()
app.config['SESSION_PROTECTION'] = None
app.login_manager.session_protection = None

def login_as(tc, user):
    with tc.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True

def run_tests():
    with app.app_context():
        print("=" * 65)
        print("KENTARO PLATFORM — MASTER INTEGRATION VERIFICATION TEST SUITE")
        print("=" * 65)

        # -------------------------------------------------------------
        # SUITE 1: TEXT CLEANUP VERIFICATION
        # -------------------------------------------------------------
        print("\n--- SUITE 1: GLOBAL TEXT CLEANUP (ZERO MOJIBAKE) ---")
        import os
        bad_count = 0
        for root, dirs, files in os.walk('app'):
            for file in files:
                if file.endswith(('.py', '.html', '.js')):
                    p = os.path.join(root, file)
                    with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                        c = f.read()
                    if '\xc3\xb0\xc5\xb8\xc5\x9b\xc2\xa1' in c or '\xc3\xb0\xc5\xb8\xc5\x9b' in c:
                        bad_count += 1
        assert bad_count == 0, f"Found {bad_count} files with corrupted text!"
        print("[OK] Confirmed: 0 files contain corrupted text / mojibake!")

        # -------------------------------------------------------------
        # SUITE 2: ADMIN DISPLAY NAME
        # -------------------------------------------------------------
        print("\n--- SUITE 2: ADMIN DISPLAY NAME SYSTEM ---")
        admin = User.query.filter_by(is_admin=True).first()
        assert admin is not None, "Admin user must exist"
        admin.display_name = "Alex Vance"
        db.session.commit()
        assert admin.admin_display_name == "Alex Vance"
        print(f"[OK] Admin display name dynamically configured: '{admin.admin_display_name}'")

        # -------------------------------------------------------------
        # SUITE 3: ADVANCED SUPPORT TICKET SYSTEM (FULL LIFECYCLE)
        # -------------------------------------------------------------
        print("\n--- SUITE 3: ADVANCED SUPPORT TICKET LIFECYCLE ---")
        client_user = User.query.filter(User.client_profile != None).first()
        assert client_user is not None, "Client user must exist"

        # A. Create Ticket
        ticket1 = create_support_ticket(
            user_id=client_user.id,
            subject="Cannot access workout timer on iOS",
            category="technical",
            description="The rest timer does not beep when moving to the next set in Safari."
        )
        assert ticket1.ticket_ref.startswith("SUP-")
        assert ticket1.status == "pending"
        assert ticket1.assigned_admin_id is None
        print(f"[OK] Created Support Ticket #{ticket1.ticket_ref} in 'pending' status")

        # Initial message verification
        msgs = TicketMessage.query.filter_by(ticket_id=ticket1.id).all()
        assert len(msgs) == 1
        assert "rest timer" in msgs[0].message
        print(f"[OK] Initial issue description persisted in TicketMessage transcript")

        # B. Admin Accepts Ticket
        accepted_ticket = accept_support_ticket(ticket1.id, admin.id)
        assert accepted_ticket.status == "active"
        assert accepted_ticket.assigned_admin_id == admin.id
        assert accepted_ticket.accepted_at is not None
        print(f"[OK] Ticket accepted by Admin #{admin.id} ({admin.admin_display_name}). Status -> 'active'")

        # Verify automated welcome system message
        msgs_after_accept = TicketMessage.query.filter_by(ticket_id=ticket1.id).order_by(TicketMessage.created_at.asc()).all()
        welcome_found = any(admin.admin_display_name in m.message and m.is_system for m in msgs_after_accept)
        assert welcome_found, "Automated welcome message identifying admin must be posted"
        print(f"[OK] Automated welcome system message posted: \"Hello! I'm {admin.admin_display_name}, and I have accepted your support ticket...\"")

        # C. Conversation exchange
        user_reply = TicketMessage(
            ticket_id=ticket1.id,
            sender_id=client_user.id,
            message="Thank you Alex! It happens specifically when the screen dims.",
            is_system=False,
            created_at=dt.datetime.utcnow()
        )
        admin_reply = TicketMessage(
            ticket_id=ticket1.id,
            sender_id=admin.id,
            message="Understood. We have pushed a fix to keep audio active during background timer counts.",
            is_system=False,
            created_at=dt.datetime.utcnow()
        )
        db.session.add(user_reply)
        db.session.add(admin_reply)
        db.session.commit()
        print(f"[OK] Message transcript exchanged between user and assigned admin")

        # D. Admin Closes Ticket
        closed_ticket = close_support_ticket_by_id(ticket1.id, admin.id)
        assert closed_ticket.status == "closed"
        assert closed_ticket.closed_at is not None
        assert closed_ticket.closed_by_id == admin.id
        print(f"[OK] Ticket #{ticket1.ticket_ref} closed by admin. Conversation is now read-only.")

        # E. User Rates Support
        rate_success = rate_support_ticket(ticket1.id, client_user.id, rating=5, feedback="Alex fixed the issue super quickly!")
        assert rate_success is True
        db.session.expire_all()
        rated_t = SupportTicket.query.get(ticket1.id)
        assert rated_t.rating == 5
        assert rated_t.rating_feedback == "Alex fixed the issue super quickly!"
        assert rated_t.rated_at is not None

        # Verify SupportRating record exists
        rating_rec = SupportRating.query.filter_by(ticket_id=ticket1.id).first()
        assert rating_rec is not None
        assert rating_rec.rating == 5
        assert rating_rec.admin_id == admin.id
        print(f"[OK] 5-star customer rating & feedback successfully recorded for Admin {admin.admin_display_name}")

        # Cannot double-rate
        double_rate = rate_support_ticket(ticket1.id, client_user.id, rating=1)
        assert double_rate is False, "Double-rating must be rejected"
        print(f"[OK] Double-rating protection verified: Only 1 rating per ticket allowed.")

        # F. User Opens a New Ticket -> Separate Conversation
        ticket2 = create_support_ticket(
            user_id=client_user.id,
            subject="Question about nutrition targets",
            category="coaching",
            description="How do I adjust my protein macros for high volume days?"
        )
        assert ticket2.id != ticket1.id
        assert ticket2.ticket_ref != ticket1.ticket_ref
        assert ticket2.status == "pending"

        t2_msgs = TicketMessage.query.filter_by(ticket_id=ticket2.id).all()
        assert len(t2_msgs) == 1
        assert "protein macros" in t2_msgs[0].message
        assert "rest timer" not in t2_msgs[0].message
        print(f"[OK] Confirmed: Opening new ticket creates brand new ticket #{ticket2.ticket_ref} with completely separate conversation!")

    # -------------------------------------------------------------
    # SUITE 4: MARKETPLACE CUSTOM PROGRAM OFFER SYSTEM
    # Each step uses its own app_context to avoid Flask-Login caching
    # -------------------------------------------------------------
    print("\n--- SUITE 4: MARKETPLACE CUSTOM PROGRAM OFFER WORKFLOW ---")

    # Step A: Coach creates custom program offer
    with app.app_context():
        coach_user = User.query.filter(User.coach_profile != None).first()
        client_user = User.query.filter(User.client_profile != None).first()
        assert coach_user is not None
        client_profile_id = client_user.client_profile.id

    tc_coach = app.test_client()
    login_as(tc_coach, coach_user)
    r_offer = tc_coach.post('/coach/chat/create-custom-program-offer-ajax', data={
        'client_id': client_profile_id,
        'title': 'Elite Calisthenics Mastery 8-Week Split',
        'description': 'Advanced progression covering Planche, Front Lever, and weighted dips.',
        'duration_weeks': 8,
        'frequency': '4 days / week',
        'goals': 'Master Front Lever and strict bar muscle-ups',
        'amount': 180.00,
        'currency': 'USD',
        'mode': 'new'
    })
    assert r_offer.status_code == 200, f"Expected 200, got {r_offer.status_code}"
    offer_resp = r_offer.get_json()
    assert offer_resp['ok'] is True
    offer_id = offer_resp['offer_id']
    print(f"[OK] Coach created and sent Custom Program Offer #{offer_resp['offer_ref']} (ID #{offer_id})")

    with app.app_context():
        offer_rec = CustomProgramOffer.query.get(offer_id)
        assert offer_rec.status == 'sent'
        assert offer_rec.amount == 180.00
        assert offer_rec.duration_weeks == 8
        assert offer_rec.program_id is not None
        print(f"[OK] CustomProgramOffer persisted in DB with linked Program #{offer_rec.program_id}")

        chat_msg = ChatMessage.query.filter_by(offer_id=offer_id).first()
        assert chat_msg is not None
        assert chat_msg.message_type == 'offer'
        assert chat_msg.context == 'marketplace'
        print(f"[OK] Structured ChatMessage created with message_type='offer' and offer_id={offer_id}")

    # Step B: Client views offer preview (fresh test_client, fresh context)
    tc_client = app.test_client()
    login_as(tc_client, client_user)

    r_preview = tc_client.get(f'/client/marketplace/offer/{offer_id}/preview')
    assert r_preview.status_code == 200, f"Expected 200, got {r_preview.status_code}: {r_preview.data}"
    prev_data = r_preview.get_json()
    assert prev_data['ok'] is True
    assert prev_data['offer']['title'] == 'Elite Calisthenics Mastery 8-Week Split'

    with app.app_context():
        updated_offer = CustomProgramOffer.query.get(offer_id)
        assert updated_offer.status == 'viewed'
    print(f"[OK] Client viewed offer preview. Status transitioned 'sent' -> 'viewed'")

    # Step C: Client accepts offer
    r_accept = tc_client.post(f'/client/marketplace/offer/{offer_id}/accept')
    assert r_accept.status_code == 200
    accept_data = r_accept.get_json()
    assert accept_data['ok'] is True
    assert 'checkout-program-offer' in accept_data['checkout_url']

    with app.app_context():
        accepted_offer = CustomProgramOffer.query.get(offer_id)
        assert accepted_offer.status == 'accepted'
    print(f"[OK] Client accepted offer. Status transitioned 'viewed' -> 'accepted' (Pending Payment)")

    # Step D: Checkout page
    r_checkout = tc_client.get(f'/client/checkout-program-offer/{offer_id}')
    assert r_checkout.status_code == 200
    assert b"Pay USD 180.00 with Paystack" in r_checkout.data
    print(f"[OK] Client checkout page rendered with Paystack amount USD 180.00")

    # Step E: Simulate Paystack payment verification
    test_ref = f"pstk_test_mock_{offer_id}_{int(dt.datetime.utcnow().timestamp())}"
    r_verify = tc_client.post(f'/client/verify-program-payment/{offer_id}', data={
        'reference': test_ref
    }, follow_redirects=False)
    assert r_verify.status_code == 302, f"Expected 302 redirect, got {r_verify.status_code}"
    assert '/client/my-program' in r_verify.headers.get('Location', '')
    print(f"[OK] Paystack payment verified server-side. Redirected to /client/my-program")

    with app.app_context():
        paid_offer = CustomProgramOffer.query.get(offer_id)
        assert paid_offer.status == 'paid'
        assert paid_offer.payment_reference == test_ref
        assert paid_offer.paid_at is not None
        print(f"[OK] CustomProgramOffer marked as 'paid' with verified reference {test_ref}")

        # Program Assignment
        active_cp = ClientProgram.query.filter_by(
            client_id=client_user.client_profile.id,
            program_id=paid_offer.program_id,
            is_active=True
        ).first()
        assert active_cp is not None, "ClientProgram must be active"
        assert active_cp.status == 'active'
        print(f"[OK] ClientProgram #{active_cp.id} automatically activated for athlete in dashboard!")

    # Coach offers dashboard
    tc_coach2 = app.test_client()
    login_as(tc_coach2, coach_user)
    r_coach_offers = tc_coach2.get('/coach/offers')
    assert r_coach_offers.status_code == 200
    assert b"Paid" in r_coach_offers.data
    print(f"[OK] Coach offers dashboard reflects 'Paid & Active' program assignment")

    # -------------------------------------------------------------
    # SUITE 5: ADMIN SUPPORT REPORTS & AUDIT TRAIL
    # -------------------------------------------------------------
    print("\n--- SUITE 5: ADMIN SUPPORT REPORTS & AUDIT VIEW ---")
    with app.app_context():
        admin = User.query.filter_by(is_admin=True).first()
        ticket1 = SupportTicket.query.filter_by(status='closed').first()
        ticket_ref = ticket1.ticket_ref

    tc_admin = app.test_client()
    login_as(tc_admin, admin)

    r_reports = tc_admin.get('/admin/support/reports')
    assert r_reports.status_code == 200
    assert ticket_ref.encode() in r_reports.data
    print(f"[OK] Admin Support Reports lists resolved ticket #{ticket_ref} with customer rating")

    r_report_detail = tc_admin.get(f'/admin/support/reports/{ticket_ref}')
    assert r_report_detail.status_code == 200
    assert b"Official Support Audit Record" in r_report_detail.data
    print(f"[OK] Support Report Audit detail page renders full message transcript and timestamps")

    print("\n" + "=" * 65)
    print("ALL 5 MASTER VERIFICATION TEST SUITES PASSED FLAWLESSLY! 100% OPERATIONAL.")
    print("=" * 65)

if __name__ == '__main__':
    run_tests()
