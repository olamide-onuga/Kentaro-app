from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.user import CoachProfile, ClientProfile
from app.models.coaching import CoachingPackage
from app.models.workout import Program
from app import socketio
from app.models.progress import ClientProgram, WorkoutCompletion
from app.models.features import ClientPost

coach_bp = Blueprint('coach', __name__, url_prefix='/coach')

@coach_bp.before_request
@login_required
def require_coach():
    if not current_user.is_coach:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))

@coach_bp.route('/dashboard')
@login_required
def dashboard():
    from app.models.calendar import Appointment
    from datetime import date as date_cls
    import datetime as dt_mod
    coach = current_user.coach_profile
    upcoming_appointments = []
    revenue_this_month = 0.0
    revenue_last_month = 0.0
    total_revenue = 0.0
    active_client_count = 0
    if coach:
        upcoming_appointments = Appointment.query.filter(
            Appointment.coach_id == coach.id,
            Appointment.date >= date_cls.today(),
            Appointment.status == 'scheduled'
        ).order_by(Appointment.date.asc(), Appointment.start_time.asc()).all()
        from app.models.coaching import ClientContract
        now = dt_mod.datetime.utcnow()
        all_contracts = ClientContract.query.filter_by(coach_id=coach.id).all()
        active_client_count = ClientContract.query.filter_by(coach_id=coach.id, status='active').count()
        total_revenue = sum(float(c.monthly_renewal_price or 0) for c in all_contracts if c.status != 'terminated')
        revenue_this_month = sum(
            float(c.monthly_renewal_price or 0) for c in all_contracts
            if c.created_at and c.created_at.month == now.month and c.created_at.year == now.year
        )
        last_month_dt = (now.replace(day=1) - dt_mod.timedelta(days=1))
        revenue_last_month = sum(
            float(c.monthly_renewal_price or 0) for c in all_contracts
            if c.created_at and c.created_at.month == last_month_dt.month and c.created_at.year == last_month_dt.year
        )
    return render_template('coach/dashboard.html',
                           upcoming_appointments=upcoming_appointments,
                           revenue_this_month=round(revenue_this_month, 2),
                           revenue_last_month=round(revenue_last_month, 2),
                           total_revenue=round(total_revenue, 2),
                           active_client_count=active_client_count)

@coach_bp.route('/scout')
@login_required
def scout():
    from app.models.coaching import ClientContract
    query = request.args.get('q', '').strip()
    specialization = request.args.get('specialization', '').strip()
    skill_level = request.args.get('skill_level', '').strip()
    duration = request.args.get('duration', '').strip()
    min_b = request.args.get('min_budget', type=float)
    max_b = request.args.get('max_budget', type=float)

    posts_query = ClientPost.query.filter_by(status='active')
    if query:
        posts_query = posts_query.filter(
            (ClientPost.title.ilike(f'%{query}%')) |
            (ClientPost.problem.ilike(f'%{query}%')) |
            (ClientPost.goal.ilike(f'%{query}%')) |
            (ClientPost.expectations.ilike(f'%{query}%'))
        )
    if specialization:
        posts_query = posts_query.filter(ClientPost.specialization.ilike(f'%{specialization}%'))
    if skill_level:
        posts_query = posts_query.filter(ClientPost.skill_level == skill_level)
    if duration:
        posts_query = posts_query.filter(ClientPost.preferred_duration == duration)
    if min_b is not None:
        posts_query = posts_query.filter((ClientPost.max_budget >= min_b) | (ClientPost.is_flexible_budget == True))
    if max_b is not None:
        posts_query = posts_query.filter((ClientPost.min_budget <= max_b) | (ClientPost.is_flexible_budget == True))

    all_posts = posts_query.order_by(ClientPost.created_at.desc()).all()

    # Filter out clients who currently have an active contract
    active_client_ids = set(c.client_id for c in ClientContract.query.filter_by(status='active').all())
    filtered_posts = [p for p in all_posts if p.client_id not in active_client_ids]

    coach = current_user.coach_profile
    packages = coach.packages.filter_by(is_active=True).all() if coach else []

    specializations = [
        'Calisthenics & Strength', 'Handstands & Balancing', 'Planche & Lever',
        'Muscle Building & Hypertrophy', 'Weight Loss & Conditioning', 'Mobility & Flexibility'
    ]
    skill_levels = ['Beginner', 'Intermediate', 'Advanced', 'Elite']
    durations = ['4 Weeks', '8 Weeks', '12 Weeks', '6 Months', 'Ongoing']

    return render_template(
        'coach/scout.html',
        posts=filtered_posts,
        query=query,
        selected_specialization=specialization,
        selected_skill=skill_level,
        selected_duration=duration,
        min_budget=min_b,
        max_budget=max_b,
        specializations=specializations,
        skill_levels=skill_levels,
        durations=durations,
        packages=packages
    )

@coach_bp.route('/scout/chat/<int:post_id>', methods=['GET', 'POST'])
@login_required
def scout_chat(post_id):
    """Pre-enrollment chat: coach contacts a client before they enroll.
    Redirects to the unified chat system with the scout client.
    """
    from app.models.features import ClientPost
    post = ClientPost.query.get_or_404(post_id)
    coach = current_user.coach_profile
    if not coach:
        flash('Coach profile required.', 'danger')
        return redirect(url_for('coach.dashboard'))

    client_profile = post.client
    if not client_profile or not client_profile.user_id:
        flash('Athlete profile not found.', 'danger')
        return redirect(url_for('coach.scout'))

    # Redirect directly into the unified chat with this athlete as partner_id
    return redirect(url_for('coach.coach_chat', partner_id=client_profile.user_id, post_id=post.id))


@coach_bp.route('/onboarding', methods=['GET', 'POST'])
def onboarding():
    # If coach already has a profile, maybe skip?
    # For now, allow editing or creating
    profile = current_user.coach_profile
    if not profile:
        profile = CoachProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()
        
    if request.method == 'POST':
        profile.first_name = request.form.get('first_name')
        profile.last_name = request.form.get('last_name')
        profile.bio = request.form.get('bio')
        profile.specialization = request.form.get('specialization')
        profile.experience_years = request.form.get('experience_years')
        profile.location = request.form.get('location')
        profile.timezone = request.form.get('timezone')
        profile.currency = request.form.get('currency', 'USD')
        profile.instagram_url = request.form.get('instagram_url')
        profile.youtube_url = request.form.get('youtube_url')
        payment_link = request.form.get('payment_link', '').strip()
        # Payment link is optional during onboarding, but required when creating packages
        if payment_link:
            profile.payment_link = payment_link
        
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename:
                from werkzeug.utils import secure_filename
                import uuid, os
                from flask import current_app
                filename = f"coach_{current_user.id}_{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
                photo_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'photos')
                os.makedirs(photo_dir, exist_ok=True)
                file.save(os.path.join(photo_dir, filename))
                profile.profile_photo = f"/static/uploads/photos/{filename}"
        
        db.session.commit()
        flash('Profile updated successfully! Now create your first package.', 'success')
        return redirect(url_for('coach.packages'))
        
    return render_template('coach/onboarding.html', profile=profile)

@coach_bp.route('/packages')
def packages():
    packages = CoachingPackage.query.filter_by(coach_id=current_user.coach_profile.id).all()
    return render_template('coach/packages.html', packages=packages)

