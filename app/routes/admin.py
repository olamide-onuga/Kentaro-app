import datetime as dt
import os, uuid
from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, jsonify
import os
from datetime import datetime, timedelta, date
from flask_login import login_required, current_user, login_user, logout_user
from sqlalchemy import or_, and_, func

from app.extensions import db
from app.models.user import User, CoachProfile, ClientProfile, Role, AccountAppeal, ChatMessage
from app.models.coaching import CoachingPackage, ClientContract, CoachDiscount
from app.models.features import SystemSetting, SystemReport, AdminActivityLog, CheckIn, CoachReview
from app.models.subscription import SubscriptionPlan, CoachSubscription, FEATURE_LABELS
from app.models.calendar import Appointment
from app.models.workout import Program, Workout
from app.models.progress import WorkoutCompletion, BodyweightLog

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.context_processor
def inject_admin_stats():
    try:
        pending_reports = SystemReport.query.filter_by(status='pending').count()
        pending_coaches = CoachProfile.query.filter_by(is_approved=False).count()
    except Exception:
        pending_reports = 0
        pending_coaches = 0
    try:
        from app.models.features import SupportTicket
        pending_tickets = SupportTicket.query.filter_by(status='pending').count()
    except Exception:
        pending_tickets = 0
    return dict(
        admin_pending_reports=pending_reports,
        admin_pending_coaches=pending_coaches,
        admin_pending_tickets=pending_tickets
    )

def log_admin_activity(action, target_type=None, target_id=None, detail=None):
    """Helper to record an action in the AdminActivityLog."""
    try:
        admin_id = current_user.id if (current_user and current_user.is_authenticated) else None
        if not admin_id:
            admin_u = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).first()
            admin_id = admin_u.id if admin_u else 1

        log = AdminActivityLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to log admin activity: {e}")

