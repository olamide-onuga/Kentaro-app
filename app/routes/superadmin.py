import json
import time
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, func

from app.extensions import db
from app.models.user import User, CoachProfile, ClientProfile, Role, ChatMessage
from app.models.coaching import CoachingPackage, ClientContract
from app.models.features import SystemSetting, SystemReport, AdminActivityLog, ClientPost, CustomOffer, SupportTicket, TicketMessage, CustomProgramOffer
from app.models.subscription import SubscriptionPlan, CoachSubscription, SubscriptionPayment
from app.services.auth_guards import require_superadmin, is_superadmin_user, is_primary_superadmin

superadmin_bp = Blueprint('superadmin', __name__, url_prefix='/superadmin')

@superadmin_bp.before_request
def superadmin_guard():
    if not current_user.is_authenticated:
        return redirect(url_for('admin.login', next=request.url))
    if not is_superadmin_user(current_user):
        abort(403)

def log_superadmin_activity(action, target_type=None, target_id=None, detail=None):
    """Log an action performed by a Super Admin."""
    try:
        log = AdminActivityLog(
            admin_id=current_user.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            created_at=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to log superadmin activity: {e}")

def get_setting(key, default=''):
    setting = SystemSetting.query.filter_by(key=key).first()
    return setting.value if setting and setting.value is not None else default

def set_setting(key, value):
    setting = SystemSetting.query.filter_by(key=key).first()
    if not setting:
        setting = SystemSetting(key=key, value=str(value))
        db.session.add(setting)
    else:
        setting.value = str(value)
        setting.updated_at = datetime.utcnow()
    db.session.commit()


# ==============================================================================
# SECTION A: OVERVIEW
# ==============================================================================
@superadmin_bp.route('/')
@superadmin_bp.route('/dashboard')
def dashboard():
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    # Core user counts
    total_users = User.query.count()
    total_coaches = CoachProfile.query.count()
    total_clients = ClientProfile.query.count()
    
    admin_role = Role.query.filter_by(name='admin').first()
    superadmin_role = Role.query.filter_by(name='superadmin').first()
    
    admin_role_id = admin_role.id if admin_role else None
    superadmin_role_id = superadmin_role.id if superadmin_role else None
    
    total_admins = User.query.filter(User.role_id == admin_role_id).count() if admin_role_id else 0
    total_superadmins = User.query.filter(User.role_id == superadmin_role_id).count() if superadmin_role_id else 0
    
    # Subscriptions & programs
    active_subscriptions = CoachSubscription.query.filter_by(status='active').count()
    new_registrations = User.query.filter(User.created_at >= thirty_days_ago).count()
    active_programs = ClientContract.query.filter_by(status='active').count()
    
    # Marketplace & custom programs
    marketplace_posts = ClientPost.query.count()
    marketplace_offers = CustomOffer.query.count()
    marketplace_activity = marketplace_posts + marketplace_offers
    
    custom_program_purchases = CustomProgramOffer.query.filter_by(status='paid').count()
    
    # Support metrics
    pending_tickets = SupportTicket.query.filter_by(status='pending').count()
    in_progress_tickets = SupportTicket.query.filter_by(status='in_progress').count()
    closed_tickets = SupportTicket.query.filter(SupportTicket.status.in_(['closed', 'resolved'])).count()
    
    # Revenue calculations
    total_paid_offers_amount = db.session.query(func.sum(CustomProgramOffer.amount)).filter_by(status='paid').scalar() or 0.0
    
    # Subscription revenue approximation from active subscriptions
    active_subs = CoachSubscription.query.filter_by(status='active').all()
    monthly_sub_revenue = sum([sub.plan.price for sub in active_subs if sub.plan and sub.plan.price])
    
    # Recent logs
    recent_logs = AdminActivityLog.query.order_by(AdminActivityLog.created_at.desc()).limit(8).all()
    
    # System statuses
    maintenance_mode = get_setting('maintenance_mode', 'false') == 'true'
    allow_registrations = get_setting('allow_registrations', 'true') == 'true'
    allow_marketplace = get_setting('allow_marketplace', 'true') == 'true'
    allow_custom_offers = get_setting('allow_custom_offers', 'true') == 'true'
    announcement_active = get_setting('announcement_active', 'false') == 'true'
    announcement_text = get_setting('announcement_text', '')

    metrics = {
        'total_users': total_users,
        'total_coaches': total_coaches,
        'total_clients': total_clients,
        'total_admins': total_admins,
        'total_superadmins': total_superadmins,
        'active_subscriptions': active_subscriptions,
        'new_registrations': new_registrations,
        'active_programs': active_programs,
        'marketplace_activity': marketplace_activity,
        'custom_program_purchases': custom_program_purchases,
        'pending_tickets': pending_tickets,
        'in_progress_tickets': in_progress_tickets,
        'closed_tickets': closed_tickets,
        'monthly_sub_revenue': monthly_sub_revenue,
        'total_paid_offers_amount': total_paid_offers_amount,
        'maintenance_mode': maintenance_mode,
        'allow_registrations': allow_registrations,
        'allow_marketplace': allow_marketplace,
        'allow_custom_offers': allow_custom_offers,
        'announcement_active': announcement_active,
        'announcement_text': announcement_text
    }

    return render_template('superadmin/dashboard.html', metrics=metrics, recent_logs=recent_logs)


# ==============================================================================
# SECTION B: USER MANAGEMENT
# ==============================================================================
@superadmin_bp.route('/users')
def users():
    role_filter = request.args.get('role', 'all')
    search_query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'all')

    query = User.query

    if role_filter != 'all':
        query = query.join(Role).filter(Role.name == role_filter)

    if status_filter == 'active':
        query = query.filter(User.is_active == True)
    elif status_filter == 'inactive':
        query = query.filter(User.is_active == False)

    if search_query:
        query = query.filter(or_(
            User.email.ilike(f'%{search_query}%'),
            User.display_name.ilike(f'%{search_query}%')
        ))

    users_list = query.order_by(User.id.desc()).all()
    roles = Role.query.all()

    return render_template('superadmin/users.html',
                           users=users_list,
                           roles=roles,
                           current_role=role_filter,
                           current_status=status_filter,
                           search_query=search_query)


