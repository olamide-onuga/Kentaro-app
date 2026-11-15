from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session, current_app
from flask_login import login_required, current_user, logout_user
import datetime as dt
from datetime import date
from app.extensions import db
from app.models.user import ClientProfile
from app.models.coaching import CoachingPackage
from app.models.workout import Workout, WorkoutExercise
from app.models.progress import ClientProgram, WorkoutCompletion
from app.models.features import ClientPost
from app import socketio


client_bp = Blueprint('client', __name__, url_prefix='/client')

@client_bp.before_request
@login_required
def require_client():
    if not current_user.is_client:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    # Ensure client profile is complete before accessing most pages
    _OPEN_ENDPOINTS = {
        'client.profile', 'client.dashboard',
        'client.delete_profile', 'client.rate_coach',
        'client.validate_discount', 'client.get_available_slots',
        'client.chat', 'client.search_users', 'client.marketplace',
        'client.start_support_chat', 'client.view_program', 'client.my_program', 'client.preview_program_offer', 'client.decline_program_offer', 'client.accept_program_offer', 'client.checkout_program_offer', 'client.verify_program_payment', 'client.select_package', 'client.verify_package_payment', 'client.edit_chat_message', 'client.delete_chat_message',
        'static',
    }
    if request.endpoint not in _OPEN_ENDPOINTS:
        profile = current_user.client_profile
        if not profile or not getattr(profile, 'is_complete', False):
            flash('Please complete your profile before accessing this page.', 'warning')
            return redirect(url_for('client.profile'))

@client_bp.route('/chat')
@client_bp.route('/messages')
@client_bp.route('/chat/<int:partner_id>')
@client_bp.route('/messages/<int:partner_id>')
@login_required
def chat(partner_id=None):
    profile = current_user.client_profile
    if not profile:
        profile = ClientProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()

    import datetime as dt
    from app.models.user import ChatMessage, CoachProfile, User, ClientProfile
    from app.models.features import CustomOffer, ClientPost
    from app.models.coaching import ClientContract
    from sqlalchemy import or_, and_

    # Target partner from URL query params
    target_partner_id = request.args.get('partner_id', type=int) or request.args.get('coach_user_id', type=int) or partner_id

    # Check contract / accepted offer status to determine if offers should be suppressed
    active_contract = ClientContract.query.filter_by(client_id=profile.id, status='active').first()
    has_active_contract = bool(active_contract)
    has_accepted_offer = (CustomOffer.query.filter_by(client_id=profile.id, status='accepted').first() is not None)
    suppress_offers = has_active_contract or has_accepted_offer

    # Find all user IDs who messaged the client or were messaged by the client
    msg_partners = db.session.query(ChatMessage.sender_id).filter(
        ChatMessage.receiver_id == current_user.id
    ).union(
        db.session.query(ChatMessage.receiver_id).filter(
            ChatMessage.sender_id == current_user.id
        )
    ).all()
    partner_uids = [uid[0] for uid in msg_partners if uid[0] != current_user.id]

    all_contact_uids = []
    seen = set()

    # 1. Target partner from URL param (guarantee they are always in contacts)
    if target_partner_id and target_partner_id not in seen:
        seen.add(target_partner_id)
        all_contact_uids.append(target_partner_id)

    # 2. Client's enrolled coach (from active contract or linked coach)
    if active_contract and active_contract.coach and active_contract.coach.user_id not in seen:
        seen.add(active_contract.coach.user_id)
        all_contact_uids.append(active_contract.coach.user_id)
    elif profile.coach and profile.coach.user_id not in seen:
        seen.add(profile.coach.user_id)
        all_contact_uids.append(profile.coach.user_id)

    # 3. All conversation partners (marketplace coaches, searched users, etc.)
    for uid in partner_uids:
        if uid not in seen:
            seen.add(uid)
            all_contact_uids.append(uid)

    from app.models.features import ClosedSupportChat

    contacts = []
    for uid in all_contact_uids:
        u = User.query.get(uid)
        if not u:
            continue
        c_coach = u.coach_profile
        c_client = u.client_profile
        is_my_coach = bool((active_contract and active_contract.coach and u.id == active_contract.coach.user_id) or (profile.coach and u.id == profile.coach.user_id and has_active_contract))
        is_admin_user = bool(u.is_admin or (u.role and u.role.name == 'admin'))

        if is_admin_user:
            is_support_closed = bool(ClosedSupportChat.query.filter_by(user_id=current_user.id).first())
            if is_support_closed and target_partner_id != u.id:
                continue
            name = "Kentaro Support"
            role_label = "Admin"
            avatar = ""
            is_support = True
        elif c_coach and c_coach.first_name:
            name = f"Coach {c_coach.first_name} {c_coach.last_name or ''}".strip()
            role_label = 'My Coach' if is_my_coach else 'Marketplace Coach'
            avatar = name[6].upper() if len(name) > 6 else 'C'
            is_support = False
        elif c_client and c_client.first_name:
            name = c_client.full_name
            role_label = 'Athlete'
            avatar = name[0].upper()
            is_support = False
        else:
            name = u.email.split('@')[0]
            role_label = 'User'
            avatar = name[0].upper() if name else '?'
            is_support = False

        last_msg = ChatMessage.query.filter(
            or_(
                and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == uid),
                and_(ChatMessage.sender_id == uid, ChatMessage.receiver_id == current_user.id)
            )
        ).order_by(ChatMessage.timestamp.desc()).first()

        pending_offer = None
        if c_coach and not suppress_offers:
            pending_offer = CustomOffer.query.filter_by(
                coach_id=c_coach.id,
                client_id=profile.id,
                status='pending'
            ).order_by(CustomOffer.created_at.desc()).first()

        unread_count = ChatMessage.query.filter_by(sender_id=uid, receiver_id=current_user.id, is_read=False).count()

        # Category classification
        if is_support:
            cat = 'support'
        elif is_my_coach:
            cat = 'my_coach'
        elif last_msg and last_msg.context == 'marketplace':
            cat = 'marketplace'
        elif c_coach:
            cat = 'marketplace'
        else:
            cat = 'direct'

        contacts.append({
            'user': u,
            'coach': c_coach,
            'client': c_client,
            'name': name,
            'email': ('' if is_admin_user else u.email),
            'avatar': avatar,
            'is_my_coach': is_my_coach,
            'is_coach': bool(c_coach),
            'is_support': is_support,
            'category': cat,
            'role_label': role_label,
            'last_msg': last_msg,
            'unread_count': unread_count,
            'pending_offer': pending_offer
        })

    contacts.sort(key=lambda c: (
        c['last_msg'].timestamp if c['last_msg'] and c['last_msg'].timestamp else dt.datetime.min,
        1 if c['is_my_coach'] else 0
    ), reverse=True)

    view_mode = request.args.get('view')
    partner_id = None
    active_user = None
    active_coach = None

    if view_mode == 'contacts':
        partner_id = None
        active_user = None
        active_coach = None
    elif target_partner_id:
        partner_id = target_partner_id
        active_user = User.query.get(target_partner_id)
        if active_user and active_user.coach_profile:
            active_coach = active_user.coach_profile
    elif contacts:
        partner_id = contacts[0]['user'].id
        active_user = contacts[0]['user']
        active_coach = contacts[0]['coach']
    elif profile.coach:
        partner_id = profile.coach.user_id
        active_user = profile.coach.user
        active_coach = profile.coach

    active_offer = None
    if active_coach and not suppress_offers:
        active_offer = CustomOffer.query.filter_by(
            coach_id=active_coach.id,
            client_id=profile.id,
            status='pending'
        ).order_by(CustomOffer.created_at.desc()).first()

    messages = []
    if partner_id:
        # Mark all messages from partner as read in database
        ChatMessage.query.filter(
            ChatMessage.receiver_id == current_user.id,
            ChatMessage.sender_id == partner_id,
            ChatMessage.is_read == False
        ).update({'is_read': True})
        db.session.commit()

        messages = ChatMessage.query.filter(
            or_(
                and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == partner_id),
                and_(ChatMessage.sender_id == partner_id, ChatMessage.receiver_id == current_user.id)
            ),
            (ChatMessage.is_deleted == False) | (ChatMessage.is_deleted == None),
            (ChatMessage.context != 'archived') | (ChatMessage.context == None)
        ).order_by(ChatMessage.timestamp.asc()).all()

    support_admin = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).order_by(User.id.asc()).first()
    support_admin_id = support_admin.id if support_admin else None
    is_partner_admin = bool(active_user and (active_user.is_admin or (active_user.role and active_user.role.name == 'admin') or (support_admin_id and active_user.id == support_admin_id)))

    return render_template('client/chat.html',
                           is_partner_admin=is_partner_admin,
                           partner_id=partner_id,
                           active_user=active_user,
                           coach=active_coach,
                           conversations=contacts,
                           contacts=contacts,
                           active_offer=active_offer,
                           profile=profile,
                           messages=messages,
                           support_admin_id=support_admin_id)