@admin_bp.before_request
def check_admin_access():
    if request.endpoint == 'admin.login':
        return None
    if not current_user.is_authenticated:
        flash('Please log in to access the admin area.', 'warning')
        return redirect(url_for('admin.login'))
    is_adm = bool(getattr(current_user, 'is_admin', False) or (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']))
    if not is_adm:
        flash('Admin access required.', 'danger')
        return redirect(url_for('main.index'))

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    def _is_admin(u):
        return bool(
            getattr(u, 'is_admin', False) or 
            getattr(u, 'is_superadmin', False) or 
            (getattr(u, 'role', None) and getattr(u.role, 'name', None) in ['admin', 'superadmin'])
        )

    if current_user.is_authenticated and _is_admin(current_user):
        return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user and user.verify_password(password) and _is_admin(user):
            if not user.is_admin:
                user.is_admin = True
                db.session.commit()
            login_user(user)
            log_admin_activity('admin_login', 'user', user.id, f'Admin logged in: {user.email}')
            flash('Admin logged in successfully.', 'success')
            return redirect(url_for('admin.dashboard'))
        flash('Invalid credentials or not an admin.', 'danger')
        return redirect(url_for('admin.login'))
    return render_template('admin/login.html')

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    users_count = User.query.count()
    coaches_count = CoachProfile.query.count()
    clients_count = ClientProfile.query.count()
    pending_coaches = CoachProfile.query.filter_by(is_approved=False).count()
    packages_count = CoachingPackage.query.count()
    contracts_count = ClientContract.query.count()
    active_contracts = ClientContract.query.filter_by(status='active').count()
    active_subscriptions = CoachSubscription.query.filter_by(status='active').count()
    
    video_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos')
    videos_count = 0
    if os.path.isdir(video_dir):
        videos_count = len([f for f in os.listdir(video_dir) if f.lower().endswith(('.mp4', '.webm', '.ogg'))])
        
    reports_count = SystemReport.query.filter_by(status='pending').count()

    # Registration trend chart (last 30 days)
    today = datetime.utcnow().date()
    start_date = datetime.utcnow() - timedelta(days=30)
    trend_labels = [(today - timedelta(days=i)).strftime('%b %d') for i in reversed(range(30))]
    
    users_trend = [0] * 30
    coaches_trend = [0] * 30
    clients_trend = [0] * 30
    
    recent_users = User.query.filter(User.created_at >= start_date).all()
    recent_coaches = CoachProfile.query.filter(CoachProfile.created_at >= start_date).all()
    recent_clients = ClientProfile.query.filter(ClientProfile.created_at >= start_date).all()
    
    for u in recent_users:
        if u.created_at:
            days_ago = (today - u.created_at.date()).days
            if 0 <= days_ago < 30:
                users_trend[29 - days_ago] += 1
                
    for c in recent_coaches:
        if c.created_at:
            days_ago = (today - c.created_at.date()).days
            if 0 <= days_ago < 30:
                coaches_trend[29 - days_ago] += 1
                
    for cl in recent_clients:
        if cl.created_at:
            days_ago = (today - cl.created_at.date()).days
            if 0 <= days_ago < 30:
                clients_trend[29 - days_ago] += 1

    # Recent activity feed (last 10 actions)
    recent_activities = AdminActivityLog.query.order_by(AdminActivityLog.created_at.desc()).limit(10).all()

    return render_template('admin/dashboard.html',
                           users_count=users_count,
                           coaches_count=coaches_count,
                           clients_count=clients_count,
                           pending_coaches=pending_coaches,
                           packages_count=packages_count,
                           contracts_count=contracts_count,
                           active_contracts=active_contracts,
                           active_subscriptions=active_subscriptions,
                           videos_count=videos_count,
                           reports_count=reports_count,
                           trend_labels=trend_labels,
                           users_trend=users_trend,
                           coaches_trend=coaches_trend,
                           clients_trend=clients_trend,
                           recent_activities=recent_activities)

# --- USER MANAGEMENT ---
@admin_bp.route('/users')
@login_required
def users():
    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role', '').strip()
    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    
    query = User.query
    if search:
        query = query.outerjoin(CoachProfile, User.id == CoachProfile.user_id)\
                     .outerjoin(ClientProfile, User.id == ClientProfile.user_id)\
                     .filter(
                         or_(
                             User.email.ilike(f'%{search}%'),
                             CoachProfile.first_name.ilike(f'%{search}%'),
                             CoachProfile.last_name.ilike(f'%{search}%'),
                             ClientProfile.first_name.ilike(f'%{search}%'),
                             ClientProfile.last_name.ilike(f'%{search}%')
                         )
                     )
    if role_filter:
        query = query.join(Role).filter(Role.name == role_filter)
    if status_filter == 'active':
        query = query.filter(User.is_active == True)
    elif status_filter == 'deactivated':
        query = query.filter(User.is_active == False)
        
    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    roles = Role.query.all()
    return render_template('admin/users.html',
                           pagination=pagination,
                           users=pagination.items,
                           roles=roles,
                           search=search,
                           role_filter=role_filter,
                           status_filter=status_filter)

@admin_bp.route('/users/<int:user_id>')
@login_required
def user_detail(user_id):
    user = User.query.get_or_404(user_id)
    roles = Role.query.all()
    coach = user.coach_profile
    client = user.client_profile
    activities = AdminActivityLog.query.filter_by(target_type='user', target_id=user.id).order_by(AdminActivityLog.created_at.desc()).all()
    return render_template('admin/user_detail.html',
                           user=user,
                           roles=roles,
                           coach=coach,
                           client=client,
                           activities=activities)

@admin_bp.route('/users/<int:user_id>/activate', methods=['POST'])
@login_required
def activate_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = True
    db.session.commit()
    log_admin_activity('activate_user', 'user', user.id, f'Activated user account: {user.email}')
    flash(f'User {user.email} has been activated.', 'success')
    return redirect(request.referrer or url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/deactivate', methods=['POST'])
@login_required
def deactivate_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot deactivate your own admin account.', 'warning')
        return redirect(url_for('admin.users'))
    user.is_active = False
    db.session.commit()
    log_admin_activity('deactivate_user', 'user', user.id, f'Deactivated user account: {user.email}')
    flash(f'User {user.email} has been deactivated.', 'warning')
    return redirect(request.referrer or url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/change-role', methods=['POST'])
@login_required
def change_user_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role_name = request.form.get('role', '').strip().lower()
    if not new_role_name:
        flash('Role name cannot be empty.', 'danger')
        return redirect(request.referrer or url_for('admin.users'))

    is_current_superadmin = bool(
        getattr(current_user, 'is_superadmin', False) or 
        (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) == 'superadmin')
    )

    if new_role_name == 'superadmin' and not is_current_superadmin:
        flash('Only a Super Admin can promote a user to Super Admin.', 'danger')
        return redirect(request.referrer or url_for('admin.users'))

    if getattr(user, 'is_superadmin', False) and not is_current_superadmin:
        flash('Only a Super Admin can change the role of another Super Admin.', 'danger')
        return redirect(request.referrer or url_for('admin.users'))

    if getattr(user, 'is_superadmin', False) and new_role_name != 'superadmin':
        superadmin_count = User.query.join(Role).filter(Role.name == 'superadmin', User.is_active == True).count()
        if superadmin_count <= 1:
            flash('Cannot demote or remove the last active Super Admin on the platform.', 'danger')
            return redirect(request.referrer or url_for('admin.users'))

    if user.id == current_user.id and new_role_name not in ['admin', 'superadmin']:
        flash('You cannot revoke your own admin role.', 'warning')
        return redirect(request.referrer or url_for('admin.users'))
        
    role_obj = Role.query.filter_by(name=new_role_name).first()
    if not role_obj:
        role_obj = Role(name=new_role_name)
        db.session.add(role_obj)
        db.session.commit()
        
    old_role = user.role.name if user.role else 'none'
    user.role = role_obj
    user.is_admin = bool(new_role_name in ['admin', 'superadmin'])
    db.session.commit()
    
    log_admin_activity('change_role', 'user', user.id, f'Changed role from {old_role} to {new_role_name} for {user.email}')
    flash(f'Role for {user.email} updated to {new_role_name}.', 'success')
    return redirect(request.referrer or url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot deactivate your own admin account.', 'warning')
        return redirect(url_for('admin.users'))
    if getattr(user, 'is_superadmin', False) and user.is_active:
        is_current_superadmin = bool(
            getattr(current_user, 'is_superadmin', False) or 
            (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) == 'superadmin')
        )
        if not is_current_superadmin:
            flash('Only a Super Admin can deactivate a Super Admin account.', 'danger')
            return redirect(request.referrer or url_for('admin.users'))
        superadmin_count = User.query.join(Role).filter(Role.name == 'superadmin', User.is_active == True).count()
        if superadmin_count <= 1:
            flash('Cannot deactivate the last active Super Admin on the platform.', 'danger')
            return redirect(request.referrer or url_for('admin.users'))
    user.is_active = not user.is_active
    db.session.commit()
    status_str = 'activated' if user.is_active else 'deactivated'
    log_admin_activity(f'{status_str}_user', 'user', user.id, f'{status_str.capitalize()} account for {user.email}')
    flash(f'User {user.email} has been {status_str}.', 'success')
    return redirect(request.referrer or url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/verify-email', methods=['POST'])
@login_required
def verify_user_email(user_id):
    user = User.query.get_or_404(user_id)
    user.is_email_confirmed = True
    db.session.commit()
    log_admin_activity('verify_email', 'user', user.id, f'Directly verified email for {user.email}')
    flash(f'Email for {user.email} has been verified successfully. User can now log in without email restrictions.', 'success')
    return redirect(request.referrer or url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/toggle-email-verified', methods=['POST'])
@login_required
def toggle_user_email_verified(user_id):
    user = User.query.get_or_404(user_id)
    user.is_email_confirmed = not user.is_email_confirmed
    db.session.commit()
    status_txt = 'verified' if user.is_email_confirmed else 'unverified'
    log_admin_activity(f'set_email_{status_txt}', 'user', user.id, f'Set email status to {status_txt} for {user.email}')
    flash(f'Email for {user.email} marked as {status_txt}.', 'success')
    return redirect(request.referrer or url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/send-password-reset', methods=['POST'])
@login_required
def send_user_password_reset(user_id):
    user = User.query.get_or_404(user_id)
    from app.utils.token import generate_confirmation_token
    from app.routes.auth import _send_email
    token = generate_confirmation_token(user.email)
    reset_url = url_for('auth.reset_password', token=token, _external=True)
    sent = _send_email(user.email, 'Password Reset Request', 'auth/email_reset.html', reset_url=reset_url, user=user)
    log_admin_activity('send_password_reset', 'user', user.id, f'Triggered password reset email for {user.email}')
    if sent:
        flash(f'Password reset link successfully sent to {user.email}.', 'success')
    else:
        flash(f'Automated email delivery failed (check mail server config). You can share this direct reset link with the user: {reset_url}', 'warning')
    return redirect(request.referrer or url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)
    new_pass = request.form.get('new_password', 'Reset123!').strip()
    user.password = new_pass
    db.session.commit()
    log_admin_activity('reset_password', 'user', user.id, f'Reset password for {user.email}')
    flash(f'Password for {user.email} reset to: {new_pass}', 'success')
    return redirect(request.referrer or url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    # Only Super Admin can delete user accounts
    is_super = getattr(current_user, 'is_superadmin', False) or (getattr(current_user, 'role', None) and current_user.role.name == 'superadmin')
    if not is_super:
        flash('Access denied: Only Super Administrators have authority to delete user accounts.', 'danger')
        abort(403)
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id or getattr(user, 'is_primary_superadmin', False):
        flash('Cannot delete this Super Admin account.', 'warning')
        return redirect(url_for('admin.users'))
    email = user.email
    db.session.delete(user)
    db.session.commit()
    log_admin_activity('delete_user', 'user', user_id, f'Deleted user account {email}')
    flash(f'User {email} deleted permanently.', 'info')
    return redirect(url_for('admin.users'))

# --- COACH VERIFICATION & APPROVAL ---
@admin_bp.route('/coaches')
@login_required
def coaches():
    status_filter = request.args.get('status', 'all').strip()
    search = request.args.get('search', '').strip()
    
    query = CoachProfile.query.outerjoin(User, CoachProfile.user_id == User.id)
    if status_filter == 'pending':
        query = query.filter(CoachProfile.is_approved == False)
    elif status_filter == 'approved':
        query = query.filter(CoachProfile.is_approved == True)
    elif status_filter == 'rejected':
        query = query.filter(CoachProfile.is_approved == False)
        
    if search:
        query = query.filter(
            or_(
                CoachProfile.first_name.ilike(f'%{search}%'),
                CoachProfile.last_name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                CoachProfile.specialization.ilike(f'%{search}%')
            )
        )
        
    coaches_list = query.order_by(CoachProfile.created_at.desc()).all()
    pending_count = CoachProfile.query.filter_by(is_approved=False).count()
    approved_count = CoachProfile.query.filter_by(is_approved=True).count()
    return render_template('admin/coaches.html',
                           coaches=coaches_list,
                           status_filter=status_filter,
                           search=search,
                           pending_count=pending_count,
                           approved_count=approved_count)

@admin_bp.route('/coaches/<int:coach_id>')
@login_required
def coach_detail(coach_id):
    coach = CoachProfile.query.get_or_404(coach_id)
    clients = coach.clients.all()
    packages = coach.packages.all()
    programs = coach.programs.all()
    contracts = ClientContract.query.filter_by(coach_id=coach.id).order_by(ClientContract.created_at.desc()).all()
    subscription = CoachSubscription.query.filter_by(coach_id=coach.id).first()
    all_plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.display_order).all()
    appointments = Appointment.query.filter_by(coach_id=coach.id).order_by(Appointment.date.desc()).limit(15).all()
    reviews = coach.reviews.order_by(CoachReview.created_at.desc()).all()
    
    return render_template('admin/coach_detail.html',
                           coach=coach,
                           clients=clients,
                           packages=packages,
                           programs=programs,
                           contracts=contracts,
                           subscription=subscription,
                           all_plans=all_plans,
                           appointments=appointments,
                           reviews=reviews)

@admin_bp.route('/coaches/<int:coach_id>/approve', methods=['POST'])
@login_required
def approve_coach(coach_id):
    coach = CoachProfile.query.get_or_404(coach_id)
    coach.is_approved = True
    db.session.commit()
    log_admin_activity('approve_coach', 'coach', coach.id, f'Approved coach {coach.first_name} {coach.last_name}')
    flash(f'Coach {coach.first_name} {coach.last_name} approved successfully.', 'success')
    return redirect(request.referrer or url_for('admin.coaches'))

@admin_bp.route('/coaches/<int:coach_id>/reject', methods=['POST'])
@login_required
def reject_coach(coach_id):
    coach = CoachProfile.query.get_or_404(coach_id)
    coach.is_approved = False
    db.session.commit()
    log_admin_activity('reject_coach', 'coach', coach.id, f'Rejected coach {coach.first_name} {coach.last_name}')
    flash(f'Coach {coach.first_name} {coach.last_name} has been set to unapproved/rejected.', 'warning')
    return redirect(request.referrer or url_for('admin.coaches'))

@admin_bp.route('/coaches/<int:coach_id>/toggle-verification', methods=['POST'])
@login_required
def toggle_coach_verification(coach_id):
    coach = CoachProfile.query.get_or_404(coach_id)
    coach.is_verified = not coach.is_verified
    db.session.commit()
    status_str = 'verified' if coach.is_verified else 'unverified'
    log_admin_activity(f'{status_str}_coach', 'coach', coach.id, f'Set coach {coach.first_name} {coach.last_name} as {status_str}')
    flash(f'Coach {coach.first_name} is now marked as {status_str}.', 'success')
    return redirect(request.referrer or url_for('admin.coaches'))

@admin_bp.route('/coaches/<int:coach_id>/toggle-approval', methods=['POST'])
@login_required
def toggle_coach_approval(coach_id):
    coach = CoachProfile.query.get_or_404(coach_id)
    coach.is_approved = not coach.is_approved
    db.session.commit()
    status_str = 'approved' if coach.is_approved else 'unapproved'
    log_admin_activity(f'{status_str}_coach', 'coach', coach.id, f'Set coach {coach.first_name} {coach.last_name} as {status_str}')
    flash(f'Coach {coach.first_name} is now {status_str}.', 'success')
    return redirect(request.referrer or url_for('admin.coaches'))

# --- ATHLETES / CLIENTS MANAGEMENT ---
@admin_bp.route('/clients')
@login_required
def clients():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    coach_id = request.args.get('coach_id', type=int)
    
    query = ClientProfile.query.outerjoin(User, ClientProfile.user_id == User.id)
    if search:
        query = query.filter(
            or_(
                ClientProfile.first_name.ilike(f'%{search}%'),
                ClientProfile.last_name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )
    if coach_id is not None:
        if coach_id == -1:
            query = query.filter(ClientProfile.coach_id == None)
        else:
            query = query.filter(ClientProfile.coach_id == coach_id)
            
    pagination = query.order_by(ClientProfile.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    coaches = CoachProfile.query.order_by(CoachProfile.first_name).all()
    total_clients = ClientProfile.query.count()
    unassigned_clients = ClientProfile.query.filter(ClientProfile.coach_id == None).count()
    
    return render_template('admin/clients.html',
                           pagination=pagination,
                           clients=pagination.items,
                           coaches=coaches,
                           search=search,
                           coach_id=coach_id,
                           total_clients=total_clients,
                           unassigned_clients=unassigned_clients)

@admin_bp.route('/clients/<int:client_id>')
@login_required
def client_detail(client_id):
    client = ClientProfile.query.get_or_404(client_id)
    contracts = client.contracts.order_by(ClientContract.created_at.desc()).all()
    check_ins = client.check_ins.order_by(CheckIn.created_at.desc()).limit(15).all()
    workout_completions = WorkoutCompletion.query.filter_by(client_id=client.id).order_by(WorkoutCompletion.completed_at.desc()).limit(15).all()
    bodyweight_logs = BodyweightLog.query.filter_by(client_id=client.id).order_by(BodyweightLog.date.desc()).limit(15).all()
    appointments = Appointment.query.filter_by(client_id=client.id).order_by(Appointment.date.desc()).all()
    all_coaches = CoachProfile.query.filter_by(is_approved=True).order_by(CoachProfile.first_name).all()
    
    return render_template('admin/client_detail.html',
                           client=client,
                           contracts=contracts,
                           check_ins=check_ins,
                           workout_completions=workout_completions,
                           bodyweight_logs=bodyweight_logs,
                           appointments=appointments,
                           all_coaches=all_coaches)

@admin_bp.route('/clients/<int:client_id>/unlink-coach', methods=['POST'])
@login_required
def unlink_client_coach(client_id):
    client = ClientProfile.query.get_or_404(client_id)
    old_coach = client.coach
    coach_name = f"{old_coach.first_name} {old_coach.last_name}" if old_coach else 'assigned coach'
    client.coach_id = None
    db.session.commit()
    log_admin_activity('unlink_coach', 'client', client.id, f'Unlinked coach {coach_name} from athlete {client.full_name}')
    flash(f'Athlete {client.full_name} unlinked from coach.', 'info')
    return redirect(request.referrer or url_for('admin.clients'))

@admin_bp.route('/clients/<int:client_id>/assign-coach', methods=['POST'])
@login_required
def assign_client_coach(client_id):
    client = ClientProfile.query.get_or_404(client_id)
    new_coach_id = request.form.get('coach_id', type=int)
    coach = CoachProfile.query.get_or_404(new_coach_id)
    client.coach_id = coach.id
    db.session.commit()
    log_admin_activity('assign_coach', 'client', client.id, f'Assigned coach {coach.first_name} {coach.last_name} to athlete {client.full_name}')
    flash(f'Athlete {client.full_name} assigned to Coach {coach.first_name} {coach.last_name}.', 'success')
    return redirect(request.referrer or url_for('admin.clients'))

# --- CONTRACTS MANAGEMENT ---
@admin_bp.route('/contracts')
@login_required
def contracts():
    status_filter = request.args.get('status', '')
    query = ClientContract.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    contracts_list = query.order_by(ClientContract.created_at.desc()).all()
    return render_template('admin/contracts.html', contracts=contracts_list, status_filter=status_filter)

@admin_bp.route('/contracts/<int:contract_id>/extend', methods=['POST'])
@login_required
def extend_contract(contract_id):
    contract = ClientContract.query.get_or_404(contract_id)
    days = request.form.get('days', 30, type=int)
    new_status = request.form.get('status', 'active').strip()
    
    start_base = contract.end_date if (contract.end_date and contract.end_date > datetime.utcnow()) else datetime.utcnow()
    contract.end_date = start_base + timedelta(days=days)
    contract.status = new_status
    db.session.commit()
    log_admin_activity('extend_contract', 'contract', contract.id, f'Extended contract #{contract.id} by {days} days')
    flash(f'Contract #{contract.id} extended by {days} days. New end date: {contract.end_date.strftime("%b %d, %Y")}', 'success')
    return redirect(url_for('admin.contracts'))

# --- SYSTEM SETTINGS & ANNOUNCEMENT ---
def get_setting(key, default=''):
    s = SystemSetting.query.filter_by(key=key).first()
    return s.value if s and s.value is not None else default

def set_setting(key, value):
    s = SystemSetting.query.filter_by(key=key).first()
    if not s:
        s = SystemSetting(key=key, value=str(value) if value is not None else '')
        db.session.add(s)
    else:
        s.value = str(value) if value is not None else ''

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    from werkzeug.utils import secure_filename

    is_superadmin = bool(
        getattr(current_user, 'is_superadmin', False) or 
        (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) == 'superadmin')
    )
    
    announcement = SystemSetting.query.filter_by(key='announcement_banner').first()
    announcement_active = SystemSetting.query.filter_by(key='announcement_banner_active').first()
    
    if request.method == 'POST':
        section = request.form.get('section', 'announcement')

        if section == 'announcement':
            banner_text = request.form.get('announcement_text', '').strip()
            is_active = '1' if request.form.get('announcement_active') else '0'
            set_setting('announcement_banner', banner_text)
            set_setting('announcement_banner_active', is_active)
            db.session.commit()
            log_admin_activity('update_settings', 'system_setting', None, 'Updated system announcement banner settings')
            flash('Announcement settings updated!', 'success')

        elif section == 'branding':
            if not is_superadmin:
                flash('Super Admin authorization required to modify platform branding.', 'danger')
                return redirect(url_for('admin.settings'))

            app_name = request.form.get('app_name', 'Kentaro').strip()
            app_tagline = request.form.get('app_tagline', '').strip()
            primary_color = request.form.get('primary_color', '#D92D3A').strip()
            
            set_setting('app_name', app_name)
            set_setting('app_tagline', app_tagline)
            set_setting('primary_color', primary_color)

            # File uploads: logo & favicon
            branding_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'branding')
            os.makedirs(branding_dir, exist_ok=True)

            logo_file = request.files.get('logo_file')
            if logo_file and logo_file.filename:
                ext = os.path.splitext(logo_file.filename)[1].lower()
                if ext in ['.png', '.jpg', '.jpeg', '.svg', '.webp']:
                    fname = f"platform_logo_{uuid.uuid4().hex[:6]}{ext}"
                    logo_path = os.path.join(branding_dir, fname)
                    logo_file.save(logo_path)
                    set_setting('platform_logo_url', f"/static/uploads/branding/{fname}")

            fav_file = request.files.get('favicon_file')
            if fav_file and fav_file.filename:
                ext = os.path.splitext(fav_file.filename)[1].lower()
                if ext in ['.ico', '.png', '.svg']:
                    fname = f"platform_fav_{uuid.uuid4().hex[:6]}{ext}"
                    fav_path = os.path.join(branding_dir, fname)
                    fav_file.save(fav_path)
                    set_setting('platform_favicon_url', f"/static/uploads/branding/{fname}")

            db.session.commit()
            log_admin_activity('update_branding', 'platform', None, f'Super Admin updated branding: name={app_name}')
            flash('Platform branding updated successfully!', 'success')

        elif section == 'general':
            if not is_superadmin:
                flash('Super Admin authorization required to modify platform settings.', 'danger')
                return redirect(url_for('admin.settings'))

            support_email = request.form.get('support_email', '').strip()
            support_phone = request.form.get('support_phone', '').strip()
            platform_desc = request.form.get('platform_description', '').strip()
            maintenance_mode = '1' if request.form.get('maintenance_mode') else '0'
            maintenance_msg = request.form.get('maintenance_message', '').strip()

            set_setting('support_email', support_email)
            set_setting('support_phone', support_phone)
            set_setting('platform_description', platform_desc)
            set_setting('maintenance_mode', maintenance_mode)
            set_setting('maintenance_message', maintenance_msg or 'Kentaro is currently undergoing scheduled maintenance. Please check back shortly.')

            db.session.commit()
            log_admin_activity('update_general_settings', 'platform', None, 'Super Admin updated general platform settings')
            flash('General platform settings updated!', 'success')

        return redirect(url_for('admin.settings'))
        
    branding = {
        'app_name': get_setting('app_name', 'Kentaro'),
        'app_tagline': get_setting('app_tagline', 'Calisthenics & Strength Coaching Platform'),
        'primary_color': get_setting('primary_color', '#D92D3A'),
        'logo_url': get_setting('platform_logo_url', ''),
        'favicon_url': get_setting('platform_favicon_url', ''),
        'support_email': get_setting('support_email', 'support@kentaro.app'),
        'support_phone': get_setting('support_phone', ''),
        'platform_description': get_setting('platform_description', 'High-performance calisthenics coaching ecosystem.'),
        'maintenance_mode': get_setting('maintenance_mode', '0') == '1',
        'maintenance_message': get_setting('maintenance_message', 'Kentaro is currently undergoing scheduled maintenance. Please check back shortly.')
    }

    return render_template('admin/settings.html',
                           is_superadmin=is_superadmin,
                           branding=branding,
                           announcement=announcement.value if announcement else '',
                           announcement_active=announcement_active.value == '1' if announcement_active else False)

# --- VIDEO MANAGEMENT ---
@admin_bp.route('/videos')
@login_required
def videos():
    video_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos')
    videos = []
    if os.path.isdir(video_dir):
        for fname in os.listdir(video_dir):
            if fname.lower().endswith(('.mp4', '.webm', '.ogg')):
                videos.append(fname)
    return render_template('admin/videos.html', videos=videos)

@admin_bp.route('/videos/delete/<filename>', methods=['POST'])
@login_required
def delete_video(filename):
    video_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos')
    file_path = os.path.join(video_dir, filename)
    if os.path.isfile(file_path):
        os.remove(file_path)
        log_admin_activity('delete_video', 'media', None, f'Deleted video file {filename}')
        flash(f'Video {filename} deleted.', 'success')
    else:
        flash('File not found.', 'warning')
    return redirect(url_for('admin.videos'))

# --- REPORTS MANAGEMENT ---
@admin_bp.route('/reports')
@login_required
def reports():
    status_filter = request.args.get('status', 'pending').strip()
    type_filter = request.args.get('type', 'all').strip()
    
    query = SystemReport.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if type_filter != 'all':
        query = query.filter_by(report_type=type_filter)
        
    reports_list = query.order_by(SystemReport.created_at.desc()).all()
    pending_count = SystemReport.query.filter_by(status='pending').count()
    investigating_count = SystemReport.query.filter_by(status='investigating').count()
    resolved_count = SystemReport.query.filter_by(status='resolved').count()
    dismissed_count = SystemReport.query.filter_by(status='dismissed').count()
    
    return render_template('admin/reports.html',
                           reports=reports_list,
                           status_filter=status_filter,
                           type_filter=type_filter,
                           pending_count=pending_count,
                           investigating_count=investigating_count,
                           resolved_count=resolved_count,
                           dismissed_count=dismissed_count)

@admin_bp.route('/reports/<int:report_id>/update-status', methods=['POST'])
@login_required
def update_report_status(report_id):
    report = SystemReport.query.get_or_404(report_id)
    new_status = request.form.get('status', 'resolved').strip()
    admin_notes = request.form.get('admin_notes', '').strip()
    action = request.form.get('action', '').strip()
    
    report.status = new_status
    if admin_notes:
        report.admin_notes = admin_notes
        
    if action == 'unapprove_coach' and report.target_coach:
        report.target_coach.is_approved = False
        flash(f'Coach {report.target_coach.first_name} has been unapproved.', 'warning')
    elif action == 'deactivate_coach' and report.target_coach and report.target_coach.user:
        report.target_coach.user.is_active = False
        flash(f'Coach user account {report.target_coach.user.email} deactivated.', 'danger')
    elif action == 'deactivate_user' and report.reporter:
        report.reporter.is_active = False
        flash(f'Reporter user account {report.reporter.email} deactivated.', 'danger')
        
    db.session.commit()
    log_admin_activity('update_report_status', 'bug_report', report.id, f'Updated report #{report.id} ({report.title}) to {new_status}')
    flash(f'Report #{report.id} updated to {new_status}.', 'success')
    return redirect(url_for('admin.reports'))

@admin_bp.route('/reports/<int:report_id>/update', methods=['POST'])
@login_required
def update_report(report_id):
    return update_report_status(report_id)


# --- APPEALS MANAGEMENT ---
@admin_bp.route('/appeals')
@login_required
def appeals():
    from app.models.user import AccountAppeal
    status_filter = request.args.get('status', 'pending')
    query = AccountAppeal.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    appeals_list = query.order_by(AccountAppeal.created_at.desc()).all()
    pending_count = AccountAppeal.query.filter_by(status='pending').count()
    return render_template('admin/appeals.html', appeals=appeals_list, status_filter=status_filter, pending_count=pending_count)

@admin_bp.route('/appeals/<int:appeal_id>/update', methods=['POST'])
@login_required
def update_appeal(appeal_id):
    from app.models.user import AccountAppeal
    from app.routes.auth import _send_email
    appeal = AccountAppeal.query.get_or_404(appeal_id)
    decision = request.form.get('decision')  # 'approve' or 'reject'
    admin_notes = request.form.get('admin_notes', '').strip()
    
    user = appeal.user
    if decision == 'approve':
        appeal.status = 'approved'
        appeal.admin_notes = admin_notes
        user.is_active = True
        db.session.commit()
        log_admin_activity('approve_appeal', 'appeal', appeal.id, f'Approved appeal #{appeal.id} for {user.email}')
        # Send confirmation email
        subject = "Your Kentaro Account Appeal Has Been Approved! 🎉"
        _send_email(
            user.email,
            subject,
            'auth/email_appeal_result.html',
            user=user,
            status='approved',
            admin_notes=admin_notes
        )
        flash(f'Appeal #{appeal.id} APPROVED. User {user.email} reactivated.', 'success')
    elif decision == 'reject':
        appeal.status = 'rejected'
        appeal.admin_notes = admin_notes
        db.session.commit()
        log_admin_activity('reject_appeal', 'appeal', appeal.id, f'Rejected appeal #{appeal.id} for {user.email}')
        # Send rejection email
        subject = "Update regarding your Kentaro Account Appeal"
        _send_email(
            user.email,
            subject,
            'auth/email_appeal_result.html',
            user=user,
            status='rejected',
            admin_notes=admin_notes
        )
        flash(f'Appeal #{appeal.id} REJECTED. Email notification sent.', 'info')
        
    return redirect(url_for('admin.appeals'))

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SUBSCRIPTION PLAN MANAGEMENT (ADMIN)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@admin_bp.route('/plans')
@login_required
def plans():
    from app.models.subscription import SubscriptionPlan
    all_plans = SubscriptionPlan.query.order_by(SubscriptionPlan.display_order, SubscriptionPlan.id).all()
    return render_template('admin/plans.html', plans=all_plans)


@admin_bp.route('/plans/create', methods=['GET', 'POST'])
@login_required
def create_plan():
    from app.models.subscription import SubscriptionPlan, FEATURE_LABELS
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip().lower().replace(' ', '_')
        description = request.form.get('description', '').strip()
        try:
            price = float(request.form.get('price', 0))
        except (ValueError, TypeError):
            price = 0.0
        billing_interval = request.form.get('billing_interval', 'monthly')
        is_unlimited = bool(request.form.get('is_unlimited_clients'))
        try:
            max_clients = None if is_unlimited else int(request.form.get('max_clients', 5))
        except (ValueError, TypeError):
            max_clients = 5
        try:
            display_order = int(request.form.get('display_order', 10))
        except (ValueError, TypeError):
            display_order = 10

        if not name or not slug:
            flash('Plan name and slug are required.', 'danger')
            return render_template('admin/edit_plan.html', plan=None, feature_labels=FEATURE_LABELS)

        if SubscriptionPlan.query.filter_by(slug=slug).first():
            flash(f'A plan with slug "{slug}" already exists.', 'danger')
            return render_template('admin/edit_plan.html', plan=None, feature_labels=FEATURE_LABELS)

        features_dict = {key: bool(request.form.get(f'feature_{key}')) for key in FEATURE_LABELS}
        plan = SubscriptionPlan(
            name=name,
            slug=slug,
            description=description,
            price=price,
            billing_interval=billing_interval,
            max_clients=max_clients,
            is_unlimited_clients=is_unlimited,
            display_order=display_order,
            is_active=True
        )
        plan.set_features(features_dict)
        db.session.add(plan)
        db.session.commit()
        log_admin_activity('create_plan', 'subscription_plan', plan.id, f'Created subscription plan {plan.name} (${plan.price})')
        flash(f'Plan "{name}" created successfully!', 'success')
        return redirect(url_for('admin.plans'))

    from app.models.subscription import FEATURE_LABELS
    return render_template('admin/edit_plan.html', plan=None, feature_labels=FEATURE_LABELS)


@admin_bp.route('/plans/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plan(plan_id):
    from app.models.subscription import SubscriptionPlan, FEATURE_LABELS
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    if request.method == 'POST':
        plan.name = request.form.get('name', plan.name).strip()
        # Allow slug edit only for custom (non-default) plans
        if plan.slug not in ('free', 'basic', 'premium'):
            plan.slug = request.form.get('slug', plan.slug).strip().lower().replace(' ', '_')
        plan.description = request.form.get('description', '').strip()
        try:
            plan.price = float(request.form.get('price', plan.price))
        except (ValueError, TypeError):
            pass
        plan.billing_interval = request.form.get('billing_interval', plan.billing_interval)
        plan.is_unlimited_clients = bool(request.form.get('is_unlimited_clients'))
        if plan.is_unlimited_clients:
            plan.max_clients = None
        else:
            try:
                plan.max_clients = int(request.form.get('max_clients', plan.max_clients or 5))
            except (ValueError, TypeError):
                pass
        try:
            plan.display_order = int(request.form.get('display_order', plan.display_order))
        except (ValueError, TypeError):
            pass

        features_dict = {key: bool(request.form.get(f'feature_{key}')) for key in FEATURE_LABELS}
        plan.set_features(features_dict)
        plan.updated_at = datetime.utcnow()
        db.session.commit()
        log_admin_activity('edit_plan', 'subscription_plan', plan.id, f'Updated subscription plan {plan.name}')
        flash(f'Plan "{plan.name}" updated successfully!', 'success')
        return redirect(url_for('admin.plans'))

    return render_template('admin/edit_plan.html', plan=plan, feature_labels=FEATURE_LABELS)


@admin_bp.route('/plans/<int:plan_id>/toggle', methods=['POST'])
@login_required
def toggle_plan(plan_id):
    from app.models.subscription import SubscriptionPlan
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    if plan.slug == 'free':
        flash('The Free plan cannot be disabled.', 'warning')
        return redirect(url_for('admin.plans'))
    plan.is_active = not plan.is_active
    db.session.commit()
    status = 'enabled' if plan.is_active else 'disabled'
    log_admin_activity('toggle_plan', 'subscription_plan', plan.id, f'{status.capitalize()} subscription plan {plan.name}')
    flash(f'Plan "{plan.name}" has been {status}.', 'success')
    return redirect(url_for('admin.plans'))


@admin_bp.route('/subscriptions')
@login_required
def subscriptions():
    from app.models.subscription import CoachSubscription, SubscriptionPlan
    all_subs = CoachSubscription.query.order_by(CoachSubscription.updated_at.desc()).all()
    all_plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.display_order).all()
    return render_template('admin/subscriptions.html', subscriptions=all_subs, plans=all_plans)


@admin_bp.route('/coaches/<int:coach_id>/assign-plan', methods=['POST'])
@login_required
def assign_coach_plan(coach_id):
    from app.models.subscription import SubscriptionPlan, CoachSubscription
    from app.services.entitlements import get_coach_subscription, log_subscription_change, get_active_client_count

    coach = CoachProfile.query.get_or_404(coach_id)
    plan_id = request.form.get('plan_id', type=int)
    reason = request.form.get('reason', '').strip() or f'Manual assignment by admin {current_user.email}'

    if not plan_id:
        flash('Please select a plan to assign.', 'danger')
        return redirect(url_for('admin.subscriptions'))

    target_plan = SubscriptionPlan.query.get_or_404(plan_id)
    sub = get_coach_subscription(coach.id)
    old_plan_id = sub.plan_id

    # Check downgrade: warn if coach has more clients than new plan allows
    if not target_plan.is_unlimited_clients and target_plan.max_clients is not None:
        current_client_count = get_active_client_count(coach.id)
        if current_client_count > target_plan.max_clients:
            flash(
                f'Warning: Coach {coach.first_name} has {current_client_count} active clients but '
                f'the {target_plan.name} plan allows only {target_plan.max_clients}. '
                f'Existing clients are retained, but no new clients can be added until within limit.',
                'warning'
            )

    sub.plan_id = target_plan.id
    sub.status = 'active'
    sub.current_price = target_plan.price
    sub.currency = target_plan.currency or 'USD'
    sub.billing_interval = target_plan.billing_interval or 'monthly'
    if target_plan.price == 0:
        sub.current_period_end = None
    sub.updated_at = datetime.utcnow()
    db.session.commit()

    log_subscription_change(
        coach_id=coach.id,
        changed_by_user_id=current_user.id,
        old_plan_id=old_plan_id,
        new_plan_id=target_plan.id,
        action='admin_assign',
        reason=reason
    )
    log_admin_activity('assign_plan', 'coach', coach.id, f'Assigned plan {target_plan.name} to coach {coach.first_name} {coach.last_name}')

    flash(f'Coach {coach.first_name} {coach.last_name} has been assigned to the {target_plan.name} plan.', 'success')
    return redirect(url_for('admin.subscriptions'))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ADMIN: SEND ANONYMOUS DM
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
                'from_name': 'Kentaro Support\U0001f6e1\ufe0f',
                'is_anonymous': True,
                'timestamp': msg.timestamp.strftime('%H:%M') if msg.timestamp else ''
            }, room=f'user_{target_id}')
            flash('Anonymous message sent.', 'success')
            sent = True
    return render_template('admin/send_dm.html', users=users, sent=sent)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ADMIN: COMPOSE & SEND EMAIL
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
                '<p>' + body.replace('\n', '<br>') + '</p>'
                '<hr/><p style="color:#888;font-size:12px">Kentaro Coaching Platform</p>'
                '</div>'
            )
            ok = send_email(to_email, subject, html=html)
            flash('Email sent successfully.' if ok else 'Email failed to send.', 'success' if ok else 'danger')
    return render_template('admin/compose_email.html', users=users)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ADMIN: SUPPORT CHAT & DM MANAGEMENT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@admin_bp.route('/chat')
@admin_bp.route('/chat/<int:partner_id>')
@admin_bp.route('/support-chat')
@admin_bp.route('/support-chat/<int:partner_id>')
@login_required
def support_chat(partner_id=None):
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))

    target_partner_id = request.args.get('partner_id', type=int) or partner_id
    view_filter = request.args.get('view', 'open')  # 'open', 'closed', 'all'
    view_closed = (view_filter == 'closed')

    from app.models.user import ChatMessage, User
    from app.models.features import ClosedSupportChat, SupportTicket
    from sqlalchemy import or_, and_
    import datetime as dt

    # Admin IDs
    admins = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).all()
    admin_ids = [u.id for u in admins]

    # Closed user IDs across support desk
    closed_records = ClosedSupportChat.query.all()
    closed_user_ids = {r.user_id for r in closed_records}
    closed_tickets = SupportTicket.query.filter_by(status='closed').all()
    for t in closed_tickets:
        closed_user_ids.add(t.user_id)

    # All users who have active support tickets or exchanged messages with support
    msg_partners = db.session.query(ChatMessage.sender_id).filter(
        ChatMessage.receiver_id.in_(admin_ids)
    ).union(
        db.session.query(ChatMessage.receiver_id).filter(
            ChatMessage.sender_id.in_(admin_ids)
        )
    ).all()

    ticket_users = [t.user_id for t in SupportTicket.query.all()]
    partner_uids = list(set([uid[0] for uid in msg_partners if uid[0] not in admin_ids] + ticket_users))

    all_contact_uids = []
    seen = set()

    if target_partner_id and target_partner_id not in admin_ids:
        all_contact_uids.append(target_partner_id)
        seen.add(target_partner_id)

    for uid in partner_uids:
        if uid not in seen:
            is_closed = uid in closed_user_ids
            if view_filter == 'open' and is_closed:
                continue
            if view_filter == 'closed' and not is_closed:
                continue
            seen.add(uid)
            all_contact_uids.append(uid)

    contacts = []
    for uid in all_contact_uids:
        u = User.query.get(uid)
        if not u:
            continue
        c_coach = u.coach_profile
        c_client = u.client_profile

        if c_coach and c_coach.first_name:
            name = f"Coach {c_coach.first_name} {c_coach.last_name or ''}".strip()
            role_label = "Coach"
            avatar = name[6].upper() if len(name) > 6 else 'C'
        elif c_client and c_client.first_name:
            name = c_client.full_name
            role_label = "Athlete"
            avatar = name[0].upper()
        else:
            name = u.email.split('@')[0]
            role_label = "User"
            avatar = name[0].upper() if name else '?'

        last_msg = ChatMessage.query.filter(
            or_(
                and_(ChatMessage.sender_id.in_(admin_ids), ChatMessage.receiver_id == uid),
                and_(ChatMessage.sender_id == uid, ChatMessage.receiver_id.in_(admin_ids))
            )
        ).order_by(ChatMessage.timestamp.desc()).first()

        unread_count = ChatMessage.query.filter(
            ChatMessage.sender_id == uid,
            ChatMessage.receiver_id.in_(admin_ids),
            ChatMessage.is_read == False
        ).count()

        ticket = SupportTicket.query.filter_by(user_id=uid).order_by(SupportTicket.created_at.desc()).first()
        is_closed = uid in closed_user_ids or (ticket and ticket.status == 'closed')

        contacts.append({
            'user': u,
            'name': name,
            'role_label': role_label,
            'avatar': avatar,
            'last_msg': last_msg,
            'unread_count': unread_count,
            'is_closed': is_closed,
            'ticket': ticket,
            'ticket_ref': ticket.ticket_ref if ticket else f"SUP-{uid:04d}",
            'status': 'closed' if is_closed else (ticket.status if ticket else 'open')
        })

    contacts.sort(key=lambda c: (
        c['last_msg'].timestamp if c['last_msg'] and c['last_msg'].timestamp else dt.datetime.min
    ), reverse=True)

    active_user = None
    messages = []
    if target_partner_id:
        active_user = User.query.get(target_partner_id)
        if active_user:
            ChatMessage.query.filter(
                ChatMessage.sender_id == target_partner_id,
                ChatMessage.receiver_id.in_(admin_ids),
                ChatMessage.is_read == False
            ).update({'is_read': True}, synchronize_session=False)
            db.session.commit()

            messages = ChatMessage.query.filter(
                or_(
                    and_(ChatMessage.sender_id.in_(admin_ids), ChatMessage.receiver_id == target_partner_id),
                    and_(ChatMessage.sender_id == target_partner_id, ChatMessage.receiver_id.in_(admin_ids))
                ),
                (ChatMessage.is_deleted == False) | (ChatMessage.is_deleted == None)
            ).order_by(ChatMessage.timestamp.asc()).all()
    elif contacts:
        target_partner_id = contacts[0]['user'].id
        active_user = contacts[0]['user']
        ChatMessage.query.filter(
            ChatMessage.sender_id == target_partner_id,
            ChatMessage.receiver_id.in_(admin_ids),
            ChatMessage.is_read == False
        ).update({'is_read': True}, synchronize_session=False)
        db.session.commit()

        messages = ChatMessage.query.filter(
            or_(
                and_(ChatMessage.sender_id.in_(admin_ids), ChatMessage.receiver_id == target_partner_id),
                and_(ChatMessage.sender_id == target_partner_id, ChatMessage.receiver_id.in_(admin_ids))
            ),
            (ChatMessage.is_deleted == False) | (ChatMessage.is_deleted == None)
        ).order_by(ChatMessage.timestamp.asc()).all()

    is_partner_closed = bool(target_partner_id and (target_partner_id in closed_user_ids or (active_user and any(c['is_closed'] for c in contacts if c['user'].id == target_partner_id))))
    active_ticket = SupportTicket.query.filter_by(user_id=target_partner_id).order_by(SupportTicket.created_at.desc()).first() if target_partner_id else None

    active_count = len([uid for uid in partner_uids if uid not in closed_user_ids])
    closed_count = len([uid for uid in partner_uids if uid in closed_user_ids])

    return render_template('admin/chat.html',
                           partner_id=target_partner_id,
                           active_user=active_user,
                           active_ticket=active_ticket,
                           contacts=contacts,
                           messages=messages,
                           view_closed=view_closed,
                           view_filter=view_filter,
                           is_partner_closed=is_partner_closed,
                           active_count=active_count,
                           closed_count=closed_count)


