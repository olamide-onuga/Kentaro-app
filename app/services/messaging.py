import datetime as dt
import uuid
import logging
from flask import url_for
from app.extensions import db
from app.models.user import User, ChatMessage
from app.models.chat import Notification
from app.models.features import SupportTicket, ClosedSupportChat, TicketMessage, SupportRating


def get_chat_url(recipient, partner_id, context='direct', post_id=None, program_id=None, ticket_id=None):
    """
    Generate an exact, verified internal URL for a user to reach a conversation,
    marketplace negotiation, support ticket, or program.
    Guarantees no trailing slashes or unregistered routes.
    """
    if not recipient:
        return "/client/chat"

    is_admin = bool(
        getattr(recipient, 'is_admin', False) or 
        (getattr(recipient, 'role', None) and getattr(recipient.role, 'name', None) in ['admin', 'superadmin'])
    )

    if is_admin:
        url = f"/admin/chat?partner_id={partner_id}"
        if ticket_id:
            url += f"&ticket_id={ticket_id}"
        return url

    if getattr(recipient, 'is_coach', False):
        url = f"/coach/chat?partner_id={partner_id}"
        if context == 'marketplace' and post_id:
            url += f"&context=marketplace&post_id={post_id}"
        elif context == 'support':
            url += "&category=support"
        return url

    # Client role or standard user
    if program_id and context == 'program':
        return "/client/my-program"

    url = f"/client/chat?partner_id={partner_id}"
    if context == 'marketplace' and post_id:
        url += f"&context=marketplace&post_id={post_id}"
    elif context == 'support':
        url += "&category=support"
    return url


def send_system_notification(recipient_id, notif_type, title, text, link=None, target_type=None, target_id=None, emit_socket=True):
    """
    Safely creates a persistent Notification record in the database
    and emits a real-time event to the recipient's personal WebSocket room.
    """
    try:
        recipient = User.query.get(recipient_id)
        if not recipient:
            return None

        if not link:
            link = "/client/dashboard" if recipient.is_client else ("/coach/dashboard" if recipient.is_coach else "/admin/dashboard")

        notif = Notification(
            user_id=recipient_id,
            type=notif_type,
            title=title,
            text=text,
            link=link,
            target_type=target_type,
            target_id=target_id
        )
        db.session.add(notif)
        db.session.commit()

        if emit_socket:
            from app import socketio
            socketio.emit('notification', {
                'id': notif.id,
                'title': title,
                'msg': text,
                'chat_url': link,
                'link': link,
                'type': notif_type
            }, room=f'user_{recipient_id}')

        return notif
    except Exception as e:
        logging.error(f"[send_system_notification] Error: {e}", exc_info=True)
        db.session.rollback()
        return None


def get_or_create_support_ticket(user_id, subject='Platform Support Request'):
    """
    Retrieve active open support ticket for user, or create a new one.
    """
    ticket = SupportTicket.query.filter_by(user_id=user_id, status='open').order_by(SupportTicket.created_at.desc()).first()
    if not ticket:
        ref = f"SUP-{uuid.uuid4().hex[:6].upper()}"
        ticket = SupportTicket(
            ticket_ref=ref,
            user_id=user_id,
            subject=subject,
            status='open',
            created_at=dt.datetime.utcnow(),
            updated_at=dt.datetime.utcnow()
        )
        db.session.add(ticket)
        # Also ensure any ClosedSupportChat record is removed
        ClosedSupportChat.query.filter_by(user_id=user_id).delete()
        db.session.commit()
    return ticket


def close_support_ticket(user_id, admin_id):
    """
    Close active support ticket for user, record closing metadata,
    and notify user in real-time.
    """
    tickets = SupportTicket.query.filter_by(user_id=user_id, status='open').all()
    now = dt.datetime.utcnow()
    for t in tickets:
        t.status = 'closed'
        t.closed_at = now
        t.closed_by_id = admin_id
        t.updated_at = now

    # Also record in ClosedSupportChat for legacy compatibility
    existing_closed = ClosedSupportChat.query.filter_by(user_id=user_id).first()
    if not existing_closed:
        db.session.add(ClosedSupportChat(admin_id=admin_id, user_id=user_id, closed_at=now))

    db.session.commit()

    from app import socketio
    socketio.emit('support_chat_closed', {
        'by_admin': True,
        'user_id': user_id
    }, room=f'user_{user_id}')


