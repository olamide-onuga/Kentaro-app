with open('app/routes/admin.py', 'r', encoding='utf-8') as f:
    admin_code = f.read()

# Update inject_admin_stats
if 'admin_pending_tickets' not in admin_code:
    admin_code = admin_code.replace(
        "    return dict(\n        admin_pending_reports=pending_reports,\n        admin_pending_coaches=pending_coaches\n    )",
        """    try:
        from app.models.features import SupportTicket
        pending_tickets = SupportTicket.query.filter_by(status='pending').count()
    except Exception:
        pending_tickets = 0
    return dict(
        admin_pending_reports=pending_reports,
        admin_pending_coaches=pending_coaches,
        admin_pending_tickets=pending_tickets
    )"""
    )

admin_ticket_routes = '''

# ─────────────────────────────────────────────────────────────────────────────
# ADVANCED SUPPORT TICKET DESK & REPORTS (PENDING, ACTIVE, CLOSED, RATINGS)
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route('/tickets')
@login_required
def support_tickets():
    """Admin dashboard dedicated support tickets management desk."""
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))

    from app.models.features import SupportTicket, SupportRating
    from app.models.user import User

    active_tab = request.args.get('tab', 'pending')  # 'pending', 'active', 'closed'
    search_q = request.args.get('q', '').strip()

    query = SupportTicket.query

    if search_q:
        query = query.join(User, SupportTicket.user_id == User.id).filter(
            (SupportTicket.ticket_ref.ilike(f'%{search_q}%')) |
            (SupportTicket.subject.ilike(f'%{search_q}%')) |
            (User.email.ilike(f'%{search_q}%'))
        )

    pending_tickets = query.filter(SupportTicket.status == 'pending').order_by(SupportTicket.created_at.desc()).all()
    active_tickets = query.filter(SupportTicket.status == 'active').order_by(SupportTicket.updated_at.desc()).all()
    closed_tickets = query.filter(SupportTicket.status == 'closed').order_by(SupportTicket.closed_at.desc()).all()

    # Counts
    pending_count = SupportTicket.query.filter_by(status='pending').count()
    active_count = SupportTicket.query.filter_by(status='active').count()
    closed_count = SupportTicket.query.filter_by(status='closed').count()

    return render_template(
        'admin/tickets.html',
        active_tab=active_tab,
        search_q=search_q,
        pending_tickets=pending_tickets,
        active_tickets=active_tickets,
        closed_tickets=closed_tickets,
        pending_count=pending_count,
        active_count=active_count,
        closed_count=closed_count,
        admin_display_name=current_user.admin_display_name
    )


@admin_bp.route('/tickets/<int:ticket_id>/accept', methods=['POST'])
@login_required
def accept_ticket(ticket_id):
    """Admin accepts an unassigned pending ticket."""
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))

    from app.services.messaging import accept_support_ticket
    ticket = accept_support_ticket(ticket_id, current_user.id)
    if not ticket:
        flash('Ticket could not be accepted.', 'danger')
        return redirect(url_for('admin.support_tickets'))

    log_admin_activity('accept_support_ticket', 'support_ticket', ticket.id, f'Accepted ticket #{ticket.ticket_ref}')
    flash(f"Ticket #{ticket.ticket_ref} accepted! You are now the assigned administrator.", 'success')
    return redirect(url_for('admin.ticket_detail', ticket_ref=ticket.ticket_ref))


@admin_bp.route('/tickets/<ticket_ref>')
@login_required
def ticket_detail(ticket_ref):
    """Admin view of a dedicated support ticket conversation."""
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))

    from app.models.features import SupportTicket, TicketMessage
    ticket = SupportTicket.query.filter_by(ticket_ref=ticket_ref).first_or_404()
    messages = TicketMessage.query.filter_by(ticket_id=ticket.id).order_by(TicketMessage.created_at.asc()).all()

    # Check assignment permissions
    is_superadmin = getattr(current_user, 'is_superadmin', False)
    is_assigned = (ticket.assigned_admin_id == current_user.id)
    can_reply = is_superadmin or is_assigned or (ticket.status == 'pending')

    return render_template(
        'admin/ticket_detail.html',
        ticket=ticket,
        messages=messages,
        is_assigned=is_assigned,
        is_superadmin=is_superadmin,
        can_reply=can_reply,
        admin_display_name=current_user.admin_display_name
    )


@admin_bp.route('/tickets/<ticket_ref>/reply', methods=['POST'])
@login_required
def admin_ticket_reply(ticket_ref):
    """Admin sends reply in ticket conversation."""
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))

    from app.models.features import SupportTicket, TicketMessage
    from app.services.messaging import send_system_notification
    from app import socketio

    ticket = SupportTicket.query.filter_by(ticket_ref=ticket_ref).first_or_404()
    if ticket.status == 'closed':
        flash('This ticket is closed.', 'warning')
        return redirect(url_for('admin.ticket_detail', ticket_ref=ticket.ticket_ref))

    msg_text = request.form.get('message', '').strip()
    if not msg_text:
        flash('Please enter a message.', 'warning')
        return redirect(url_for('admin.ticket_detail', ticket_ref=ticket.ticket_ref))

    admin_name = current_user.admin_display_name

    msg = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        message=msg_text,
        is_system=False,
        created_at=dt.datetime.utcnow()
    )
    db.session.add(msg)
    ticket.updated_at = dt.datetime.utcnow()
    db.session.commit()

    # Emit socket message to ticket room
    payload = {
        'id': msg.id,
        'ticket_id': ticket.id,
        'ticket_ref': ticket.ticket_ref,
        'sender_id': current_user.id,
        'sender_name': admin_name,
        'is_admin': True,
        'is_system': False,
        'message': msg.message,
        'timestamp': msg.created_at.strftime('%H:%M'),
        'date': msg.created_at.strftime('%b %d, %Y')
    }
    socketio.emit('ticket_message', payload, room=f'ticket_{ticket.id}')

    # Send persistent in-app notification to ticket creator
    send_system_notification(
        recipient_id=ticket.user_id,
        notif_type='support_reply',
        title=f"Support message from {admin_name}",
        text=msg.message[:120],
        link=f"/support/ticket/{ticket.ticket_ref}",
        target_type='ticket',
        target_id=ticket.id,
        emit_socket=True
    )

    return redirect(url_for('admin.ticket_detail', ticket_ref=ticket.ticket_ref))


@admin_bp.route('/tickets/<int:ticket_id>/close', methods=['POST'])
@login_required
def close_ticket(ticket_id):
    """Admin closes ticket."""
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))

    from app.services.messaging import close_support_ticket_by_id
    ticket = close_support_ticket_by_id(ticket_id, current_user.id)
    if ticket:
        log_admin_activity('close_support_ticket', 'support_ticket', ticket.id, f'Closed ticket #{ticket.ticket_ref}')
        flash(f'Ticket #{ticket.ticket_ref} closed successfully.', 'info')

    return redirect(url_for('admin.support_tickets', tab='closed'))


@admin_bp.route('/support/reports')
@login_required
def support_reports():
    """Support Reports section for Admins and Super Admin with filters and ratings."""
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))

    from app.models.features import SupportTicket, SupportRating
    from app.models.user import User

    search_q = request.args.get('q', '').strip()
    rating_filter = request.args.get('rating', type=int)

    query = SupportTicket.query.filter(SupportTicket.status == 'closed')

    # Regular admins see their own tickets unless superadmin
    if not getattr(current_user, 'is_superadmin', False):
        query = query.filter((SupportTicket.assigned_admin_id == current_user.id) | (SupportTicket.closed_by_id == current_user.id))

    if search_q:
        query = query.join(User, SupportTicket.user_id == User.id).filter(
            (SupportTicket.ticket_ref.ilike(f'%{search_q}%')) |
            (SupportTicket.subject.ilike(f'%{search_q}%')) |
            (User.email.ilike(f'%{search_q}%'))
        )

    if rating_filter:
        query = query.filter(SupportTicket.rating == rating_filter)

    closed_tickets = query.order_by(SupportTicket.closed_at.desc()).all()

    # Compute overall platform metrics
    all_closed = SupportTicket.query.filter_by(status='closed').all()
    ratings_list = [t.rating for t in all_closed if t.rating is not None]
    avg_rating = round(sum(ratings_list) / len(ratings_list), 1) if ratings_list else 5.0
    pending_count = SupportTicket.query.filter_by(status='pending').count()
    active_count = SupportTicket.query.filter_by(status='active').count()

    return render_template(
        'admin/support_reports.html',
        tickets=closed_tickets,
        search_q=search_q,
        rating_filter=rating_filter,
        avg_rating=avg_rating,
        total_closed=len(all_closed),
        pending_count=pending_count,
        active_count=active_count,
        is_superadmin=getattr(current_user, 'is_superadmin', False)
    )


@admin_bp.route('/support/reports/<ticket_ref>')
@login_required
def support_report_detail(ticket_ref):
    """Detailed permanent support report for a closed ticket."""
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))

    from app.models.features import SupportTicket, TicketMessage
    ticket = SupportTicket.query.filter_by(ticket_ref=ticket_ref).first_or_404()
    messages = TicketMessage.query.filter_by(ticket_id=ticket.id).order_by(TicketMessage.created_at.asc()).all()

    # Calculate response metrics
    resolution_time = None
    if ticket.created_at and ticket.closed_at:
        diff = ticket.closed_at - ticket.created_at
        hours = int(diff.total_seconds() // 3600)
        minutes = int((diff.total_seconds() % 3600) // 60)
        resolution_time = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

    return render_template(
        'admin/support_report_detail.html',
        ticket=ticket,
        messages=messages,
        resolution_time=resolution_time,
        is_superadmin=getattr(current_user, 'is_superadmin', False)
    )


@admin_bp.route('/profile/display-name', methods=['POST'])
@login_required
def update_admin_display_name():
    """Allow admin to set/update their professional display name."""
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))

    name = request.form.get('display_name', '').strip()
    if not name:
        flash('Please provide a valid display name.', 'warning')
        return redirect(request.referrer or url_for('admin.settings'))

    current_user.display_name = name
    db.session.commit()
    log_admin_activity('update_display_name', 'user', current_user.id, f'Updated display name to {name}')
    flash(f"Display name updated to '{name}'. This name will be displayed in all support tickets.", 'success')
    return redirect(request.referrer or url_for('admin.settings'))
'''

if 'def support_tickets():' not in admin_code:
    admin_code += admin_ticket_routes

with open('app/routes/admin.py', 'w', encoding='utf-8') as f:
    f.write(admin_code)

print("Updated app/routes/admin.py with Support Tickets, Reports, and Admin Display Name")
