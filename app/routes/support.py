import os
import uuid
import datetime as dt
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models.user import User
from app.models.features import SupportTicket, TicketMessage, SupportRating
from app.services.messaging import (
    create_support_ticket,
    rate_support_ticket,
    send_system_notification
)
from app import socketio

support_bp = Blueprint('support', __name__, url_prefix='/support')


def _save_attachment(file_obj):
    if not file_obj or not file_obj.filename:
        return None
    allowed = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'webp'}
    ext = file_obj.filename.rsplit('.', 1)[-1].lower() if '.' in file_obj.filename else ''
    if ext not in allowed:
        return None
    filename = f"ticket_att_{uuid.uuid4().hex[:10]}_{secure_filename(file_obj.filename)}"
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'tickets')
    os.makedirs(upload_folder, exist_ok=True)
    full_path = os.path.join(upload_folder, filename)
    file_obj.save(full_path)
    return f"/static/uploads/tickets/{filename}"


@support_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_ticket():
    if request.method == 'POST':
        form_data = request.form or (request.get_json(silent=True) or {})
        subject = form_data.get('subject', '').strip() or 'Platform Support Request'
        category = form_data.get('category', 'general').strip()
        description = (form_data.get('description', '') or form_data.get('message', '') or form_data.get('body', '') or form_data.get('msg', '')).strip()
        attachment = request.files.get('attachment')

        if not description:
            flash('Please describe your issue or question.', 'warning')
            return redirect(request.referrer or url_for('support.history'))

        attachment_url = _save_attachment(attachment) if attachment else None

        ticket = create_support_ticket(
            user_id=current_user.id,
            subject=subject,
            category=category,
            description=description,
            attachment_url=attachment_url
        )

        flash(f'Support ticket #{ticket.ticket_ref} created. An administrator will review your ticket shortly.', 'success')
        return redirect(url_for('support.view_ticket', ticket_ref=ticket.ticket_ref))

    return redirect(url_for('support.history'))