@coach_bp.route('/packages/create', methods=['GET', 'POST'])
@login_required
def create_package():
    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price')
        renewal_monthly_price = request.form.get('renewal_monthly_price') or price
        duration = request.form.get('duration_weeks')
        features = request.form.get('features')
        payment_link = request.form.get('payment_link', '').strip() or getattr(current_user.coach_profile, 'payment_link', None) or None
        if not payment_link:
            flash('Payment link is compulsory. Please enter your Paystack payment link for this package.', 'danger')
            return render_template('coach/create_package.html')        
        package = CoachingPackage(
            coach_id=current_user.coach_profile.id,
            name=name,
            price=price,
            renewal_monthly_price=renewal_monthly_price,
            duration_weeks=duration,
            features=features,
            payment_link=payment_link
        )
        db.session.add(package)
        db.session.commit()
        flash('Package created successfully!', 'success')
        return redirect(url_for('coach.packages'))
        
    return render_template('coach/create_package.html')

@coach_bp.route('/packages/edit/<int:package_id>', methods=['GET', 'POST'])
@login_required
def edit_package(package_id):
    package = CoachingPackage.query.get_or_404(package_id)
    if package.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.packages'))
    if request.method == 'POST':
        package.name = request.form.get('name')
        package.price = request.form.get('price')
        package.renewal_monthly_price = request.form.get('renewal_monthly_price') or package.price
        package.duration_weeks = request.form.get('duration_weeks')
        package.features = request.form.get('features')
        package.payment_link = request.form.get('payment_link', '').strip() or getattr(current_user.coach_profile, 'payment_link', None) or None
        if not package.payment_link:
            flash('Payment link is compulsory. Please enter your Paystack payment link for this package.', 'danger')
            return render_template('coach/edit_package.html', package=package)
        db.session.commit()
        flash('Package updated!', 'success')
        return redirect(url_for('coach.packages'))
    return render_template('coach/edit_package.html', package=package)

@coach_bp.route('/discounts')
@login_required
def discounts():
    from app.models.coaching import CoachDiscount
    discounts = CoachDiscount.query.filter_by(coach_id=current_user.coach_profile.id).order_by(CoachDiscount.created_at.desc()).all()
    return render_template('coach/discounts.html', discounts=discounts)

@coach_bp.route('/discounts/create', methods=['POST'])
@login_required
def create_discount():
    from app.models.coaching import CoachDiscount
    code = request.form.get('code', '').strip().upper()
    discount_type = request.form.get('discount_type', 'percentage')
    discount_value = request.form.get('discount_value', 0)
    max_uses = request.form.get('max_uses') or None
    if max_uses:
        try: max_uses = int(max_uses)
        except ValueError: max_uses = None
    if not code:
        flash('Discount code is required.', 'danger')
        return redirect(url_for('coach.discounts'))

    discount = CoachDiscount(
        coach_id=current_user.coach_profile.id,
        code=code,
        discount_type=discount_type,
        discount_value=discount_value,
        max_uses=max_uses
    )
    db.session.add(discount)
    db.session.commit()
    flash(f'Discount code "{code}" created successfully!', 'success')
    return redirect(url_for('coach.discounts'))

@coach_bp.route('/discounts/<int:discount_id>/toggle', methods=['POST'])
@login_required
def toggle_discount(discount_id):
    from app.models.coaching import CoachDiscount
    discount = CoachDiscount.query.get_or_404(discount_id)
    if discount.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.discounts'))
    discount.is_active = not discount.is_active
    db.session.commit()
    flash(f'Discount code "{discount.code}" updated.', 'info')
    return redirect(url_for('coach.discounts'))

@coach_bp.route('/clients/<int:client_id>/terminate-contract', methods=['POST'])
@login_required
def terminate_client_contract(client_id):
    client = ClientProfile.query.get_or_404(client_id)
    if client.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.clients'))
    
    reason = request.form.get('reason', 'Coach requested contract termination.').strip()
    
    from app.models.coaching import ClientContract
    from datetime import datetime
    
    contract = ClientContract.query.filter_by(client_id=client.id, coach_id=current_user.coach_profile.id, status='active').first()
    if not contract:
        contract = ClientContract(client_id=client.id, coach_id=current_user.coach_profile.id, package_id=client.active_package_id)
        db.session.add(contract)
        
    # Set pending athlete approval - contract remains active until approved
    contract.termination_requested_by = 'coach'
    contract.termination_status = 'pending_client_approval'
    contract.termination_reason = reason
    contract.termination_requested_at = datetime.utcnow()
    db.session.commit()
    
    if client.user_id:
        from app import socketio
        socketio.emit('notification', {
            'msg': f'Coach {current_user.coach_profile.first_name} has requested to end your coaching contract. Please review and approve on your dashboard.'
        }, room=f'user_{client.user_id}')
        
    flash(f'Termination request sent to {client.full_name}. The contract remains active until the athlete approves.', 'info')
    return redirect(url_for('coach.clients'))

@coach_bp.route('/packages/delete/<int:package_id>', methods=['POST'])
@login_required
def delete_package(package_id):
    package = CoachingPackage.query.get_or_404(package_id)
    if package.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.packages'))
    db.session.delete(package)
    db.session.commit()
    flash('Package deleted.', 'success')
    return redirect(url_for('coach.packages'))

@coach_bp.route('/clients')
@login_required
def clients():
    # Ensure the logged-in user has a coach profile before accessing relationship
    if not current_user.coach_profile:
        flash('Please complete your coach profile first.', 'warning')
        return redirect(url_for('coach.onboarding'))
    # Retrieve clients safely — if the relationship is missing, fall back to empty list
    try:
        clients = current_user.coach_profile.clients.all()
    except Exception:
        clients = []
    return render_template('coach/clients.html', clients=clients)

@coach_bp.route('/voice-call/<int:client_id>')
@login_required
def coach_voice_call(client_id):
    client = ClientProfile.query.get_or_404(client_id)
    if client.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.clients'))
    partner_id = client.user.id
    partner_name = f"{client.first_name} {client.last_name}".strip() or "Client"
    from app.models.progress import FormCheckSubmission
    form_checks = client.form_checks.order_by(FormCheckSubmission.created_at.desc()).all()
    return render_template('coach/voice_call.html', partner_id=partner_id, client=client, partner_name=partner_name, form_checks=form_checks)

@coach_bp.route('/clients/<int:client_id>')
@login_required
def client_detail(client_id):
    client = ClientProfile.query.get_or_404(client_id)
    # Ensure this client belongs to this coach
    if client.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.clients'))
        
    programs = Program.query.filter_by(coach_id=current_user.coach_profile.id).all()
    active_cp = client.client_programs.filter_by(is_active=True).first()
    completions = client.completions.order_by(WorkoutCompletion.completed_at.desc()).all()
    
    # Progress & metrics data
    from app.models.progress import BodyweightLog, ProgressPhoto, FormCheckSubmission
    weight_logs = client.bodyweight_logs.order_by(BodyweightLog.date.asc()).all()
    chart_labels = [w.date.strftime('%b %d') for w in weight_logs]
    chart_data = [w.weight for w in weight_logs]
    
    photos = client.progress_photos.order_by(ProgressPhoto.date.desc()).all()
    form_checks = client.form_checks.order_by(FormCheckSubmission.created_at.desc()).all()
    
    return render_template('coach/client_detail.html',
                           client=client,
                           programs=programs,
                           active_cp=active_cp,
                           completions=completions,
                           weight_logs=weight_logs,
                           chart_labels=chart_labels,
                           chart_data=chart_data,
                           photos=photos,
                           form_checks=form_checks)