@client_bp.route('/chat/start-support', methods=['POST'])
@login_required
def start_support_chat():
    from app.services.messaging import get_or_create_support_ticket, get_chat_url, send_system_notification
    from app.models.user import ChatMessage, User
    from app import socketio

    subject = request.form.get('subject', '').strip() or 'Platform Support Request'
    message_text = request.form.get('message', '').strip()

    if not message_text:
        flash('Please describe your support request.', 'warning')
        return redirect(url_for('client.chat', category='support'))

    support_admin = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).order_by(User.id.asc()).first()
    if not support_admin:
        flash('Support is currently unavailable. Please check back shortly.', 'error')
        return redirect(url_for('client.chat'))

    ticket = get_or_create_support_ticket(current_user.id, subject=subject)

    msg = ChatMessage(
        sender_id=current_user.id,
        receiver_id=support_admin.id,
        message=message_text,
        context='support',
        ticket_id=ticket.id
    )
    db.session.add(msg)
    db.session.commit()

    time_str = msg.timestamp.strftime('%H:%M') if msg.timestamp else ''
    sender_name = current_user.client_profile.full_name if current_user.client_profile else current_user.email
    admin_url = f"/admin/chat?partner_id={current_user.id}&ticket_id={ticket.id}"

    payload = {
        'id': msg.id,
        'from': current_user.id,
        'sender_id': current_user.id,
        'target_user_id': support_admin.id,
        'receiver_id': support_admin.id,
        'msg': message_text,
        'message': message_text,
        'timestamp': time_str,
        'from_name': sender_name,
        'context': 'support',
        'ticket_id': ticket.id,
        'chat_url': admin_url
    }
    socketio.emit('chat_message', payload, room='admin_support')
    socketio.emit('support_ticket_created', {
        'ticket_id': ticket.id,
        'ticket_ref': ticket.ticket_ref,
        'user_id': current_user.id,
        'user_name': sender_name,
        'subject': subject
    }, room='admin_support')

    flash(f'Support ticket {ticket.ticket_ref} created. A specialist will assist you shortly.', 'success')
    return redirect(url_for('client.chat', partner_id=support_admin.id, category='support'))


@client_bp.route('/chat/search-users')
@login_required
def search_users():
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify([])
    from app.models.user import User, ClientProfile, CoachProfile
    # Exclude admins and current user from user search
    query = User.query.filter(User.id != current_user.id, User.is_admin == False, ~User.role.has(name='admin'))
    query = query.filter(
        (User.email.ilike(f'%{q}%')) |
        (User.id.in_(
            CoachProfile.query.filter(
                (CoachProfile.first_name.ilike(f'%{q}%')) |
                (CoachProfile.last_name.ilike(f'%{q}%')) |
                (CoachProfile.specialization.ilike(f'%{q}%'))
            ).with_entities(CoachProfile.user_id)
        )) |
        (User.id.in_(
            ClientProfile.query.filter(
                (ClientProfile.first_name.ilike(f'%{q}%')) |
                (ClientProfile.last_name.ilike(f'%{q}%'))
            ).with_entities(ClientProfile.user_id)
        ))
    ).limit(10).all()

    results = []
    for u in query:
        coach = u.coach_profile
        client = u.client_profile
        if coach:
            name = f"Coach {coach.first_name} {coach.last_name or ''}".strip()
            role = f"Coach • {coach.specialization or 'Calisthenics'}"
        elif client:
            name = client.full_name or u.email.split('@')[0]
            role = "Athlete"
        else:
            name = u.email.split('@')[0]
            role = "User"
        results.append({
            'user_id': u.id,
            'name': name,
            'email': u.email,
            'avatar': name[0].upper() if name else '?',
            'role': role,
            'chat_url': url_for('client.chat', partner_id=u.id)
        })
    return jsonify(results)

@client_bp.route('/upload-voice', methods=['POST'])
@login_required
def upload_voice():
    is_json = request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if 'voice' not in request.files or request.files['voice'].filename == '':
        if is_json:
            return jsonify({'success': False, 'error': 'No voice file selected'}), 400
        flash('No voice file selected.', 'warning')
        return redirect(url_for('client.chat'))
    file = request.files['voice']
    from werkzeug.utils import secure_filename
    import uuid, os
    from flask import current_app
    filename = f"voice_{current_user.id}_{uuid.uuid4().hex[:8]}_{secure_filename(file.filename or 'voice.webm')}"
    voice_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'voice')
    os.makedirs(voice_dir, exist_ok=True)
    file_path = os.path.join(voice_dir, filename)
    file.save(file_path)
    voice_url = f"/static/uploads/voice/{filename}"

    from app.models.user import VoiceMessage, ChatMessage
    receiver_id = request.form.get('receiver_id', type=int)
    voice_msg = VoiceMessage(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        file_path=voice_url
    )
    chat_msg = ChatMessage(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        message='[Voice Message]',
        voice_url=voice_url
    )
    db.session.add(voice_msg)
    db.session.add(chat_msg)
    db.session.commit()

    time_str = chat_msg.timestamp.strftime('%H:%M') if chat_msg.timestamp else ''

    socketio.emit('chat_message', {
        'id': chat_msg.id,
        'from': current_user.id,
        'sender_id': current_user.id,
        'target_user_id': receiver_id,
        'receiver_id': receiver_id,
        'msg': '[Voice Message]',
        'message': '[Voice Message]',
        'voice_url': voice_url,
        'timestamp': time_str,
        'is_anonymous': False
    }, room=f'user_{receiver_id}')

    if is_json:
        return jsonify({'success': True, 'url': voice_url, 'timestamp': time_str})

    flash('Voice message sent.', 'success')
    return redirect(url_for('client.chat', partner_id=receiver_id))

@client_bp.route('/progress/photo', methods=['POST'])
@login_required
def upload_photo():
    import os, uuid
    import datetime as dt
    from datetime import datetime, date
    from werkzeug.utils import secure_filename
    from flask import current_app
    from app.models.progress import ProgressPhoto
    
    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))
        
    if 'photo' not in request.files or request.files['photo'].filename == '':
        flash('Please select an image file.', 'warning')
        return redirect(url_for('client.progress'))
        
    pfile = request.files['photo']
    ext = os.path.splitext(pfile.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
        flash('Allowed photo formats: JPG, PNG, WEBP.', 'danger')
        return redirect(url_for('client.progress'))
        
    filename = f"progress_{uuid.uuid4().hex[:10]}_{secure_filename(pfile.filename)}"
    save_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'photos')
    os.makedirs(save_dir, exist_ok=True)
    pfile.save(os.path.join(save_dir, filename))
    
    category = request.form.get('category', 'front')
    date_str = request.form.get('date')
    notes = request.form.get('notes')
    
    try:
        photo_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except ValueError:
        photo_date = date.today()
        
    photo = ProgressPhoto(
        client_id=profile.id,
        photo_filename=filename,
        category=category,
        date=photo_date,
        notes=notes
    )
    db.session.add(photo)
    db.session.commit()
    
    flash('Progress photo uploaded successfully!', 'success')
    return redirect(url_for('client.progress'))

@client_bp.route('/progress/form-check', methods=['POST'])
@login_required
def submit_form_check():
    import os, uuid
    from werkzeug.utils import secure_filename
    from flask import current_app
    from app.models.progress import FormCheckSubmission
    
    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))
        
    if 'video' not in request.files or request.files['video'].filename == '':
        flash('Please select a video file.', 'warning')
        return redirect(url_for('client.progress'))
        
    vfile = request.files['video']
    ext = os.path.splitext(vfile.filename)[1].lower()
    if ext not in ['.mp4', '.mov', '.webm', '.avi', '.mkv']:
        flash('Allowed video formats: MP4, MOV, WEBM.', 'danger')
        return redirect(url_for('client.progress'))
        
    filename = f"formcheck_{uuid.uuid4().hex[:10]}_{secure_filename(vfile.filename)}"
    save_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos')
    os.makedirs(save_dir, exist_ok=True)
    vfile.save(os.path.join(save_dir, filename))
    
    exercise_id = request.form.get('exercise_id', type=int) or None
    exercise_name = request.form.get('exercise_name', '').strip() or None
    notes = request.form.get('notes')
    
    # If exercise_name is given, see if it matches an existing exercise or use custom name
    if exercise_name and not exercise_id:
        from app.models.workout import Exercise
        matched_ex = Exercise.query.filter(Exercise.name.ilike(exercise_name)).first()
        if matched_ex:
            exercise_id = matched_ex.id
    
    submission = FormCheckSubmission(
        client_id=profile.id,
        exercise_id=exercise_id,
        exercise_name=exercise_name,
        video_filename=filename,
        client_notes=notes,
        status='pending'
    )
    db.session.add(submission)
    db.session.commit()
    
    # Notify coach
    if profile.coach and profile.coach.user_id:
        socketio.emit('notification', {
            'msg': f'Client {profile.first_name or profile.user.email} submitted a form check video for review.'
        }, room=f'user_{profile.coach.user_id}')
        
    flash('Form check video submitted! Your coach will review it soon.', 'success')
    return redirect(url_for('client.progress'))

@client_bp.route('/book-session')
@login_required
def book_session():
    import datetime as dt
    from datetime import date, timedelta
    from app.models.calendar import CoachScheduleConfig
    
    profile = current_user.client_profile
    coach = profile.coach if profile else None
    config = CoachScheduleConfig.query.filter_by(coach_id=profile.coach_id).first() if profile and profile.coach_id else None
    
    min_date = date.today().isoformat()
    window_days = config.booking_window_days if config else 14
    max_date = (date.today() + timedelta(days=window_days)).isoformat()
    
    return render_template('client/book_session.html',
                           coach=coach,
                           config=config,
                           min_date=min_date,
                           max_date=max_date)

