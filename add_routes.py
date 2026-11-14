import base64

coach_code = """
@coach_bp.route('/session-notes', methods=['GET', 'POST'])
@login_required
def session_notes():
    profile = current_user.coach_profile
    if not profile:
        return redirect(url_for('coach.dashboard'))
    from app.models.features import SessionNote
    from app.models.user import ClientProfile
    clients = profile.clients.all()
    
    if request.method == 'POST':
        client_id = request.form.get('client_id', type=int)
        title = request.form.get('title', 'Session Note').strip()
        summary = request.form.get('summary', '').strip()
        homework = request.form.get('homework', '').strip()
        next_goal = request.form.get('next_goal', '').strip()
        import datetime as dt
        session_date_str = request.form.get('session_date', dt.date.today().isoformat())
        try:
            session_date = dt.date.fromisoformat(session_date_str)
        except ValueError:
            session_date = dt.date.today()
        
        client_profile = ClientProfile.query.get(client_id)
        if client_profile and client_profile.coach_id == profile.id:
            note = SessionNote(
                coach_id=profile.id,
                client_id=client_id,
                title=title,
                summary=summary,
                homework=homework,
                next_goal=next_goal,
                session_date=session_date
            )
            db.session.add(note)
            db.session.commit()
            # Email client
            from app.services.email import send_session_note_email
            try:
                send_session_note_email(profile, client_profile, note)
            except Exception:
                pass
            from app import socketio
            socketio.emit('notification', {
                'msg': f'Coach {profile.first_name} left a session note for you!'
            }, room=f'user_{client_profile.user_id}')
            flash('Session note saved!', 'success')
        return redirect(url_for('coach.session_notes'))
    
    from app.models.features import SessionNote
    notes = SessionNote.query.filter_by(coach_id=profile.id).order_by(SessionNote.session_date.desc()).limit(50).all()
    return render_template('coach/session_notes.html', profile=profile, clients=clients, notes=notes)

@coach_bp.route('/habits', methods=['GET', 'POST'])
@login_required
def habits():
    profile = current_user.coach_profile
    if not profile:
        return redirect(url_for('coach.dashboard'))
    from app.models.features import HabitTemplate
    from app.models.user import ClientProfile
    clients = profile.clients.all()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            client_id = request.form.get('client_id', type=int)
            name = request.form.get('name', '').strip()
            icon = request.form.get('icon', '✅').strip()
            if client_id and name:
                client = ClientProfile.query.get(client_id)
                if client and client.coach_id == profile.id:
                    db.session.add(HabitTemplate(coach_id=profile.id, client_id=client_id, name=name, icon=icon))
                    db.session.commit()
                    from app import socketio
                    socketio.emit('notification', {
                        'msg': f'Coach {profile.first_name} assigned a new habit: {name}'
                    }, room=f'user_{client.user_id}')
                    flash('Habit assigned!', 'success')
        elif action == 'delete':
            habit_id = request.form.get('habit_id', type=int)
            habit = HabitTemplate.query.get(habit_id)
            if habit and habit.coach_id == profile.id:
                db.session.delete(habit)
                db.session.commit()
                flash('Habit removed.', 'info')
        return redirect(url_for('coach.habits'))
    
    habits = HabitTemplate.query.filter_by(coach_id=profile.id).order_by(HabitTemplate.created_at.desc()).all()
    return render_template('coach/habits.html', profile=profile, clients=clients, habits=habits)

@coach_bp.route('/check-ins')
@login_required
def check_ins():
    profile = current_user.coach_profile
    if not profile:
        return redirect(url_for('coach.dashboard'))
    from app.models.features import CheckIn
    from app.models.user import ClientProfile
    client_id = request.args.get('client_id', type=int)
    clients = profile.clients.all()
    selected_client = None
    check_ins_list = []
    if client_id:
        selected_client = ClientProfile.query.get(client_id)
        if selected_client and selected_client.coach_id == profile.id:
            check_ins_list = CheckIn.query.filter_by(client_id=client_id).order_by(CheckIn.created_at.desc()).limit(20).all()
    else:
        check_ins_list = CheckIn.query.filter_by(coach_id=profile.id).order_by(CheckIn.created_at.desc()).limit(30).all()
    return render_template('coach/check_ins.html', profile=profile, clients=clients, check_ins=check_ins_list, selected_client=selected_client)

@coach_bp.route('/check-ins/<int:checkin_id>/reply', methods=['POST'])
@login_required
def reply_checkin(checkin_id):
    from app.models.features import CheckIn
    profile = current_user.coach_profile
    checkin = CheckIn.query.get_or_404(checkin_id)
    if checkin.coach_id != profile.id:
        return '', 403
    checkin.coach_reply = request.form.get('reply', '').strip()
    db.session.commit()
    from app import socketio
    socketio.emit('notification', {
        'msg': f'Coach {profile.first_name} replied to your check-in!'
    }, room=f'user_{checkin.client.user_id}')
    flash('Reply sent!', 'success')
    return redirect(url_for('coach.check_ins', client_id=checkin.client_id))

@coach_bp.route('/earnings')
@login_required
def earnings():
    profile = current_user.coach_profile
    if not profile:
        return redirect(url_for('coach.dashboard'))
    from app.models.coaching import ClientContract
    import datetime as dt
    from sqlalchemy import extract
    
    all_contracts = ClientContract.query.filter_by(coach_id=profile.id).order_by(ClientContract.created_at.desc()).all()
    
    now = dt.datetime.utcnow()
    this_month_contracts = [c for c in all_contracts if c.created_at and c.created_at.month == now.month and c.created_at.year == now.year]
    
    total_earned = sum(float(c.monthly_renewal_price or 0) * int(c.months_subscribed or 1) for c in all_contracts if c.status != 'terminated')
    this_month_earned = sum(float(c.monthly_renewal_price or 0) * int(c.months_subscribed or 1) for c in this_month_contracts)
    active_clients = ClientContract.query.filter_by(coach_id=profile.id, status='active').count()
    
    # Monthly breakdown (last 6 months)
    monthly = []
    for i in range(5, -1, -1):
        m_date = now.replace(day=1) - dt.timedelta(days=i*30)
        m_contracts = [c for c in all_contracts if c.created_at and c.created_at.month == m_date.month and c.created_at.year == m_date.year]
        m_total = sum(float(c.monthly_renewal_price or 0) * int(c.months_subscribed or 1) for c in m_contracts)
        monthly.append({'month': m_date.strftime('%b'), 'amount': round(m_total, 2)})
    
    currency = profile.currency or 'NGN'
    return render_template('coach/earnings.html', profile=profile, all_contracts=all_contracts,
                           total_earned=round(total_earned, 2), this_month_earned=round(this_month_earned, 2),
                           active_clients=active_clients, monthly=monthly, currency=currency)

@coach_bp.route('/referral')
@login_required
def referral():
    profile = current_user.coach_profile
    if not profile:
        return redirect(url_for('coach.dashboard'))
    from app.models.features import ReferralLink
    import secrets
    ref = profile.referral_link
    if not ref:
        slug = secrets.token_urlsafe(8)
        ref = ReferralLink(coach_id=profile.id, slug=slug)
        db.session.add(ref)
        db.session.commit()
    return render_template('coach/referral.html', profile=profile, ref=ref)

@coach_bp.route('/appointments/<int:appt_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appt_id):
    from app.models.calendar import Appointment
    from app.services.email import send_appointment_cancelled_email
    profile = current_user.coach_profile
    appt = Appointment.query.get_or_404(appt_id)
    if appt.coach_id != profile.id:
        return '', 403
    appt.status = 'cancelled'
    db.session.commit()
    try:
        send_appointment_cancelled_email(profile, appt.client, appt, 'your coach')
    except Exception:
        pass
    from app import socketio
    socketio.emit('notification', {
        'msg': f'Coach {profile.first_name} cancelled the appointment on {appt.date.strftime("%b %d")}.'
    }, room=f'user_{appt.client.user_id}')
    flash('Appointment cancelled.', 'info')
    return redirect(url_for('coach.calendar'))
"""

