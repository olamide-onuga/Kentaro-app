from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.extensions import db, login_manager

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    users = db.relationship('User', backref='role', lazy='dynamic')
    
    def __repr__(self):
        return f'<Role {self.name}>'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(256))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    online = db.Column(db.Boolean, default=False, nullable=False)  # Real-time presence flag
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    timezone = db.Column(db.String(64), default='UTC')
    is_email_confirmed = db.Column(db.Boolean, default=False, nullable=False)  # Email confirmation flag
    display_name = db.Column(db.String(64), nullable=True)  # Admin/user display name
    admin_permissions = db.Column(db.Text, nullable=True)  # JSON dictionary of granted permissions
    admin_status = db.Column(db.String(32), default='active')  # 'active', 'suspended', 'deactivated'
    admin_created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # Real-time presence flag — updated on socket connect/disconnect
# duplicate online column removed
    
    # Relationships
    coach_profile = db.relationship('CoachProfile', backref='user', uselist=False)
    client_profile = db.relationship('ClientProfile', backref='user', uselist=False)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    @property
    def admin_display_name(self):
        if getattr(self, 'display_name', None) and self.display_name and self.display_name.strip():
            return self.display_name.strip()
        if self.email:
            prefix = self.email.split('@')[0]
            clean = prefix.replace('.', ' ').replace('_', ' ').replace('-', ' ').title()
            return clean
        return "Support Administrator"

    @property
    def is_superadmin(self):
        return (self.role is not None and self.role.name == 'superadmin')

    @property
    def is_primary_superadmin(self):
        return bool(self.is_superadmin and (self.email == 'admin@kentaro.test' or self.id == 3))

    def has_perm(self, perm_key):
        if self.is_superadmin:
            return True
        if not self.is_admin or getattr(self, 'admin_status', 'active') != 'active':
            return False
        raw = getattr(self, 'admin_permissions', None)
        if not raw:
            return True  # Default legacy admin has permissions
        try:
            import json
            perms = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(perms, dict):
                return bool(perms.get(perm_key, False) or perms.get('all', False))
            if isinstance(perms, list):
                return bool(perm_key in perms or 'all' in perms)
        except Exception:
            pass
        return False

    def get_permissions_dict(self):
        default_keys = ['manage_coaches', 'manage_clients', 'manage_support', 'manage_marketplace', 'view_financials', 'manage_content']
        if self.is_superadmin:
            return {k: True for k in default_keys}
        raw = getattr(self, 'admin_permissions', None)
        if not raw:
            return {k: True for k in default_keys}
        try:
            import json
            perms = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(perms, dict):
                return {k: bool(perms.get(k, False)) for k in default_keys}
            if isinstance(perms, list):
                return {k: (k in perms) for k in default_keys}
        except Exception:
            pass
        return {k: False for k in default_keys}
        
    @property
    def is_coach(self):
        if self.role is not None and self.role.name == 'coach':
            return True
        return self.coach_profile is not None
        
    @property
    def is_client(self):
        if self.role is not None and self.role.name == 'client':
            return True
        return self.client_profile is not None

    def __repr__(self):
        return f'<User {self.email}>'

class AccountAppeal(db.Model):
    __tablename__ = 'account_appeals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(32), default='pending')  # 'pending', 'approved', 'rejected'
    admin_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('appeals', lazy='dynamic', cascade='all, delete-orphan'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class CoachProfile(db.Model):
    __tablename__ = 'coach_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    profile_photo = db.Column(db.String(255))
    bio = db.Column(db.Text)
    specialization = db.Column(db.String(128))
    experience_years = db.Column(db.Integer)
    location = db.Column(db.String(128))
    timezone = db.Column(db.String(64))
    currency = db.Column(db.String(3), default='USD')
    instagram_url = db.Column(db.String(255))
    youtube_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Additional fields like paystack config / payment link
    payment_link = db.Column(db.String(512), nullable=True)
    paystack_public_key = db.Column(db.String(255))
    paystack_secret_key = db.Column(db.String(255))
    
    # Admin controls
    is_verified = db.Column(db.Boolean, default=True)
    is_approved = db.Column(db.Boolean, default=True)
    
    # clients relationship will go here
    clients = db.relationship('ClientProfile', backref='coach', lazy='dynamic')

    @property
    def is_complete(self):
        """Return True if all required profile fields are completed.
        Note: payment_link is NOT required for profile completeness -
        it's only required when creating packages or sending offers."""
        return bool(
            self.first_name and str(self.first_name).strip() and
            self.last_name and str(self.last_name).strip() and
            self.bio and str(self.bio).strip() and
            self.specialization and str(self.specialization).strip()
        )

    @property
    def average_rating(self):
        try:
            from app.models.features import CoachReview
            reviews = CoachReview.query.filter_by(coach_id=self.id, is_visible=True).all()
            if not reviews:
                return 5.0
            return round(sum(r.rating for r in reviews) / len(reviews), 1)
        except Exception:
            return 5.0

    @property
    def review_count(self):
        try:
            from app.models.features import CoachReview
            return CoachReview.query.filter_by(coach_id=self.id, is_visible=True).count()
        except Exception:
            return 0

class ClientProfile(db.Model):
    __tablename__ = 'client_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'))
    active_package_id = db.Column(db.Integer, db.ForeignKey('coaching_packages.id'))
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    profile_photo = db.Column(db.String(255))
    timezone = db.Column(db.String(64), default='UTC')
    phone = db.Column(db.String(32))
    fitness_goals = db.Column(db.Text)
    bio = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    active_package = db.relationship('CoachingPackage', foreign_keys=[active_package_id])

    @property
    def is_complete(self):
        """Return True if client has filled their first and last name."""
        return bool(
            self.first_name and str(self.first_name).strip() and
            self.last_name and str(self.last_name).strip()
        )

    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or "Athlete"

class VoiceMessage(db.Model):
    __tablename__ = 'voice_messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    voice_url = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    is_anonymous = db.Column(db.Boolean, default=False)
    is_edited = db.Column(db.Boolean, default=False)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'), nullable=True)
    context = db.Column(db.String(20), default='direct')  # 'direct', 'marketplace', 'coaching', 'support', 'archived'
    message_type = db.Column(db.String(32), default='text')  # 'text', 'voice', 'offer', 'program'
    post_id = db.Column(db.Integer, db.ForeignKey('client_posts.id'), nullable=True)
    post = db.relationship('ClientPost', foreign_keys=[post_id])
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_tickets.id'), nullable=True)
    ticket = db.relationship('SupportTicket', foreign_keys=[ticket_id])
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id'), nullable=True)
    program = db.relationship('Program', foreign_keys=[program_id])
    offer_id = db.Column(db.Integer, db.ForeignKey('custom_program_offers.id'), nullable=True)
    offer = db.relationship('CustomProgramOffer', foreign_keys=[offer_id])

    sender = db.relationship('User', foreign_keys=[sender_id], backref=db.backref('sent_messages', lazy='dynamic'))
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref=db.backref('received_messages', lazy='dynamic'))
    reply_to = db.relationship('ChatMessage', foreign_keys=[reply_to_id], remote_side='ChatMessage.id')

    @property
    def content(self):
        return self.message

    @content.setter
    def content(self, val):
        self.message = val

