from datetime import datetime
from app.extensions import db

class CoachingPackage(db.Model):
    __tablename__ = 'coaching_packages'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'))
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    renewal_monthly_price = db.Column(db.Numeric(10, 2), nullable=True)  # Coach configurable monthly renewal fee
    currency = db.Column(db.String(3), default='USD')
    payment_link = db.Column(db.String(255), nullable=True)
    duration_weeks = db.Column(db.Integer)
    features = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    coach = db.relationship('CoachProfile', backref=db.backref('packages', lazy='dynamic'))

    def __repr__(self):
        return f'<CoachingPackage {self.name}>'

class ClientContract(db.Model):
    __tablename__ = 'client_contracts'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey('coaching_packages.id'), nullable=True)
    status = db.Column(db.String(32), default='active') # active, completed, terminated, expired, pending_renewal
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=True)
    monthly_renewal_price = db.Column(db.Numeric(10, 2), nullable=True)
    months_subscribed = db.Column(db.Integer, default=1)
    auto_renew = db.Column(db.Boolean, default=False)
    discount_applied = db.Column(db.Numeric(10, 2), default=0.0)
    discount_code = db.Column(db.String(64), nullable=True)
    terminated_by = db.Column(db.String(32), nullable=True) # auto, coach, client
    termination_reason = db.Column(db.Text, nullable=True)
    terminated_at = db.Column(db.DateTime, nullable=True)
    termination_status = db.Column(db.String(32), nullable=True) # None, pending_client_approval, approved, declined
    termination_requested_by = db.Column(db.String(32), nullable=True) # coach, client
    termination_requested_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    offer_id = db.Column(db.Integer, db.ForeignKey('custom_program_offers.id'), nullable=True)

    client = db.relationship('ClientProfile', backref=db.backref('contracts', lazy='dynamic', cascade='all, delete-orphan'))
    coach = db.relationship('CoachProfile', backref=db.backref('client_contracts', lazy='dynamic'))
    package = db.relationship('CoachingPackage')
    offer = db.relationship('CustomProgramOffer', foreign_keys=[offer_id])

    def __repr__(self):
        return f'<ClientContract client={self.client_id} status={self.status}>'

class CoachDiscount(db.Model):
    __tablename__ = 'coach_discounts'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    code = db.Column(db.String(32), nullable=False)
    discount_type = db.Column(db.String(16), default='percentage') # percentage or fixed
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    usage_count = db.Column(db.Integer, default=0)
    max_uses = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('discounts', lazy='dynamic'))

    def __repr__(self):
        return f'<CoachDiscount code={self.code}>'