@admin_bp.route('/chat/close/<int:user_id>', methods=['GET', 'POST'])
@login_required
def close_support_chat(user_id):
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))
    from app.services.messaging import close_support_ticket
    close_support_ticket(user_id, current_user.id)
    log_admin_activity('close_support_chat', 'user', user_id, f'Closed support chat with user #{user_id}')
    flash('Support ticket closed successfully.', 'info')
    return redirect(url_for('admin.support_chat'))


@admin_bp.route('/chat/reopen/<int:user_id>', methods=['GET', 'POST'])
@login_required
def reopen_support_chat(user_id):
    if not getattr(current_user, 'is_admin', False) and not (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin']):
        return redirect(url_for('admin.dashboard'))
    from app.services.messaging import reopen_support_ticket
    reopen_support_ticket(user_id)
    log_admin_activity('reopen_support_chat', 'user', user_id, f'Reopened support chat with user #{user_id}')
    flash('Support ticket reopened.', 'success')
    return redirect(url_for('admin.support_chat', partner_id=user_id))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ADMIN: ANALYTICS & BUSINESS INTELLIGENCE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@admin_bp.route('/analytics')
@login_required
def analytics():
    total_users = User.query.count()
    coaches_count = CoachProfile.query.count()
    clients_count = ClientProfile.query.count()
    admins_count = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).count()

    # Subscription distribution
    active_subs = CoachSubscription.query.filter_by(status='active').count()
    cancelled_subs = CoachSubscription.query.filter_by(status='cancelled').count()
    expired_subs = CoachSubscription.query.filter_by(status='expired').count()
    free_or_no_sub = max(0, coaches_count - (active_subs + cancelled_subs + expired_subs))

    # 30-day daily registration trend
    today = datetime.utcnow().date()
    start_date = datetime.utcnow() - timedelta(days=30)
    trend_labels = [(today - timedelta(days=i)).strftime('%b %d') for i in reversed(range(30))]

    users_trend = [0] * 30
    coaches_trend = [0] * 30
    clients_trend = [0] * 30

    recent_users = User.query.filter(User.created_at >= start_date).all()
    recent_coaches = CoachProfile.query.filter(CoachProfile.created_at >= start_date).all()
    recent_clients = ClientProfile.query.filter(ClientProfile.created_at >= start_date).all()

    for u in recent_users:
        if u.created_at:
            days_ago = (today - u.created_at.date()).days
            if 0 <= days_ago < 30:
                users_trend[29 - days_ago] += 1

    for c in recent_coaches:
        if c.created_at:
            days_ago = (today - c.created_at.date()).days
            if 0 <= days_ago < 30:
                coaches_trend[29 - days_ago] += 1

    for cl in recent_clients:
        if cl.created_at:
            days_ago = (today - cl.created_at.date()).days
            if 0 <= days_ago < 30:
                clients_trend[29 - days_ago] += 1

    # Monthly registrations (last 12 months)
    monthly_labels = []
    monthly_users = []
    for i in reversed(range(12)):
        month_dt = today.replace(day=1) - timedelta(days=i * 30)
        label = month_dt.strftime('%b %Y')
        monthly_labels.append(label)
        m_start = datetime(month_dt.year, month_dt.month, 1)
        if month_dt.month == 12:
            m_end = datetime(month_dt.year + 1, 1, 1)
        else:
            m_end = datetime(month_dt.year, month_dt.month + 1, 1)
        count = User.query.filter(User.created_at >= m_start, User.created_at < m_end).count()
        monthly_users.append(count)

    # Top coaches by client count
    top_coaches = db.session.query(
        CoachProfile, func.count(ClientProfile.id).label('client_count')
    ).outerjoin(ClientProfile, CoachProfile.id == ClientProfile.coach_id)\
     .group_by(CoachProfile.id)\
     .order_by(func.count(ClientProfile.id).desc())\
     .limit(5).all()

    total_workouts = WorkoutCompletion.query.count()
    total_check_ins = CheckIn.query.count()
    total_appointments = Appointment.query.count()
    total_contracts = ClientContract.query.count()

    return render_template('admin/analytics.html',
                           total_users=total_users,
                           coaches_count=coaches_count,
                           clients_count=clients_count,
                           admins_count=admins_count,
                           active_subs=active_subs,
                           cancelled_subs=cancelled_subs,
                           expired_subs=expired_subs,
                           free_or_no_sub=free_or_no_sub,
                           trend_labels=trend_labels,
                           users_trend=users_trend,
                           coaches_trend=coaches_trend,
                           clients_trend=clients_trend,
                           monthly_labels=monthly_labels,
                           monthly_users=monthly_users,
                           top_coaches=top_coaches,
                           total_workouts=total_workouts,
                           total_check_ins=total_check_ins,
                           total_appointments=total_appointments,
                           total_contracts=total_contracts)