@client_bp.route('/api/available-slots')
@login_required
def get_available_slots():
    import datetime as dt
    from datetime import datetime, date, time, timedelta
    from app.models.calendar import CoachAvailability, CoachScheduleConfig, Appointment
    
    profile = current_user.client_profile
    if not profile or not profile.coach_id:
        return jsonify({'slots': []})
        
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'slots': []})
        
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'slots': []})
        
    # Past dates have no slots
    if selected_date < date.today():
        return jsonify({'slots': []})
        
    day_idx = selected_date.weekday()  # 0=Monday ... 6=Sunday
    coach_id = profile.coach_id
    
    av = CoachAvailability.query.filter_by(coach_id=coach_id, day_of_week=day_idx, is_active=True).first()
    if not av:
        return jsonify({'slots': []})
        
    config = CoachScheduleConfig.query.filter_by(coach_id=coach_id).first()
    slot_duration = config.slot_duration if config else 30
    
    # Existing booked appointments on that date
    # Existing booked appointments on that date
    booked = Appointment.query.filter(
        Appointment.coach_id == coach_id,
        Appointment.date == selected_date,
        Appointment.status == 'scheduled'
    ).all()
    
    slots = []
    # Build timeline from av.start_time to av.end_time
    cur_dt = datetime.combine(selected_date, av.start_time)
    end_dt = datetime.combine(selected_date, av.end_time)
    now_dt = datetime.now()
    
    while cur_dt + timedelta(minutes=slot_duration) <= end_dt:
        slot_end_dt = cur_dt + timedelta(minutes=slot_duration)
        slot_st = cur_dt.time()
        slot_et = slot_end_dt.time()
        
        # Check if slot is in the future
        is_future = True
        if selected_date == date.today():
            is_future = cur_dt > now_dt + timedelta(minutes=15)
            
        # Check if slot overlaps with any scheduled appointment (start < slot_et and end > slot_st)
        is_booked = any(
            (a.start_time < slot_et and a.end_time > slot_st)
            for a in booked
        )
            
        if is_future and not is_booked:
            slots.append({
                'start_time': slot_st.strftime('%H:%M'),
                'end_time': slot_et.strftime('%H:%M'),
                'formatted_start': cur_dt.strftime('%I:%M %p'),
                'formatted_end': slot_end_dt.strftime('%I:%M %p')
            })
            
        cur_dt += timedelta(minutes=slot_duration)
        
    return jsonify({'slots': slots})

@client_bp.route('/book-session', methods=['POST'])
@login_required
def book_session_submit():
    import datetime as dt
    from datetime import datetime, date, time
    from app.models.calendar import CoachScheduleConfig, Appointment
    
    profile = current_user.client_profile
    if not profile or not profile.coach_id:
        flash('No coach assigned.', 'danger')
        return redirect(url_for('client.dashboard'))
        
    date_str = request.form.get('date')
    start_str = request.form.get('start_time')
    end_str = request.form.get('end_time')
    notes = request.form.get('client_notes')
    
    if not date_str or not start_str or not end_str:
        flash('Please select both a date and an available time slot.', 'warning')
        return redirect(url_for('client.book_session'))
        
    try:
        appt_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        st = datetime.strptime(start_str, '%H:%M').time()
        et = datetime.strptime(end_str, '%H:%M').time()
    except ValueError:
        flash('Invalid date or time format.', 'danger')
        return redirect(url_for('client.book_session'))
        
    # Strict Double-Booking & Overlap Prevention
    overlapping = Appointment.query.filter(
        Appointment.coach_id == profile.coach_id,
        Appointment.date == appt_date,
        Appointment.status == 'scheduled',
        Appointment.start_time < et,
        Appointment.end_time > st
    ).first()
    
    if overlapping:
        flash('This time slot is no longer available. Someone else has already booked this session time.', 'warning')
        return redirect(url_for('client.book_session'))
        
    config = CoachScheduleConfig.query.filter_by(coach_id=profile.coach_id).first()
    platform = config.meeting_platform if config else 'in_app'
    meeting_url = config.google_meet_url if (platform == 'google_meet' and config and config.google_meet_url) else url_for('client.voice_call')
    
    appt = Appointment(
        coach_id=profile.coach_id,
        client_id=profile.id,
        date=appt_date,
        start_time=st,
        end_time=et,
        title='1-on-1 Coaching Session',
        client_notes=notes,
        meeting_platform=platform,
        meeting_url=meeting_url,
        status='scheduled'
    )
    db.session.add(appt)
    db.session.commit()
    
    # Send email notification to coach
    try:
        from app.services.email import send_appointment_booked_email
        send_appointment_booked_email(profile.coach, appt)
    except Exception:
        pass

    # Notify coach via Socket.IO
    if profile.coach and profile.coach.user_id:
        date_formatted = appt_date.strftime("%A, %b %d, %Y")
        time_formatted = f'{st.strftime("%I:%M %p")} - {et.strftime("%I:%M %p")}'
        client_name = profile.full_name or profile.user.email
        
        socketio.emit('notification', {
            'msg': f'📅 New Session Booked! {client_name} booked a session for {date_formatted} ({time_formatted}).',
            'type': 'booking'
        }, room=f'user_{profile.coach.user_id}')
        
        socketio.emit('new_booking', {
            'appointment_id': appt.id,
            'client_name': client_name,
            'date': date_formatted,
            'time': time_formatted
        }, room=f'user_{profile.coach.user_id}')
        
    flash('Coaching session booked successfully! Your coach has been notified.', 'success')
    return redirect(url_for('client.appointments'))

@client_bp.route('/appointments')
@login_required
def appointments():
    import datetime as dt
    from datetime import date
    from app.models.calendar import Appointment
    
    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))
        
    today = date.today()
    upcoming = Appointment.query.filter(
        Appointment.client_id == profile.id,
        Appointment.date >= today,
        Appointment.status == 'scheduled'
    ).order_by(Appointment.date.asc(), Appointment.start_time.asc()).all()
    
    past = Appointment.query.filter(
        Appointment.client_id == profile.id,
        (Appointment.date < today) | (Appointment.status != 'scheduled')
    ).order_by(Appointment.date.desc(), Appointment.start_time.desc()).all()
    
    return render_template('client/appointments.html',
                           upcoming_appointments=upcoming,
                           past_appointments=past)

@client_bp.route('/appointment/<int:appointment_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    from app.models.calendar import Appointment
    from app.services.email import send_appointment_cancelled_email
    
    profile = current_user.client_profile
    appt = Appointment.query.get_or_404(appointment_id)
    if appt.client_id != profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('client.appointments'))
        
    appt.status = 'cancelled'
    db.session.commit()
    
    try:
        if profile.coach:
            send_appointment_cancelled_email(profile.coach, profile, appt, 'the client')
    except Exception:
        pass

    # Notify coach
    if profile.coach and profile.coach.user_id:
        socketio.emit('notification', {
            'msg': f'Client {profile.first_name or profile.user.email} cancelled their session on {appt.date.strftime("%b %d")}.'
        }, room=f'user_{profile.coach.user_id}')
        
    flash('Appointment cancelled.', 'info')
    return redirect(url_for('client.appointments'))

@client_bp.route('/delete_profile', methods=['POST'])
@login_required
def delete_profile():
    from app.models.progress import (
        BodyweightLog, ProgressPhoto, FormCheckSubmission,
        WorkoutCompletion, ClientProgram, ExerciseCompletion
    )
    from app.models.calendar import Appointment
    from app.models.user import ChatMessage

    profile = current_user.client_profile
    user = current_user

    if profile:
        # 1. Delete appointments
        Appointment.query.filter_by(client_id=profile.id).delete()

        # 2. Delete progress tracking
        BodyweightLog.query.filter_by(client_id=profile.id).delete()
        ProgressPhoto.query.filter_by(client_id=profile.id).delete()
        FormCheckSubmission.query.filter_by(client_id=profile.id).delete()

        # 3. Delete workout completions and exercise completions
        completions = WorkoutCompletion.query.filter_by(client_id=profile.id).all()
        for comp in completions:
            ExerciseCompletion.query.filter_by(workout_completion_id=comp.id).delete()
            db.session.delete(comp)

        # 4. Delete program assignments
        ClientProgram.query.filter_by(client_id=profile.id).delete()

        # 5. Delete Chat messages involving this user
        ChatMessage.query.filter(
            (ChatMessage.sender_id == user.id) | (ChatMessage.receiver_id == user.id)
        ).delete()

        # 6. Delete profile
        db.session.delete(profile)

    # 7. Delete user account
    db.session.delete(user)
    db.session.commit()

    logout_user()
    flash('Your client account and all progress data have been permanently deleted.', 'info')
    return redirect(url_for('main.index'))


def _get_workout_streak(profile):
    """Return current consecutive-day workout streak for a client."""
    import datetime as dt
    from app.models.progress import WorkoutCompletion
    streak = 0
    check_date = dt.date.today()
    while True:
        completed = WorkoutCompletion.query.filter(
            WorkoutCompletion.client_id == profile.id,
            db.func.date(WorkoutCompletion.completed_at) == check_date
        ).first()
        if completed:
            streak += 1
            check_date = check_date - dt.timedelta(days=1)
        else:
            break
    return streak

@client_bp.route('/check-in', methods=['GET', 'POST'])
@login_required
def check_in():
    profile = current_user.client_profile
    if not profile or not profile.coach:
        flash('No active coach.', 'warning')
        return redirect(url_for('client.dashboard'))
    
    from app.models.features import CheckIn
    import datetime as dt
    
    # Recent check-ins
    recent = CheckIn.query.filter_by(client_id=profile.id).order_by(CheckIn.created_at.desc()).limit(8).all()
    
    # Check if already submitted this week
    week_num = dt.datetime.utcnow().isocalendar()[1]
    year = dt.datetime.utcnow().year
    already_this_week = CheckIn.query.filter_by(client_id=profile.id, week_number=week_num).first()
    
    if request.method == 'POST':
        energy = request.form.get('energy', type=int)
        sleep_hours = request.form.get('sleep_hours', type=float)
        mood = request.form.get('mood', type=int)
        weight = request.form.get('weight', type=float)
        weight_unit = request.form.get('weight_unit', 'kg')
        notes = request.form.get('notes', '').strip()
        
        checkin = CheckIn(
            client_id=profile.id,
            coach_id=profile.coach_id,
            energy=energy,
            sleep_hours=sleep_hours,
            mood=mood,
            weight=weight,
            weight_unit=weight_unit,
            notes=notes,
            week_number=week_num
        )
        db.session.add(checkin)
        db.session.commit()
        
        # Award first-checkin badge
        _maybe_award_badge(profile, 'first_checkin')
        
        # Email coach
        from app.services.email import send_checkin_email
        try:
            send_checkin_email(profile.coach, profile, checkin)
        except Exception:
            pass
        
        # Socket notify coach
        socketio.emit('notification', {
            'msg': f'{profile.full_name} submitted their weekly check-in!'
        }, room=f'user_{profile.coach.user_id}')
        
        flash('Check-in submitted! Your coach has been notified.', 'success')
        return redirect(url_for('client.check_in'))
    
    return render_template('client/check_in.html', profile=profile, recent=recent, already_this_week=already_this_week)