@coach_bp.route('/workout-completion/<int:completion_id>/feedback', methods=['POST'])
@login_required
def submit_workout_feedback(completion_id):
    from datetime import datetime
    from app.models.progress import WorkoutCompletion
    
    completion = WorkoutCompletion.query.get_or_404(completion_id)
    if completion.client.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.clients'))
        
    feedback = request.form.get('feedback')
    completion.coach_feedback = feedback
    completion.reviewed_at = datetime.utcnow()
    db.session.commit()
    
    # Send notification to client
    if completion.client.user_id:
        socketio.emit('notification', {
            'msg': f'Coach {current_user.coach_profile.first_name} left feedback on your {completion.workout.name} workout!'
        }, room=f'user_{completion.client.user_id}')
        
    flash('Workout feedback submitted!', 'success')
    return redirect(url_for('coach.client_detail', client_id=completion.client_id))

@coach_bp.route('/form-check/<int:submission_id>/feedback', methods=['POST'])
@login_required
def submit_form_check_feedback(submission_id):
    from datetime import datetime
    from app.models.progress import FormCheckSubmission
    
    submission = FormCheckSubmission.query.get_or_404(submission_id)
    if submission.client.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.clients'))
        
    feedback = request.form.get('feedback')
    submission.coach_feedback = feedback
    submission.status = 'reviewed'
    submission.reviewed_at = datetime.utcnow()
    db.session.commit()
    
    # Send notification to client
    if submission.client.user_id:
        socketio.emit('notification', {
            'msg': f'Coach {current_user.coach_profile.first_name} reviewed your form check video!'
        }, room=f'user_{submission.client.user_id}')
        
    flash('Form check feedback submitted!', 'success')
    return redirect(url_for('coach.client_detail', client_id=submission.client_id))
@coach_bp.route('/messages')
@coach_bp.route('/messages/<int:client_id>')
@login_required
def messages(client_id=None):
    return coach_chat(client_id=client_id)

@coach_bp.route('/chat')
@coach_bp.route('/chat/<int:client_id>')
@login_required
def coach_chat(client_id=None):
    coach = current_user.coach_profile
    if not coach:
        flash('Please complete your coach profile first.', 'warning')
        return redirect(url_for('coach.onboarding'))

    import datetime as dt
    from app.models.user import ChatMessage, ClientProfile, User
    from app.models.features import CustomOffer, ClientPost, CustomProgramOffer
    from app.models.coaching import ClientContract
    from sqlalchemy import or_, and_

    target_partner_id = request.args.get('partner_id', type=int)
    active_client = None
    partner_id = None
    target_user = None

    if target_partner_id:
        partner_id = target_partner_id
        target_user = User.query.get(target_partner_id)
        if target_user:
            active_client = target_user.client_profile
    elif client_id:
        c = ClientProfile.query.get(client_id)
        if c:
            active_client = c
            partner_id = c.user_id
            target_user = c.user
        else:
            u = User.query.get(client_id)
            if u:
                target_user = u
                partner_id = u.id
                active_client = u.client_profile

    # Gather contacts:
    enrolled_clients = coach.clients.all()
    enrolled_user_ids = {c.user_id for c in enrolled_clients}

    msg_partners = db.session.query(ChatMessage.sender_id).filter(
        ChatMessage.receiver_id == current_user.id
    ).union(
        db.session.query(ChatMessage.receiver_id).filter(
            ChatMessage.sender_id == current_user.id
        )
    ).all()
    message_user_ids = [uid[0] for uid in msg_partners if uid[0] != current_user.id]

    active_marketplace_posts = ClientPost.query.filter_by(status='active').order_by(ClientPost.created_at.desc()).all()
    marketplace_client_map = {p.client_id: p for p in active_marketplace_posts if p.client_id}

    all_contact_uids = []
    seen = set()

    # Ensure targeted partner is always in contact list
    if partner_id and partner_id not in seen:
        seen.add(partner_id)
        all_contact_uids.append(partner_id)

    # All message partners (never hide conversations!)
    for uid in message_user_ids:
        if uid not in seen:
            seen.add(uid)
            all_contact_uids.append(uid)

    # All enrolled clients
    for c in enrolled_clients:
        if c.user_id not in seen:
            seen.add(c.user_id)
            all_contact_uids.append(c.user_id)

    # Active marketplace posters
    for p in active_marketplace_posts:
        if p.client and p.client.user_id not in seen:
            seen.add(p.client.user_id)
            all_contact_uids.append(p.client.user_id)

    contacts = []
    for uid in all_contact_uids:
        u = User.query.get(uid)
        if not u:
            continue
        c_prof = u.client_profile
        active_contract = ClientContract.query.filter_by(client_id=c_prof.id, status='active').first() if c_prof else None
        is_enrolled = bool(active_contract and active_contract.coach_id == coach.id)
        has_other_coach = bool(active_contract and active_contract.coach_id != coach.id)
        m_post = marketplace_client_map.get(c_prof.id) if c_prof else None

        last_msg = ChatMessage.query.filter(
            or_(
                and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == uid),
                and_(ChatMessage.sender_id == uid, ChatMessage.receiver_id == current_user.id)
            )
        ).order_by(ChatMessage.timestamp.desc()).first()

        # Check pending offers
        pending_offer = None
        if c_prof:
            # If client already has an active contract or accepted offer, suppress offer
            has_accepted = (CustomOffer.query.filter_by(client_id=c_prof.id, status='accepted').first() is not None)
            if not active_contract and not has_accepted:
                pending_offer = CustomOffer.query.filter_by(
                    coach_id=coach.id,
                    client_id=c_prof.id,
                    status='pending'
                ).order_by(CustomOffer.created_at.desc()).first()

        is_admin_user = bool(u.is_admin or (u.role and u.role.name == 'admin'))
        if is_admin_user:
            from app.models.features import ClosedSupportChat
            is_support_closed = bool(ClosedSupportChat.query.filter_by(user_id=current_user.id).first())
            if is_support_closed and target_partner_id != u.id:
                continue
            name = "Kentaro Support"
            role_label = "Admin"
            avatar = ""
            is_enrolled = False
            has_other_coach = False
        elif c_prof and c_prof.first_name:
            name = c_prof.full_name
            role_label = "Enrolled Athlete" if is_enrolled else "Athlete"
            avatar = name[0].upper()
        else:
            name = u.email.split('@')[0]
            role_label = "User"
            avatar = name[0].upper() if name else '?'

        unread_count = ChatMessage.query.filter_by(sender_id=uid, receiver_id=current_user.id, is_read=False).count()

        # Category classification
        if is_admin_user:
            cat = 'support'
        elif is_enrolled:
            cat = 'my_coach'
        elif m_post or (last_msg and last_msg.context == 'marketplace'):
            cat = 'marketplace'
        elif c_prof and not is_enrolled:
            cat = 'marketplace'
        else:
            cat = 'direct'

        contacts.append({
            'user': u,
            'client': c_prof,
            'name': name,
            'email': ('' if is_admin_user else u.email),
            'avatar': avatar,
            'is_enrolled': is_enrolled,
            'has_other_coach': has_other_coach,
            'is_marketplace': (False if is_admin_user else not is_enrolled),
            'marketplace_post': m_post,
            'last_msg': last_msg,
            'unread_count': unread_count,
            'category': cat,
            'role_label': role_label,
            'is_support': is_admin_user,
            'pending_offer': pending_offer
        })

    contacts.sort(key=lambda c: (
        c['last_msg'].timestamp if c['last_msg'] and c['last_msg'].timestamp else dt.datetime.min,
        1 if c['is_enrolled'] else 0
    ), reverse=True)

    view_mode = request.args.get('view')
    if view_mode == 'contacts':
        partner_id = None
        target_user = None
        active_client = None
    elif not partner_id and contacts:
        partner_id = contacts[0]['user'].id
        target_user = contacts[0]['user']
        active_client = contacts[0]['client']

    messages = []
    active_offer = None
    is_marketplace_contact = False
    can_send_offer = False

    if partner_id:
        # Mark unread messages as read in DB
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

        is_target_admin = bool(target_user and (target_user.is_admin or (target_user.role and target_user.role.name == 'admin')))
        if active_client:
            active_contract = ClientContract.query.filter_by(client_id=active_client.id, status='active').first()
            is_enrolled = bool(active_contract and active_contract.coach_id == coach.id)
            has_other_coach = bool(active_contract and active_contract.coach_id != coach.id)
            has_accepted = (CustomOffer.query.filter_by(client_id=active_client.id, status='accepted').first() is not None)

            # Custom budget offers are strictly for marketplace negotiation (client is not enrolled)
            if not has_other_coach and not is_enrolled:
                active_offer = CustomOffer.query.filter_by(
                    coach_id=coach.id,
                    client_id=active_client.id,
                    status='pending'
                ).order_by(CustomOffer.created_at.desc()).first()
                is_marketplace_contact = True
                can_send_offer = True
            else:
                active_offer = None
                can_send_offer = False
                is_marketplace_contact = False if is_enrolled else True
        elif is_target_admin:
            is_marketplace_contact = False
            can_send_offer = False
        else:
            is_marketplace_contact = True
            can_send_offer = False

    support_admin = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).order_by(User.id.asc()).first()
    support_admin_id = support_admin.id if support_admin else None
    is_partner_admin = bool(target_user and (target_user.is_admin or (target_user.role and target_user.role.name == 'admin') or (support_admin_id and target_user.id == support_admin_id)))

    coach_programs = Program.query.filter_by(coach_id=coach.id).order_by(Program.name.asc()).all()

    return render_template('coach/chat.html',
                           is_partner_admin=is_partner_admin,
                           partner_id=partner_id,
                           target_user=target_user,
                           client=active_client,
                           contacts=contacts,
                           all_clients=enrolled_clients,
                           messages=messages,
                           coach=coach,
                           coach_programs=coach_programs,
                           active_offer=active_offer,
                           is_marketplace_contact=is_marketplace_contact,
                           can_send_offer=can_send_offer,
                           is_enrolled=is_enrolled if active_client else False,
                           has_other_coach=has_other_coach if active_client else False,
                           support_admin_id=support_admin_id)


