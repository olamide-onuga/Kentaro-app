from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.extensions import db, socketio
from app.models.community import CommunityMessage
from app.models.user import CoachProfile
import os, uuid
from werkzeug.utils import secure_filename

community_bp = Blueprint('community', __name__, url_prefix='/community')

def _allowed_access(coach_id):
    """Return True if current_user is the coach or a client of that coach."""
    if not current_user.is_authenticated:
        return False
    if getattr(current_user, 'is_coach', False) and current_user.coach_profile.id == coach_id:
        return True
    if getattr(current_user, 'is_client', False) and current_user.client_profile.coach_id == coach_id:
        return True
    return False

@community_bp.route('/coach/<int:coach_id>')
@login_required
def view(coach_id):
    if not _allowed_access(coach_id):
        flash('You are not a member of this community.', 'danger')
        return redirect(url_for('client.dashboard'))
    coach = CoachProfile.query.get_or_404(coach_id)
    messages = CommunityMessage.query.filter_by(coach_id=coach_id).order_by(CommunityMessage.created_at.asc()).all()
    return render_template('client/community.html', coach=coach, messages=messages)

@community_bp.route('/coach/<int:coach_id>/post', methods=['POST'])
@login_required
def post_message(coach_id):
    if not _allowed_access(coach_id):
        flash('You are not a member of this community.', 'danger')
        return redirect(url_for('client.dashboard'))
    content = request.form.get('content', '').strip()
    media_url = None
    if 'media' in request.files:
        file = request.files['media']
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext in ['.mp4', '.mov', '.webm', '.avi', '.mkv', '.jpg', '.jpeg', '.png', '.gif']:
                filename = f"community_{uuid.uuid4().hex[:10]}_{secure_filename(file.filename)}"
                upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'community')
                os.makedirs(upload_dir, exist_ok=True)
                file.save(os.path.join(upload_dir, filename))
                media_url = f"/static/uploads/community/{filename}"
    msg = CommunityMessage(
        coach_id=coach_id,
        sender_id=current_user.id,
        content=content or None,
        media_url=media_url,
    )
    db.session.add(msg)
    db.session.commit()
    # Emit to all participants via Socket.IO
    socketio.emit('community_message', {
        'id': msg.id,
        'coach_id': coach_id,
        'sender_name': current_user.full_name,
        'content': msg.content,
        'media_url': msg.media_url,
        'created_at': msg.created_at.isoformat(),
    }, room=f'coach_{coach_id}')
    return redirect(url_for('community.view', coach_id=coach_id))
