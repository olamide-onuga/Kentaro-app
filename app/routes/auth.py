from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, mail
from app.models.user import User, Role
from app.utils.token import generate_confirmation_token, confirm_token
from app.utils.validators import validate_password_strength
from itsdangerous import SignatureExpired, BadSignature
from flask_mail import Message
import os

auth_bp = Blueprint('auth', __name__)

# Helper to send emails
def _send_email(to, subject, template, **kwargs):
    import traceback
    try:
        html_body = render_template(template, **kwargs)
    except Exception as e:
        current_app.logger.error(f"Email template render failed ({template}): {e}\n{traceback.format_exc()}")
        return False

    msg = Message(
        subject,
        recipients=[to],
        sender=current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME')
    )
    msg.html = html_body
    try:
        mail.send(msg)
        current_app.logger.info(f"Email sent to {to} — subject: {subject}")
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send email to {to}: {e}\n{traceback.format_exc()}")
        return False


def _get_dashboard_url(user):
    """Return the role-specific dashboard URL for a user."""
    if not user:
        return url_for('main.index')
    if getattr(user, 'is_superadmin', False) or (getattr(user, 'role', None) and getattr(user.role, 'name', None) == 'superadmin'):
        return url_for('superadmin.dashboard')
    if getattr(user, 'is_admin', False) or (getattr(user, 'role', None) and getattr(user.role, 'name', None) in ['admin', 'superadmin']):
        return url_for('admin.dashboard')
    elif getattr(user, 'is_coach', False) or getattr(user, 'coach_profile', None) is not None:
        return url_for('coach.dashboard')
    elif getattr(user, 'is_client', False) or getattr(user, 'client_profile', None) is not None:
        return url_for('client.dashboard')
    return url_for('main.index')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(_get_dashboard_url(current_user))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user and user.verify_password(password):
            if not user.is_active:
                from flask import session as flask_session
                flask_session['suspended_user_id'] = user.id
                return redirect(url_for('auth.suspended'))
            # Disallow login before email confirmation (admins and superadmins exempt)
            is_adm_or_super = bool(getattr(user, 'is_admin', False) or getattr(user, 'is_superadmin', False) or (getattr(user, 'role', None) and getattr(user.role, 'name', None) in ['admin', 'superadmin']))
            if not user.is_email_confirmed and not is_adm_or_super:
                flash('Please verify your email address before logging in. Check your inbox for the instant verification link.', 'warning')
                return render_template('auth/login.html')
            login_user(user)
            return redirect(_get_dashboard_url(user))
        flash('Invalid email or password.', 'danger')
    return render_template('auth/login.html')

@auth_bp.route('/suspended', methods=['GET', 'POST'])
def suspended():
    from flask import session as flask_session
    from app.models.user import User, AccountAppeal
    user_id = flask_session.get('suspended_user_id')
    if not user_id:
        flash('No suspended account session found. Please log in.', 'warning')
        return redirect(url_for('auth.login'))
    user = User.query.get_or_404(user_id)
    if user.is_active:
        flask_session.pop('suspended_user_id', None)
        flash('Your account is active! You may log in now.', 'success')
        return redirect(url_for('auth.login'))

    existing_appeal = AccountAppeal.query.filter_by(user_id=user.id).order_by(AccountAppeal.created_at.desc()).first()

    if request.method == 'POST':
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash('Please provide a reason for your appeal.', 'warning')
            return render_template('auth/suspended.html', user=user, existing_appeal=existing_appeal)
        
        appeal = AccountAppeal(user_id=user.id, reason=reason, status='pending')
        db.session.add(appeal)
        db.session.commit()
        flash('Your appeal has been submitted successfully. Administrators will review your request.', 'success')
        return redirect(url_for('auth.suspended'))

    return render_template('auth/suspended.html', user=user, existing_appeal=existing_appeal)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))

@auth_bp.route('/register', methods=['GET'])
def register_choice():
    """Render a page where the user selects Coach or Client registration."""
    if current_user.is_authenticated:
        return redirect(_get_dashboard_url(current_user))
    return render_template('auth/register_choice.html')

# Client registration – formerly the generic register view
@auth_bp.route('/register/client', methods=['GET', 'POST'])
def register_client():
    if current_user.is_authenticated:
        return redirect(_get_dashboard_url(current_user))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        terms = request.form.get('terms')
        if not all([email, password, confirm_password, terms]):
            flash('All fields are required and terms must be accepted.', 'danger')
            return render_template('auth/client_register.html')
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/client_register.html')
        is_valid_pw, pw_err = validate_password_strength(password)
        if not is_valid_pw:
            flash(pw_err, 'danger')
            return render_template('auth/client_register.html')
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/client_register.html')
        role = Role.query.filter_by(name='client').first()
        if not role:
            role = Role(name='client')
            db.session.add(role)
            db.session.flush()
        user = User(email=email, role=role)
        user.password = password
        db.session.add(user)
        db.session.flush()
        # Auto-create an empty ClientProfile so is_client=True immediately
        from app.models.user import ClientProfile
        client_profile = ClientProfile(user_id=user.id)
        db.session.add(client_profile)
        db.session.commit()
        token = generate_confirmation_token(email)
        confirm_url = url_for('auth.confirm_email', token=token, _external=True)
        _send_email(email, 'Please confirm your email', 'auth/email_confirmation.html', confirm_url=confirm_url, user=user)
        flash('Registration successful! Please check your email and click the verification link to immediately log in.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/client_register.html')