@superadmin_bp.route('/users/<int:user_id>/change-role', methods=['POST'])
def user_change_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role_name = request.form.get('role')

    # Guard primary superadmin
    if is_primary_superadmin(user) and new_role_name != 'superadmin':
        flash('The primary Super Admin account cannot be demoted.', 'danger')
        return redirect(url_for('superadmin.users'))

    role = Role.query.filter_by(name=new_role_name).first()
    if not role:
        flash('Invalid role specified.', 'danger')
        return redirect(url_for('superadmin.users'))

    old_role_name = user.role.name if user.role else 'None'
    user.role_id = role.id
    user.is_admin = bool(new_role_name in ['admin', 'superadmin'])
    db.session.commit()

    log_superadmin_activity(
        action='Changed User Role',
        target_type='user',
        target_id=user.id,
        detail=f"Changed {user.email} from {old_role_name} to {new_role_name}"
    )
    flash(f"Updated role for {user.email} to {new_role_name}.", 'success')
    return redirect(url_for('superadmin.users'))


@superadmin_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
def user_toggle_status(user_id):
    user = User.query.get_or_404(user_id)
    if is_primary_superadmin(user):
        flash('The primary Super Admin account cannot be deactivated.', 'danger')
        return redirect(url_for('superadmin.users'))

    user.is_active = not user.is_active
    db.session.commit()

    status_str = 'Activated' if user.is_active else 'Deactivated'
    log_superadmin_activity(
        action=f"{status_str} User",
        target_type='user',
        target_id=user.id,
        detail=f"{status_str} account {user.email}"
    )
    flash(f"User {user.email} has been {status_str.lower()}.", 'success')
    return redirect(url_for('superadmin.users'))


@superadmin_bp.route('/users/<int:user_id>/toggle-email-verify', methods=['POST'])
def user_toggle_email_verify(user_id):
    user = User.query.get_or_404(user_id)
    user.is_email_confirmed = not user.is_email_confirmed
    db.session.commit()

    state = "verified" if user.is_email_confirmed else "unverified"
    log_superadmin_activity(
        action="Toggled Email Verification",
        target_type="user",
        target_id=user.id,
        detail=f"Marked {user.email} as {state}"
    )
    flash(f"Email for {user.email} marked as {state}.", 'success')
    return redirect(url_for('superadmin.users'))


