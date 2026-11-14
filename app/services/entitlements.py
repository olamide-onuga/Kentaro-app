from datetime import datetime, timedelta
import logging
from functools import wraps
from flask import flash, redirect, url_for, request, jsonify
from flask_login import current_user
from sqlalchemy import or_

from app.extensions import db
from app.models.subscription import (
    SubscriptionPlan, CoachSubscription, SubscriptionAuditLog, SubscriptionPayment, DEFAULT_FEATURES
)
from app.models.user import CoachProfile, ClientProfile
from app.models.coaching import ClientContract

def get_coach_subscription(coach_id):
    """
    Get or create the coach's subscription.
    Handles expiration: if subscription period ended, marks expired and falls back to Free plan.
    """
    sub = CoachSubscription.query.filter_by(coach_id=coach_id).first()
    if not sub:
        # Assign Free plan automatically
        free_plan = SubscriptionPlan.query.filter_by(slug='free').first()
        if not free_plan:
            free_plan = seed_default_plans().get('free')

        sub = CoachSubscription(
            coach_id=coach_id,
            plan_id=free_plan.id,
            status='active',
            billing_interval='monthly',
            current_price=free_plan.price,
            currency=free_plan.currency or 'USD',
            started_at=datetime.utcnow(),
            current_period_start=datetime.utcnow(),
            current_period_end=None,
            auto_renew=True
        )
        db.session.add(sub)
        try:
            db.session.commit()
            log_subscription_change(
                coach_id=coach_id,
                changed_by_user_id=None,
                old_plan_id=None,
                new_plan_id=free_plan.id,
                action='system_seed',
                reason='Automatic assignment of Free plan'
            )
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating default coach subscription: {e}")
            sub = CoachSubscription.query.filter_by(coach_id=coach_id).first()
        return sub

    # Check expiration for paid subscriptions with end date
    if sub.current_period_end and sub.current_period_end < datetime.utcnow() and sub.status == 'active':
        sub.status = 'expired'
        try:
            db.session.commit()
            log_subscription_change(
                coach_id=coach_id,
                changed_by_user_id=None,
                old_plan_id=sub.plan_id,
                new_plan_id=sub.plan_id,
                action='auto_expire',
                reason='Subscription period expired'
            )
        except Exception:
            db.session.rollback()

    return sub


def get_coach_plan(coach_id):
    """Return the active effective SubscriptionPlan for a coach."""
    sub = get_coach_subscription(coach_id)
    if sub and sub.effective_plan:
        return sub.effective_plan

    free_plan = SubscriptionPlan.query.filter_by(slug='free').first()
    if not free_plan:
        free_plan = seed_default_plans().get('free')
    return free_plan


def get_active_client_count(coach_id):
    """
    Consistent definition of an active client for a coach:
    Clients currently contracted or assigned to the coach.
    """
    active_contract_clients = db.session.query(ClientContract.client_id).filter(
        ClientContract.coach_id == coach_id,
        ClientContract.status == 'active',
        or_(ClientContract.end_date == None, ClientContract.end_date >= datetime.utcnow())
    ).distinct().count()

    assigned_clients = ClientProfile.query.filter_by(coach_id=coach_id).count()
    return max(active_contract_clients, assigned_clients)


def can_coach_add_client(coach_id, count_incoming=1):
    """
    Check if a coach can add or link additional client(s).
    Returns dict:
      {
        'allowed': bool,
        'current_count': int,
        'max_limit': int or None,
        'is_unlimited': bool,
        'plan_name': str,
        'message': str
      }
    """
    plan = get_coach_plan(coach_id)
    current_count = get_active_client_count(coach_id)
    is_unlimited = bool(plan.is_unlimited_clients or plan.max_clients is None)
    max_limit = None if is_unlimited else plan.max_clients

    if is_unlimited:
        return {
            'allowed': True,
            'current_count': current_count,
            'max_limit': None,
            'is_unlimited': True,
            'plan_name': plan.name,
            'message': 'Unlimited client capacity'
        }

    allowed = (current_count + count_incoming) <= max_limit
    if not allowed:
        msg = (
            f"Coach has reached the maximum client capacity ({current_count}/{max_limit}) "
            f"for the {plan.name} plan. An upgrade to Basic or Premium is required to add more clients."
        )
    else:
        msg = f"Within capacity: {current_count}/{max_limit} active clients"

    return {
        'allowed': allowed,
        'current_count': current_count,
        'max_limit': max_limit,
        'is_unlimited': False,
        'plan_name': plan.name,
        'message': msg
    }


def has_feature_access(coach_id, feature_key):
    """Return True if coach's active plan grants access to the specified feature."""
    plan = get_coach_plan(coach_id)
    if not plan:
        return False
    return plan.has_feature(feature_key)