@support_bp.route('/ticket/<ticket_ref>')
@login_required
def view_ticket(ticket_ref):
    ticket = SupportTicket.query.filter_by(ticket_ref=ticket_ref).first_or_404()

    # Permission check: owner or authorized admin
    is_admin = bool(getattr(current_user, 'is_admin', False) or 
                    (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']))

    if ticket.user_id != current_user.id and not is_admin:
        flash('You are not authorized to view this support ticket.', 'danger')
        return redirect(url_for('main.index'))

    messages = TicketMessage.query.filter_by(ticket_id=ticket.id).order_by(TicketMessage.created_at.asc()).all()

    assigned_admin_name = "Support Administrator"
    if ticket.assigned_admin:
        assigned_admin_name = getattr(ticket.assigned_admin, 'admin_display_name', 'Support Administrator')

    return render_template(
        'support/ticket.html',
        ticket=ticket,
        messages=messages,
        assigned_admin_name=assigned_admin_name,
        is_admin=is_admin
    )


@support_bp.route('/ticket/<ticket_ref>/reply', methods=['POST'])
@login_required
def reply_ticket(ticket_ref):
    ticket = SupportTicket.query.filter_by(ticket_ref=ticket_ref).first_or_404()

    is_admin = bool(getattr(current_user, 'is_admin', False) or 
                    (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']))

    if ticket.user_id != current_user.id and not is_admin:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('main.index'))

    if ticket.status == 'closed':
        flash('This support ticket has been closed and cannot receive new messages.', 'warning')
        return redirect(url_for('support.view_ticket', ticket_ref=ticket.ticket_ref))

    if ticket.status == 'pending' and not is_admin:
        flash('Please wait while an administrator reviews and accepts your ticket.', 'info')
        return redirect(url_for('support.view_ticket', ticket_ref=ticket.ticket_ref))

    msg_text = request.form.get('message', '').strip()
    attachment = request.files.get('attachment')
    attachment_url = _save_attachment(attachment) if attachment else None

    if not msg_text and not attachment_url:
        flash('Please enter a message or attach a file.', 'warning')
        return redirect(url_for('support.view_ticket', ticket_ref=ticket.ticket_ref))

    msg = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        message=msg_text or '[Attachment]',
        attachment_url=attachment_url,
        is_system=False,
        created_at=dt.datetime.utcnow()
    )
    db.session.add(msg)
    ticket.updated_at = dt.datetime.utcnow()
    db.session.commit()

    # Determine sender display name
    if is_admin:
        sender_name = getattr(current_user, 'admin_display_name', 'Support Administrator')
    elif current_user.is_coach and current_user.coach_profile:
        sender_name = f"Coach {current_user.coach_profile.first_name}"
    elif current_user.is_client and current_user.client_profile:
        sender_name = current_user.client_profile.full_name
    else:
        sender_name = current_user.email.split('@')[0]

    # Socket broadcast to ticket room
    payload = {
        'id': msg.id,
        'ticket_id': ticket.id,
        'ticket_ref': ticket.ticket_ref,
        'sender_id': current_user.id,
        'sender_name': sender_name,
        'is_admin': is_admin,
        'is_system': False,
        'message': msg.message,
        'attachment_url': msg.attachment_url,
        'timestamp': msg.created_at.strftime('%H:%M'),
        'date': msg.created_at.strftime('%b %d, %Y')
    }
    socketio.emit('ticket_message', payload, room=f'ticket_{ticket.id}')

    # Send notification to the other party
    if is_admin:
        # Notify the user
        send_system_notification(
            recipient_id=ticket.user_id,
            notif_type='support_reply',
            title=f"Support response from {sender_name}",
            text=msg.message[:120],
            link=f"/support/ticket/{ticket.ticket_ref}",
            target_type='ticket',
            target_id=ticket.id,
            emit_socket=True
        )
    else:
        # Notify the assigned admin or admin desk
        target_admin_id = ticket.assigned_admin_id
        if target_admin_id:
            send_system_notification(
                recipient_id=target_admin_id,
                notif_type='support_reply',
                title=f"User reply in ticket #{ticket.ticket_ref}",
                text=msg.message[:120],
                link=f"/admin/tickets/{ticket.ticket_ref}",
                target_type='ticket',
                target_id=ticket.id,
                emit_socket=True
            )
        socketio.emit('admin_ticket_activity', {
            'ticket_id': ticket.id,
            'ticket_ref': ticket.ticket_ref,
            'text': f"New reply in #{ticket.ticket_ref} from {sender_name}"
        }, room='admin_support')

    return redirect(url_for('support.view_ticket', ticket_ref=ticket.ticket_ref))


@support_bp.route('/ticket/<ticket_ref>/rate', methods=['POST'])
@login_required
def rate_ticket(ticket_ref):
    ticket = SupportTicket.query.filter_by(ticket_ref=ticket_ref).first_or_404()

    if ticket.user_id != current_user.id:
        flash('Unauthorized rating attempt.', 'danger')
        return redirect(url_for('main.index'))

    if ticket.status != 'closed':
        flash('You can only rate a closed support ticket.', 'warning')
        return redirect(url_for('support.view_ticket', ticket_ref=ticket.ticket_ref))

    if ticket.rating is not None:
        flash('You have already submitted feedback for this support ticket.', 'info')
        return redirect(url_for('support.view_ticket', ticket_ref=ticket.ticket_ref))

    rating_val = request.form.get('rating', type=int) or 5
    feedback = request.form.get('feedback', '').strip()

    success = rate_support_ticket(ticket.id, current_user.id, rating_val, feedback)
    if success:
        flash('Thank you for rating your support experience! Your feedback helps us improve.', 'success')
    else:
        flash('Failed to submit rating. Please try again.', 'danger')

    return redirect(url_for('support.view_ticket', ticket_ref=ticket.ticket_ref))


@support_bp.route('/history')
@login_required
def history():
    user_tickets = SupportTicket.query.filter_by(user_id=current_user.id).order_by(SupportTicket.created_at.desc()).all()
    return render_template('support/history.html', tickets=user_tickets)