@superadmin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def user_delete(user_id):
    user = User.query.get_or_404(user_id)
    if is_primary_superadmin(user) or user.id == current_user.id:
        flash('Cannot delete this Super Admin account.', 'danger')
        return redirect(url_for('superadmin.users'))

    email = user.email
    uid = user.id
    try:
        # Cascade or clean up profile
        if user.coach_profile:
            db.session.delete(user.coach_profile)
        if user.client_profile:
            db.session.delete(user.client_profile)
        db.session.delete(user)
        db.session.commit()

        log_superadmin_activity(
            action="Deleted User Account",
            target_type="user",
            target_id=uid,
            detail=f"Permanently deleted account {email}"
        )
        flash(f"User account {email} permanently deleted.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Could not delete user: {e}", 'danger')

    return redirect(url_for('superadmin.users'))


# ==============================================================================
# SECTION C: ADMINISTRATOR MANAGEMENT
# ==============================================================================
@superadmin_bp.route('/admins')
def admins():
    admin_role = Role.query.filter_by(name='admin').first()
    superadmin_role = Role.query.filter_by(name='superadmin').first()
    role_ids = [r.id for r in [admin_role, superadmin_role] if r]

    admin_users = User.query.filter(
        or_(User.role_id.in_(role_ids), User.is_admin == True)
    ).order_by(User.id.asc()).all()

    return render_template('superadmin/admins.html', admins=admin_users)


@superadmin_bp.route('/admins/create', methods=['POST'])
def admin_create():
    email = request.form.get('email', '').strip().lower()
    display_name = request.form.get('display_name', '').strip()
    password = request.form.get('password', '').strip()
    
    if not email or not password:
        flash('Email and temporary password are required.', 'danger')
        return redirect(url_for('superadmin.admins'))

    existing = User.query.filter_by(email=email).first()
    if existing:
        flash(f'An account with email {email} already exists.', 'danger')
        return redirect(url_for('superadmin.admins'))

    admin_role = Role.query.filter_by(name='admin').first()
    if not admin_role:
        admin_role = Role(name='admin', description='Administrator')
        db.session.add(admin_role)
        db.session.commit()

    perms = {
        'manage_coaches': bool(request.form.get('perm_manage_coaches')),
        'manage_clients': bool(request.form.get('perm_manage_clients')),
        'manage_support': bool(request.form.get('perm_manage_support')),
        'manage_marketplace': bool(request.form.get('perm_manage_marketplace')),
        'view_financials': bool(request.form.get('perm_view_financials')),
        'manage_content': bool(request.form.get('perm_manage_content'))
    }

    new_admin = User(
        email=email,
        display_name=display_name or email.split('@')[0].title(),
        role_id=admin_role.id,
        is_admin=True,
        is_active=True,
        is_email_confirmed=True,
        admin_status='active',
        admin_created_by=current_user.id,
        admin_permissions=json.dumps(perms),
        created_at=datetime.utcnow()
    )
    new_admin.password = password
    db.session.add(new_admin)
    db.session.commit()

    log_superadmin_activity(
        action='Created Administrator',
        target_type='admin',
        target_id=new_admin.id,
        detail=f"Created normal admin {email} with custom permissions"
    )
    flash(f"Administrator {email} successfully created.", 'success')
    return redirect(url_for('superadmin.admins'))


