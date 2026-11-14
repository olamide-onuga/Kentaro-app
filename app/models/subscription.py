from datetime import datetime
import json
from app.extensions import db

DEFAULT_FEATURES = {
    'program_builder': True,
    'exercise_library': True,
    'progress_tracking': True,
    'video_uploads': True,
    'messaging': True,
    'scheduling': True,
    'analytics': True,
}

FEATURE_LABELS = {
    'program_builder': 'Program & Workout Builder',
    'exercise_library': 'Exercise Library Access',
    'progress_tracking': 'Client Progress Tracking & Program Adjustments',
    'video_uploads': 'Exercise Video Uploads',
    'messaging': 'Direct Coach-Client Messaging & Chat',
    'scheduling': 'Scheduling & Calendar Management',
    'analytics': 'Advanced Analytics & Earnings Reports',
}

class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    slug = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, default=0.0, nullable=False)
    currency = db.Column(db.String(3), default='USD', nullable=False)
    billing_interval = db.Column(db.String(16), default='monthly', nullable=False)  # 'monthly', 'yearly'
    max_clients = db.Column(db.Integer, nullable=True)  # None = unlimited
    is_unlimited_clients = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    features = db.Column(db.Text, nullable=True)  # JSON dictionary of boolean entitlements
    feature_limits = db.Column(db.Text, nullable=True)  # JSON dictionary of numeric limits
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_features(self):
        result = dict(DEFAULT_FEATURES)
        if self.features:
            try:
                loaded = json.loads(self.features)
                if isinstance(loaded, dict):
                    result.update(loaded)
            except Exception:
                pass
        return result

    def set_features(self, feat_dict):
        if not isinstance(feat_dict, dict):
            feat_dict = {}
        self.features = json.dumps(feat_dict)

    def has_feature(self, feature_key):
        return bool(self.get_features().get(feature_key, False))

    def get_feature_limits(self):
        if self.feature_limits:
            try:
                loaded = json.loads(self.feature_limits)
                if isinstance(loaded, dict):
                    return loaded
            except Exception:
                pass
        return {}

    def set_feature_limits(self, limits_dict):
        if not isinstance(limits_dict, dict):
            limits_dict = {}
        self.feature_limits = json.dumps(limits_dict)

    @property
    def client_limit_display(self):
        if self.is_unlimited_clients or self.max_clients is None:
            return "Unlimited"
        return f"{self.max_clients} clients"

    @property
    def price_display(self):
        if self.price == 0:
            return "Free"
        return f"${self.price:,.2f}/{'mo' if self.billing_interval == 'monthly' else 'yr'}"

    @property
    def subscribers_count(self):
        from app.models.subscription import CoachSubscription
        return CoachSubscription.query.filter_by(plan_id=self.id, status='active').count()


class CoachSubscription(db.Model):
    __tablename__ = 'coach_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), unique=True, nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)
    status = db.Column(db.String(32), default='active', nullable=False)  # 'active', 'past_due', 'cancelled', 'expired'
    billing_interval = db.Column(db.String(16), default='monthly', nullable=False)
    current_price = db.Column(db.Float, default=0.0, nullable=False)
    currency = db.Column(db.String(3), default='USD', nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    current_period_start = db.Column(db.DateTime, default=datetime.utcnow)
    current_period_end = db.Column(db.DateTime, nullable=True)  # None = indefinite/free
    paystack_subscription_code = db.Column(db.String(128), nullable=True)
    paystack_customer_code = db.Column(db.String(128), nullable=True)
    paystack_auth_code = db.Column(db.String(128), nullable=True)
    last_payment_date = db.Column(db.DateTime, nullable=True)
    last_payment_reference = db.Column(db.String(128), nullable=True)
    auto_renew = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('subscription', uselist=False))
    plan = db.relationship('SubscriptionPlan', backref=db.backref('coach_subscriptions', lazy='dynamic'))

    @property
    def is_active_and_valid(self):
        if self.status != 'active':
            return False
        if self.current_period_end and self.current_period_end < datetime.utcnow():
            return False
        return True

    @property
    def effective_plan(self):
        if self.is_active_and_valid and self.plan:
            return self.plan
        # Fallback to Free plan
        free_plan = SubscriptionPlan.query.filter_by(slug='free').first()
        if not free_plan:
            free_plan = SubscriptionPlan.query.filter(SubscriptionPlan.price == 0).first()
        return free_plan or self.plan

    @property
    def recent_payments(self):
        from app.models.subscription import SubscriptionPayment
        return SubscriptionPayment.query.filter_by(subscription_id=self.id).order_by(SubscriptionPayment.created_at.desc()).limit(5).all()


class SubscriptionAuditLog(db.Model):
    __tablename__ = 'subscription_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    old_plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=True)
    new_plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)
    action = db.Column(db.String(64), nullable=False)  # 'admin_assign', 'coach_upgrade', 'coach_downgrade', 'auto_expire', 'system_seed'
    reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('CoachProfile')
    changed_by = db.relationship('User')
    old_plan = db.relationship('SubscriptionPlan', foreign_keys=[old_plan_id])
    new_plan = db.relationship('SubscriptionPlan', foreign_keys=[new_plan_id])


class SubscriptionPayment(db.Model):
    __tablename__ = 'subscription_payments'

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('coach_subscriptions.id'), nullable=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)
    reference = db.Column(db.String(128), unique=True, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD', nullable=False)
    amount_paid_ngn = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(32), default='pending', nullable=False)  # 'pending', 'successful', 'failed'
    gateway = db.Column(db.String(32), default='paystack', nullable=False)
    channel = db.Column(db.String(64), nullable=True)
    gateway_response = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)

    subscription = db.relationship('CoachSubscription', backref=db.backref('payments', lazy='dynamic'))
    coach = db.relationship('CoachProfile')
    plan = db.relationship('SubscriptionPlan')
