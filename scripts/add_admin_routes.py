"""Append admin anonymous DM and email compose routes to admin.py"""

ADMIN_ROUTES = '''

# ─────────────────────────────────────────────────────────────────────────────
# ADMIN: SEND ANONYMOUS DM
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/messages/send-anonymous', methods=['GET', 'POST'])
@login_required
def send_anonymous_dm():
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('admin.dashboard'))
    users = User.query.filter(User.is_admin == False).order_by(User.email).all()
    sent = False
    if request.method == 'POST':
        target_id = request.form.get('target_user_id', type=int)
        message = request.form.get('message', '').strip()
        if target_id and message:
            from app.models.user import ChatMessage
            from app import socketio
            msg = ChatMessage(
                sender_id=current_user.id,
                receiver_id=target_id,
                message=message,
                is_anonymous=True
            )
            db.session.add(msg)
            db.session.commit()
            socketio.emit('chat_message', {
                'id': msg.id,
                'from': current_user.id,
                'sender_id': current_user.id,
                'receiver_id': target_id,
                'msg': message,
                'message': message,
                'from_name': 'Kentaro Support\\U0001f6e1\\ufe0f',
                'is_anonymous': True,
                'timestamp': msg.timestamp.strftime('%H:%M') if msg.timestamp else ''
            }, room=f'user_{target_id}')
            flash('Anonymous message sent.', 'success')
            sent = True
    return render_template('admin/send_dm.html', users=users, sent=sent)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN: COMPOSE & SEND EMAIL
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/email/compose', methods=['GET', 'POST'])
@login_required
def compose_email():
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('admin.dashboard'))
    users = User.query.order_by(User.email).all()
    if request.method == 'POST':
        to_email = request.form.get('to_email', '').strip()
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()
        if to_email and subject and body:
            from app.services.email import send_email
            html = (
                '<div style="font-family:sans-serif;max-width:600px;margin:auto">'
                '<p>' + body.replace('\\n', '<br>') + '</p>'
                '<hr/><p style="color:#888;font-size:12px">Kentaro Coaching Platform</p>'
                '</div>'
            )
            ok = send_email(to_email, subject, html=html)
            flash('Email sent successfully.' if ok else 'Email failed to send.', 'success' if ok else 'danger')
    return render_template('admin/compose_email.html', users=users)
'''

with open('app/routes/admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'send_anonymous_dm' not in content:
    with open('app/routes/admin.py', 'a', encoding='utf-8') as f:
        f.write(ADMIN_ROUTES)
    print("Admin routes appended successfully.")
else:
    print("Admin routes already present — skipping.")