main_code = """
@main_bp.route('/join/<slug>')
def referral_join(slug):
    from app.models.features import ReferralLink
    from flask import session as flask_session
    ref = ReferralLink.query.filter_by(slug=slug).first()
    if ref:
        flask_session['referral_coach_id'] = ref.coach_id
        ref.referral_count += 1
        from app.extensions import db
        db.session.commit()
    return redirect(url_for('main.coaches_directory'))
"""

client_code = """
@client_bp.route('/appointments/<int:appt_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appt_id):
    from app.models.calendar import Appointment
    from app.services.email import send_appointment_cancelled_email
    profile = current_user.client_profile
    appt = Appointment.query.get_or_404(appt_id)
    if appt.client_id != profile.id:
        return '', 403
    appt.status = 'cancelled'
    db.session.commit()
    # Email both
    try:
        send_appointment_cancelled_email(appt.coach, profile, appt, 'the client')
    except Exception:
        pass
    from app import socketio
    socketio.emit('notification', {
        'msg': f'{profile.full_name} cancelled the appointment on {appt.date.strftime("%b %d")}.'
    }, room=f'user_{appt.coach.user_id}')
    flash('Appointment cancelled.', 'info')
    return redirect(url_for('client.appointments'))
"""

with open('app/routes/coach.py', 'a', encoding='utf-8') as f:
    f.write(coach_code)

with open('app/routes/main.py', 'a', encoding='utf-8') as f:
    f.write(main_code)

with open('app/routes/client.py', 'a', encoding='utf-8') as f:
    f.write(client_code)

print("Routes successfully appended.")
