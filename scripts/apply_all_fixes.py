# scripts/apply_all_fixes.py
import re

# ==========================================
# 1. PATCH app/routes/coach.py
# ==========================================
with open('app/routes/coach.py', 'r', encoding='utf-8') as f:
    coach_code = f.read()

# Fix scout_chat redirect to coach.coach_chat with partner_id
old_scout_chat = """@coach_bp.route('/scout/chat/<int:post_id>', methods=['GET', 'POST'])
@login_required
def scout_chat(post_id):
    \"\"\"Pre-enrollment chat: coach contacts a client before they enroll.
    Redirects to the unified chat system with the scout client.
    \"\"\"
    from app.models.features import ClientPost
    post = ClientPost.query.get_or_404(post_id)
    coach = current_user.coach_profile
    if not coach:
        flash('Coach profile required.', 'danger')
        return redirect(url_for('coach.dashboard'))
    
    if post.status == 'closed':
        flash('This scout request is closed.', 'info')
        return redirect(url_for('coach.scout'))

    client_profile = post.client
    if not client_profile:
        flash('Client not found.', 'danger')
        return redirect(url_for('coach.scout'))

    # Redirect directly into the unified chat with this client as partner
    return redirect(url_for('coach.messages', client_id=client_profile.id, post_id=post.id))"""

new_scout_chat = """@coach_bp.route('/scout/chat/<int:post_id>', methods=['GET', 'POST'])
@login_required
def scout_chat(post_id):
    \"\"\"Pre-enrollment chat: coach contacts a client before they enroll.
    Redirects to the unified chat system with the scout client.
    \"\"\"
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
    return redirect(url_for('coach.coach_chat', partner_id=client_profile.user_id, post_id=post.id))"""

# Fix terminate_client_contract: Coach initiates request, athlete must approve, NO message deletion
old_terminate = """@coach_bp.route('/clients/<int:client_id>/terminate-contract', methods=['POST'])
@login_required
def terminate_client_contract(client_id):
    client = ClientProfile.query.get_or_404(client_id)
    if client.coach_id != current_user.coach_profile.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('coach.clients'))
    
    reason = request.form.get('reason', 'Contract terminated by coach.').strip()
    
    from app.models.coaching import ClientContract
    from datetime import datetime
    
    contract = ClientContract.query.filter_by(client_id=client.id, coach_id=current_user.coach_profile.id, status='active').first()
    if not contract:
        contract = ClientContract(client_id=client.id, coach_id=current_user.coach_profile.id, package_id=client.active_package_id)
        db.session.add(contract)
        
    contract.status = 'terminated'
    contract.terminated_by = 'coach'
    contract.termination_reason = reason
    contract.terminated_at = datetime.utcnow()
    
    client.coach_id = None
    client.active_package_id = None

    # Clear chat messages with client so fresh chat starts on future contracts/posts
    from app.models.user import ChatMessage
    if client.user_id:
        ChatMessage.query.filter(
            ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id == client.user_id)) |
            ((ChatMessage.sender_id == client.user_id) & (ChatMessage.receiver_id == current_user.id))
        ).delete()

    db.session.commit()
    
    if client.user_id:
        socketio.emit('notification', {
            'msg': f'Your coaching contract with Coach {current_user.coach_profile.first_name} was terminated.'
        }, room=f'user_{client.user_id}')
        
    flash(f'Contract with {client.full_name} has been terminated.', 'info')
    return redirect(url_for('coach.clients'))"""

new_terminate = """@coach_bp.route('/clients/<int:client_id>/terminate-contract', methods=['POST'])
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
    return redirect(url_for('coach.clients'))"""

# Normalize and replace in coach.py
coach_code_norm = coach_code.replace('\r\n', '\n')
if old_scout_chat.replace('\r\n', '\n') in coach_code_norm:
    coach_code_norm = coach_code_norm.replace(old_scout_chat.replace('\r\n', '\n'), new_scout_chat)
    print("Replaced scout_chat in coach.py")
else:
    print("WARNING: old_scout_chat not found in coach.py")

if old_terminate.replace('\r\n', '\n') in coach_code_norm:
    coach_code_norm = coach_code_norm.replace(old_terminate.replace('\r\n', '\n'), new_terminate)
    print("Replaced terminate_client_contract in coach.py")