def reopen_support_ticket(user_id):
    """
    Reopen closed ticket or set to open when user sends a new support message.
    """
    now = dt.datetime.utcnow()
    ticket = SupportTicket.query.filter_by(user_id=user_id).order_by(SupportTicket.created_at.desc()).first()
    if ticket:
        ticket.status = 'open'
        ticket.reopened_at = now
        ticket.updated_at = now
    else:
        ref = f"SUP-{uuid.uuid4().hex[:6].upper()}"
        ticket = SupportTicket(
            ticket_ref=ref,
            user_id=user_id,
            subject='Platform Support Request',
            status='open',
            created_at=now,
            updated_at=now
        )
        db.session.add(ticket)

    ClosedSupportChat.query.filter_by(user_id=user_id).delete()
    db.session.commit()

    from app import socketio
    socketio.emit('support_chat_reopened', {
        'user_id': user_id,
        'ticket_ref': ticket.ticket_ref
    }, room='admin_support')

    return ticket


def create_support_ticket(user_id, subject, category='general', description='', attachment_url=None):
    """
    Creates a brand new support ticket in 'pending' status with its own unique conversation.
    Never mixes with previous tickets.
    """
    ref = f"SUP-{uuid.uuid4().hex[:6].upper()}"
    ticket = SupportTicket(
        ticket_ref=ref,
        user_id=user_id,
        subject=subject or 'Platform Support Request',
        category=category or 'general',
        description=description or '',
        attachment_url=attachment_url,
        status='pending',
        created_at=dt.datetime.utcnow(),
        updated_at=dt.datetime.utcnow()
    )
    db.session.add(ticket)
    db.session.flush()

    # Initial message in the dedicated ticket conversation
    if description or attachment_url:
        init_msg = TicketMessage(
            ticket_id=ticket.id,
            sender_id=user_id,
            message=description or '[Attachment submitted]',
            attachment_url=attachment_url,
            is_system=False,
            created_at=dt.datetime.utcnow()
        )
        db.session.add(init_msg)

    db.session.commit()

    # Notify admin desk of the new pending ticket
    from app import socketio
    user = User.query.get(user_id)
    user_name = user.email if user else "User"
    role_name = "User"
    if user:
        if user.is_coach:
            role_name = "Coach"
            user_name = f"Coach {user.coach_profile.first_name}" if user.coach_profile and user.coach_profile.first_name else user.email
        elif user.is_client:
            role_name = "Athlete"
            user_name = user.client_profile.full_name if user.client_profile else user.email

    socketio.emit('new_support_ticket', {
        'ticket_id': ticket.id,
        'ticket_ref': ticket.ticket_ref,
        'user_id': user_id,
        'user_name': user_name,
        'role': role_name,
        'subject': ticket.subject,
        'category': ticket.category,
        'created_at': ticket.created_at.strftime('%Y-%m-%d %H:%M')
    }, room='admin_support')

    # Send persistent notifications to all administrators
    try:
        admins = User.query.filter(
            (User.is_admin == True) | 
            (User.role.has(name='admin')) | 
            (User.role.has(name='superadmin'))
        ).all()
        for admin in admins:
            send_system_notification(
                recipient_id=admin.id,
                notif_type='support_ticket',
                title=f"New Support Ticket #{ticket.ticket_ref}",
                text=f"{user_name} ({role_name}): {ticket.subject}",
                link="/admin/support",
                target_type='ticket',
                target_id=ticket.id,
                emit_socket=True
            )
    except Exception as e:
        logging.error(f"[create_support_ticket admin notification error]: {e}")

    return ticket


