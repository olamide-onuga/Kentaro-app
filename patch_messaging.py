with open('app/services/messaging.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Add imports for TicketMessage, SupportRating
if 'from app.models.features import SupportTicket, ClosedSupportChat' in code:
    code = code.replace(
        'from app.models.features import SupportTicket, ClosedSupportChat',
        'from app.models.features import SupportTicket, ClosedSupportChat, TicketMessage, SupportRating'
    )

new_functions = '''

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
'''

if 'def create_support_ticket(' not in code:
    code += new_functions

with open('app/services/messaging.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Updated app/services/messaging.py with full support ticket lifecycle")