def _maybe_award_badge(profile, slug):
    """Award a badge to a client if they don't already have it."""
    try:
        from app.models.features import Badge, ClientBadge
        badge = Badge.query.filter_by(slug=slug).first()
        if not badge:
            return
        already = ClientBadge.query.filter_by(client_id=profile.id, badge_id=badge.id).first()
        if not already:
            db.session.add(ClientBadge(client_id=profile.id, badge_id=badge.id))
            db.session.commit()
            socketio.emit('notification', {
                'msg': f'🏆 You earned a badge: {badge.name}!'
            }, room=f'user_{profile.user_id}')
    except Exception:
        pass


@client_bp.route('/nutrition', methods=['GET', 'POST'])
@login_required
def nutrition():
    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))
    
    from app.models.features import NutritionLog, MacroTarget
    import datetime as dt
    
    date_str = request.args.get('date', dt.date.today().isoformat())
    try:
        selected_date = dt.date.fromisoformat(date_str)
    except ValueError:
        selected_date = dt.date.today()
    
    if request.method == 'POST':
        meal_name = request.form.get('meal_name', '').strip()
        calories = request.form.get('calories', 0, type=float)
        protein_g = request.form.get('protein_g', 0, type=float)
        carbs_g = request.form.get('carbs_g', 0, type=float)
        fat_g = request.form.get('fat_g', 0, type=float)
        notes = request.form.get('notes', '').strip()
        log_date_str = request.form.get('log_date', dt.date.today().isoformat())
        try:
            log_date = dt.date.fromisoformat(log_date_str)
        except ValueError:
            log_date = dt.date.today()
        
        if meal_name:
            entry = NutritionLog(
                client_id=profile.id,
                date=log_date,
                meal_name=meal_name,
                calories=calories,
                protein_g=protein_g,
                carbs_g=carbs_g,
                fat_g=fat_g,
                notes=notes
            )
            db.session.add(entry)
            db.session.commit()
            flash('Meal logged!', 'success')
        return redirect(url_for('client.nutrition', date=log_date_str))
    
    logs = NutritionLog.query.filter_by(client_id=profile.id, date=selected_date).order_by(NutritionLog.created_at.asc()).all()
    targets = profile.macro_target
    
    totals = {
        'calories': sum(l.calories for l in logs),
        'protein_g': sum(l.protein_g for l in logs),
        'carbs_g': sum(l.carbs_g for l in logs),
        'fat_g': sum(l.fat_g for l in logs),
    }
    
    prev_date = selected_date - dt.timedelta(days=1)
    next_date = selected_date + dt.timedelta(days=1)
    
    return render_template('client/nutrition.html', profile=profile, logs=logs, totals=totals, targets=targets, selected_date=selected_date, prev_date=prev_date, next_date=next_date)


@client_bp.route('/nutrition/delete/<int:log_id>', methods=['POST'])
@login_required
def delete_nutrition_log(log_id):
    from app.models.features import NutritionLog
    entry = NutritionLog.query.get_or_404(log_id)
    profile = current_user.client_profile
    if entry.client_id != profile.id:
        return '', 403
    date_str = entry.date.isoformat()
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for('client.nutrition', date=date_str))


@client_bp.route('/habits', methods=['GET', 'POST'])
@login_required
def habits():
    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))
    
    from app.models.features import HabitTemplate, HabitLog
    import datetime as dt
    
    today = dt.date.today()
    my_habits = HabitTemplate.query.filter_by(client_id=profile.id, is_active=True).all()
    
    # Get today's logs
    today_logs = {log.habit_id: log for log in HabitLog.query.filter_by(client_id=profile.id, date=today).all()}
    
    if request.method == 'POST':
        habit_id = request.form.get('habit_id', type=int)
        completed = request.form.get('completed') == '1'
        
        existing = HabitLog.query.filter_by(habit_id=habit_id, client_id=profile.id, date=today).first()
        if existing:
            existing.completed = completed
        else:
            db.session.add(HabitLog(habit_id=habit_id, client_id=profile.id, date=today, completed=completed))
        db.session.commit()
        return jsonify({'ok': True})
    
    # Compute streaks per habit
    streaks = {}
    for habit in my_habits:
        streak = 0
        check_date = today
        while True:
            log = HabitLog.query.filter_by(habit_id=habit.id, client_id=profile.id, date=check_date, completed=True).first()
            if log:
                streak += 1
                check_date = check_date - dt.timedelta(days=1)
            else:
                break
        streaks[habit.id] = streak
    
    return render_template('client/habits.html', profile=profile, habits=my_habits, today_logs=today_logs, streaks=streaks, today=today)


@client_bp.route('/session-notes')
@login_required
def session_notes():
    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))
    from app.models.features import SessionNote
    notes = SessionNote.query.filter_by(client_id=profile.id).order_by(SessionNote.session_date.desc()).all()
    return render_template('client/session_notes.html', profile=profile, notes=notes)


@client_bp.route('/rate-coach', methods=['POST'])
@login_required
def rate_coach():
    profile = current_user.client_profile
    if not profile or not profile.coach_id:
        flash('You do not have an active coach to review.', 'warning')
        return redirect(url_for('client.dashboard'))
        
    rating = request.form.get('rating', 5, type=int)
    review_text = request.form.get('review_text', '').strip()
    
    from app.models.features import CoachReview
    review = CoachReview.query.filter_by(client_id=profile.id, coach_id=profile.coach_id).first()
    if review:
        review.rating = rating
        review.review_text = review_text
    else:
        review = CoachReview(client_id=profile.id, coach_id=profile.coach_id, rating=rating, review_text=review_text)
        db.session.add(review)
        
    db.session.commit()
    flash('Thank you for rating your coach!', 'success')
    return redirect(url_for('client.dashboard'))

@client_bp.route('/community', methods=['GET', 'POST'])
@login_required
def community():
    import os
    from werkzeug.utils import secure_filename
    from app.models.features import Community, CommunityMember, CommunityMessage as CM

    profile = current_user.client_profile
    if not profile or not profile.coach_id:
        flash('Community Chat is reserved for athletes enrolled with a coach. Find a coach to join their Squad!', 'warning')
        return redirect(url_for('client.dashboard'))

    coach = profile.coach
    comm = Community.query.filter_by(coach_id=coach.id).first()
    if not comm:
        comm = Community(coach_id=coach.id, name=f"Coach {coach.first_name}'s Calisthenics Squad")
        db.session.add(comm)
        db.session.commit()

    membership = CommunityMember.query.filter_by(community_id=comm.id, user_id=current_user.id).first()
    if not membership:
        db.session.add(CommunityMember(community_id=comm.id, user_id=current_user.id))
        db.session.commit()

    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        reply_to_id = request.form.get('reply_to_id', type=int)
        if not content:
            flash('Message cannot be empty.', 'warning')
            return redirect(url_for('client.community'))

        video_url = None
        video_file = request.files.get('video_file')
        if video_file and video_file.filename:
            uploads_dir = os.path.join(current_app.static_folder, 'uploads', 'videos')
            os.makedirs(uploads_dir, exist_ok=True)
            filename = secure_filename(video_file.filename)
            video_file.save(os.path.join(uploads_dir, filename))
            video_url = filename

        msg = CM(
            community_id=comm.id,
            sender_id=current_user.id,
            content=content,
            video_url=video_url,
            reply_to_id=reply_to_id if reply_to_id else None
        )
        db.session.add(msg)
        db.session.commit()
        flash('Message posted to Squad feed!', 'success')
        return redirect(url_for('client.community'))

    squad_clients = coach.clients.all() if hasattr(coach, 'clients') else []
    messages = CM.query.filter_by(community_id=comm.id).order_by(CM.created_at.asc()).all()
    return render_template('client/community.html', messages=messages, profile=profile, coach=coach, squad_clients=squad_clients, community=comm)



@client_bp.route('/checkout-offer/<int:offer_id>')
@login_required
def checkout_offer(offer_id):
    from app.models.features import CustomOffer
    profile = current_user.client_profile
    if not profile:
        flash('Profile not found.', 'danger')
        return redirect(url_for('client.dashboard'))

    offer = CustomOffer.query.get_or_404(offer_id)
    if offer.client_id != profile.id:
        flash('Unauthorized offer action.', 'danger')
        return redirect(url_for('client.dashboard'))

    payment_url = offer.payment_link or ''
    from app.services.paystack import get_paystack_public_key, _convert_to_ngn
    paystack_public_key = get_paystack_public_key()
    import time
    ref = f"pstk_offer_{offer.id}_{current_user.id}_{int(time.time())}"
    # Convert to NGN for Nigerian Paystack merchant accounts
    original_currency = (offer.currency or 'USD').upper()
    original_amount = float(offer.amount)
    ngn_amount, _, rate_used = _convert_to_ngn(original_amount, original_currency)
    amount_in_kobo = int(round(ngn_amount * 100))
    currency = 'NGN'  # Always charge in NGN for Nigerian Paystack accounts

    return render_template('client/checkout_offer.html',
                           offer=offer,
                           payment_url=payment_url,
                           coach=offer.coach,
                           paystack_public_key=paystack_public_key,
                           payment_reference=ref,
                           amount_in_kobo=amount_in_kobo,
                           currency=currency,
                           original_currency=original_currency,
                           ngn_amount=ngn_amount,
                           rate_used=rate_used)