else:
    print("WARNING: old_terminate not found in coach.py")

# Replace coach_chat implementation
old_coach_chat_pattern = re.compile(
    r'@coach_bp\.route\(\'/messages\'\)\n@coach_bp\.route\(\'/messages/<int:client_id>\'\)\n@login_required\ndef messages\(client_id=None\):.*?def search_users\(\):',
    re.DOTALL
)

new_coach_chat_block = """@coach_bp.route('/messages')
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
    from app.models.features import CustomOffer, ClientPost
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
        is_enrolled = bool(c_prof and c_prof.coach_id == coach.id)
        has_other_coach = bool(c_prof and c_prof.coach_id and c_prof.coach_id != coach.id)
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
            # If client already has a coach or accepted offer, suppress offer
            has_contract = bool(c_prof.coach_id) or (ClientContract.query.filter_by(client_id=c_prof.id, status='active').first() is not None)
            has_accepted = (CustomOffer.query.filter_by(client_id=c_prof.id, status='accepted').first() is not None)
            if not has_contract and not has_accepted:
                pending_offer = CustomOffer.query.filter_by(
                    coach_id=coach.id,
                    client_id=c_prof.id,
                    status='pending'
                ).order_by(CustomOffer.created_at.desc()).first()

        is_admin_user = bool(u.is_admin or (u.role and u.role.name == 'admin'))
        if is_admin_user:
            name = "Kentaro Support"
            role_label = "Platform Admin"
            avatar = ""
        elif c_prof and c_prof.first_name:
            name = c_prof.full_name
            role_label = "Enrolled Athlete" if is_enrolled else "Athlete"
            avatar = name[0].upper()
        else:
            name = u.email.split('@')[0]
            role_label = "User"
            avatar = name[0].upper() if name else '?'

        unread_count = ChatMessage.query.filter_by(sender_id=uid, receiver_id=current_user.id, is_read=False).count()

        contacts.append({
            'user': u,
            'client': c_prof,
            'name': name,
            'email': u.email,
            'avatar': avatar,
            'is_enrolled': is_enrolled,
            'has_other_coach': has_other_coach,
            'is_marketplace': not is_enrolled,
            'marketplace_post': m_post,
            'last_msg': last_msg,
            'unread_count': unread_count,
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
            (ChatMessage.is_deleted == False) | (ChatMessage.is_deleted == None)
        ).order_by(ChatMessage.timestamp.asc()).all()

        if active_client:
            has_contract = bool(active_client.coach_id) or (ClientContract.query.filter_by(client_id=active_client.id, status='active').first() is not None)
            has_accepted = (CustomOffer.query.filter_by(client_id=active_client.id, status='accepted').first() is not None)

            if not has_contract and not has_accepted:
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
                is_marketplace_contact = (active_client.coach_id != coach.id)
        else:
            is_marketplace_contact = True
            can_send_offer = False

    support_admin = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).first()
    support_admin_id = support_admin.id if support_admin else None

    return render_template('coach/chat.html',
                           partner_id=partner_id,
                           target_user=target_user,
                           client=active_client,
                           contacts=contacts,
                           all_clients=enrolled_clients,
                           messages=messages,
                           coach=coach,
                           active_offer=active_offer,
                           is_marketplace_contact=is_marketplace_contact,
                           can_send_offer=can_send_offer,
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
    return jsonify(results)"""

# Replace search_users in coach_code_norm
search_pos = coach_code_norm.find("@coach_bp.route('/messages')\n@coach_bp.route('/messages/<int:client_id>')")
if search_pos != -1:
    end_pos = coach_code_norm.find("@coach_bp.route('/upload-voice', methods=['POST'])")
    if end_pos != -1:
        coach_code_norm = coach_code_norm[:search_pos] + new_coach_chat_block + "\n\n" + coach_code_norm[end_pos:]
        print("Replaced coach_chat and search_users in coach.py successfully!")
    else:
        print("WARNING: end_pos for upload-voice not found in coach.py")
else:
    print("WARNING: coach_chat start pos not found in coach.py")

with open('app/routes/coach.py', 'w', encoding='utf-8') as f:
    f.write(coach_code_norm)
print("Updated app/routes/coach.py!")