@coach_bp.route('/chat/search-users')
@login_required
def search_users():
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify([])
    coach = current_user.coach_profile
    from app.models.user import User, ClientProfile
    # Exclude current user and admins from general contact search
    query = User.query.filter(User.id != current_user.id, User.is_admin == False, ~User.role.has(name='admin'))
    query = query.filter(
        (User.email.ilike(f'%{q}%')) |
        (User.id.in_(
            ClientProfile.query.filter(
                (ClientProfile.first_name.ilike(f'%{q}%')) |
                (ClientProfile.last_name.ilike(f'%{q}%'))
            ).with_entities(ClientProfile.user_id)
        ))
    ).limit(10).all()

    results = []
    for u in query:
        cp = u.client_profile
        name = cp.full_name if cp and cp.first_name else u.email.split('@')[0]
        is_enrolled = bool(cp and coach and cp.coach_id == coach.id)
        has_other_coach = bool(cp and cp.coach_id and cp.coach_id != (coach.id if coach else None))
        results.append({
            'user_id': u.id,
            'client_id': cp.id if cp else None,
            'name': name,
            'email': u.email,
            'avatar': name[0].upper() if name else '?',
            'is_enrolled': is_enrolled,
            'has_other_coach': has_other_coach,
            'role': 'Enrolled Athlete' if is_enrolled else ('Athlete' if u.is_client else 'Coach'),
            'chat_url': url_for('coach.coach_chat', partner_id=u.id)
        })
    return jsonify(results)

@coach_bp.route('/upload-voice', methods=['POST'])
@login_required
def upload_voice():
    is_json = request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if 'voice' not in request.files or request.files['voice'].filename == '':
        if is_json:
            return jsonify({'success': False, 'error': 'No voice file selected'}), 400
        flash('No voice file selected.', 'warning')
        return redirect(url_for('coach.messages'))
    file = request.files['voice']
    from werkzeug.utils import secure_filename
    import uuid, os
    from flask import current_app
    filename = f"voice_coach_{current_user.id}_{uuid.uuid4().hex[:8]}_{secure_filename(file.filename or 'voice.webm')}"
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
    return redirect(url_for('coach.messages', partner_id=receiver_id))

@coach_bp.route('/clients/<int:client_id>/assign-program', methods=['POST'])
def assign_program(client_id):
    client = ClientProfile.query.get_or_404(client_id)
    if client.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.clients'))

    program_id = request.form.get('program_id')
    if not program_id:
        flash('Please select a program.', 'warning')
        return redirect(url_for('coach.client_detail', client_id=client_id))

    # Deactivate existing
    for cp in client.client_programs.all():
        cp.is_active = False

    new_cp = ClientProgram(client_id=client.id, program_id=int(program_id), is_active=True)
    db.session.add(new_cp)
    db.session.commit()
    socketio.emit('notification', {'msg': f'Program {new_cp.program.name} assigned to you.'}, room=f'user_{client.user.id}')
    return redirect(url_for('coach.client_detail', client_id=client_id))

@coach_bp.route('/schedule')
@login_required
def schedule():
    from app.services.entitlements import has_feature_access
    if not has_feature_access(current_user.coach_profile.id, 'scheduling'):
        flash('Scheduling & Calendar Management is not included in your current subscription plan. Please upgrade to access scheduling.', 'warning')
        return redirect(url_for('coach.subscription'))
    from app.models.calendar import CoachAvailability, CoachScheduleConfig, Appointment
    from datetime import date
    
    coach = current_user.coach_profile
    if not coach:
        flash('Please complete your coach profile first.', 'warning')
        return redirect(url_for('coach.onboarding'))
        
    config = CoachScheduleConfig.query.filter_by(coach_id=coach.id).first()
    availabilities_list = CoachAvailability.query.filter_by(coach_id=coach.id).all()
    availabilities = {av.day_of_week: av for av in availabilities_list}
    
    today = date.today()
    upcoming_appointments = Appointment.query.filter(
        Appointment.coach_id == coach.id,
        Appointment.date >= today,
        Appointment.status == 'scheduled'
    ).order_by(Appointment.date.asc(), Appointment.start_time.asc()).all()
    
    past_appointments = Appointment.query.filter(
        Appointment.coach_id == coach.id,
        (Appointment.date < today) | (Appointment.status != 'scheduled')
    ).order_by(Appointment.date.desc(), Appointment.start_time.desc()).all()
    
    return render_template('coach/schedule.html',
                           config=config,
                           availabilities=availabilities,
                           upcoming_appointments=upcoming_appointments,
                           past_appointments=past_appointments)

