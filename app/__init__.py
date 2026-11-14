import os
from flask import Flask, request
from flask_socketio import SocketIO, join_room, leave_room
from flask_login import current_user
from config import config
from app.extensions import db, migrate, login_manager, mail, scheduler
import logging
logging.basicConfig(level=logging.DEBUG)
def _allowed_communication(sender_id, target_id):
    """Check if sender can communicate with target.
    Coach can talk to client and vice-versa.
    Admins can talk to anyone.
    Users can talk to themselves.
    """
    try:
        sender_id = int(sender_id)
        target_id = int(target_id)
    except (TypeError, ValueError):
        return False

    if sender_id == target_id:
        return True

    from app.models.user import User
    sender = User.query.get(sender_id)
    target = User.query.get(target_id)
    if not sender or not target:
        return False

    # Admins can communicate with anyone
    if getattr(sender, 'is_admin', False) or getattr(target, 'is_admin', False) or getattr(sender, 'is_superadmin', False) or getattr(target, 'is_superadmin', False):
        return True

    # Coach <-> Client communication
    if getattr(sender, 'is_coach', False) and getattr(target, 'is_client', False):
        return True
    if getattr(sender, 'is_client', False) and getattr(target, 'is_coach', False):
        return True

    return True

socketio = SocketIO(async_mode=os.environ.get('SOCKETIO_ASYNC_MODE', None), cors_allowed_origins='*')

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, async_mode='threading')
    login_manager.init_app(app)
    mail.init_app(app)
    scheduler.init_app(app)
    app.login_manager = login_manager
    
    @scheduler.task('cron', id='check_expiring_contracts', hour=8, minute=0)
    def check_expiring_contracts():
        with app.app_context():
            from datetime import datetime, timedelta
            from app.models.coaching import ClientContract
            from app.models.user import ClientProfile
            from app.services.email import send_contract_expiry_warning
            warning_days = [7, 3, 1]
            for days in warning_days:
                target_date = datetime.utcnow().date() + timedelta(days=days)
                contracts = ClientContract.query.filter(
                    ClientContract.status == 'active',
                    db.func.date(ClientContract.end_date) == target_date
                ).all()
                for c in contracts:
                    try:
                        send_contract_expiry_warning(c.client, days)
                    except Exception:
                        pass
    scheduler.start()
    
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'photos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'form_checks'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'voice'), exist_ok=True)
    # Register blueprints
    # Import all models so flask-migrate sees them
    from app.models import features  # noqa
    from app.models import subscription  # noqa - subscription plans and entitlements
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.coach import coach_bp
    from app.routes.client import client_bp
    from app.routes.programs import programs_bp
    from app.routes.exercises import exercises_bp
    from app.routes.admin import admin_bp
    from app.routes.social import social_bp
    from app.routes.support import support_bp
    from app.routes.superadmin import superadmin_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(coach_bp)
    app.register_blueprint(client_bp)
    app.register_blueprint(programs_bp)
    app.register_blueprint(exercises_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(support_bp)
    app.register_blueprint(superadmin_bp)
    
    @socketio.on('connect')
    def handle_connect(auth=None):
        if not current_user.is_authenticated:
            return False  # reject connection
        # Join a personal room for notifications and events
        room = f'user_{current_user.id}'
        join_room(room)
        # Admins join the admin_support room
        is_admin = bool(getattr(current_user, 'is_admin', False) or (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']))
        if is_admin:
            join_room('admin_support')
        # Set online status
        current_user.online = True
        db.session.commit()
        logging.debug(f'User {current_user.id} connected, joined room {room}')
        socketio.emit('connected', {'msg': 'Connected to real-time service'}, room=room)
        socketio.emit('user_status', {'user_id': current_user.id, 'online': True})

    @socketio.on('check_user_status')
    def handle_check_user_status(data):
        target_id = data.get('target_user_id')
        if target_id and current_user.is_authenticated:
            from app.models.user import User
            try:
                t_user = User.query.get(int(target_id))
                if t_user:
                    socketio.emit('user_status', {
                        'user_id': t_user.id,
                        'online': bool(t_user.online)
                    }, room=f'user_{current_user.id}')
            except Exception:
                pass


    @socketio.on('join_ticket')
    def handle_join_ticket(data):
        if not current_user.is_authenticated:
            return
        ticket_id = data.get('ticket_id')
        if ticket_id:
            join_room(f'ticket_{ticket_id}')

    @socketio.on('leave_ticket')
    def handle_leave_ticket(data):
        if not current_user.is_authenticated:
            return
        ticket_id = data.get('ticket_id')
        if ticket_id:
            leave_room(f'ticket_{ticket_id}')

    @socketio.on('chat_message')
    def handle_chat_message(data):
        if not current_user.is_authenticated:
            return
        target_user_id = data.get('target_user_id')
        msg_text = (data.get('msg') or data.get('message') or '').strip()
        voice_url = data.get('voice_url')
        if not target_user_id or (not msg_text and not voice_url):
            return
        try:
            target_user_id = int(target_user_id)
        except (TypeError, ValueError):
            return

        from app.models.user import ChatMessage, User
        from app.services.messaging import get_chat_url, send_system_notification, get_or_create_support_ticket, reopen_support_ticket
        from app.models.features import ClosedSupportChat

        target_user = User.query.get(target_user_id)
        if not target_user:
            return

        # Context & metadata extraction
        context = data.get('context') or 'direct'
        post_id = data.get('post_id')
        program_id = data.get('program_id')
        ticket_id = data.get('ticket_id')
        message_type = 'voice' if voice_url else (data.get('message_type') or 'text')

        # Role & admin checks
        is_admin_sender = bool(getattr(current_user, 'is_admin', False) or (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']))
        is_target_admin = bool(getattr(target_user, 'is_admin', False) or (getattr(target_user, 'role', None) and getattr(target_user.role, 'name', None) in ['admin', 'superadmin']))
        is_anon = True if is_admin_sender else False

        if is_admin_sender or is_target_admin:
            context = 'support'
            support_user_id = target_user_id if is_admin_sender else current_user.id
            ticket = get_or_create_support_ticket(support_user_id)
            reopen_support_ticket(support_user_id)
            ticket_id = ticket.id
            ClosedSupportChat.query.filter_by(user_id=support_user_id).delete()

        reply_to_id = data.get('reply_to_id')
        if reply_to_id:
            try:
                reply_to_id = int(reply_to_id)
            except (TypeError, ValueError):
                reply_to_id = None

        chat_msg = ChatMessage(
            sender_id=current_user.id,
            receiver_id=target_user_id,
            message=msg_text or '[Voice Message]',
            voice_url=voice_url,
            is_anonymous=is_anon,
            context=context,
            message_type=message_type,
            post_id=post_id,
            ticket_id=ticket_id,
            program_id=program_id,
            reply_to_id=reply_to_id
        )
        db.session.add(chat_msg)
        db.session.commit()

        time_str = chat_msg.timestamp.strftime('%H:%M') if chat_msg.timestamp else ''
        sender_disp_name = 'Kentaro Support' if is_anon else _get_user_display_name(current_user)

        target_chat_url = get_chat_url(target_user, current_user.id, context=context, post_id=post_id, program_id=program_id, ticket_id=ticket_id)
        sender_chat_url = get_chat_url(current_user, target_user_id, context=context, post_id=post_id, program_id=program_id, ticket_id=ticket_id)

        reply_to_data = None
        if reply_to_id:
            replied_msg = ChatMessage.query.get(reply_to_id)
            if replied_msg:
                reply_to_data = {
                    'id': replied_msg.id,
                    'sender_name': 'Kentaro Support' if replied_msg.is_anonymous else _get_user_display_name(replied_msg.sender),
                    'message': replied_msg.message[:80] if replied_msg.message else '[Voice Message]'
                }

        payload = {
            'id': chat_msg.id,
            'from': current_user.id,
            'sender_id': current_user.id,
            'target_user_id': target_user_id,
            'receiver_id': target_user_id,
            'msg': chat_msg.message,
            'message': chat_msg.message,
            'voice_url': voice_url,
            'timestamp': time_str,
            'from_name': sender_disp_name,
            'is_read': False,
            'is_anonymous': is_anon,
            'context': context,
            'message_type': message_type,
            'post_id': post_id,
            'ticket_id': ticket_id,
            'program_id': program_id,
            'chat_url': target_chat_url,
            'reply_to_id': reply_to_id,
            'reply_to': reply_to_data,
            'is_edited': False
        }

        # Send persistent Notification to recipient
        send_system_notification(
            recipient_id=target_user_id,
            notif_type='chat_message',
            title=f"New message from {sender_disp_name}",
            text=chat_msg.message[:120],
            link=target_chat_url,
            target_type='chat',
            target_id=chat_msg.id,
            emit_socket=False
        )

        # Relay to target user's personal room and admin desk if target is admin
        if is_target_admin:
            socketio.emit('chat_message', payload, room='admin_support')
        else:
            socketio.emit('chat_message', payload, room=f'user_{target_user_id}')
        # Confirm to sender's room
        sender_payload = dict(payload)
        sender_payload['chat_url'] = sender_chat_url
        socketio.emit('chat_message_sent', sender_payload, room=f'user_{current_user.id}')

    @socketio.on('delete_message')
    def handle_delete_message(data):
        if not current_user.is_authenticated:
            return
        msg_id = data.get('message_id') or data.get('id')
        if not msg_id:
            return
        try:
            msg_id = int(msg_id)
        except (TypeError, ValueError):
            return

        from app.models.user import ChatMessage
        msg = ChatMessage.query.get(msg_id)
        if not msg:
            return
        # Only sender or receiver can delete, or sender can delete
        if msg.sender_id != current_user.id and msg.receiver_id != current_user.id:
            return

        msg.is_deleted = True
        db.session.commit()

        delete_payload = {'message_id': msg.id, 'deleted_by': current_user.id}
        socketio.emit('message_deleted', delete_payload, room=f'user_{msg.sender_id}')
        socketio.emit('message_deleted', delete_payload, room=f'user_{msg.receiver_id}')

    @socketio.on('call_invite')
    def handle_call_invite(data):
        target_id = data.get('target_user_id')
        if not target_id:
            return
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return

        logging.debug(f'call_invite received from {current_user.id} to target {target_id}')
        if not _allowed_communication(current_user.id, target_id):
            logging.debug('call_invite REJECTED: allowed_communication failed')
            return
            
        join_url = ""
        caller_name = "Someone"
        if current_user.is_coach:
            caller_name = f"Coach {current_user.coach_profile.first_name if current_user.coach_profile and current_user.coach_profile.first_name else 'Coach'}"
            join_url = "/client/voice-call"
        elif current_user.is_client:
            caller_name = current_user.client_profile.first_name if current_user.client_profile and current_user.client_profile.first_name else 'Client'
            join_url = f"/coach/voice-call/{current_user.client_profile.id if current_user.client_profile else current_user.id}"
            
        logging.debug(f'call_invite sending to room user_{target_id} with url {join_url}')
        socketio.emit('call_invite', {
            'caller_name': caller_name, 
            'join_url': join_url,
            'caller_user_id': current_user.id
        }, room=f'user_{target_id}')

    def _get_user_display_name(user):
        if not user:
            return "The participant"
        if getattr(user, 'is_admin', False) or (getattr(user, 'role', None) and getattr(user.role, 'name', None) == 'admin'):
            return "Kentaro Support"
        if getattr(user, 'is_coach', False) and user.coach_profile:
            name = user.coach_profile.first_name or "Coach"
            return f"Coach {name}"
        elif getattr(user, 'is_client', False) and user.client_profile:
            return user.client_profile.full_name or "Client"
        return user.email.split('@')[0] if user.email else "The participant"

    @socketio.on('call_declined')
    def handle_call_declined(data):
        target_id = data.get('target_user_id')
        if not target_id:
            return
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return
        sender_name = _get_user_display_name(current_user)
        logging.debug(f'call_declined from {sender_name} ({current_user.id}) to {target_id}')
        socketio.emit('call_declined', {
            'from_user_id': current_user.id,
            'from_name': sender_name
        }, room=f'user_{target_id}')

    @socketio.on('call_accepted')
    def handle_call_accepted(data):
        target_id = data.get('target_user_id')
        if not target_id:
            return
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return
        sender_name = _get_user_display_name(current_user)
        logging.debug(f'call_accepted from {sender_name} ({current_user.id}) to {target_id}')
        socketio.emit('call_accepted', {
            'from_user_id': current_user.id,
            'from_name': sender_name
        }, room=f'user_{target_id}')

    @socketio.on('voice_call_end')
    def handle_voice_call_end(data):
        target_id = data.get('target_user_id')
        if not target_id:
            return
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return
        sender_name = _get_user_display_name(current_user)
        logging.debug(f'voice_call_end from {sender_name} ({current_user.id}) to {target_id}')
        socketio.emit('voice_call_end', {
            'from_user_id': current_user.id,
            'from_name': sender_name
        }, room=f'user_{target_id}')

    @socketio.on('call_peer_state')
    def handle_call_peer_state(data):
        target_id = data.get('target_user_id')
        if not target_id:
            return
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return
        sender_name = _get_user_display_name(current_user)
        data['from_user_id'] = current_user.id
        data['from_name'] = sender_name
        socketio.emit('call_peer_state', data, room=f'user_{target_id}')

    @socketio.on('voice_signal')
    def handle_voice_signal(data):
        target_id = data.get('target_user_id')
        if not target_id:
            return
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return
        logging.debug(f'Voice signal from user {current_user.id} to target {target_id}')
        socketio.emit('voice_signal', data, room=f'user_{target_id}')

    @socketio.on('cast_form_check')
    def handle_cast_form_check(data):
        target_id = data.get('target_user_id')
        if not target_id:
            return
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return
        sender_name = _get_user_display_name(current_user)
        data['from_user_id'] = current_user.id
        data['from_name'] = sender_name
        socketio.emit('cast_form_check', data, room=f'user_{target_id}')

    @socketio.on('stop_cast_form_check')
    def handle_stop_cast_form_check(data):
        target_id = data.get('target_user_id')
        if not target_id:
            return
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return
        socketio.emit('stop_cast_form_check', data, room=f'user_{target_id}')

    @socketio.on('disconnect')
    def handle_disconnect():
        if not current_user.is_authenticated:
            return
        user_id = current_user.id
        room = f'user_{user_id}'
        leave_room(room)
        # Set online flag to False on disconnect
        current_user.online = False
        db.session.commit()
        logging.debug(f'User {user_id} disconnected, left room {room}, set online=False')
        socketio.emit('user_status', {'user_id': user_id, 'online': False})

    @socketio.on('mark_read')
    def handle_mark_read(data):
        """Mark all messages from partner as read for current user.
        Expected payload: {'partner_id': <int>}
        """
        partner_id = data.get('partner_id')
        if not partner_id:
            return
        try:
            partner_id = int(partner_id)
        except (TypeError, ValueError):
            return
        if not _allowed_communication(current_user.id, partner_id):
            return
        # Update unread messages where receiver is current user and sender is partner
        from app.models.user import ChatMessage
        unread = ChatMessage.query.filter(
            ChatMessage.receiver_id == current_user.id,
            ChatMessage.sender_id == partner_id,
            ChatMessage.is_read == False
        ).all()
        for msg in unread:
            msg.is_read = True
        db.session.commit()
        # Emit an update to sender and reader
        socketio.emit('messages_read', {'by_user': current_user.id, 'partner_id': partner_id}, room=f'user_{partner_id}')
        socketio.emit('messages_read', {'by_user': current_user.id, 'partner_id': partner_id}, room=f'user_{current_user.id}')

    @socketio.on('join_community')
    def handle_join_community(data):
        community_id = data.get('community_id')
        if community_id:
            from flask_socketio import join_room
            from app.models.features import CommunityMember
            join_room(f"community_{community_id}")
            # Auto-add as member if not already
            membership = CommunityMember.query.filter_by(
                community_id=community_id, user_id=current_user.id).first()
            if not membership:
                db.session.add(CommunityMember(
                    community_id=community_id, user_id=current_user.id))
                db.session.commit()


    @socketio.on('squad_message')
    def handle_squad_message(data):
        community_id = data.get('community_id')
        content = (data.get('content') or '').strip()
        voice_url = (data.get('voice_url') or '').strip() or None
        reply_to_id = data.get('reply_to_id') or None

        if not community_id or (not content and not voice_url):
            return

        from app.models.features import Community, CommunityMember, CommunityMessage as CM
        comm = Community.query.get(community_id)
        if not comm:
            return

        # Must be a member
        membership = CommunityMember.query.filter_by(community_id=community_id, user_id=current_user.id).first()
        if not membership:
            return

        msg = CM(
            community_id=community_id,
            sender_id=current_user.id,
            content=content,
            voice_url=voice_url,
            reply_to_id=reply_to_id
        )
        db.session.add(msg)
        db.session.commit()

        reply_preview = None
        if reply_to_id:
            replied = CM.query.get(reply_to_id)
            if replied:
                rp_sender = replied.sender
                rp_name = ''
                if rp_sender:
                    rp_profile = getattr(rp_sender, 'client_profile', None) or getattr(rp_sender, 'coach_profile', None)
                    rp_name = getattr(rp_profile, 'first_name', None) or rp_sender.email.split('@')[0]
                reply_preview = {
                    'sender_name': rp_name,
                    'content_snippet': (replied.content[:60] if replied.content else ('🎤 Voice Message' if replied.voice_url else ''))
                }

        # Resolve sender display name from profile
        sender_profile = getattr(current_user, 'client_profile', None) or getattr(current_user, 'coach_profile', None)
        sender_name = getattr(sender_profile, 'first_name', None) or current_user.email.split('@')[0]
        coach_profile = getattr(current_user, 'coach_profile', None)

        payload = {
            'id': msg.id,
            'content': content,
            'voice_url': voice_url,
            'sender_id': current_user.id,
            'sender_name': sender_name,
            'is_coach': comm.coach_id == (coach_profile.id if coach_profile else -1),
            'timestamp': msg.created_at.strftime('%b %d, %H:%M'),
            'reply_preview': reply_preview
        }
        socketio.emit('squad_message', payload, room=f'community_{community_id}')

    @socketio.on('squad_history')
    def handle_squad_history(data):
        community_id = data.get('community_id')
        if not community_id:
            return

        from app.models.features import Community, CommunityMember, CommunityMessage as CM
        comm = Community.query.get(community_id)
        membership = CommunityMember.query.filter_by(community_id=community_id, user_id=current_user.id).first()
        if not membership:
            return

        messages = CM.query.filter_by(community_id=community_id).order_by(CM.created_at.asc()).limit(100).all()
        history = []
        for m in messages:
            reply_preview = None
            if m.reply_to_id and m.reply_to:
                rp_sender = m.reply_to.sender
                rp_name = ''
                if rp_sender:
                    rp_profile = getattr(rp_sender, 'client_profile', None) or getattr(rp_sender, 'coach_profile', None)
                    rp_name = getattr(rp_profile, 'first_name', None) or rp_sender.email.split('@')[0]
                reply_preview = {
                    'sender_name': rp_name,
                    'content_snippet': (m.reply_to.content[:60] if m.reply_to.content else ('🎤 Voice Message' if m.reply_to.voice_url else ''))
                }
            # Resolve sender name from their profile
            sender = m.sender
            sender_name = '?'
            is_coach = False
            if sender:
                s_profile = getattr(sender, 'client_profile', None) or getattr(sender, 'coach_profile', None)
                sender_name = getattr(s_profile, 'first_name', None) or sender.email.split('@')[0]
                if comm and getattr(sender, 'coach_profile', None):
                    is_coach = (comm.coach_id == sender.coach_profile.id)
            history.append({
                'id': m.id,
                'content': m.content,
                'voice_url': m.voice_url or None,
                'sender_id': m.sender_id,
                'sender_name': sender_name,
                'is_coach': is_coach,
                'timestamp': m.created_at.strftime('%b %d, %H:%M'),
                'reply_preview': reply_preview,
                'video_url': m.video_url or None
            })

        from flask_socketio import emit as socketio_emit
        socketio_emit('squad_history', {'history': history})


    @socketio.on('request_history')
    @socketio.on('chat_history')
    def handle_request_history(data):
        target_id = data.get('target_user_id') or data.get('partner_id')
        if not target_id:
            return
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return

        if not _allowed_communication(current_user.id, target_id):
            return
            
        from app.models.user import ChatMessage
        from sqlalchemy import or_, and_
        
        messages = ChatMessage.query.filter(
            or_(
                and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == target_id),
                and_(ChatMessage.sender_id == target_id, ChatMessage.receiver_id == current_user.id)
            ),
            (ChatMessage.is_deleted == False) | (ChatMessage.is_deleted == None)
        ).order_by(ChatMessage.timestamp.asc()).all()
        
        history = []
        for m in messages:
            rp_data = None
            if m.reply_to_id and m.reply_to:
                rp_data = {
                    'id': m.reply_to.id,
                    'sender_name': 'Kentaro Support' if m.reply_to.is_anonymous else _get_user_display_name(m.reply_to.sender),
                    'message': m.reply_to.message[:80] if m.reply_to.message else '[Voice Message]'
                }
            history.append({
                'id': m.id,
                'from': m.sender_id,
                'sender_id': m.sender_id,
                'to': m.receiver_id,
                'msg': m.message,
                'message': m.message,
                'voice_url': m.voice_url or None,
                'timestamp': m.timestamp.strftime('%H:%M') if m.timestamp else '',
                'is_read': bool(m.is_read),
                'is_anonymous': bool(getattr(m, 'is_anonymous', False)),
                'reply_to_id': m.reply_to_id,
                'reply_to': rp_data,
                'is_edited': bool(getattr(m, 'is_edited', False))
            })
        # Emit the history back to the requesting socket
        from flask_socketio import emit as socketio_emit
        socketio_emit('chat_history', {'history': history})


    @app.before_request
    def check_maintenance_mode():
        from flask import request, render_template
        from flask_login import current_user
        if (
            request.path.startswith('/static') or 
            request.path.startswith('/admin') or 
            request.path.startswith('/auth/login') or 
            request.path.startswith('/auth/logout')
        ):
            return None
            
        try:
            from app.models.features import SystemSetting
            m_mode = SystemSetting.query.filter_by(key='maintenance_mode').first()
            if m_mode and m_mode.value == '1':
                if current_user.is_authenticated and (
                    getattr(current_user, 'is_admin', False) or 
                    getattr(current_user, 'is_superadmin', False) or 
                    (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin'])
                ):
                    return None
                    
                msg_row = SystemSetting.query.filter_by(key='maintenance_message').first()
                msg = msg_row.value if (msg_row and msg_row.value) else 'Kentaro is currently undergoing scheduled maintenance. Please check back shortly.'
                return render_template('maintenance.html', maintenance_message=msg), 503
        except Exception:
            pass
        return None

    @app.context_processor
    def inject_global_data():
        import zoneinfo
        all_tz = sorted([tz for tz in zoneinfo.available_timezones() if '/' in tz and not tz.startswith('Etc/') and not tz.startswith('SystemV/')])
        
        all_countries = [
            "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda", "Argentina", "Armenia", "Australia", "Austria",
            "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bhutan",
            "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cabo Verde", "Cambodia",
            "Cameroon", "Canada", "Central African Republic", "Chad", "Chile", "China", "Colombia", "Comoros", "Congo", "Costa Rica",
            "Croatia", "Cuba", "Cyprus", "Czech Republic", "Denmark", "Djibouti", "Dominica", "Dominican Republic", "Ecuador", "Egypt",
            "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon",
            "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala", "Guinea", "Guyana", "Haiti",
            "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy",
            "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Korea, North", "Korea, South", "Kuwait", "Kyrgyzstan",
            "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar",
            "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia",
            "Moldova", "Monaco", "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nepal",
            "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria", "North Macedonia", "Norway", "Oman", "Pakistan", "Palau",
            "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Qatar", "Romania",
            "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia", "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Saudi Arabia", "Senegal", "Serbia",
            "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Sudan", "Spain",
            "Sri Lanka", "Sudan", "Suriname", "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania", "Thailand",
            "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine",
            "United Arab Emirates", "United Kingdom", "United States", "Uruguay", "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela", "Vietnam", "Yemen",
            "Zambia", "Zimbabwe"
        ]

        # Global announcement banner & platform branding
        global_announcement = None
        branding = {
            'app_name': 'Kentaro',
            'app_tagline': 'Calisthenics & Strength Coaching Platform',
            'primary_color': '#D92D3A',
            'logo_url': None,
            'favicon_url': None,
            'support_email': 'support@kentaro.app',
            'support_phone': '',
            'platform_description': 'High-performance calisthenics coaching ecosystem.'
        }
        try:
            from app.models.features import SystemSetting
            settings = SystemSetting.query.filter(
                SystemSetting.key.in_([
                    'announcement_banner', 'announcement_banner_active',
                    'app_name', 'app_tagline', 'primary_color',
                    'platform_logo_url', 'platform_favicon_url',
                    'support_email', 'support_phone', 'platform_description'
                ])
            ).all()
            for s in settings:
                if s.key == 'app_name' and s.value:
                    branding['app_name'] = s.value
                elif s.key == 'app_tagline' and s.value:
                    branding['app_tagline'] = s.value
                elif s.key == 'primary_color' and s.value:
                    branding['primary_color'] = s.value
                elif s.key == 'platform_logo_url' and s.value:
                    branding['logo_url'] = s.value
                elif s.key == 'platform_favicon_url' and s.value:
                    branding['favicon_url'] = s.value
                elif s.key == 'support_email' and s.value:
                    branding['support_email'] = s.value
                elif s.key == 'support_phone' and s.value:
                    branding['support_phone'] = s.value
                elif s.key == 'platform_description' and s.value:
                    branding['platform_description'] = s.value
            
            ann = next((s for s in settings if s.key == 'announcement_banner'), None)
            act = next((s for s in settings if s.key == 'announcement_banner_active'), None)
            if act and act.value == '1' and ann and ann.value:
                global_announcement = ann.value
        except Exception:
            pass

        return dict(all_timezones=all_tz, all_countries=all_countries, global_announcement=global_announcement, platform_branding=branding)

    @app.template_filter('money')
    def money_filter(value):
        """Format number with commas and 2 decimal places."""
        try:
            v = float(value)
            return '{:,.2f}'.format(v)
        except (TypeError, ValueError):
            return str(value) if value is not None else '0.00'

    @app.context_processor
    def inject_unread_count():
        """Inject global unread message count for nav badges."""
        from flask_login import current_user
        try:
            if current_user.is_authenticated:
                from app.models.user import ChatMessage
                count = ChatMessage.query.filter_by(
                    receiver_id=current_user.id, is_read=False
                ).count()
                return {'unread_count': count}
        except Exception:
            pass
        return {'unread_count': 0}

    return app