def _fulfill_offer_acceptance(profile, offer_id, reference=None):
    from app.models.features import CustomOffer, ClientPost
    from app.models.coaching import ClientContract
    from app.models.user import ChatMessage
    from app import socketio
    import datetime as dt

    offer = CustomOffer.query.get_or_404(offer_id)
    if offer.client_id != profile.id:
        flash('Unauthorized offer action.', 'danger')
        return redirect(url_for('client.dashboard'))

    offer.status = 'accepted'

    now = dt.datetime.utcnow()
    end_date = now + dt.timedelta(weeks=offer.duration_weeks or 4)

    # Supersede previous active contracts
    old_contract = ClientContract.query.filter_by(client_id=profile.id, status='active').first()
    if old_contract:
        old_contract.status = 'superseded'

    contract = ClientContract(
        client_id=profile.id,
        coach_id=offer.coach_id,
        status='active',
        start_date=now,
        end_date=end_date,
        monthly_renewal_price=offer.amount,
        months_subscribed=max(1, (offer.duration_weeks or 4) // 4)
    )
    db.session.add(contract)
    profile.coach_id = offer.coach_id

    # Close any open marketplace posts for this client
    posts = ClientPost.query.filter_by(client_id=profile.id, status='active').all()
    for p in posts:
        p.status = 'closed'

    # Archive previous marketplace messages between client & coach so they start fresh
    coach = offer.coach
    if coach and coach.user_id:
        ChatMessage.query.filter(
            or_(
                and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == coach.user_id),
                and_(ChatMessage.sender_id == coach.user_id, ChatMessage.receiver_id == current_user.id)
            )
        ).update({'context': 'archived'}, synchronize_session=False)

    db.session.commit()

    # Real-time notifications to coach and client
    if coach and coach.user_id:
        socketio.emit('notification', {
            'msg': f'{profile.full_name} accepted your budget offer of {offer.currency or 'USD'} {offer.amount:,.2f}!'
        }, room=f'user_{coach.user_id}')

    socketio.emit('notification', {
        'msg': f'Offer accepted! You are now connected with Coach {coach.first_name}. You can make your payment and get started with your coaching.',
        'chat_url': url_for('client.dashboard')
    }, room=f'user_{current_user.id}')

    flash(f'Budget accepted! You are now coached by {coach.first_name}.', 'success')
    return redirect(url_for('client.dashboard'))


@client_bp.route('/accept-offer/<int:offer_id>', methods=['POST'])
@login_required
def accept_offer(offer_id):
    profile = current_user.client_profile
    ref = request.form.get('reference') or request.args.get('reference')
    return _fulfill_offer_acceptance(profile, offer_id, reference=ref)


@client_bp.route('/contract/approve-termination', methods=['POST'])
@login_required
def approve_contract_termination():
    profile = current_user.client_profile
    if not profile:
        flash('Athlete profile not found.', 'danger')
        return redirect(url_for('client.dashboard'))
    
    from app.models.coaching import ClientContract
    import datetime as dt
    from datetime import datetime
    
    contract = ClientContract.query.filter_by(
        client_id=profile.id,
        status='active',
        termination_status='pending_client_approval'
    ).first()
    
    if not contract:
        flash('No pending contract termination request found.', 'warning')
        return redirect(url_for('client.dashboard'))
        
    contract.status = 'terminated'
    contract.termination_status = 'approved'
    contract.terminated_by = 'coach'
    contract.terminated_at = datetime.utcnow()
    
    coach = contract.coach
    coach_user_id = coach.user_id if coach else None
    
    profile.coach_id = None
    profile.active_package_id = None
    db.session.commit()
    
    if coach_user_id:
        from app import socketio
        socketio.emit('notification', {
            'msg': f'{profile.full_name} approved your contract termination request.'
        }, room=f'user_{coach_user_id}')
        
    flash('Contract termination approved. Your coaching contract has ended.', 'info')
    return redirect(url_for('client.dashboard'))


@client_bp.route('/contract/decline-termination', methods=['POST'])
@login_required
def decline_contract_termination():
    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))
        
    from app.models.coaching import ClientContract
    contract = ClientContract.query.filter_by(
        client_id=profile.id,
        status='active',
        termination_status='pending_client_approval'
    ).first()
    
    if not contract:
        flash('No pending contract termination request found.', 'warning')
        return redirect(url_for('client.dashboard'))
        
    contract.termination_status = 'declined'
    coach = contract.coach
    coach_user_id = coach.user_id if coach else None
    db.session.commit()
    
    if coach_user_id:
        from app import socketio
        socketio.emit('notification', {
            'msg': f'{profile.full_name} declined your contract termination request.'
        }, room=f'user_{coach_user_id}')
        
    flash('Contract termination request declined. Your contract remains active.', 'success')
    return redirect(url_for('client.dashboard'))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# DASHBOARD
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/dashboard')
@login_required
def dashboard():
    import datetime as dt
    from app.models.coaching import ClientContract
    from app.models.features import CustomOffer
    from app.models.progress import WorkoutCompletion, BodyweightLog
    from app.models.calendar import Appointment

    profile = current_user.client_profile
    if not profile:
        profile = ClientProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()

    from app.models.features import ClientPost
    active_post = ClientPost.query.filter_by(client_id=profile.id, status='active').first()

    # Active contract & days remaining
    active_contract = None
    days_remaining = None
    if profile.coach_id:
        active_contract = ClientContract.query.filter_by(
            client_id=profile.id, status='active'
        ).first()
        if active_contract and active_contract.end_date:
            delta = active_contract.end_date - dt.datetime.utcnow()
            days_remaining = max(delta.days, 0)

    # Pending offers (suppressed if already has active contract / accepted offer)
    has_active_contract = bool(profile.coach_id) or (active_contract is not None)
    has_accepted_offer = CustomOffer.query.filter_by(client_id=profile.id, status='accepted').first() is not None
    if not has_active_contract and not has_accepted_offer:
        pending_offers = CustomOffer.query.filter_by(
            client_id=profile.id, status='pending'
        ).order_by(CustomOffer.created_at.desc()).all()
    else:
        pending_offers = []

    # Today's workout
    today_day_name = dt.datetime.utcnow().strftime('%A')
    today_workout = None
    today_is_completed = False
    program = None
    progress = {'total': 0, 'completed': 0}

    if profile.coach_id:
        client_program = ClientProgram.query.filter_by(client_id=profile.id).first()
        if client_program:
            program = client_program.program if hasattr(client_program, 'program') else None
            if program:
                from app.models.workout import ProgramPhase
                phase_ids = [p.id for p in ProgramPhase.query.filter_by(program_id=program.id).all()]
                workouts = Workout.query.filter(Workout.phase_id.in_(phase_ids)).all() if phase_ids else []
                progress['total'] = len([w for w in workouts if not w.is_rest])
                completed_ids = {
                    c.workout_id for c in WorkoutCompletion.query.filter_by(client_id=profile.id).all()
                }
                progress['completed'] = len([w for w in workouts if w.id in completed_ids and not w.is_rest])
                today_workout = next(
                    (w for w in workouts if w.day_name and w.day_name.lower() == today_day_name.lower()),
                    None
                )
                if today_workout:
                    today_is_completed = WorkoutCompletion.query.filter(
                        WorkoutCompletion.client_id == profile.id,
                        WorkoutCompletion.workout_id == today_workout.id,
                        db.func.date(WorkoutCompletion.completed_at) == dt.date.today()
                    ).first() is not None

    # Workout streak
    workout_streak = _get_workout_streak(profile) if profile else 0

    # Upcoming appointments
    try:
        upcoming_appointments = Appointment.query.filter(
            Appointment.client_id == profile.id,
            Appointment.status.in_(['confirmed', 'scheduled']),
            Appointment.date >= dt.date.today()
        ).order_by(Appointment.date.asc()).limit(3).all()
    except Exception:
        upcoming_appointments = []

    return render_template(
        'client/dashboard.html',
        profile=profile,
        pending_offers=pending_offers,
        active_contract=active_contract,
        days_remaining=days_remaining,
        today_workout=today_workout,
        today_is_completed=today_is_completed,
        today_day_name=today_day_name,
        progress=progress,
        workout_streak=workout_streak,
        upcoming_appointments=upcoming_appointments,
        active_post=active_post,
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PROFILE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    import os, uuid
    from werkzeug.utils import secure_filename

    p = current_user.client_profile
    if not p:
        p = ClientProfile(user_id=current_user.id)
        db.session.add(p)
        db.session.commit()

    if request.method == 'POST':
        p.first_name = request.form.get('first_name', '').strip()
        p.last_name = request.form.get('last_name', '').strip()
        p.age = request.form.get('age', type=int)
        p.gender = request.form.get('gender', '').strip() or None
        p.height_cm = request.form.get('height_cm', type=float)
        p.weight_kg = request.form.get('weight_kg', type=float)
        p.fitness_goal = request.form.get('fitness_goal', '').strip() or None
        p.experience_level = request.form.get('experience_level', '').strip() or None
        p.preferred_days = request.form.get('preferred_days', '').strip() or None
        p.injuries = request.form.get('injuries', '').strip() or None
        p.timezone = request.form.get('timezone', '').strip() or None

        # Profile photo
        photo_file = request.files.get('profile_photo')
        if photo_file and photo_file.filename:
            ext = os.path.splitext(photo_file.filename)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                fname = f"client_{p.id}_{uuid.uuid4().hex[:8]}{ext}"
                save_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'app/static/uploads'), 'avatars')
                os.makedirs(save_dir, exist_ok=True)
                photo_file.save(os.path.join(save_dir, fname))
                p.profile_photo = f'/static/uploads/avatars/{fname}'

        # Mark complete if required fields present
        if p.first_name and p.last_name and p.fitness_goal:
            p.is_complete = True

        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('client.profile'))

    return render_template('client/profile.html', profile=p)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MY PROGRAM
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/my-program')
@login_required
def my_program():
    import datetime as dt
    from app.models.progress import WorkoutCompletion

    profile = current_user.client_profile
    if not profile:
        flash('Please complete your profile to view your program.', 'warning')
        return redirect(url_for('client.dashboard'))

    client_program = ClientProgram.query.filter_by(client_id=profile.id).order_by(ClientProgram.is_active.desc(), ClientProgram.assigned_at.desc()).first()
    if not client_program and not profile.coach_id:
        flash('You do not have an active workout program assigned yet.', 'info')
        return redirect(url_for('client.dashboard'))

    program = client_program.program if client_program and hasattr(client_program, 'program') else None
    if client_program and getattr(client_program, 'status', None) == 'sent':
        client_program.status = 'viewed'
        db.session.commit()

    workouts = []
    if program:
        from app.models.workout import ProgramPhase
        phase_ids = [p.id for p in ProgramPhase.query.filter_by(program_id=program.id).all()]
        raw_workouts = Workout.query.filter(Workout.phase_id.in_(phase_ids)).order_by(Workout.day_number).all() if phase_ids else []
        completed_ids = {
            c.workout_id for c in WorkoutCompletion.query.filter_by(client_id=profile.id).all()
        }
        today_name = dt.datetime.utcnow().strftime('%A').lower()
        for w in raw_workouts:
            workouts.append({
                'workout': w,
                'is_completed': w.id in completed_ids,
                'is_today': w.day_name and w.day_name.lower() == today_name,
                'exercises': WorkoutExercise.query.filter_by(workout_id=w.id).all(),
            })

    return render_template('client/my_program.html', profile=profile, program=program, workouts=workouts)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# WORKOUT VIEW
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/programs/<int:program_id>')
@login_required
def view_program(program_id):
    from app.models.workout import Program, ProgramPhase, Workout, WorkoutExercise
    from app.models.progress import WorkoutCompletion, ClientProgram
    import datetime as dt

    profile = current_user.client_profile
    if not profile:
        flash('Please complete your profile first.', 'warning')
        return redirect(url_for('client.profile'))

    program = Program.query.get_or_404(program_id)
    cp = ClientProgram.query.filter_by(client_id=profile.id, program_id=program.id).first()
    if not cp and profile.coach_id != program.coach_id:
        flash('You are not authorized to view this program.', 'danger')
        return redirect(url_for('client.dashboard'))

    if cp and getattr(cp, 'status', None) == 'sent':
        cp.status = 'viewed'
        db.session.commit()

    phase_ids = [p.id for p in ProgramPhase.query.filter_by(program_id=program.id).all()]
    raw_workouts = Workout.query.filter(Workout.phase_id.in_(phase_ids)).order_by(Workout.day_number).all() if phase_ids else []
    completed_ids = {
        c.workout_id for c in WorkoutCompletion.query.filter_by(client_id=profile.id).all()
    }
    today_name = dt.datetime.utcnow().strftime('%A').lower()
    workouts = []
    for w in raw_workouts:
        workouts.append({
            'workout': w,
            'is_completed': w.id in completed_ids,
            'is_today': w.day_name and w.day_name.lower() == today_name,
            'exercises': WorkoutExercise.query.filter_by(workout_id=w.id).all(),
        })

    return render_template('client/my_program.html', profile=profile, program=program, workouts=workouts)