@superadmin_bp.route('/admins/<int:admin_id>/edit', methods=['POST'])
def admin_edit(admin_id):
    target_admin = User.query.get_or_404(admin_id)

    if is_primary_superadmin(target_admin):
        flash('Primary Super Admin account configuration cannot be modified here.', 'warning')
        return redirect(url_for('superadmin.admins'))

    display_name = request.form.get('display_name', '').strip()
    status = request.form.get('admin_status', 'active')
    new_password = request.form.get('password', '').strip()

    if display_name:
        target_admin.display_name = display_name

    target_admin.admin_status = status
    if status == 'suspended' or status == 'deactivated':
        target_admin.is_active = False
    else:
        target_admin.is_active = True

    if new_password:
        target_admin.password = new_password

    # Update granular permissions if normal admin
    if not target_admin.is_superadmin:
        perms = {
            'manage_coaches': bool(request.form.get('perm_manage_coaches')),
            'manage_clients': bool(request.form.get('perm_manage_clients')),
            'manage_support': bool(request.form.get('perm_manage_support')),
            'manage_marketplace': bool(request.form.get('perm_manage_marketplace')),
            'view_financials': bool(request.form.get('perm_view_financials')),
            'manage_content': bool(request.form.get('perm_manage_content'))
        }
        target_admin.admin_permissions = json.dumps(perms)

    db.session.commit()

    log_superadmin_activity(
        action='Updated Administrator Profile',
        target_type='admin',
        target_id=target_admin.id,
        detail=f"Updated profile/permissions for admin {target_admin.email}"
    )
    flash(f"Administrator {target_admin.email} updated successfully.", 'success')
    return redirect(url_for('superadmin.admins'))


# ==============================================================================
# SECTION D: WEBSITE SETTINGS
# ==============================================================================
@superadmin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        keys = [
            'platform_name', 'support_email', 'default_currency',
            'announcement_banner_text', 'announcement_banner_type'
        ]
        for k in keys:
            if k in request.form:
                set_setting(k, request.form.get(k, '').strip())

        set_setting('announcement_banner_active', 'true' if request.form.get('announcement_banner_active') else 'false')

        log_superadmin_activity(
            action='Updated Website Settings',
            target_type='settings',
            detail='Updated branding, contact, and announcement settings'
        )
        flash('Website settings saved successfully.', 'success')
        return redirect(url_for('superadmin.settings'))

    current_settings = {
        'platform_name': get_setting('platform_name', 'Kentaro Coaching Platform'),
        'support_email': get_setting('support_email', 'support@kentaro.app'),
        'default_currency': get_setting('default_currency', 'USD'),
        'announcement_banner_text': get_setting('announcement_banner_text', ''),
        'announcement_banner_active': get_setting('announcement_banner_active', 'false') == 'true',
        'announcement_banner_type': get_setting('announcement_banner_type', 'info')
    }

    return render_template('superadmin/settings.html', settings=current_settings)


# ==============================================================================
# SECTION E: SUBSCRIPTION MANAGEMENT
# ==============================================================================
@superadmin_bp.route('/subscriptions', methods=['GET', 'POST'])
def subscriptions():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_plan':
            name = request.form.get('name', '').strip()
            price = float(request.form.get('price', 0))
            client_limit = int(request.form.get('client_limit', 5))
            duration_days = int(request.form.get('duration_days', 30))
            features = request.form.get('features', '').strip()

            plan = SubscriptionPlan(
                name=name,
                price=price,
                client_limit=client_limit,
                duration_days=duration_days,
                features=features,
                is_active=True
            )
            db.session.add(plan)
            db.session.commit()

            log_superadmin_activity(
                action='Created Subscription Plan',
                target_type='plan',
                target_id=plan.id,
                detail=f"Created tier {name} at ${price}/mo (limit: {client_limit} clients)"
            )
            flash(f"Subscription tier '{name}' created successfully.", 'success')
            return redirect(url_for('superadmin.subscriptions'))

    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.price.asc()).all()
    coach_subs = CoachSubscription.query.order_by(CoachSubscription.id.desc()).limit(50).all()

    return render_template('superadmin/subscriptions.html', plans=plans, subscriptions=coach_subs)


@superadmin_bp.route('/subscriptions/plan/<int:plan_id>/toggle', methods=['POST'])
def plan_toggle(plan_id):
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    plan.is_active = not plan.is_active
    db.session.commit()
    status_str = "Enabled" if plan.is_active else "Disabled"
    flash(f"Plan '{plan.name}' is now {status_str.lower()}.", 'info')
    return redirect(url_for('superadmin.subscriptions'))