@admin_bp.route('/analytics/data')
@login_required
def analytics_data():
    today = datetime.utcnow().date()
    start_date = datetime.utcnow() - timedelta(days=30)
    trend_labels = [(today - timedelta(days=i)).strftime('%b %d') for i in reversed(range(30))]

    users_trend = [0] * 30
    coaches_trend = [0] * 30
    clients_trend = [0] * 30

    recent_users = User.query.filter(User.created_at >= start_date).all()
    recent_coaches = CoachProfile.query.filter(CoachProfile.created_at >= start_date).all()
    recent_clients = ClientProfile.query.filter(ClientProfile.created_at >= start_date).all()

    for u in recent_users:
        if u.created_at:
            days_ago = (today - u.created_at.date()).days
            if 0 <= days_ago < 30:
                users_trend[29 - days_ago] += 1

    for c in recent_coaches:
        if c.created_at:
            days_ago = (today - c.created_at.date()).days
            if 0 <= days_ago < 30:
                coaches_trend[29 - days_ago] += 1

    for cl in recent_clients:
        if cl.created_at:
            days_ago = (today - cl.created_at.date()).days
            if 0 <= days_ago < 30:
                clients_trend[29 - days_ago] += 1

    coaches_count = CoachProfile.query.count()
    active_subs = CoachSubscription.query.filter_by(status='active').count()
    cancelled_subs = CoachSubscription.query.filter_by(status='cancelled').count()
    expired_subs = CoachSubscription.query.filter_by(status='expired').count()
    free_or_no_sub = max(0, coaches_count - (active_subs + cancelled_subs + expired_subs))

    clients_count = ClientProfile.query.count()
    admins_count = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).count()

    monthly_labels = []
    monthly_users = []
    for i in reversed(range(12)):
        month_dt = today.replace(day=1) - timedelta(days=i * 30)
        label = month_dt.strftime('%b %Y')
        monthly_labels.append(label)
        m_start = datetime(month_dt.year, month_dt.month, 1)
        if month_dt.month == 12:
            m_end = datetime(month_dt.year + 1, 1, 1)
        else:
            m_end = datetime(month_dt.year, month_dt.month + 1, 1)
        count = User.query.filter(User.created_at >= m_start, User.created_at < m_end).count()
        monthly_users.append(count)

    return jsonify({
        'registration_trend': {
            'labels': trend_labels,
            'users': users_trend,
            'coaches': coaches_trend,
            'clients': clients_trend
        },
        'subscription_distribution': {
            'labels': ['Active Subscriptions', 'Cancelled', 'Expired', 'Free / Without Plan'],
            'data': [active_subs, cancelled_subs, expired_subs, free_or_no_sub]
        },
        'role_ratio': {
            'labels': ['Coaches', 'Athletes', 'Admins'],
            'data': [coaches_count, clients_count, admins_count]
        },
        'monthly_users': {
            'labels': monthly_labels,
            'data': monthly_users
        }
    })


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ADMIN: ACTIVITY LOG
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@admin_bp.route('/activity')
@login_required
def activity():
    page = request.args.get('page', 1, type=int)
    admin_id = request.args.get('admin_id', type=int)
    action_filter = request.args.get('action', '').strip()
    target_type_filter = request.args.get('target_type', '').strip()

    query = AdminActivityLog.query
    if admin_id:
        query = query.filter_by(admin_id=admin_id)
    if action_filter:
        query = query.filter_by(action=action_filter)
    if target_type_filter:
        query = query.filter_by(target_type=target_type_filter)

    pagination = query.order_by(AdminActivityLog.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    admins = User.query.filter((User.is_admin == True) | (User.role.has(name='admin'))).all()

    unique_actions = [r[0] for r in db.session.query(AdminActivityLog.action).distinct().all()]
    unique_targets = [r[0] for r in db.session.query(AdminActivityLog.target_type).distinct().filter(AdminActivityLog.target_type != None).all()]

    return render_template('admin/activity.html',
                           pagination=pagination,
                           logs=pagination.items,
                           admins=admins,
                           actions=unique_actions,
                           target_types=unique_targets,
                           admin_id=admin_id,
                           action_filter=action_filter,
                           target_type_filter=target_type_filter)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ADMIN: APPOINTMENTS SCHEDULING OVERVIEW
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@admin_bp.route('/appointments')
@login_required
def appointments():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all').strip()
    coach_id = request.args.get('coach_id', type=int)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    query = Appointment.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if coach_id:
        query = query.filter_by(coach_id=coach_id)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(Appointment.date >= d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(Appointment.date <= d_to)
        except ValueError:
            pass

    pagination = query.order_by(Appointment.date.desc(), Appointment.start_time.desc()).paginate(page=page, per_page=20, error_out=False)
    coaches = CoachProfile.query.order_by(CoachProfile.first_name).all()

    total_count = Appointment.query.count()
    scheduled_count = Appointment.query.filter_by(status='scheduled').count()
    completed_count = Appointment.query.filter_by(status='completed').count()
    cancelled_count = Appointment.query.filter_by(status='cancelled').count()

    return render_template('admin/appointments.html',
                           pagination=pagination,
                           appointments=pagination.items,
                           coaches=coaches,
                           status_filter=status_filter,
                           coach_id=coach_id,
                           date_from=date_from,
                           date_to=date_to,
                           total_count=total_count,
                           scheduled_count=scheduled_count,
                           completed_count=completed_count,
                           cancelled_count=cancelled_count)



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
