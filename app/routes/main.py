from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        if getattr(current_user, 'is_admin', False) or getattr(current_user, 'is_superadmin', False):
            return redirect(url_for('admin.dashboard'))
        elif getattr(current_user, 'is_coach', False):
            return redirect(url_for('coach.dashboard'))
        elif getattr(current_user, 'is_client', False):
            return redirect(url_for('client.dashboard'))
    return render_template('index.html')
    
@main_bp.route('/admin')
def admin_dashboard():
    return redirect(url_for('admin.dashboard'))

@main_bp.route('/coach')
def coach_dashboard():
    return redirect(url_for('coach.dashboard'))

@main_bp.route('/client')
def client_dashboard():
    return redirect(url_for('client.dashboard'))

@main_bp.route('/coaches')
def coaches_directory():
    from flask import flash, redirect, url_for
    if current_user.is_authenticated and getattr(current_user, 'is_client', False):
        profile = getattr(current_user, 'client_profile', None)
        if profile and profile.coach_id:
            flash('The Marketplace is reserved for athletes looking for a coach. You already have an active Calisthenics Coach!', 'info')
            return redirect(url_for('client.dashboard'))

    from app.models.user import CoachProfile
    # Only show coaches who have finished profile setup
    all_coaches = CoachProfile.query.all()
    coaches = [c for c in all_coaches if getattr(c, 'is_complete', False) and getattr(c, 'is_approved', True)]
    return render_template('public/coaches.html', coaches=coaches)

@main_bp.route('/coach/<int:coach_id>')
def public_coach_profile(coach_id):
    from app.models.user import CoachProfile
    from app.models.features import CoachReview
    coach = CoachProfile.query.get_or_404(coach_id)
    if not getattr(coach, 'is_complete', False):
        return render_template('public/coach_incomplete.html', coach=coach)
    reviews = CoachReview.query.filter_by(coach_id=coach.id, is_visible=True).order_by(CoachReview.created_at.desc()).all()
    avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else 0.0
    return render_template('public/coach_profile.html', coach=coach, reviews=reviews, avg_rating=avg_rating)

@main_bp.route('/join/<slug>')
def referral_join(slug):
    from app.models.features import ReferralLink
    from flask import session as flask_session
    ref = ReferralLink.query.filter_by(slug=slug).first()
    if ref:
        flask_session['referral_coach_id'] = ref.coach_id
        ref.referral_count += 1
        from app.extensions import db
        db.session.commit()
    return redirect(url_for('main.coaches_directory'))


@main_bp.route('/report', methods=['POST'])
def submit_report():
    from flask import request, flash
    from flask_login import login_required, current_user
    if not current_user.is_authenticated:
        flash('Please log in to submit a report.', 'warning')
        return redirect(url_for('auth.login'))
        
    report_type = request.form.get('report_type', 'bug').strip()
    target_coach_id = request.form.get('target_coach_id', type=int)
    title = request.form.get('title', 'System Report').strip()
    description = request.form.get('description', '').strip()
    
    if not description:
        flash('Please provide details for your report.', 'warning')
        return redirect(request.referrer or url_for('main.index'))
        
    from app.extensions import db
    from app.models.features import SystemReport
    report = SystemReport(
        reporter_id=current_user.id,
        report_type=report_type,
        target_coach_id=target_coach_id if report_type == 'coach' else None,
        title=title,
        description=description
    )
    db.session.add(report)
    db.session.commit()
    
    flash('Thank you! Your report has been submitted to the admin team.', 'success')
    return redirect(request.referrer or url_for('main.index'))


@main_bp.route('/squad/upload-voice', methods=['POST'])
def squad_upload_voice():
    from flask import request, jsonify, current_app
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    if 'voice' not in request.files or request.files['voice'].filename == '':
        return jsonify({'success': False, 'error': 'No voice file provided'}), 400
    file = request.files['voice']
    community_id = request.form.get('community_id', type=int)
    reply_to_id = request.form.get('reply_to_id', type=int)
    if not community_id:
        return jsonify({'success': False, 'error': 'Missing community_id'}), 400

    from app.models.features import Community, CommunityMember, CommunityMessage as CM
    comm = Community.query.get(community_id)
    if not comm:
        return jsonify({'success': False, 'error': 'Community not found'}), 404

    membership = CommunityMember.query.filter_by(community_id=community_id, user_id=current_user.id).first()
    if not membership:
        return jsonify({'success': False, 'error': 'Not a member of this community'}), 403

    from werkzeug.utils import secure_filename
    import uuid, os
    ext = os.path.splitext(file.filename)[1].lower() or '.webm'
    filename = f"squad_voice_{current_user.id}_{uuid.uuid4().hex[:8]}{ext}"
    voice_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'voice')
    os.makedirs(voice_dir, exist_ok=True)
    file_path = os.path.join(voice_dir, filename)
    file.save(file_path)
    voice_url = f"/static/uploads/voice/{filename}"

    msg = CM(
        community_id=community_id,
        sender_id=current_user.id,
        content='🎤 Voice Message',
        voice_url=voice_url,
        reply_to_id=reply_to_id
    )
    from app.extensions import db
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

    sender_profile = getattr(current_user, 'client_profile', None) or getattr(current_user, 'coach_profile', None)
    sender_name = getattr(sender_profile, 'first_name', None) or current_user.email.split('@')[0]
    coach_profile = getattr(current_user, 'coach_profile', None)

    from app import socketio
    payload = {
        'id': msg.id,
        'content': msg.content,
        'voice_url': voice_url,
        'sender_id': current_user.id,
        'sender_name': sender_name,
        'is_coach': comm.coach_id == (coach_profile.id if coach_profile else -1),
        'timestamp': msg.created_at.strftime('%b %d, %H:%M'),
        'reply_preview': reply_preview
    }
    socketio.emit('squad_message', payload, room=f'community_{community_id}')
    return jsonify({'success': True, 'msg': payload})