def get_feature_limit(coach_id, feature_key, default=None):
    """Return numeric limit for a feature on the coach's plan."""
    plan = get_coach_plan(coach_id)
    if not plan:
        return default
    return plan.get_feature_limits().get(feature_key, default)


def log_subscription_change(coach_id, changed_by_user_id, old_plan_id, new_plan_id, action, reason=''):
    """Audit log for any subscription plan change or override."""
    try:
        log = SubscriptionAuditLog(
            coach_id=coach_id,
            changed_by_user_id=changed_by_user_id,
            old_plan_id=old_plan_id,
            new_plan_id=new_plan_id,
            action=action,
            reason=reason or ''
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Failed to record subscription audit log: {e}")


def require_plan_feature(feature_key, feature_name=None):
    """
    Decorator for coach views: enforces backend feature-level entitlement.
    Blocks unauthorized access with redirect and friendly upgrade message.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not getattr(current_user, 'is_coach', False) or not current_user.coach_profile:
                flash('Coach access required.', 'danger')
                return redirect(url_for('main.index'))

            coach_id = current_user.coach_profile.id
            if not has_feature_access(coach_id, feature_key):
                display_name = feature_name or feature_key.replace('_', ' ').title()
                msg = f"The '{display_name}' feature is not included in your current subscription plan. Please upgrade your plan to unlock it."
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': msg, 'upgrade_url': url_for('coach.subscription')}), 403
                flash(msg, 'warning')
                return redirect(url_for('coach.subscription'))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def seed_default_plans():
    """
    Seed Free ($0, max 5 clients), Basic ($19/mo, max 15 clients),
    and Premium ($49/mo, unlimited clients) idempotently.
    Also ensures all existing coaches have a valid subscription.
    """
    plans = {}
    default_defs = [
        {
            'slug': 'free',
            'name': 'Free',
            'price': 0.0,
            'currency': 'USD',
            'billing_interval': 'monthly',
            'max_clients': 5,
            'is_unlimited_clients': False,
            'display_order': 1,
            'description': 'Essential features for new coaches beginning their client roster.',
            'features': {
                'program_builder': True,
                'exercise_library': True,
                'progress_tracking': True,
                'video_uploads': True,
                'messaging': True,
                'scheduling': True,
                'analytics': False,
            }
        },
        {
            'slug': 'basic',
            'name': 'Basic',
            'price': 19.0,
            'currency': 'USD',
            'billing_interval': 'monthly',
            'max_clients': 15,
            'is_unlimited_clients': False,
            'display_order': 2,
            'description': 'For established coaches expanding their active athlete roster.',
            'features': {
                'program_builder': True,
                'exercise_library': True,
                'progress_tracking': True,
                'video_uploads': True,
                'messaging': True,
                'scheduling': True,
                'analytics': True,
            }
        },
        {
            'slug': 'premium',
            'name': 'Premium',
            'price': 49.0,
            'currency': 'USD',
            'billing_interval': 'monthly',
            'max_clients': None,
            'is_unlimited_clients': True,
            'display_order': 3,
            'description': 'Unlimited clients and premier features for elite fitness professionals.',
            'features': {
                'program_builder': True,
                'exercise_library': True,
                'progress_tracking': True,
                'video_uploads': True,
                'messaging': True,
                'scheduling': True,
                'analytics': True,
            }
        }
    ]

    for d in default_defs:
        plan = SubscriptionPlan.query.filter_by(slug=d['slug']).first()
        if not plan:
            plan = SubscriptionPlan(
                name=d['name'],
                slug=d['slug'],
                price=d['price'],
                currency=d['currency'],
                billing_interval=d['billing_interval'],
                max_clients=d['max_clients'],
                is_unlimited_clients=d['is_unlimited_clients'],
                display_order=d['display_order'],
                description=d['description'],
                is_active=True
            )
            plan.set_features(d['features'])
            db.session.add(plan)
            db.session.commit()
        plans[d['slug']] = plan

    # Ensure all existing coach profiles have an active subscription
    free_plan = plans.get('free') or SubscriptionPlan.query.filter_by(slug='free').first()
    if free_plan:
        all_coaches = CoachProfile.query.all()
        for coach in all_coaches:
            existing_sub = CoachSubscription.query.filter_by(coach_id=coach.id).first()
            if not existing_sub:
                new_sub = CoachSubscription(
                    coach_id=coach.id,
                    plan_id=free_plan.id,
                    status='active',
                    billing_interval='monthly',
                    current_price=free_plan.price,
                    currency=free_plan.currency or 'USD',
                    started_at=datetime.utcnow(),
                    current_period_start=datetime.utcnow(),
                    current_period_end=None,
                    auto_renew=True
                )
                db.session.add(new_sub)
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

    return plans