@coach_bp.route('/schedule/setup')
@login_required
def setup_schedule():
    from app.models.calendar import CoachAvailability, CoachScheduleConfig
    
    coach = current_user.coach_profile
    if not coach:
        flash('Please complete your coach profile first.', 'warning')
        return redirect(url_for('coach.onboarding'))
        
    config = CoachScheduleConfig.query.filter_by(coach_id=coach.id).first()
    availabilities_list = CoachAvailability.query.filter_by(coach_id=coach.id).all()
    availabilities = {av.day_of_week: av for av in availabilities_list}
    
    return render_template('coach/setup_schedule.html',
                           config=config,
                           availabilities=availabilities)

@coach_bp.route('/schedule/availability', methods=['POST'])
@login_required
def update_availability():
    from datetime import datetime, time
    from app.models.calendar import CoachAvailability
    
    coach = current_user.coach_profile
    if not coach:
        return redirect(url_for('coach.dashboard'))
        
    for day_idx in range(7):
        is_active = request.form.get(f'active_{day_idx}') == '1'
        start_str = request.form.get(f'start_{day_idx}', '09:00')
        end_str = request.form.get(f'end_{day_idx}', '17:00')
        
        try:
            st = datetime.strptime(start_str, '%H:%M').time()
            et = datetime.strptime(end_str, '%H:%M').time()
        except ValueError:
            st = time(9, 0)
            et = time(17, 0)
            
        av = CoachAvailability.query.filter_by(coach_id=coach.id, day_of_week=day_idx).first()
        if not av:
            av = CoachAvailability(
                coach_id=coach.id,
                day_of_week=day_idx,
                start_time=st,
                end_time=et,
                is_active=is_active
            )
            db.session.add(av)
        else:
            av.start_time = st
            av.end_time = et
            av.is_active = is_active
            
    db.session.commit()
    flash('Weekly availability hours updated successfully!', 'success')
    return redirect(url_for('coach.setup_schedule'))

@coach_bp.route('/schedule/config', methods=['POST'])
@login_required
def update_schedule_config():
    from app.models.calendar import CoachScheduleConfig
    
    coach = current_user.coach_profile
    if not coach:
        return redirect(url_for('coach.dashboard'))
        
    config = CoachScheduleConfig.query.filter_by(coach_id=coach.id).first()
    if not config:
        config = CoachScheduleConfig(coach_id=coach.id)
        db.session.add(config)
        
    config.slot_duration = request.form.get('slot_duration', type=int) or 30
    config.booking_window_days = request.form.get('booking_window_days', type=int) or 14
    config.meeting_platform = request.form.get('meeting_platform', 'in_app')
    config.google_meet_url = request.form.get('google_meet_url') if config.meeting_platform == 'google_meet' else None
    
    db.session.commit()
    flash('Meeting preferences updated successfully!', 'success')
    return redirect(url_for('coach.setup_schedule'))

@coach_bp.route('/appointment/<int:appointment_id>/status', methods=['POST'])
@login_required
def update_appointment_status(appointment_id):
    from app.models.calendar import Appointment
    
    appt = Appointment.query.get_or_404(appointment_id)
    if appt.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.schedule'))
        
    new_status = request.form.get('status', 'completed')
    if new_status in ['completed', 'cancelled', 'scheduled']:
        appt.status = new_status
        db.session.commit()
        
        # Notify client
        if appt.client and appt.client.user_id:
            socketio.emit('notification', {
                'msg': f'Your appointment on {appt.date.strftime("%b %d")} was marked as {new_status}.'
            }, room=f'user_{appt.client.user_id}')
            
        flash(f'Appointment marked as {new_status}.', 'success')
        
    return redirect(url_for('coach.schedule'))

@coach_bp.route('/profile')
def public_profile():
    # If the coach profile is not complete, send them to the onboarding wizard
    if not current_user.coach_profile or not current_user.coach_profile.is_complete:
        flash('Complete your profile before it becomes public.', 'warning')
        return redirect(url_for('coach.onboarding'))
    # Support dashboard redirect after a successful update
    next_page = request.args.get('next')
    if next_page == 'dashboard':
        return redirect(url_for('coach.dashboard'))
    return redirect(url_for('main.public_coach_profile', coach_id=current_user.coach_profile.id))

@coach_bp.route('/delete_profile', methods=['POST'])
@login_required
def delete_profile():
    from flask_login import logout_user
    from app.models.calendar import CoachAvailability, CoachScheduleConfig, Appointment
    from app.models.workout import Exercise
    from app.models.user import ChatMessage

    coach = current_user.coach_profile
    user = current_user

    if coach:
        # 1. Unassign clients linked to this coach
        for client in ClientProfile.query.filter_by(coach_id=coach.id).all():
            client.coach_id = None
            client.active_package_id = None

        # 2. Delete coach appointments
        Appointment.query.filter_by(coach_id=coach.id).delete()

        # 3. Delete coach schedule configuration and availability
        CoachScheduleConfig.query.filter_by(coach_id=coach.id).delete()
        CoachAvailability.query.filter_by(coach_id=coach.id).delete()

        # 4. Delete coaching packages
        CoachingPackage.query.filter_by(coach_id=coach.id).delete()

        # 5. Delete programs and exercises created by coach
        for prog in Program.query.filter_by(coach_id=coach.id).all():
            db.session.delete(prog)
        Exercise.query.filter_by(coach_id=coach.id).delete()

        # 6. Delete chat messages involving this user
        ChatMessage.query.filter(
            (ChatMessage.sender_id == user.id) | (ChatMessage.receiver_id == user.id)
        ).delete()

        # 7. Delete CoachProfile
        db.session.delete(coach)

    # 8. Delete user account
    db.session.delete(user)
    db.session.commit()

    logout_user()
    flash('Your coach profile and account have been permanently deleted.', 'info')
    return redirect(url_for('main.index'))

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
            icon = request.form.get('icon', 'check').strip()
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
    from app.services.entitlements import has_feature_access
    if not has_feature_access(profile.id, 'analytics'):
        flash('Advanced Analytics & Earnings Reports are not included in your current subscription plan. Please upgrade to unlock detailed analytics.', 'warning')
        return redirect(url_for('coach.subscription'))
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
    for i in range(11, -1, -1):
        m_date = now.replace(day=1) - dt.timedelta(days=i*30)
        m_contracts = [c for c in all_contracts if c.created_at and c.created_at.month == m_date.month and c.created_at.year == m_date.year]
        m_total = sum(float(c.monthly_renewal_price or 0) * int(c.months_subscribed or 1) for c in m_contracts)
        monthly.append({'month': m_date.strftime('%b'), 'amount': round(m_total, 2)})
    
    currency = profile.currency or 'NGN'
    return render_template('coach/earnings.html', profile=profile, all_contracts=all_contracts,
                           total_earned=round(total_earned, 2), this_month_earned=round(this_month_earned, 2),
                           active_clients=active_clients, monthly=monthly, currency=currency, now=now)

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