@client_bp.route('/workout/<int:workout_id>')
@login_required
def workout_view(workout_id):
    import datetime as dt
    from app.models.progress import WorkoutCompletion

    profile = current_user.client_profile
    workout = Workout.query.get_or_404(workout_id)
    exercises = WorkoutExercise.query.filter_by(workout_id=workout_id).all()

    already_completed = WorkoutCompletion.query.filter(
        WorkoutCompletion.client_id == profile.id,
        WorkoutCompletion.workout_id == workout_id,
        db.func.date(WorkoutCompletion.completed_at) == dt.date.today()
    ).first()

    return render_template(
        'client/workout_view.html',
        profile=profile,
        workout=workout,
        exercises=exercises,
        already_completed=already_completed,
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# COMPLETE WORKOUT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/workout/<int:workout_id>/complete', methods=['POST'])
@login_required
def complete_workout(workout_id):
    from app.models.progress import WorkoutCompletion
    import datetime as dt

    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))

    workout = Workout.query.get_or_404(workout_id)
    client_notes = request.form.get('client_notes', '').strip()
    perceived_effort = request.form.get('perceived_effort', type=int)
    video_file = request.files.get('video')
    video_filename = None

    if video_file and video_file.filename:
        import os, uuid
        from werkzeug.utils import secure_filename
        ext = os.path.splitext(video_file.filename)[1].lower()
        if ext in ['.mp4', '.mov', '.webm', '.avi']:
            fname = f"completion_{uuid.uuid4().hex[:8]}{ext}"
            save_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'app/static/uploads'), 'videos')
            os.makedirs(save_dir, exist_ok=True)
            video_file.save(os.path.join(save_dir, fname))
            video_filename = fname

    comp = WorkoutCompletion(
        client_id=profile.id,
        workout_id=workout_id,
        completed_at=dt.datetime.utcnow(),
        client_notes=client_notes or None,
        perceived_effort=perceived_effort,
        video_filename=video_filename,
    )
    db.session.add(comp)
    db.session.commit()

    # Award first-workout badge
    _maybe_award_badge(profile, 'first_workout')

    # Notify coach
    if profile.coach and profile.coach.user_id:
        socketio.emit('notification', {
            'msg': f'{profile.first_name or "Client"} completed: {workout.name}'
        }, room=f'user_{profile.coach.user_id}')

    flash(f'Great job! {workout.name} marked as complete. 💪', 'success')
    return redirect(url_for('client.my_program'))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PROGRESS & TRACKING
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/progress', methods=['GET', 'POST'])
@login_required
def progress():
    import datetime as dt
    from app.models.progress import BodyweightLog, ProgressPhoto, FormCheckSubmission

    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))

    weight_logs = BodyweightLog.query.filter_by(client_id=profile.id).order_by(BodyweightLog.date.asc()).all()
    latest_weight = BodyweightLog.query.filter_by(client_id=profile.id).order_by(BodyweightLog.date.desc()).first()
    photos = ProgressPhoto.query.filter_by(client_id=profile.id).order_by(ProgressPhoto.date.desc()).all()
    form_checks = FormCheckSubmission.query.filter_by(client_id=profile.id).order_by(FormCheckSubmission.created_at.desc()).all()
    today_str = dt.date.today().isoformat()

    chart_labels = [w.date.strftime('%b %d') if hasattr(w.date, 'strftime') else str(w.date) for w in weight_logs]
    chart_data = [float(w.weight) for w in weight_logs]

    return render_template(
        'client/progress.html',
        profile=profile,
        weight_logs=weight_logs,
        latest_weight=latest_weight,
        photos=photos,
        form_checks=form_checks,
        today_str=today_str,
        chart_labels=chart_labels,
        chart_data=chart_data,
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# LOG WEIGHT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/log-weight', methods=['POST'])
@login_required
def log_weight():
    import datetime as dt
    from app.models.progress import BodyweightLog

    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))

    weight = request.form.get('weight', type=float)
    unit = request.form.get('unit', 'kg')
    notes = request.form.get('notes', '').strip() or None
    date_str = request.form.get('date', dt.date.today().isoformat())
    try:
        log_date = dt.date.fromisoformat(date_str)
    except ValueError:
        log_date = dt.date.today()

    if weight:
        log = BodyweightLog(client_id=profile.id, weight=weight, unit=unit, date=log_date, notes=notes)
        db.session.add(log)
        db.session.commit()
        flash('Weight logged!', 'success')

    return redirect(url_for('client.progress'))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# WORKOUT HISTORY
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/history')
@login_required
def history():
    from app.models.progress import WorkoutCompletion

    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))

    completions = WorkoutCompletion.query.filter_by(client_id=profile.id).order_by(
        WorkoutCompletion.completed_at.desc()
    ).all()

    return render_template('client/history.html', profile=profile, completions=completions)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# TERMINATE CONTRACT (client-side — client can also request termination)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/terminate-contract', methods=['POST'])
@login_required
def terminate_contract():
    import datetime as dt
    from app.models.coaching import ClientContract

    profile = current_user.client_profile
    if not profile or not profile.coach_id:
        flash('No active coaching contract found.', 'warning')
        return redirect(url_for('client.dashboard'))

    reason = request.form.get('reason', '').strip() or None
    contract = ClientContract.query.filter_by(client_id=profile.id, status='active').first()

    if contract:
        contract.status = 'terminated'
        contract.terminated_by = 'client'
        contract.termination_reason = reason
        try:
            contract.terminated_at = dt.datetime.utcnow()
        except Exception:
            pass

    coach_user_id = profile.coach.user_id if profile.coach else None
    profile.coach_id = None
    profile.active_package_id = None
    db.session.commit()

    if coach_user_id:
        socketio.emit('notification', {
            'msg': f'{profile.full_name} ended the coaching contract.'
        }, room=f'user_{coach_user_id}')

    flash('Your coaching contract has been ended.', 'info')
    return redirect(url_for('client.dashboard'))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# RENEW CONTRACT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/renew-contract', methods=['GET', 'POST'])
@login_required
def renew_contract():
    profile = current_user.client_profile
    if not profile or not profile.coach_id:
        flash('You need an active coach to renew.', 'warning')
        return redirect(url_for('client.dashboard'))

    packages = CoachingPackage.query.filter_by(
        coach_id=profile.coach_id, is_active=True
    ).order_by(CoachingPackage.price.asc()).all()

    return render_template('client/renew_contract.html', profile=profile, packages=packages)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# RENEW PAYMENT (dummy / Paystack webhook)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/renew-payment', methods=['POST'])