# ==============================================================================
# SECTION F: FINANCIAL OVERVIEW
# ==============================================================================
@superadmin_bp.route('/finance')
def finance():
    paid_offers = CustomProgramOffer.query.filter_by(status='paid').order_by(CustomProgramOffer.paid_at.desc()).all()
    total_paid_offers = sum([o.amount for o in paid_offers if o.amount])

    active_subs = CoachSubscription.query.filter_by(status='active').all()
    mrr = sum([s.plan.price for s in active_subs if s.plan and s.plan.price])

    # Recent verified Paystack transactions
    transactions = []
    for offer in paid_offers:
        transactions.append({
            'reference': offer.payment_reference or f"pstk_offer_{offer.id}",
            'type': 'Custom Program Purchase',
            'amount': offer.amount,
            'currency': offer.currency or 'USD',
            'date': offer.paid_at or offer.created_at,
            'client_name': offer.client.user.display_name if (offer.client and offer.client.user) else 'Client',
            'coach_name': offer.coach.first_name if offer.coach else 'Coach',
            'status': 'Verified / Paid'
        })

    summary = {
        'total_revenue': total_paid_offers,
        'monthly_recurring_revenue': mrr,
        'total_transactions_count': len(transactions),
        'active_paying_coaches': len(active_subs)
    }

    return render_template('superadmin/finance.html', summary=summary, transactions=transactions)


# ==============================================================================
# SECTION G: SUPPORT SYSTEM OVERSIGHT
# ==============================================================================
@superadmin_bp.route('/support')
def support():
    status_filter = request.args.get('status', 'all')
    priority_filter = request.args.get('priority', 'all')

    query = SupportTicket.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if priority_filter != 'all':
        query = query.filter_by(priority=priority_filter)

    tickets = query.order_by(SupportTicket.created_at.desc()).all()
    
    # List of available admins for ticket reassignment
    admin_users = User.query.filter(User.is_admin == True, User.is_active == True).all()

    return render_template('superadmin/support.html',
                           tickets=tickets,
                           admins=admin_users,
                           current_status=status_filter,
                           current_priority=priority_filter)


@superadmin_bp.route('/support/ticket/<ticket_ref>/assign', methods=['POST'])
def support_reassign(ticket_ref):
    ticket = SupportTicket.query.filter_by(ticket_ref=ticket_ref).first_or_404()
    admin_id = request.form.get('admin_id', type=int)

    admin_user = User.query.get(admin_id) if admin_id else None
    ticket.assigned_admin_id = admin_id
    ticket.assigned_admin_name = admin_user.admin_display_name if admin_user else None
    if ticket.status == 'pending':
        ticket.status = 'in_progress'
    db.session.commit()

    target_name = admin_user.admin_display_name if admin_user else "Unassigned"
    log_superadmin_activity(
        action='Reassigned Support Ticket',
        target_type='ticket',
        target_id=ticket.id,
        detail=f"Assigned ticket #{ticket.ticket_ref} to {target_name}"
    )
    flash(f"Ticket #{ticket.ticket_ref} reassigned to {target_name}.", 'success')
    return redirect(url_for('superadmin.support'))


# ==============================================================================
# SECTION H: PLATFORM ANALYTICS
# ==============================================================================
@superadmin_bp.route('/analytics')
def analytics():
    total_users = User.query.count()
    total_coaches = CoachProfile.query.count()
    total_clients = ClientProfile.query.count()
    total_contracts = ClientContract.query.count()
    active_contracts = ClientContract.query.filter_by(status='active').count()

    total_tickets = SupportTicket.query.count()
    resolved_tickets = SupportTicket.query.filter(SupportTicket.status.in_(['closed', 'resolved'])).count()
    resolution_rate = round((resolved_tickets / total_tickets * 100), 1) if total_tickets > 0 else 100.0

    stats = {
        'total_users': total_users,
        'total_coaches': total_coaches,
        'total_clients': total_clients,
        'active_contracts': active_contracts,
        'total_contracts': total_contracts,
        'total_tickets': total_tickets,
        'resolved_tickets': resolved_tickets,
        'resolution_rate': resolution_rate
    }

    return render_template('superadmin/analytics.html', stats=stats)


# ==============================================================================
# SECTION I: MARKETPLACE MANAGEMENT
# ==============================================================================
@superadmin_bp.route('/marketplace')
def marketplace():
    posts = ClientPost.query.order_by(ClientPost.id.desc()).all()
    offers = CustomProgramOffer.query.order_by(CustomProgramOffer.id.desc()).all()
    return render_template('superadmin/marketplace.html', posts=posts, offers=offers)