@coach_bp.route('/create-offer', methods=['POST'])
@coach_bp.route('/scout-chat/<int:client_profile_id>', methods=['GET', 'POST'])
@login_required
def create_offer(client_profile_id=None):
    from app.models.features import CustomOffer
    from app.models.user import ClientProfile, ChatMessage
    from app import socketio

    coach = current_user.coach_profile
    if not coach:
        flash('Coach profile not found.', 'danger')
        return redirect(url_for('coach.dashboard'))

    if client_profile_id is None:
        client_profile_id = request.form.get('client_id', type=int)

    if not client_profile_id:
        flash('Client profile required.', 'danger')
        return redirect(url_for('coach.clients'))

    client_profile = ClientProfile.query.get_or_404(client_profile_id)

    if request.method == 'POST':
        action = request.form.get('action', 'create_offer')

        # Pre-enrollment message — coach sends chat without needing a contract
        if action == 'pre_message':
            msg_text = request.form.get('msg', '').strip()
            if msg_text:
                new_msg = ChatMessage(
                    sender_id=current_user.id,
                    receiver_id=client_profile.user_id,
                    message=msg_text
                )
                db.session.add(new_msg)
                db.session.commit()
                ts = new_msg.timestamp.strftime('%H:%M') if new_msg.timestamp else ''
                socketio.emit('chat_message', {
                    'msg': msg_text, 'from': current_user.id, 'timestamp': ts
                }, room=f'user_{client_profile.user_id}')
                socketio.emit('chat_message', {
                    'msg': msg_text, 'from': current_user.id, 'timestamp': ts
                }, room=f'user_{current_user.id}')
                return jsonify({'ok': True})
            return jsonify({'ok': False, 'error': 'Empty message'}), 400

        # Create custom offer - only lock if athlete has an active contract with another coach
        other_active_contract = ClientContract.query.filter_by(client_id=client_profile.id, status='active').filter(ClientContract.coach_id != coach.id).first()
        if other_active_contract:
            flash('This athlete already has an active contract with another coach and cannot receive new budget offers.', 'warning')
            if request.referrer and '/coach/chat/' in request.referrer:
                return redirect(url_for('coach.coach_chat', client_id=client_profile.id))
            return redirect(url_for('coach.scout'))

        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        amount = request.form.get('amount', type=float)
        duration_weeks = request.form.get('duration_weeks', 4, type=int)
        payment_link = request.form.get('payment_link', '').strip() or getattr(current_user.coach_profile, 'payment_link', None) or None
        if not payment_link:
            flash('Payment link is compulsory. Please enter your Paystack payment link for this package.', 'danger')
            return render_template('coach/create_package.html')
        if not title or not amount:
            flash('Title and amount are required.', 'danger')
            return redirect(url_for('coach.create_offer', client_profile_id=client_profile_id))

        offer = CustomOffer(
            coach_id=coach.id,
            client_id=client_profile.id,
            title=title,
            description=description,
            amount=amount,
            currency=getattr(coach, 'currency', None) or 'USD',
            duration_weeks=duration_weeks,
            payment_link=payment_link,
            status='pending'
        )
        db.session.add(offer)
        db.session.commit()

        socketio.emit('notification', {
            'msg': f'Coach {coach.first_name} sent you a custom offer: "{title}" for ${amount:.2f}!'
        }, room=f'user_{client_profile.user_id}')

        flash(f'Custom offer "{title}" sent to {client_profile.full_name}!', 'success')
        if request.referrer and '/coach/chat/' in request.referrer:
            return redirect(url_for('coach.coach_chat', client_id=client_profile.id))
        return redirect(url_for('coach.create_offer', client_profile_id=client_profile_id))

    # GET — redirect to scout_chat if client has a post, or coach_chat if enrolled
    if client_profile.coach_id == coach.id:
        return redirect(url_for('coach.coach_chat', client_id=client_profile.id))
    from app.models.features import ClientPost
    post = ClientPost.query.filter_by(client_id=client_profile.id).order_by(ClientPost.created_at.desc()).first()
    if post:
        return redirect(url_for('coach.scout_chat', post_id=post.id))
    return redirect(url_for('coach.scout'))



@coach_bp.route('/chat/send-offer-ajax', methods=['POST'])
@login_required
def send_offer_ajax():
    """Send a custom offer directly from the marketplace chat (AJAX)."""
    from app.models.features import CustomOffer
    from app.models.user import ClientProfile, ChatMessage
    from app.models.coaching import ClientContract
    from app import socketio

    coach = current_user.coach_profile
    if not coach:
        return jsonify({'ok': False, 'error': 'Coach profile not found'}), 403

    client_user_id = request.form.get('client_user_id', type=int)
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    amount = request.form.get('amount', type=float)
    duration_weeks = request.form.get('duration_weeks', 4, type=int)
    payment_link = request.form.get('payment_link', '').strip() or getattr(coach, 'payment_link', None) or ''

    if not client_user_id or not title or not amount:
        return jsonify({'ok': False, 'error': 'Missing required fields'}), 400
    if not payment_link:
        return jsonify({'ok': False, 'error': 'Payment link is required. Add it in your coach profile.'}), 400

    client_profile = ClientProfile.query.filter_by(user_id=client_user_id).first()
    if not client_profile:
        return jsonify({'ok': False, 'error': 'Client not found'}), 404

    other_active = ClientContract.query.filter_by(client_id=client_profile.id, status='active').filter(ClientContract.coach_id != coach.id).first()
    if other_active:
        return jsonify({'ok': False, 'error': 'This client already has an active contract with another coach.'}), 400

    offer = CustomOffer(
        coach_id=coach.id,
        client_id=client_profile.id,
        title=title,
        description=description,
        amount=amount,
        currency=getattr(coach, 'currency', None) or 'USD',
        duration_weeks=duration_weeks,
        payment_link=payment_link,
        status='pending'
    )
    db.session.add(offer)
    db.session.commit()

    offer_card_msg = f'[OFFER] {title} | {offer.currency} {amount:,.2f} | {duration_weeks} weeks'
    sys_msg = ChatMessage(
        sender_id=current_user.id,
        receiver_id=client_profile.user_id,
        message=offer_card_msg,
        context='marketplace'
    )
    db.session.add(sys_msg)
    db.session.commit()

    ts = sys_msg.timestamp.strftime('%H:%M') if sys_msg.timestamp else ''
    offer_data = {
        'offer_id': offer.id,
        'title': offer.title,
        'amount': offer.amount,
        'currency': offer.currency,
        'duration_weeks': offer.duration_weeks,
        'payment_link': offer.payment_link,
        'description': offer.description or ''
    }

    socketio.emit('chat_offer_card', {
        'msg': offer_card_msg,
        'from': current_user.id,
        'from_name': coach.first_name or current_user.email,
        'timestamp': ts,
        'id': sys_msg.id,
        'offer': offer_data,
        'chat_url': f'/client/chat?partner_id={current_user.id}'
    }, room=f'user_{client_profile.user_id}')

    socketio.emit('chat_offer_card', {
        'msg': offer_card_msg,
        'from': current_user.id,
        'from_name': coach.first_name or current_user.email,
        'timestamp': ts,
        'id': sys_msg.id,
        'offer': offer_data,
        'is_own': True
    }, room=f'user_{current_user.id}')

    socketio.emit('notification', {
        'msg': f'Coach {coach.first_name or "Coach"} sent you a custom offer: "{title}" for {offer.currency} {amount:,.2f}!',
        'chat_url': f'/client/chat?partner_id={current_user.id}'
    }, room=f'user_{client_profile.user_id}')

    return jsonify({'ok': True, 'offer_id': offer.id})


