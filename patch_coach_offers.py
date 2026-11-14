import re

# 1. Update app/routes/coach.py
with open('app/routes/coach.py', 'r', encoding='utf-8') as f:
    coach_code = f.read()

# Add imports if needed
if 'CustomProgramOffer' not in coach_code:
    coach_code = coach_code.replace(
        'from app.models.features import CustomOffer, ClientPost',
        'from app.models.features import CustomOffer, ClientPost, CustomProgramOffer'
    )

coach_offer_endpoints = '''

@coach_bp.route('/chat/create-custom-program-offer-ajax', methods=['POST'])
@login_required
def create_custom_program_offer_ajax():
    """Create and send a rich custom coaching program offer inside marketplace DM."""
    import uuid
    import datetime as dt
    from app.models.workout import Program, ProgramPhase, Workout
    from app.models.progress import ClientProgram
    from app.models.user import ClientProfile, ChatMessage, User
    from app.models.features import CustomProgramOffer, ClientPost
    from app.services.messaging import send_system_notification, get_chat_url
    from app import socketio

    coach = current_user.coach_profile
    if not coach:
        return jsonify({'ok': False, 'error': 'Coach profile not found'}), 403

    client_id = request.form.get('client_id', type=int)
    client = ClientProfile.query.get(client_id)
    if not client:
        target_u = User.query.get(client_id)
        if target_u and target_u.client_profile:
            client = target_u.client_profile
    if not client:
        return jsonify({'ok': False, 'error': 'Client profile not found'}), 404

    # Offer parameters
    title = request.form.get('title', '').strip() or request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    duration_weeks = request.form.get('duration_weeks', type=int) or 4
    frequency = request.form.get('frequency', '').strip() or '4 days / week'
    goals = request.form.get('goals', '').strip()
    instructions = request.form.get('instructions', '').strip()
    terms = request.form.get('terms', '').strip()
    start_date_str = request.form.get('start_date', '').strip()
    amount = request.form.get('amount', type=float) or request.form.get('price', type=float) or 0.0
    currency = request.form.get('currency', 'USD').strip().upper()
    program_mode = request.form.get('mode', 'new')
    post_id = request.form.get('post_id', type=int)

    if not title:
        return jsonify({'ok': False, 'error': 'Program title is required'}), 400
    if amount <= 0:
        return jsonify({'ok': False, 'error': 'Please provide a valid program price'}), 400

    start_date = None
    if start_date_str:
        try:
            start_date = dt.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except Exception:
            start_date = dt.date.today()

    # Link or build program
    program = None
    if program_mode == 'assign':
        existing_prog_id = request.form.get('program_id', type=int)
        program = Program.query.filter_by(id=existing_prog_id, coach_id=coach.id).first()
    
    if not program:
        program = Program(coach_id=coach.id, name=title, description=description or goals)
        db.session.add(program)
        db.session.flush()

        phase = ProgramPhase(program_id=program.id, name='Phase 1: Foundation & Mastery', order=1)
        db.session.add(phase)
        db.session.flush()

        w1 = Workout(phase_id=phase.id, name=f'{frequency} Core Workout', day_name='Day 1', day_number=1)
        db.session.add(w1)
        db.session.flush()

    offer_ref = f"OFFER-{uuid.uuid4().hex[:6].upper()}"
    offer = CustomProgramOffer(
        offer_ref=offer_ref,
        coach_id=coach.id,
        client_id=client.id,
        program_id=program.id,
        post_id=post_id,
        title=title,
        description=description,
        amount=amount,
        currency=currency,
        duration_weeks=duration_weeks,
        frequency=frequency,
        goals=goals,
        instructions=instructions,
        terms=terms,
        start_date=start_date,
        status='sent',
        created_at=dt.datetime.utcnow(),
        updated_at=dt.datetime.utcnow()
    )
    db.session.add(offer)
    db.session.flush()

    # Create structured ChatMessage linking to this offer
    offer_msg_text = f"🎯 Custom Program Offer: {title} ({duration_weeks} Weeks • {currency} {amount:,.2f})"
    sys_msg = ChatMessage(
        sender_id=current_user.id,
        receiver_id=client.user_id,
        message=offer_msg_text,
        message_type='offer',
        offer_id=offer.id,
        program_id=program.id,
        context='marketplace',
        post_id=post_id
    )
    db.session.add(sys_msg)
    db.session.commit()

    coach_name = f"Coach {coach.first_name}" if coach.first_name else "Coach"
    client_chat_url = get_chat_url(client.user, current_user.id, context='marketplace', post_id=post_id)

    offer_payload = {
        'id': sys_msg.id,
        'from': current_user.id,
        'sender_id': current_user.id,
        'receiver_id': client.user_id,
        'target_user_id': client.user_id,
        'msg': offer_msg_text,
        'message': offer_msg_text,
        'message_type': 'offer',
        'context': 'marketplace',
        'timestamp': sys_msg.timestamp.strftime('%H:%M') if sys_msg.timestamp else '',
        'from_name': coach_name,
        'chat_url': client_chat_url,
        'offer': {
            'id': offer.id,
            'offer_ref': offer.offer_ref,
            'title': offer.title,
            'description': offer.description or '',
            'amount': offer.amount,
            'currency': offer.currency,
            'duration_weeks': offer.duration_weeks,
            'frequency': offer.frequency or '4 days / week',
            'goals': offer.goals or '',
            'status': offer.status,
            'coach_name': coach_name,
            'created_at': offer.created_at.strftime('%b %d, %Y'),
            'program_id': program.id
        }
    }

    # Emit socket events to both rooms
    socketio.emit('chat_message', offer_payload, room=f'user_{client.user_id}')
    sender_payload = dict(offer_payload)
    sender_payload['chat_url'] = get_chat_url(current_user, client.user_id, context='marketplace', post_id=post_id)
    socketio.emit('chat_message_sent', sender_payload, room=f'user_{current_user.id}')

    # Send persistent notification to client
    send_system_notification(
        recipient_id=client.user_id,
        notif_type='custom_program_offer',
        title=f"Custom Program Offer from {coach_name}",
        text=f'{coach_name} sent you a custom coaching program proposal: "{title}" ({currency} {amount:,.2f})',
        link=client_chat_url,
        target_type='offer',
        target_id=offer.id,
        emit_socket=True
    )

    return jsonify({
        'ok': True,
        'offer_id': offer.id,
        'offer_ref': offer.offer_ref,
        'message': 'Custom program offer sent successfully!'
    })


@coach_bp.route('/offers')
@login_required
def coach_offers():
    """List of all custom program offers sent by the coach."""
    coach = current_user.coach_profile
    if not coach:
        flash('Coach profile not found.', 'danger')
        return redirect(url_for('coach.dashboard'))

    from app.models.features import CustomProgramOffer
    offers = CustomProgramOffer.query.filter_by(coach_id=coach.id).order_by(CustomProgramOffer.created_at.desc()).all()
    return render_template('coach/offers.html', offers=offers, coach=coach)


@coach_bp.route('/offers/<int:offer_id>/cancel', methods=['POST'])
@login_required
def cancel_coach_offer(offer_id):
    """Cancel an unpaid program offer."""
    coach = current_user.coach_profile
    if not coach:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('main.index'))

    from app.models.features import CustomProgramOffer
    from app import socketio

    offer = CustomProgramOffer.query.filter_by(id=offer_id, coach_id=coach.id).first_or_404()
    if offer.status in ['paid', 'accepted']:
        flash('Cannot cancel an offer that has been accepted or paid.', 'warning')
        return redirect(url_for('coach.coach_offers'))

    offer.status = 'cancelled'
    db.session.commit()

    socketio.emit('offer_status_changed', {
        'offer_id': offer.id,
        'status': 'cancelled'
    }, room=f'user_{offer.client.user_id}')

    flash(f'Offer #{offer.offer_ref or offer.id} has been cancelled.', 'info')
    return redirect(url_for('coach.coach_offers'))
'''

if 'def create_custom_program_offer_ajax(' not in coach_code:
    coach_code += coach_offer_endpoints

with open('app/routes/coach.py', 'w', encoding='utf-8') as f:
    f.write(coach_code)
print("Updated app/routes/coach.py with marketplace custom program offer creation and management")