@login_required
def renew_payment():
    import datetime as dt
    from app.models.coaching import ClientContract, CoachDiscount

    profile = current_user.client_profile
    if not profile:
        return redirect(url_for('client.dashboard'))

    package_id = request.form.get('package_id', type=int)
    discount_code = request.form.get('discount_code', '').strip().upper()

    package = CoachingPackage.query.get(package_id) if package_id else None
    if not package:
        flash('Invalid package selected.', 'danger')
        return redirect(url_for('client.renew_contract'))

    # Apply discount
    discount_pct = 0
    if discount_code:
        discount_obj = CoachDiscount.query.filter_by(
            coach_id=package.coach_id, code=discount_code, is_active=True
        ).first()
        if discount_obj:
            discount_pct = discount_obj.percent_off or 0

    # Create new contract (extend existing or create new)
    now = dt.datetime.utcnow()
    old_contract = ClientContract.query.filter_by(client_id=profile.id, status='active').first()
    start_date = now
    if old_contract and old_contract.end_date and old_contract.end_date > now:
        start_date = old_contract.end_date
        old_contract.status = 'renewed'

    end_date = start_date + dt.timedelta(weeks=package.duration_weeks or 4)
    new_contract = ClientContract(
        client_id=profile.id,
        coach_id=package.coach_id,
        package_id=package.id,
        status='active',
        start_date=start_date,
        end_date=end_date,
    )
    db.session.add(new_contract)
    profile.coach_id = package.coach_id
    profile.active_package_id = package.id
    db.session.commit()

    if package.coach and package.coach.user_id:
        socketio.emit('notification', {
            'msg': f'{profile.full_name} renewed their contract ({package.name}).'
        }, room=f'user_{package.coach.user_id}')

    flash(f'Contract renewed! You have {package.duration_weeks} weeks of coaching access.', 'success')
    return redirect(url_for('client.dashboard'))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# VALIDATE DISCOUNT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/validate-discount')