@coach_bp.route('/chat/create-custom-program-ajax', methods=['POST'])
@login_required
def create_custom_program_ajax():
    """Create or assign a program directly from the coach chat."""
    from app.models.workout import Program, ProgramPhase, Workout
    from app.models.progress import ClientProgram
    from app.models.user import ClientProfile, ChatMessage, User
    from app.models.coaching import ClientContract
    from app.services.messaging import send_system_notification, get_chat_url
    from app import socketio

    coach = current_user.coach_profile
    if not coach:
        return jsonify({'ok': False, 'error': 'Coach profile not found'}), 403

    client_id = request.form.get('client_id', type=int)
    program_mode = request.form.get('mode', 'assign')  # 'assign' or 'new'

    client = ClientProfile.query.get(client_id)
    if not client:
        target_u = User.query.get(client_id)
        if target_u and target_u.client_profile:
            client = target_u.client_profile
    if not client:
        return jsonify({'ok': False, 'error': 'Client profile not found'}), 404

    active_contract = ClientContract.query.filter_by(client_id=client.id, coach_id=coach.id, status='active').first()
    is_enrolled = bool(active_contract or (client.coach_id == coach.id))

    if program_mode == 'assign':
        program_id = request.form.get('program_id', type=int)
        program = Program.query.filter_by(id=program_id, coach_id=coach.id).first()
        if not program:
            return jsonify({'ok': False, 'error': 'Selected program not found'}), 404
    else:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        if not name:
            return jsonify({'ok': False, 'error': 'Program name is required'}), 400
        program = Program(coach_id=coach.id, name=name, description=description)
        db.session.add(program)
        db.session.flush()
        phase = ProgramPhase(program_id=program.id, name='Phase 1: Foundation', order=1)
        db.session.add(phase)
        db.session.flush()
        w1 = Workout(phase_id=phase.id, name='Full Body Routine', day_name='Day 1', day_number=1)
        db.session.add(w1)

    if is_enrolled:
        for cp in client.client_programs.all():
            cp.is_active = False
        new_cp = ClientProgram(client_id=client.id, program_id=program.id, is_active=True, status='active')
    else:
        new_cp = ClientProgram(client_id=client.id, program_id=program.id, is_active=False, status='sent')

    db.session.add(new_cp)

    context = 'coaching' if is_enrolled else 'marketplace'
    prog_msg = f'🎯 Coaching Program: "{program.name}"'
    sys_msg = ChatMessage(
        sender_id=current_user.id,
        receiver_id=client.user_id,
        message=prog_msg,
        message_type='program',
        program_id=program.id,
        context=context
    )
    db.session.add(sys_msg)
    db.session.commit()

    prog_data = {
        'id': program.id,
        'name': program.name,
        'description': program.description or '',
        'coach_name': f"Coach {coach.first_name}" if coach.first_name else 'Coach',
        'status': new_cp.status,
        'view_url': f'/client/programs/{program.id}'
    }

    send_system_notification(
        recipient_id=client.user_id,
        notif_type='custom_program',
        title=f"Program from Coach {coach.first_name}" if coach.first_name else 'Program from Coach',
        text=f'Coach {coach.first_name or ""} sent you a coaching program: "{program.name}"',
        link=f'/client/programs/{program.id}',
        target_type='program',
        target_id=program.id,
        emit_socket=True
    )

    client_chat_url = get_chat_url(client.user, current_user.id, context=context, program_id=program.id)

    payload = {
        'id': sys_msg.id,
        'from': current_user.id,
        'sender_id': current_user.id,
        'target_user_id': client.user_id,
        'receiver_id': client.user_id,
        'from_name': f"Coach {coach.first_name}" if coach.first_name else 'Coach',
        'msg': prog_msg,
        'message': prog_msg,
        'message_type': 'program',
        'program': prog_data,
        'context': context,
        'chat_url': client_chat_url,
        'timestamp': sys_msg.timestamp.strftime('%H:%M') if sys_msg.timestamp else ''
    }

    socketio.emit('chat_message', payload, room=f'user_{client.user_id}')
    socketio.emit('chat_message_sent', payload, room=f'user_{current_user.id}')

    return jsonify({'ok': True, 'program_name': program.name, 'program_id': program.id, 'status': new_cp.status})


@coach_bp.route('/community', methods=['GET', 'POST'])
@login_required
def community():
    import os
    from werkzeug.utils import secure_filename
    from flask import current_app
    from app.models.features import Community, CommunityMember, CommunityMessage as CM

    coach = current_user.coach_profile
    if not coach:
        flash('Coach profile not found.', 'danger')
        return redirect(url_for('coach.dashboard'))

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
            return redirect(url_for('coach.community'))

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
        return redirect(url_for('coach.community'))

    squad_clients = coach.clients.all() if hasattr(coach, 'clients') else []
    messages = CM.query.filter_by(community_id=comm.id).order_by(CM.created_at.asc()).all()
    return render_template('client/community.html', messages=messages, coach=coach, squad_clients=squad_clients, community=comm, profile=coach)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# COACH SUBSCRIPTION ROUTES
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@coach_bp.route('/subscription')
@login_required
def subscription():
    profile = current_user.coach_profile
    if not profile:
        flash('Please complete your coach profile first.', 'warning')
        return redirect(url_for('coach.onboarding'))

    from app.services.entitlements import get_coach_subscription, can_coach_add_client
    from app.models.subscription import SubscriptionPlan, FEATURE_LABELS

    sub = get_coach_subscription(profile.id)
    plan = sub.effective_plan
    client_info = can_coach_add_client(profile.id)
    available_plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.display_order).all()
    recent_payments = sub.recent_payments if sub else []

    return render_template('coach/subscription.html',
                           profile=profile,
                           subscription=sub,
                           plan=plan,
                           client_info=client_info,
                           available_plans=available_plans,
                           feature_labels=FEATURE_LABELS,
                           recent_payments=recent_payments)