# Coach registration – new flow
@auth_bp.route('/register/coach', methods=['GET', 'POST'])
def register_coach():
    if current_user.is_authenticated:
        return redirect(_get_dashboard_url(current_user))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        terms = request.form.get('terms')
        if not all([email, password, confirm_password, terms]):
            flash('All fields are required and terms must be accepted.', 'danger')
            return render_template('auth/coach_register.html')
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/coach_register.html')
        is_valid_pw, pw_err = validate_password_strength(password)
        if not is_valid_pw:
            flash(pw_err, 'danger')
            return render_template('auth/coach_register.html')
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/coach_register.html')
        role = Role.query.filter_by(name='coach').first()
        user = User(email=email, role=role)
        user.password = password
        db.session.add(user)
        db.session.commit()
        
        from app.models.user import CoachProfile
        profile = CoachProfile(user_id=user.id, is_approved=False)
        db.session.add(profile)
        db.session.commit()

        token = generate_confirmation_token(email)
        confirm_url = url_for('auth.confirm_email', token=token, _external=True)
        _send_email(email, 'Please confirm your email', 'auth/email_confirmation.html', confirm_url=confirm_url, user=user)
        flash('Coach account registered! Please check your email to verify and log in. Note: Coach accounts require administrator approval before becoming publicly visible.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/coach_register.html')

# Admin registration
@auth_bp.route('/register/admin', methods=['GET', 'POST'])
def register_admin():
    if current_user.is_authenticated and not getattr(current_user, 'is_admin', False):
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        admin_key = request.form.get('admin_key', '').strip()
        
        expected_key = os.getenv('ADMIN_REGISTRATION_KEY') or 'kentaro-admin-secret-2026'
        
        if not all([email, password, confirm_password]):
            flash('All fields are required.', 'danger')
            return render_template('auth/admin_register.html')
            
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/admin_register.html')
        is_valid_pw, pw_err = validate_password_strength(password)
        if not is_valid_pw:
            flash(pw_err, 'danger')
            return render_template('auth/admin_register.html')

        # Require admin key unless no admin user exists in DB
        admin_count = User.query.filter_by(is_admin=True).count()
        if admin_count > 0 and admin_key != expected_key:
            flash('Invalid Admin Security Key. Please contact system owner.', 'danger')
            return render_template('auth/admin_register.html')
            
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/admin_register.html')
            
        role = Role.query.filter_by(name='admin').first()
        if not role:
            role = Role(name='admin')
            db.session.add(role)
            db.session.commit()
            
        user = User(
            email=email,
            role=role,
            is_admin=True,
            is_active=True,
            is_email_confirmed=True
        )
        user.password = password
        db.session.add(user)
        db.session.commit()
        
        flash('Admin account created successfully! You may log in now.', 'success')
        return redirect(url_for('admin.login'))
        
    return render_template('auth/admin_register.html')

@auth_bp.route('/confirm/<token>')
def confirm_email(token):
    try:
        email = confirm_token(token)
    except SignatureExpired:
        flash('The confirmation link has expired.', 'danger')
        return redirect(url_for('auth.login'))
    except BadSignature:
        flash('Invalid confirmation token.', 'danger')
        return redirect(url_for('auth.login'))
    user = User.query.filter_by(email=email).first_or_404()
    if not user.is_email_confirmed:
        user.is_email_confirmed = True
        db.session.commit()
    # Instantly log the user in on this device and redirect straight to dashboard
    login_user(user, remember=True)
    flash('Email verified successfully! You are now logged in.', 'success')
    return redirect(_get_dashboard_url(user))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            token = generate_confirmation_token(email)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            _send_email(email, 'Password Reset Request', 'auth/email_reset.html', reset_url=reset_url, user=user)
        flash('If the email exists, a password reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')

@auth_bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = confirm_token(token)
    except (SignatureExpired, BadSignature):
        flash('The password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    user = User.query.filter_by(email=email).first_or_404()
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if not password or password != confirm_password:
            flash('Passwords must match.', 'danger')
            return render_template('auth/reset_password.html', token=token)
        is_valid_pw, pw_err = validate_password_strength(password)
        if not is_valid_pw:
            flash(pw_err, 'danger')
            return render_template('auth/reset_password.html', token=token)
        user.password = password
        db.session.commit()
        flash('Your password has been updated. Please log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', token=token)