@login_required
def validate_discount():
    from app.models.coaching import CoachDiscount

    code = request.args.get('code', '').strip().upper()
    coach_id = request.args.get('coach_id', type=int)

    if not code or not coach_id:
        return jsonify({'valid': False, 'message': 'Missing code or coach.'})

    discount = CoachDiscount.query.filter_by(code=code, coach_id=coach_id, is_active=True).first()
    if discount:
        return jsonify({'valid': True, 'percent_off': discount.percent_off or 0, 'message': f'{discount.percent_off}% off applied!'})
    return jsonify({'valid': False, 'message': 'Invalid or expired discount code.'})


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# VOICE CALL
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/voice-call')
@login_required
def voice_call():
    import os
    from app.models.user import User
    from app import _allowed_communication

    profile = current_user.client_profile
    partner_id = request.args.get('partner_id', type=int)

    # If partner_id not provided via URL, fallback to the client's assigned coach
    if not partner_id and profile and profile.coach and profile.coach.user:
        partner_id = profile.coach.user.id

    if not partner_id:
        flash('No coach or calling partner found. Please select a coach or contact first.', 'warning')
        return redirect(url_for('client.dashboard'))

    # Verify authorization
    if not _allowed_communication(current_user.id, partner_id):
        flash('You are not permitted to start a call with this user.', 'danger')
        return redirect(url_for('client.dashboard'))

    partner_user = User.query.get(partner_id)
    if not partner_user:
        flash('Calling partner not found.', 'danger')
        return redirect(url_for('client.dashboard'))

    partner_name = "Coach"
    if partner_user.coach_profile:
        name = partner_user.coach_profile.first_name or "Coach"
        partner_name = f"Coach {name}".strip()
    elif partner_user.client_profile:
        partner_name = partner_user.client_profile.full_name or "Athlete"
    elif partner_user.is_admin:
        partner_name = "Kentaro Support"
    else:
        partner_name = partner_user.email.split('@')[0] if partner_user.email else "Participant"

    turn_config = None
    turn_url = os.environ.get('TURN_URL') or os.environ.get('COTURN_URL')
    if turn_url:
        turn_config = {
            'urls': turn_url,
            'username': os.environ.get('TURN_USERNAME', ''),
            'credential': os.environ.get('TURN_CREDENTIAL', '')
        }

    return render_template(
        'client/voice_call.html',
        profile=profile,
        partner_id=partner_id,
        partner_name=partner_name,
        turn_config=turn_config
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MARKETPLACE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/marketplace', methods=['GET', 'POST'])
@login_required
def marketplace():
    from app.models.user import CoachProfile
    from app.models.features import ClientPost
    from app.models.coaching import ClientContract
    profile = current_user.client_profile
    if not profile:
        profile = ClientProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()

    active_contract = ClientContract.query.filter_by(client_id=profile.id, status='active').first()

    if request.method == 'POST':
        if active_contract:
            flash('You already have an active coach and coaching contract! Access your coach directly in Chat.', 'info')
            return redirect(url_for('client.marketplace'))

        # Check if already has an active post
        existing_active = ClientPost.query.filter_by(client_id=profile.id, status='active').first()
        if existing_active:
            flash('You already have an active coaching request published. You can withdraw or update it below.', 'warning')
            return redirect(url_for('client.marketplace'))

        title = request.form.get('title', '').strip()
        problem = request.form.get('problem', '').strip()
        goal = request.form.get('goal', '').strip()
        specialization = request.form.get('specialization', '').strip() or 'Calisthenics & Strength'
        skill_level = request.form.get('skill_level', '').strip() or 'Beginner'
        experience = request.form.get('experience', '').strip() or '0-6 Months'
        min_budget = request.form.get('min_budget', type=float)
        max_budget = request.form.get('max_budget', type=float)
        currency = request.form.get('currency', 'USD').strip().upper()
        is_flexible_budget = bool(request.form.get('is_flexible_budget'))
        expectations = request.form.get('expectations', '').strip()
        preferred_duration = request.form.get('preferred_duration', '').strip() or '12 Weeks'
        comm_preference = request.form.get('comm_preference', '').strip() or 'In-App Chat & Voice Notes'

        budget_str = f"{currency} {min_budget:g} - {max_budget:g}" if (min_budget and max_budget) else (f"Up to {currency} {max_budget:g}" if max_budget else ("Flexible" if is_flexible_budget else None))

        if title and problem and goal:
            new_post = ClientPost(
                client_id=profile.id,
                title=title,
                problem=problem,
                goal=goal,
                specialization=specialization,
                skill_level=skill_level,
                experience=experience,
                min_budget=min_budget,
                max_budget=max_budget,
                currency=currency,
                is_flexible_budget=is_flexible_budget,
                budget=budget_str,
                expectations=expectations,
                preferred_duration=preferred_duration,
                comm_preference=comm_preference,
                status='active'
            )
            db.session.add(new_post)
            db.session.commit()
            flash('Your coaching request has been published! Eligible certified coaches can now discover and contact you.', 'success')
            return redirect(url_for('client.marketplace'))
        else:
            flash('Please fill in all required fields (Title, Struggles, and Goals).', 'danger')

    my_posts = ClientPost.query.filter_by(client_id=profile.id).order_by(ClientPost.created_at.desc()).all()
    active_post = next((p for p in my_posts if p.status == 'active'), None)
    all_coaches = CoachProfile.query.filter(CoachProfile.is_approved == True).order_by(CoachProfile.created_at.desc()).all()
    coaches = [c for c in all_coaches if getattr(c, 'is_complete', False)]
    return render_template('client/marketplace.html', profile=profile, coaches=coaches, my_posts=my_posts, active_post=active_post, active_contract=active_contract)


@client_bp.route('/marketplace/withdraw/<int:post_id>', methods=['POST'])
@client_bp.route('/marketplace/close/<int:post_id>', methods=['POST'])
@login_required
def close_marketplace_post(post_id):
    from app.models.features import ClientPost
    profile = current_user.client_profile
    if profile:
        post = ClientPost.query.filter_by(id=post_id, client_id=profile.id).first()
        if post:
            post.status = 'withdrawn'
            db.session.commit()
            flash('Your coaching request has been withdrawn from the marketplace.', 'info')
    return redirect(url_for('client.marketplace'))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SELECT PACKAGE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/select-package/<int:package_id>', methods=['GET', 'POST'])
@client_bp.route('/select-package', methods=['GET', 'POST'])
@login_required
def select_package(package_id=None):
    from app.models.coaching import CoachingPackage, ClientContract
    from app.services.paystack import get_paystack_public_key, _convert_to_ngn
    import datetime as dt
    import time

    if package_id is None:
        package_id = request.args.get('package_id', type=int)
    if not package_id:
        flash('Please select a coaching package.', 'warning')
        return redirect(url_for('client.marketplace'))

    package = CoachingPackage.query.get_or_404(package_id)
    profile = current_user.client_profile
    if not profile:
        profile = ClientProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()

    # Package-level payment link with fallback to coach-level payment link
    payment_link = getattr(package, 'payment_link', None) or (package.coach.payment_link if package.coach else None) or ''

    # Calculate pricing & Paystack parameters
    paystack_public_key = get_paystack_public_key()
    payment_reference = f"pstk_pkg_{package.id}_{current_user.id}_{int(time.time())}"
    original_currency = (package.currency or (package.coach.currency if package.coach else 'USD') or 'USD').upper()
    original_amount = float(package.price or 0.0)
    ngn_amount, _, rate_used = _convert_to_ngn(original_amount, original_currency)
    amount_in_kobo = int(round(ngn_amount * 100))

    if request.method == 'POST':
        # Payment must be made and verified before enrollment
        reference = request.form.get('reference') or request.args.get('reference')
        if not reference:
            if payment_link:
                return redirect(payment_link)
            flash('Payment is required to enroll in this package. Please complete payment first.', 'danger')
            return redirect(url_for('client.select_package', package_id=package.id))

        return redirect(url_for('client.verify_package_payment', package_id=package.id, reference=reference))

    return render_template(
        'client/select_package.html',
        profile=profile,
        package=package,
        coach=package.coach,
        payment_link=payment_link,
        paystack_public_key=paystack_public_key,
        payment_reference=payment_reference,
        amount_in_kobo=amount_in_kobo,
        currency='NGN',
        original_currency=original_currency,
        ngn_amount=ngn_amount,
        rate_used=rate_used
    )


@client_bp.route('/verify-package-payment/<int:package_id>', methods=['GET', 'POST'])
@login_required
def verify_package_payment(package_id):
    """Server-side verified payment callback when client enrolls from a coach package."""
    from app.models.coaching import CoachingPackage, ClientContract
    from app.models.features import ClientPost
    from app.services.paystack import verify_paystack_payment
    from app.services.messaging import send_system_notification
    from app import socketio
    import datetime as dt

    profile = current_user.client_profile
    if not profile:
        profile = ClientProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()

    package = CoachingPackage.query.get_or_404(package_id)

    reference = request.args.get('reference') or request.form.get('reference')
    if not reference:
        flash('Payment reference missing. Please complete payment before confirming.', 'danger')
        return redirect(url_for('client.select_package', package_id=package.id))

    # Verify transaction with Paystack (supports live and sandbox mock modes)
    verification = verify_paystack_payment(reference)
    if not verification.get('status'):
        flash(f"Payment verification failed: {verification.get('message', 'Please check your transaction reference')}", 'danger')
        return redirect(url_for('client.select_package', package_id=package.id))

    now = dt.datetime.utcnow()
    duration_weeks = package.duration_weeks or 4
    end_date = now + dt.timedelta(weeks=duration_weeks)

    # Supersede existing active contracts
    old_contracts = ClientContract.query.filter_by(client_id=profile.id, status='active').all()
    for oc in old_contracts:
        oc.status = 'superseded'

    # Create new active contract
    contract = ClientContract(
        client_id=profile.id,
        coach_id=package.coach_id,
        package_id=package.id,
        status='active',
        start_date=now,
        end_date=end_date,
        monthly_renewal_price=package.price,
        months_subscribed=max(1, duration_weeks // 4)
    )
    db.session.add(contract)

    # Update profile coach and active package
    profile.coach_id = package.coach_id
    profile.active_package_id = package.id

    # If the client had an active marketplace post, mark it fulfilled
    active_post = ClientPost.query.filter_by(client_id=profile.id, status='active').first()
    if active_post:
        active_post.status = 'fulfilled'
        active_post.fulfilled_at = now
        active_post.fulfilled_coach_id = package.coach_id

    db.session.commit()

    # Real-time notifications to coach
    if package.coach and package.coach.user_id:
        socketio.emit('notification', {
            'msg': f'{profile.full_name} enrolled in {package.name} (Ref: {reference})!'
        }, room=f'user_{package.coach.user_id}')

        send_system_notification(
            recipient_id=package.coach.user_id,
            notif_type='contract_enrolled',
            title="New Athlete Enrolled!",
            text=f"{profile.full_name} paid and enrolled in your '{package.name}' package.",
            link=f"/coach/client/{profile.id}",
            target_type='client',
            target_id=profile.id,
            emit_socket=True
        )

    flash(f'Payment verified! You are now successfully enrolled in {package.name} with Coach {package.coach.first_name}.', 'success')
    return redirect(url_for('client.dashboard'))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PAYMENT SUCCESS / DUMMY PAYMENT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@client_bp.route('/payment-success')
@login_required
def payment_success():
    import datetime as dt
    from app.models.coaching import ClientContract

    profile = current_user.client_profile
    package_id = request.args.get('package_id', type=int)
    package = CoachingPackage.query.get(package_id) if package_id else None

    if package and profile:
        now = dt.datetime.utcnow()
        end_date = now + dt.timedelta(weeks=package.duration_weeks or 4)
        old = ClientContract.query.filter_by(client_id=profile.id, status='active').first()
        if old:
            old.status = 'superseded'
        contract = ClientContract(
            client_id=profile.id,
            coach_id=package.coach_id,
            package_id=package.id,
            status='active',
            start_date=now,
            end_date=end_date,
        )
        db.session.add(contract)
        profile.coach_id = package.coach_id
        profile.active_package_id = package.id
        db.session.commit()

        if package.coach and package.coach.user_id:
            socketio.emit('notification', {
                'msg': f'{profile.full_name} enrolled in {package.name}!'
            }, room=f'user_{package.coach.user_id}')

        flash(f'Payment successful! You are now enrolled in {package.name}.', 'success')

    return redirect(url_for('client.dashboard'))


@client_bp.route('/dummy-payment/<int:package_id>')
@login_required
def dummy_payment(package_id):
    package = CoachingPackage.query.get_or_404(package_id)
    profile = current_user.client_profile
    return render_template('client/dummy_payment.html', profile=profile, package=package)


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

    from app.services.paystack import _convert_to_ngn
    paystack_public_key = get_paystack_public_key()
    payment_reference = f"pstk_offer_{offer.id}_{current_user.id}_{int(time.time())}"
    # Convert to NGN for Nigerian Paystack merchant accounts
    original_currency = (offer.currency or 'USD').upper()
    original_amount = float(offer.amount)
    ngn_amount, _, rate_used = _convert_to_ngn(original_amount, original_currency)
    amount_in_kobo = int(round(ngn_amount * 100))
    currency = 'NGN'  # Always charge in NGN for Nigerian Paystack accounts
    display_currency = original_currency  # Keep original for display only

    return render_template(
        'client/checkout_program_offer.html',
        offer=offer,
        coach=offer.coach,
        paystack_public_key=paystack_public_key,
        payment_reference=payment_reference,
        amount_in_kobo=amount_in_kobo,
        currency=currency,
        original_currency=original_currency,
        ngn_amount=ngn_amount,
        rate_used=rate_used
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

    now = dt.datetime.utcnow()
    # Mark offer as Paid
    offer.status = 'paid'
    offer.payment_reference = reference
    offer.paid_at = now

    from app.models.coaching import ClientContract
    # Superseed any previous active contract
    old_contracts = ClientContract.query.filter_by(client_id=profile.id, status='active').all()
    for oc in old_contracts:
        oc.status = 'superseded'

    # Create new active client contract
    duration_weeks = offer.duration_weeks or 12
    end_date = now + dt.timedelta(weeks=duration_weeks)
    new_contract = ClientContract(
        client_id=profile.id,
        coach_id=offer.coach_id,
        offer_id=offer.id,
        status='active',
        start_date=now,
        end_date=end_date,
        monthly_renewal_price=offer.amount,
        months_subscribed=max(1, duration_weeks // 4)
    )
    db.session.add(new_contract)

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

    # Link coach to client profile
    profile.coach_id = offer.coach_id

    # Mark client marketplace post as fulfilled
    if offer.post_id:
        post = ClientPost.query.get(offer.post_id)
        if post and post.client_id == profile.id:
            post.status = 'fulfilled'
            post.fulfilled_at = now
            post.fulfilled_coach_id = offer.coach_id
    else:
        active_post = ClientPost.query.filter_by(client_id=profile.id, status='active').first()
        if active_post:
            active_post.status = 'fulfilled'
            active_post.fulfilled_at = now
            active_post.fulfilled_coach_id = offer.coach_id

    # Reclassify chat messages between this coach & client from 'marketplace' to 'coaching'
    coach_user_id = offer.coach.user_id
    from app.models.user import ChatMessage
    ChatMessage.query.filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id == coach_user_id)) |
        ((ChatMessage.sender_id == coach_user_id) & (ChatMessage.receiver_id == current_user.id)),
        ChatMessage.context == 'marketplace'
    ).update({'context': 'coaching'}, synchronize_session=False)

    # Archive competing marketplace conversations with other coaches
    ChatMessage.query.filter(
        ((ChatMessage.sender_id == current_user.id) | (ChatMessage.receiver_id == current_user.id)),
        ChatMessage.context == 'marketplace'
    ).update({'context': 'archived'}, synchronize_session=False)

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


# ============================================================
# CHAT MESSAGE ACTIONS: Edit, Delete (client-side)
# ============================================================

@client_bp.route('/chat/message/<int:msg_id>/delete', methods=['POST'])
@login_required
def delete_chat_message(msg_id):
    """Soft-delete a chat message (own messages only)."""
    from app.models.user import ChatMessage
    from app import socketio
    msg = ChatMessage.query.get_or_404(msg_id)
    if msg.sender_id != current_user.id:
        return {'success': False, 'error': 'Unauthorized'}, 403
    msg.is_deleted = True
    msg.message = '[Message deleted]'
    db.session.commit()
    socketio.emit('message_deleted', {'message_id': msg_id}, room=f'user_{msg.sender_id}')
    socketio.emit('message_deleted', {'message_id': msg_id}, room=f'user_{msg.receiver_id}')
    return {'success': True}


@client_bp.route('/chat/message/<int:msg_id>/edit', methods=['POST'])
@login_required
def edit_chat_message(msg_id):
    """Edit the text of a sent chat message (own messages only)."""
    from app.models.user import ChatMessage
    from app import socketio
    msg = ChatMessage.query.get_or_404(msg_id)
    if msg.sender_id != current_user.id:
        return {'success': False, 'error': 'Unauthorized'}, 403
    if msg.is_deleted:
        return {'success': False, 'error': 'Cannot edit deleted message'}, 400
    new_text = (request.json or {}).get('message', '').strip()
    if not new_text:
        return {'success': False, 'error': 'Message cannot be empty'}, 400
    msg.message = new_text
    msg.is_edited = True
    db.session.commit()
    socketio.emit('message_edited', {
        'message_id': msg_id,
        'new_text': new_text,
        'is_edited': True
    }, room=f'user_{msg.sender_id}')
    socketio.emit('message_edited', {
        'message_id': msg_id,
        'new_text': new_text,
        'is_edited': True
    }, room=f'user_{msg.receiver_id}')
    return {'success': True, 'new_text': new_text}