@coach_bp.route('/subscription/checkout/<int:plan_id>', methods=['POST'])
@login_required
def subscription_checkout(plan_id):
    profile = current_user.coach_profile
    if not profile:
        flash('Coach profile required.', 'danger')
        return redirect(url_for('coach.onboarding'))

    from app.models.subscription import SubscriptionPlan, SubscriptionPayment
    from app.services.paystack import initialize_paystack_payment
    from app.services.entitlements import get_coach_subscription, log_subscription_change
    import uuid as _uuid

    target_plan = SubscriptionPlan.query.get_or_404(plan_id)
    if not target_plan.is_active:
        flash('This plan is no longer available.', 'warning')
        return redirect(url_for('coach.subscription'))

    if target_plan.price == 0:
        # Free plan — assign directly without payment
        sub = get_coach_subscription(profile.id)
        old_plan_id = sub.plan_id
        sub.plan_id = target_plan.id
        sub.status = 'active'
        sub.current_price = 0.0
        sub.current_period_end = None
        db.session.commit()
        log_subscription_change(
            profile.id, current_user.id, old_plan_id, target_plan.id,
            'coach_downgrade', 'Coach switched to Free plan'
        )
        flash(f'Switched to {target_plan.name} plan.', 'success')
        return redirect(url_for('coach.subscription'))

    # Generate unique reference for paid plans
    reference = f"SUB_{profile.id}_{target_plan.slug}_{_uuid.uuid4().hex[:12]}"

    # Check for existing pending payment to avoid duplicates
    existing = SubscriptionPayment.query.filter_by(
        coach_id=profile.id, plan_id=target_plan.id, status='pending'
    ).first()
    if existing:
        reference = existing.reference

    billing = request.form.get('billing_interval', target_plan.billing_interval) or 'monthly'
    amount = target_plan.price
    if billing == 'yearly':
        amount = round(target_plan.price * 10, 2)   # 2 months free on yearly

    callback_url = url_for('coach.subscription_callback', _external=True)

    result = initialize_paystack_payment(
        email=current_user.email,
        amount=amount,
        currency=target_plan.currency or 'USD',
        reference=reference,
        callback_url=callback_url,
        metadata={
            'plan_id': target_plan.id,
            'plan_name': target_plan.name,
            'coach_id': profile.id,
            'billing_interval': billing,
            'type': 'subscription_upgrade'
        }
    )

    if result.get('status'):
        if not existing:
            conv = result.get('converted_from') or {}
            payment = SubscriptionPayment(
                coach_id=profile.id,
                plan_id=target_plan.id,
                reference=reference,
                amount=amount,
                currency=target_plan.currency or 'USD',
                amount_paid_ngn=conv.get('ngn_amount'),
                status='pending',
                gateway='paystack'
            )
            db.session.add(payment)
            db.session.commit()

        auth_url = result.get('authorization_url')
        if auth_url:
            from flask import redirect as _redirect
            return _redirect(auth_url)
        flash('Payment initialized but no redirect URL received.', 'warning')
    else:
        flash(f'Payment failed: {result.get("message", "Unknown error")}', 'danger')

    return redirect(url_for('coach.subscription'))


@coach_bp.route('/subscription/callback')
@login_required
def subscription_callback():
    from flask import request as _req
    reference = _req.args.get('reference') or _req.args.get('trxref')
    if not reference:
        flash('No payment reference found.', 'danger')
        return redirect(url_for('coach.subscription'))

    from app.services.paystack import verify_paystack_payment
    from app.models.subscription import SubscriptionPayment, SubscriptionPlan
    from app.services.entitlements import get_coach_subscription, log_subscription_change
    from datetime import datetime, timedelta

    profile = current_user.coach_profile
    if not profile:
        flash('Coach profile required.', 'danger')
        return redirect(url_for('main.index'))

    # Idempotency: find existing payment record
    payment = SubscriptionPayment.query.filter_by(reference=reference).first()
    if not payment:
        flash('Payment record not found. Please contact support.', 'danger')
        return redirect(url_for('coach.subscription'))

    if payment.status == 'successful':
        flash('This payment was already processed. Your subscription is active.', 'info')
        return redirect(url_for('coach.subscription'))

    # Security: verify with Paystack server-side (never trust client-submitted status)
    verify = verify_paystack_payment(reference)
    if not verify.get('status'):
        payment.status = 'failed'
        payment.gateway_response = verify.get('message', 'Verification failed')
        db.session.commit()
        flash(f'Payment verification failed: {verify.get("message")}. Please try again.', 'danger')
        return redirect(url_for('coach.subscription'))

    # Payment verified — activate subscription
    from datetime import datetime as dt, timedelta as td
    payment.status = 'successful'
    payment.paid_at = dt.utcnow()
    if verify.get('data'):
        payment.channel = verify['data'].get('channel', '')
        payment.gateway_response = verify['data'].get('gateway_response', '')

    sub = get_coach_subscription(profile.id)
    old_plan_id = sub.plan_id

    target_plan = SubscriptionPlan.query.get(payment.plan_id)
    if not target_plan:
        flash('Subscription plan not found.', 'danger')
        return redirect(url_for('coach.subscription'))

    billing = target_plan.billing_interval or 'monthly'
    sub.plan_id = target_plan.id
    sub.status = 'active'
    sub.current_price = payment.amount
    sub.currency = payment.currency
    sub.billing_interval = billing
    sub.current_period_start = dt.utcnow()
    sub.current_period_end = dt.utcnow() + td(days=365 if billing == 'yearly' else 30)
    sub.last_payment_date = dt.utcnow()
    sub.last_payment_reference = reference
    payment.subscription_id = sub.id
    db.session.commit()

    action = 'coach_upgrade' if (target_plan.price > 0) else 'coach_downgrade'
    log_subscription_change(
        profile.id, current_user.id, old_plan_id, target_plan.id,
        action, f'Verified Paystack payment. Ref: {reference}'
    )

    flash(f'🎉 Successfully upgraded to the {target_plan.name} plan!', 'success')
    return redirect(url_for('coach.subscription'))


@coach_bp.route('/chat/start-support', methods=['POST'])
@login_required
def start_coach_support_chat():
    from app.services.messaging import get_or_create_support_ticket, get_chat_url
    from app.models.user import ChatMessage, User
    from app import socketio

    subject = request.form.get('subject', '').strip() or 'Coach Support Request'
    message_text = request.form.get('message', '').strip()

    if not message_text:
        flash('Please describe your support request.', 'warning')
        return redirect(url_for('coach.coach_chat', category='support'))

    support_admin = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).order_by(User.id.asc()).first()
    if not support_admin:
        flash('Support is currently unavailable.', 'error')
        return redirect(url_for('coach.coach_chat'))

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
    sender_name = f"Coach {current_user.coach_profile.first_name}" if current_user.coach_profile else current_user.email
    admin_url = get_chat_url(support_admin, current_user.id, context='support', ticket_id=ticket.id)

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

    flash(f'Support ticket {ticket.ticket_ref} created. Our support team has been notified.', 'success')
    return redirect(url_for('coach.coach_chat', partner_id=support_admin.id, category='support'))


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

    # Disallow custom budget offers if client is already enrolled
    from app.models.coaching import ClientContract
    active_contract = ClientContract.query.filter_by(client_id=client.id, status='active').first()
    if active_contract and active_contract.coach_id == coach.id:
        return jsonify({'ok': False, 'error': 'This client is already enrolled with you. Custom budget offers are for marketplace negotiation only.'}), 400
    if active_contract and active_contract.coach_id != coach.id:
        return jsonify({'ok': False, 'error': 'This client already has an active coach.'}), 400

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


# ============================================================
# CHAT MESSAGE ACTIONS: Edit, Delete (coach-side)
# ============================================================

@coach_bp.route('/chat/message/<int:msg_id>/delete', methods=['POST'])
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


@coach_bp.route('/chat/message/<int:msg_id>/edit', methods=['POST'])
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
