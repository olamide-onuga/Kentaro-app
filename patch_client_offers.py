with open('app/routes/client.py', 'r', encoding='utf-8') as f:
    client_code = f.read()

# Update _OPEN_ENDPOINTS
old_endpoints = "'client.start_support_chat', 'client.view_program', 'client.my_program',"
new_endpoints = "'client.start_support_chat', 'client.view_program', 'client.my_program', 'client.preview_program_offer', 'client.decline_program_offer', 'client.accept_program_offer', 'client.checkout_program_offer', 'client.verify_program_payment',"

if old_endpoints in client_code:
    client_code = client_code.replace(old_endpoints, new_endpoints)

client_offer_routes = '''

# ─────────────────────────────────────────────────────────────────────────────
# MARKETPLACE CUSTOM PROGRAM OFFERS (ACCEPT, DECLINE, CHECKOUT, PAYSTACK)
# ─────────────────────────────────────────────────────────────────────────────

@client_bp.route('/marketplace/offer/<int:offer_id>/preview')
@login_required
def preview_program_offer(offer_id):
    """View full detailed custom coaching program offer preview."""
    from app.models.features import CustomProgramOffer
    from app.models.workout import ProgramPhase, Workout, WorkoutExercise
    from app import socketio

    profile = current_user.client_profile
    if not profile:
        return jsonify({'ok': False, 'error': 'Client profile not found'}), 404

    offer = CustomProgramOffer.query.get_or_404(offer_id)
    if offer.client_id != profile.id:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403

    # If first time viewing, update status from 'sent' to 'viewed'
    if offer.status == 'sent':
        offer.status = 'viewed'
        db.session.commit()
        socketio.emit('offer_status_changed', {
            'offer_id': offer.id,
            'status': 'viewed'
        }, room=f'user_{offer.coach.user_id}')

    workouts_data = []
    if offer.program:
        phases = ProgramPhase.query.filter_by(program_id=offer.program.id).order_by(ProgramPhase.order).all()
        for p in phases:
            phase_workouts = Workout.query.filter_by(phase_id=p.id).order_by(Workout.day_number).all()
            for w in phase_workouts:
                exercises = WorkoutExercise.query.filter_by(workout_id=w.id).all()
                workouts_data.append({
                    'phase': p.name,
                    'workout_name': w.name,
                    'day_name': w.day_name,
                    'is_rest': w.is_rest,
                    'exercises': [{'name': e.exercise.name if e.exercise else 'Exercise', 'sets': e.sets, 'reps': e.reps, 'rest': e.rest_seconds} for e in exercises]
                })

    coach_name = f"Coach {offer.coach.first_name} {offer.coach.last_name or ''}".strip()
    return jsonify({
        'ok': True,
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
            'instructions': offer.instructions or '',
            'terms': offer.terms or '',
            'status': offer.status,
            'coach_name': coach_name,
            'start_date': offer.start_date.strftime('%b %d, %Y') if offer.start_date else 'Immediate',
            'created_at': offer.created_at.strftime('%b %d, %Y'),
            'workouts': workouts_data
        }
    })


@client_bp.route('/marketplace/offer/<int:offer_id>/decline', methods=['POST'])
@login_required
def decline_program_offer(offer_id):
    """Decline a custom program offer."""
    from app.models.features import CustomProgramOffer
    from app.services.messaging import send_system_notification
    from app import socketio

    profile = current_user.client_profile
    if not profile:
        return jsonify({'ok': False, 'error': 'Profile required'}), 404

    offer = CustomProgramOffer.query.get_or_404(offer_id)
    if offer.client_id != profile.id:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403

    offer.status = 'declined'
    offer.declined_at = dt.datetime.utcnow()
    db.session.commit()

    coach_user_id = offer.coach.user_id
    socketio.emit('offer_status_changed', {
        'offer_id': offer.id,
        'status': 'declined'
    }, room=f'user_{coach_user_id}')

    send_system_notification(
        recipient_id=coach_user_id,
        notif_type='offer_declined',
        title="Custom Program Offer Declined",
        text=f"{profile.full_name} declined your custom coaching program proposal for '{offer.title}'.",
        link=f"/coach/chat?partner_id={current_user.id}&context=marketplace",
        target_type='offer',
        target_id=offer.id,
        emit_socket=True
    )

    return jsonify({'ok': True, 'status': 'declined', 'message': 'Offer declined.'})


@client_bp.route('/marketplace/offer/<int:offer_id>/accept', methods=['POST'])
@login_required
def accept_program_offer(offer_id):
    """Accept offer and proceed to payment."""
    from app.models.features import CustomProgramOffer
    from app.services.messaging import send_system_notification
    from app import socketio

    profile = current_user.client_profile
    if not profile:
        return jsonify({'ok': False, 'error': 'Profile required'}), 404

    offer = CustomProgramOffer.query.get_or_404(offer_id)
    if offer.client_id != profile.id:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403

    if offer.status not in ['sent', 'viewed']:
        return jsonify({'ok': False, 'error': f'Offer is already {offer.status}'}), 400

    offer.status = 'accepted'
    db.session.commit()

    coach_user_id = offer.coach.user_id
    socketio.emit('offer_status_changed', {
        'offer_id': offer.id,
        'status': 'accepted'
    }, room=f'user_{coach_user_id}')

    send_system_notification(
        recipient_id=coach_user_id,
        notif_type='offer_accepted',
        title="Custom Program Offer Accepted",
        text=f"{profile.full_name} accepted your custom coaching program '{offer.title}'. Pending payment.",
        link=f"/coach/chat?partner_id={current_user.id}&context=marketplace",
        target_type='offer',
        target_id=offer.id,
        emit_socket=True
    )

    return jsonify({
        'ok': True,
        'status': 'accepted',
        'checkout_url': url_for('client.checkout_program_offer', offer_id=offer.id)
    })


@client_bp.route('/checkout-program-offer/<int:offer_id>')
@login_required
def checkout_program_offer(offer_id):
    """Payment checkout page for custom program offer via Paystack."""
    from app.models.features import CustomProgramOffer
    from app.services.paystack import get_paystack_public_key
    import time

    profile = current_user.client_profile
    if not profile:
        flash('Please complete your profile first.', 'warning')
        return redirect(url_for('client.profile'))

    offer = CustomProgramOffer.query.get_or_404(offer_id)
    if offer.client_id != profile.id:
        flash('Unauthorized access to this offer.', 'danger')
        return redirect(url_for('client.dashboard'))

    if offer.status == 'paid':
        flash('This custom program has already been paid and activated!', 'info')
        return redirect(url_for('client.my_program'))

    paystack_public_key = get_paystack_public_key()
    payment_reference = f"pstk_offer_{offer.id}_{current_user.id}_{int(time.time())}"
    amount_in_kobo = int(round(float(offer.amount) * 100))
    currency = (offer.currency or 'USD').upper()

    return render_template(
        'client/checkout_program_offer.html',
        offer=offer,
        coach=offer.coach,
        paystack_public_key=paystack_public_key,
        payment_reference=payment_reference,
        amount_in_kobo=amount_in_kobo,
        currency=currency
    )


@client_bp.route('/verify-program-payment/<int:offer_id>', methods=['GET', 'POST'])
@login_required
def verify_program_payment(offer_id):
    """Server-side verified Paystack payment callback for custom program offers."""
    from app.models.features import CustomProgramOffer, ClientPost
    from app.models.progress import ClientProgram
    from app.services.paystack import verify_paystack_payment
    from app.services.messaging import send_system_notification
    from app import socketio

    profile = current_user.client_profile
    if not profile:
        flash('Profile required.', 'warning')
        return redirect(url_for('client.dashboard'))

    offer = CustomProgramOffer.query.get_or_404(offer_id)
    if offer.client_id != profile.id:
        flash('Unauthorized payment action.', 'danger')
        return redirect(url_for('client.dashboard'))

    if offer.status == 'paid':
        flash('This program offer is already verified and active!', 'success')
        return redirect(url_for('client.my_program'))

    reference = request.args.get('reference') or request.form.get('reference')
    if not reference:
        flash('Payment reference missing. Please try again.', 'danger')
        return redirect(url_for('client.checkout_program_offer', offer_id=offer.id))

    # Server-side verification with Paystack
    verification = verify_paystack_payment(reference)
    if not verification.get('status'):
        flash(f"Payment verification failed: {verification.get('message', 'Please contact support')}", 'danger')
        return redirect(url_for('client.checkout_program_offer', offer_id=offer.id))

    # Mark offer as Paid
    offer.status = 'paid'
    offer.payment_reference = reference
    offer.paid_at = dt.datetime.utcnow()

    # Automatically create/activate ClientProgram
    if offer.program_id:
        for existing_cp in ClientProgram.query.filter_by(client_id=profile.id).all():
            existing_cp.is_active = False
        
        active_cp = ClientProgram(
            client_id=profile.id,
            program_id=offer.program_id,
            is_active=True,
            status='active'
        )
        db.session.add(active_cp)

    # Link coach to client if not already linked
    if not profile.coach_id:
        profile.coach_id = offer.coach_id

    # Close any open marketplace post related to this
    if offer.post_id:
        post = ClientPost.query.get(offer.post_id)
        if post and post.client_id == profile.id:
            post.status = 'closed'

    db.session.commit()

    coach_user_id = offer.coach.user_id
    coach_name = f"Coach {offer.coach.first_name}" if offer.coach.first_name else "your Coach"

    # Notify Client
    send_system_notification(
        recipient_id=current_user.id,
        notif_type='program_activated',
        title="Payment Successful!",
        text="Your payment was successful. Your custom coaching program is now available in your dashboard.",
        link="/client/my-program",
        target_type='program',
        target_id=offer.program_id,
        emit_socket=True
    )

    # Notify Coach
    send_system_notification(
        recipient_id=coach_user_id,
        notif_type='offer_paid',
        title="Custom Program Purchased!",
        text=f"{profile.full_name} has successfully purchased your custom coaching program '{offer.title}'.",
        link="/coach/clients",
        target_type='client',
        target_id=profile.id,
        emit_socket=True
    )

    # Broadcast to socket rooms
    socketio.emit('offer_status_changed', {
        'offer_id': offer.id,
        'status': 'paid'
    }, room=f'user_{coach_user_id}')

    flash(f"Payment successful! Your custom coaching program '{offer.title}' is now active and ready in your dashboard.", 'success')
    return redirect(url_for('client.my_program'))
'''

if 'def preview_program_offer(' not in client_code:
    client_code += client_offer_routes

with open('app/routes/client.py', 'w', encoding='utf-8') as f:
    f.write(client_code)

print("Updated app/routes/client.py with custom program offer acceptance, preview, checkout, and verification")