def accept_support_ticket(ticket_id, admin_id):
    """
    Assigns an unassigned/pending ticket to the accepting admin, unlocks the conversation,
    and automatically posts the welcome message with the admin's professional display name.
    """
    ticket = SupportTicket.query.get(ticket_id)
    if not ticket:
        return None

    admin = User.query.get(admin_id)
    if not admin:
        return None

    admin_name = getattr(admin, 'admin_display_name', admin.email.split('@')[0].capitalize())

    ticket.assigned_admin_id = admin_id
    ticket.status = 'active'
    ticket.accepted_at = dt.datetime.utcnow()
    ticket.updated_at = dt.datetime.utcnow()

    # Automatic welcome system message identifying the accepting admin
    welcome_msg = TicketMessage(
        ticket_id=ticket.id,
        sender_id=admin_id,
        message=f"Hello! I'm {admin_name}, and I have accepted your support ticket. I'll be assisting you with this issue.",
        is_system=True,
        created_at=dt.datetime.utcnow()
    )
    db.session.add(welcome_msg)

    # Secondary system notification message visible in thread
    system_notice = TicketMessage(
        ticket_id=ticket.id,
        sender_id=admin_id,
        message=f"Your support ticket has been accepted by {admin_name}. You can now continue this conversation with your assigned support administrator.",
        is_system=True,
        created_at=dt.datetime.utcnow()
    )
    db.session.add(system_notice)
    db.session.commit()

    # Persistent notification to ticket creator
    send_system_notification(
        recipient_id=ticket.user_id,
        notif_type='support_ticket_accepted',
        title="Support Ticket Accepted",
        text=f"Your support ticket #{ticket.ticket_ref} has been accepted by {admin_name}.",
        link=f"/support/ticket/{ticket.ticket_ref}",
        target_type='ticket',
        target_id=ticket.id,
        emit_socket=True
    )

    # Real-time socket announcement
    from app import socketio
    socketio.emit('ticket_accepted', {
        'ticket_id': ticket.id,
        'ticket_ref': ticket.ticket_ref,
        'admin_id': admin_id,
        'admin_name': admin_name,
        'status': 'active',
        'accepted_at': ticket.accepted_at.strftime('%H:%M')
    }, room=f'user_{ticket.user_id}')

    socketio.emit('ticket_accepted', {
        'ticket_id': ticket.id,
        'ticket_ref': ticket.ticket_ref,
        'admin_id': admin_id,
        'admin_name': admin_name,
        'status': 'active'
    }, room=f'ticket_{ticket.id}')

    return ticket


def close_support_ticket_by_id(ticket_id, admin_id):
    """
    Closes support ticket, makes conversation read-only, and prompts creator for rating.
    """
    ticket = SupportTicket.query.get(ticket_id)
    if not ticket:
        return None

    admin = User.query.get(admin_id)
    admin_name = getattr(admin, 'admin_display_name', 'Support Administrator') if admin else 'Support Administrator'

    ticket.status = 'closed'
    ticket.closed_at = dt.datetime.utcnow()
    ticket.closed_by_id = admin_id
    ticket.updated_at = dt.datetime.utcnow()

    # System closure record
    close_msg = TicketMessage(
        ticket_id=ticket.id,
        sender_id=admin_id,
        message=f"This support ticket has been closed by {admin_name}.",
        is_system=True,
        created_at=dt.datetime.utcnow()
    )
    db.session.add(close_msg)
    db.session.commit()

    # Persistent notification to creator
    send_system_notification(
        recipient_id=ticket.user_id,
        notif_type='support_ticket_closed',
        title="Support Ticket Closed",
        text=f"Your support ticket #{ticket.ticket_ref} was closed by {admin_name}. Please rate your experience.",
        link=f"/support/ticket/{ticket.ticket_ref}",
        target_type='ticket',
        target_id=ticket.id,
        emit_socket=True
    )

    from app import socketio
    socketio.emit('ticket_closed', {
        'ticket_id': ticket.id,
        'ticket_ref': ticket.ticket_ref,
        'admin_name': admin_name,
        'status': 'closed'
    }, room=f'user_{ticket.user_id}')

    socketio.emit('ticket_closed', {
        'ticket_id': ticket.id,
        'ticket_ref': ticket.ticket_ref,
        'admin_name': admin_name,
        'status': 'closed'
    }, room=f'ticket_{ticket.id}')

    return ticket


def rate_support_ticket(ticket_id, user_id, rating, feedback=None):
    """
    Submits client/coach rating for an assigned admin on a closed ticket.
    One rating per ticket only.
    """
    ticket = SupportTicket.query.get(ticket_id)
    if not ticket or ticket.user_id != user_id or ticket.status != 'closed':
        return False

    if ticket.rating is not None:
        return False  # Already rated

    try:
        rating_val = max(1, min(5, int(rating)))
    except (ValueError, TypeError):
        rating_val = 5

    ticket.rating = rating_val
    ticket.rating_feedback = (feedback or '').strip()
    ticket.rated_at = dt.datetime.utcnow()

    # Persist in SupportRating model as well
    rating_rec = SupportRating(
        ticket_id=ticket.id,
        user_id=user_id,
        admin_id=ticket.assigned_admin_id or (ticket.closed_by_id or user_id),
        rating=rating_val,
        feedback=ticket.rating_feedback,
        created_at=dt.datetime.utcnow()
    )
    db.session.add(rating_rec)
    db.session.commit()
    return True
