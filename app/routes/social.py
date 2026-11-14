from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.user import User, CoachProfile, ClientProfile
from app.models.features import FriendRequest, Community, CommunityMember, CommunityMessage
from app import socketio

social_bp = Blueprint('social', __name__, url_prefix='/social')

@social_bp.route('/friends')
@login_required
def friends():
    search_q = request.args.get('q', '').strip()
    users_found = []
    if search_q:
        users_found = User.query.filter(
            (User.email.ilike(f'%{search_q}%')) & (User.id != current_user.id)
        ).limit(20).all()

    # Incoming pending friend requests
    incoming_requests = FriendRequest.query.filter_by(receiver_id=current_user.id, status='pending').all()
    # Outgoing pending friend requests
    outgoing_requests = FriendRequest.query.filter_by(sender_id=current_user.id, status='pending').all()

    # Accepted friends
    accepted_sent = FriendRequest.query.filter_by(sender_id=current_user.id, status='accepted').all()
    accepted_recv = FriendRequest.query.filter_by(receiver_id=current_user.id, status='accepted').all()

    friend_user_ids = [r.receiver_id for r in accepted_sent] + [r.sender_id for r in accepted_recv]
    friends_list = User.query.filter(User.id.in_(friend_user_ids)).all() if friend_user_ids else []

    return render_template(
        'social/friends.html',
        search_q=search_q,
        users_found=users_found,
        incoming_requests=incoming_requests,
        outgoing_requests=outgoing_requests,
        friends_list=friends_list
    )

@social_bp.route('/friend-request/send/<int:user_id>', methods=['POST'])
@login_required
def send_friend_request(user_id):
    if user_id == current_user.id:
        flash('You cannot send a friend request to yourself.', 'warning')
        return redirect(url_for('social.friends'))

    target_user = User.query.get_or_404(user_id)
    existing = FriendRequest.query.filter(
        ((FriendRequest.sender_id == current_user.id) & (FriendRequest.receiver_id == user_id)) |
        ((FriendRequest.sender_id == user_id) & (FriendRequest.receiver_id == current_user.id))
    ).first()

    if existing:
        flash(f'Friend request already exists (Status: {existing.status}).', 'info')
    else:
        req = FriendRequest(sender_id=current_user.id, receiver_id=user_id, status='pending')
        db.session.add(req)
        db.session.commit()
        flash(f'Friend request sent to {target_user.email}!', 'success')

    return redirect(url_for('social.friends'))

@social_bp.route('/friend-request/<int:req_id>/respond/<string:action>', methods=['POST'])
@login_required
def respond_friend_request(req_id, action):
    req = FriendRequest.query.get_or_404(req_id)
    if req.receiver_id != current_user.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('social.friends'))

    if action == 'accept':
        req.status = 'accepted'
        db.session.commit()
        flash('Friend request accepted!', 'success')
    elif action == 'reject':
        req.status = 'rejected'
        db.session.commit()
        flash('Friend request declined.', 'info')

    return redirect(url_for('social.friends'))

def ensure_community_for_coach(coach):
    if not coach:
        return None
    community = Community.query.filter_by(coach_id=coach.id).first()
    if not community:
        name = f"Coach {coach.first_name or 'Coach'}'s Squad 🏋️"
        community = Community(
            coach_id=coach.id,
            name=name,
            description=f"Welcome to Coach {coach.first_name or ''}'s official athlete community!"
        )
        db.session.add(community)
        db.session.commit()

        # Add coach as member
        db.session.add(CommunityMember(community_id=community.id, user_id=coach.user_id))
        db.session.commit()
    return community

def ensure_client_in_community(client_profile):
    if not client_profile or not client_profile.coach:
        return None
    community = ensure_community_for_coach(client_profile.coach)
    if community:
        member = CommunityMember.query.filter_by(community_id=community.id, user_id=client_profile.user_id).first()
        if not member:
            db.session.add(CommunityMember(community_id=community.id, user_id=client_profile.user_id))
            db.session.commit()
    return community

@social_bp.route('/community')
@login_required
def community():
    target_community = None
    if current_user.is_coach and current_user.coach_profile:
        target_community = ensure_community_for_coach(current_user.coach_profile)
        for client in current_user.coach_profile.clients:
            ensure_client_in_community(client)
    elif current_user.is_client and current_user.client_profile:
        if current_user.client_profile.coach:
            target_community = ensure_client_in_community(current_user.client_profile)

    if not target_community:
        first_membership = CommunityMember.query.filter_by(user_id=current_user.id).first()
        if first_membership:
            target_community = first_membership.community
        else:
            target_community = Community.query.first()

    if not target_community:
        flash('No community available yet. If you are a client, sign up with a coach to join their community!', 'info')
        return redirect(url_for('social.friends'))

    messages = CommunityMessage.query.filter_by(community_id=target_community.id).order_by(CommunityMessage.created_at.asc()).all()
    members = target_community.members.all()
    return render_template('social/community.html', community=target_community, messages=messages, members=members)

@social_bp.route('/community/<int:community_id>/post', methods=['POST'])
@login_required
def post_community_message(community_id):
    community = Community.query.get_or_404(community_id)
    content = request.form.get('content', '').strip()
    reply_to_id = request.form.get('reply_to_id', type=int)

    video_url = None
    if 'video' in request.files:
        file = request.files['video']
        if file and file.filename:
            from werkzeug.utils import secure_filename
            import uuid, os
            from flask import current_app
            filename = f"vid_{current_user.id}_{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
            video_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos')
            os.makedirs(video_dir, exist_ok=True)
            file.save(os.path.join(video_dir, filename))
            video_url = f"/static/uploads/videos/{filename}"

    if content or video_url:
        msg = CommunityMessage(
            community_id=community.id,
            sender_id=current_user.id,
            content=content,
            video_url=video_url,
            reply_to_id=reply_to_id
        )
        db.session.add(msg)
        db.session.commit()

        sender_name = current_user.email.split('@')[0]
        if current_user.is_coach and current_user.coach_profile and current_user.coach_profile.first_name:
            sender_name = f"Coach {current_user.coach_profile.first_name}"
        elif current_user.is_client and current_user.client_profile and current_user.client_profile.first_name:
            sender_name = current_user.client_profile.full_name

        socketio.emit('community_message', {
            'id': msg.id,
            'community_id': community.id,
            'sender_id': current_user.id,
            'sender_name': sender_name,
            'content': msg.content,
            'video_url': msg.video_url,
            'reply_to_id': msg.reply_to_id,
            'reply_to_content': msg.reply_to.content if msg.reply_to else None,
            'created_at': msg.created_at.strftime('%H:%M')
        }, room=f"community_{community.id}")

        flash('Message posted to community!', 'success')

    return redirect(url_for('social.community'))