@superadmin_bp.route('/marketplace/post/<int:post_id>/delete', methods=['POST'])
def marketplace_delete_post(post_id):
    post = ClientPost.query.get_or_404(post_id)
    title = post.title
    db.session.delete(post)
    db.session.commit()

    log_superadmin_activity(
        action='Deleted Marketplace Post',
        target_type='post',
        target_id=post_id,
        detail=f"Removed post: {title}"
    )
    flash(f"Marketplace post '{title}' removed.", 'success')
    return redirect(url_for('superadmin.marketplace'))


# ==============================================================================
# SECTION J: SECURITY & ACTIVITY LOGS
# ==============================================================================
@superadmin_bp.route('/logs')
def logs():
    search = request.args.get('q', '').strip()
    query = AdminActivityLog.query

    if search:
        query = query.filter(or_(
            AdminActivityLog.action.ilike(f'%{search}%'),
            AdminActivityLog.detail.ilike(f'%{search}%')
        ))

    logs_list = query.order_by(AdminActivityLog.created_at.desc()).limit(150).all()
    return render_template('superadmin/logs.html', logs=logs_list, search=search)


# ==============================================================================
# SECTION K: EMERGENCY SYSTEM CONTROLS
# ==============================================================================
@superadmin_bp.route('/controls', methods=['GET', 'POST'])
def controls():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'toggle_maintenance':
            curr = get_setting('maintenance_mode', 'false') == 'true'
            new_val = 'false' if curr else 'true'
            set_setting('maintenance_mode', new_val)
            log_superadmin_activity(
                action='Toggled Maintenance Mode',
                detail=f"Maintenance mode set to {new_val}"
            )
            flash(f"Maintenance mode has been {'activated' if new_val == 'true' else 'deactivated'}.", 'warning' if new_val == 'true' else 'success')

        elif action == 'toggle_registrations':
            curr = get_setting('allow_registrations', 'true') == 'true'
            new_val = 'false' if curr else 'true'
            set_setting('allow_registrations', new_val)
            log_superadmin_activity(
                action='Toggled User Registrations',
                detail=f"User registrations set to {new_val}"
            )
            flash(f"User registrations {'disabled' if new_val == 'false' else 'enabled'}.", 'info')

        elif action == 'toggle_marketplace':
            curr = get_setting('allow_marketplace', 'true') == 'true'
            new_val = 'false' if curr else 'true'
            set_setting('allow_marketplace', new_val)
            log_superadmin_activity(
                action='Toggled Marketplace Access',
                detail=f"Marketplace active set to {new_val}"
            )
            flash(f"Marketplace has been {'disabled' if new_val == 'false' else 'enabled'}.", 'info')

        elif action == 'toggle_custom_offers':
            curr = get_setting('allow_custom_offers', 'true') == 'true'
            new_val = 'false' if curr else 'true'
            set_setting('allow_custom_offers', new_val)
            log_superadmin_activity(
                action='Toggled Custom Offers',
                detail=f"Custom offers set to {new_val}"
            )
            flash(f"Custom program offers {'disabled' if new_val == 'false' else 'enabled'}.", 'info')

        elif action == 'update_announcement':
            text = request.form.get('announcement_text', '').strip()
            active = bool(request.form.get('announcement_active'))
            set_setting('announcement_text', text)
            set_setting('announcement_active', 'true' if active else 'false')
            log_superadmin_activity(
                action='Broadcast Announcement Updated',
                detail=f"Announcement active: {active}"
            )
            flash("Global announcement banner updated.", 'success')

        return redirect(url_for('superadmin.controls'))

    controls_data = {
        'maintenance_mode': get_setting('maintenance_mode', 'false') == 'true',
        'allow_registrations': get_setting('allow_registrations', 'true') == 'true',
        'allow_marketplace': get_setting('allow_marketplace', 'true') == 'true',
        'allow_custom_offers': get_setting('allow_custom_offers', 'true') == 'true',
        'announcement_active': get_setting('announcement_active', 'false') == 'true',
        'announcement_text': get_setting('announcement_text', '')
    }

    return render_template('superadmin/controls.html', controls=controls_data)
