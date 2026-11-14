import json
from functools import wraps
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user

PRIMARY_SUPERADMIN_EMAIL = 'admin@kentaro.test'

def is_superadmin_user(user):
    """Check if a user is a superadmin."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superadmin', False):
        return True
    if getattr(user, 'role', None) and getattr(user.role, 'name', None) == 'superadmin':
        return True
    return False

def is_primary_superadmin(user):
    """Check if the user is the protected primary superadmin."""
    if not is_superadmin_user(user):
        return False
    if getattr(user, 'email', '') == PRIMARY_SUPERADMIN_EMAIL:
        return True
    # If id is 3 (original admin)
    if getattr(user, 'id', None) == 3:
        return True
    return False

def require_superadmin(f):
    """Route decorator: strictly requires Super Admin authority."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login', next=request.url))
        if not is_superadmin_user(current_user):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def require_admin_permission(perm_key):
    """Route decorator: checks granular permission for normal admins (superadmin always bypasses)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('admin.login', next=request.url))
            if is_superadmin_user(current_user):
                return f(*args, **kwargs)

            # Check if normal admin
            is_adm = bool(
                getattr(current_user, 'is_admin', False) or
                (getattr(current_user, 'role', None) and getattr(current_user.role, 'name', None) in ['admin', 'superadmin'])
            )
            if not is_adm:
                abort(403)

            # Check if admin account is active
            status = getattr(current_user, 'admin_status', 'active')
            if status != 'active':
                flash('Your administrator account is inactive or suspended. Please contact Super Admin.', 'danger')
                abort(403)

            # Check granular permissions
            perms = getattr(current_user, 'admin_permissions', None)
            if perms:
                try:
                    perms_data = json.loads(perms) if isinstance(perms, str) else perms
                    if isinstance(perms_data, dict):
                        if not perms_data.get(perm_key, False) and not perms_data.get('all', False):
                            abort(403)
                    elif isinstance(perms_data, list):
                        if perm_key not in perms_data and 'all' not in perms_data:
                            abort(403)
                except Exception:
                    pass

            return f(*args, **kwargs)
        return decorated_function
    return decorator
