# scripts/patch_client.py
import re

with open('app/routes/client.py', 'r', encoding='utf-8') as f:
    client_code = f.read().replace('\r\n', '\n')

new_chat_and_search = """@client_bp.route('/messages')
@client_bp.route('/chat')
@login_required
def chat():
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
    target_partner_id = request.args.get('partner_id', type=int) or request.args.get('coach_user_id', type=int)

    # Check contract / accepted offer status to determine if offers should be suppressed
    has_active_contract = bool(profile.coach_id) or (ClientContract.query.filter_by(client_id=profile.id, status='active').first() is not None)
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

    # 2. Client's enrolled coach
    if profile.coach and profile.coach.user_id not in seen:
        seen.add(profile.coach.user_id)
        all_contact_uids.append(profile.coach.user_id)

    # 3. All conversation partners (marketplace coaches, searched users, etc.)
    for uid in partner_uids:
        if uid not in seen:
            seen.add(uid)
            all_contact_uids.append(uid)

    contacts = []
    for uid in all_contact_uids:
        u = User.query.get(uid)
        if not u:
            continue
        c_coach = u.coach_profile
        c_client = u.client_profile
        is_my_coach = bool(profile.coach and u.id == profile.coach.user_id)
        is_admin_user = bool(u.is_admin or (u.role and u.role.name == 'admin'))

        if is_admin_user:
            name = "Kentaro Support"
            role_label = "Platform Support"
            avatar = ""
            is_support = True
        elif c_coach and c_coach.first_name:
            name = f"Coach {c_coach.first_name} {c_coach.last_name or ''}".strip()
            role_label = 'My Coach' if is_my_coach else 'Coach'
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

        contacts.append({
            'user': u,
            'coach': c_coach,
            'client': c_client,
            'name': name,
            'email': u.email,
            'avatar': avatar,
            'is_my_coach': is_my_coach,
            'is_coach': bool(c_coach),
            'is_support': is_support,
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
            (ChatMessage.is_deleted == False) | (ChatMessage.is_deleted == None)
        ).order_by(ChatMessage.timestamp.asc()).all()

    support_admin = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).first()
    support_admin_id = support_admin.id if support_admin else None

    return render_template('client/chat.html',
                           partner_id=partner_id,
                           active_user=active_user,
                           coach=active_coach,
                           conversations=contacts,
                           contacts=contacts,
                           active_offer=active_offer,
                           profile=profile,
                           messages=messages,
                           support_admin_id=support_admin_id)


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
    return jsonify(results)"""

# Locate old chat and search_users block in client.py
start_chat_pos = client_code.find("@client_bp.route('/messages')\n@login_required\ndef chat():")
if start_chat_pos != -1:
    end_chat_pos = client_code.find("@client_bp.route('/upload-voice', methods=['POST'])")
    if end_chat_pos != -1:
        client_code = client_code[:start_chat_pos] + new_chat_and_search + "\n\n" + client_code[end_chat_pos:]
        print("Replaced chat and search_users in client.py successfully!")
    else:
        print("WARNING: end_chat_pos not found in client.py")
else:
    print("WARNING: start_chat_pos not found in client.py")

# Update dashboard route in client.py to suppress offers if client has accepted an offer or active contract
old_dash_offers = """        pending_offers = CustomOffer.query.filter_by(client_id=profile.id, status='pending').order_by(CustomOffer.created_at.desc()).all()

        # For coachless clients, check if any coaches have messaged them for negotiations
        if not profile.coach_id:"""

new_dash_offers = """        from app.models.coaching import ClientContract
        has_active_contract = bool(profile.coach_id) or (ClientContract.query.filter_by(client_id=profile.id, status='active').first() is not None)
        has_accepted_offer = (CustomOffer.query.filter_by(client_id=profile.id, status='accepted').first() is not None)

        if not has_active_contract and not has_accepted_offer:
            pending_offers = CustomOffer.query.filter_by(client_id=profile.id, status='pending').order_by(CustomOffer.created_at.desc()).all()
        else:
            pending_offers = []

        # For coachless clients, check if any coaches have messaged them for negotiations
        if not profile.coach_id and not has_accepted_offer:"""

if old_dash_offers in client_code:
    client_code = client_code.replace(old_dash_offers, new_dash_offers)
    print("Updated dashboard offer suppression in client.py successfully!")
else:
    print("WARNING: old_dash_offers not found in client.py")

# Add approve/decline termination routes
termination_routes = """
@client_bp.route('/contract/approve-termination', methods=['POST'])
@login_required
def approve_contract_termination():
    profile = current_user.client_profile
    if not profile:
        flash('Athlete profile not found.', 'danger')
        return redirect(url_for('client.dashboard'))
    
    from app.models.coaching import ClientContract
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
"""

if "/contract/approve-termination" not in client_code:
    client_code += "\n" + termination_routes
    print("Added contract termination approval routes to client.py!")

with open('app/routes/client.py', 'w', encoding='utf-8') as f:
    f.write(client_code)
print("Updated app/routes/client.py!")
