from datetime import datetime
from app.extensions import db

class CheckIn(db.Model):
    __tablename__ = 'check_ins'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    energy = db.Column(db.Integer)  # 1-10
    sleep_hours = db.Column(db.Float)
    mood = db.Column(db.Integer)  # 1-10
    weight = db.Column(db.Float, nullable=True)
    weight_unit = db.Column(db.String(4), default='kg')
    notes = db.Column(db.Text, nullable=True)
    coach_reply = db.Column(db.Text, nullable=True)
    week_number = db.Column(db.Integer, nullable=True)  # ISO week
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('ClientProfile', backref=db.backref('check_ins', lazy='dynamic', cascade='all, delete-orphan'))
    coach = db.relationship('CoachProfile', backref=db.backref('client_check_ins', lazy='dynamic'))

class SessionNote(db.Model):
    __tablename__ = 'session_notes'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    title = db.Column(db.String(128), default='Session Note')
    summary = db.Column(db.Text, nullable=True)
    homework = db.Column(db.Text, nullable=True)
    next_goal = db.Column(db.Text, nullable=True)
    session_date = db.Column(db.Date, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('session_notes', lazy='dynamic'))
    client = db.relationship('ClientProfile', backref=db.backref('session_notes', lazy='dynamic', cascade='all, delete-orphan'))

class NutritionLog(db.Model):
    __tablename__ = 'nutrition_logs'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)
    meal_name = db.Column(db.String(128), nullable=False)
    calories = db.Column(db.Float, default=0)
    protein_g = db.Column(db.Float, default=0)
    carbs_g = db.Column(db.Float, default=0)
    fat_g = db.Column(db.Float, default=0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('ClientProfile', backref=db.backref('nutrition_logs', lazy='dynamic', cascade='all, delete-orphan'))

class HabitTemplate(db.Model):
    __tablename__ = 'habit_templates'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)  # e.g. "Drink 2L water"
    icon = db.Column(db.String(8), default='✅')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('habit_templates', lazy='dynamic'))
    client = db.relationship('ClientProfile', backref=db.backref('habit_templates', lazy='dynamic', cascade='all, delete-orphan'))

class HabitLog(db.Model):
    __tablename__ = 'habit_logs'
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit_templates.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    habit = db.relationship('HabitTemplate', backref=db.backref('logs', lazy='dynamic'))
    client = db.relationship('ClientProfile', backref=db.backref('habit_logs', lazy='dynamic', cascade='all, delete-orphan'))

class CoachReview(db.Model):
    __tablename__ = 'coach_reviews'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    review_text = db.Column(db.Text, nullable=True)
    is_visible = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('reviews', lazy='dynamic'))
    client = db.relationship('ClientProfile', backref=db.backref('reviews_given', lazy='dynamic'))

class Badge(db.Model):
    __tablename__ = 'badges'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True, nullable=False)  # e.g. 'first_workout'
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.String(255))
    icon = db.Column(db.String(8), default='🏅')
    is_system = db.Column(db.Boolean, default=True)  # False = coach custom
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=True)

class ClientBadge(db.Model):
    __tablename__ = 'client_badges'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badges.id'), nullable=False)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)
    awarded_by = db.Column(db.String(32), default='system')  # 'system' or 'coach'

    client = db.relationship('ClientProfile', backref=db.backref('client_badges', lazy='dynamic', cascade='all, delete-orphan'))
    badge = db.relationship('Badge')

class ReferralLink(db.Model):
    __tablename__ = 'referral_links'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), unique=True, nullable=False)
    slug = db.Column(db.String(32), unique=True, nullable=False)
    referral_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('referral_link', uselist=False))

class MacroTarget(db.Model):
    __tablename__ = 'macro_targets'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), unique=True, nullable=False)
    calories = db.Column(db.Float, default=2000)
    protein_g = db.Column(db.Float, default=150)
    carbs_g = db.Column(db.Float, default=200)
    fat_g = db.Column(db.Float, default=65)
    set_by_coach = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('ClientProfile', backref=db.backref('macro_target', uselist=False))

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SystemReport(db.Model):
    __tablename__ = 'system_reports'
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    report_type = db.Column(db.String(32), default='bug')  # 'coach', 'bug', 'other'
    target_coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=True)
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(32), default='pending')  # 'pending', 'resolved', 'dismissed'
    admin_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reporter = db.relationship('User', foreign_keys=[reporter_id])
    target_coach = db.relationship('CoachProfile', foreign_keys=[target_coach_id])

class ClientPost(db.Model):
    __tablename__ = 'client_posts'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    title = db.Column(db.String(128), nullable=False)
    problem = db.Column(db.Text, nullable=False)
    goal = db.Column(db.Text, nullable=False)
    budget = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(32), default='active')  # 'active', 'closed', 'fulfilled', 'withdrawn'
    
    # Extended Marketplace Fields
    specialization = db.Column(db.String(64), default='Calisthenics & Strength')
    skill_level = db.Column(db.String(32), default='Beginner')  # Beginner, Intermediate, Advanced, Elite
    experience = db.Column(db.String(64), default='0-6 Months')  # 0-6 Months, 6-12 Months, 1-2 Years, 2+ Years
    min_budget = db.Column(db.Float, nullable=True)
    max_budget = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(8), default='USD')
    is_flexible_budget = db.Column(db.Boolean, default=False)
    expectations = db.Column(db.Text, nullable=True)
    preferred_duration = db.Column(db.String(64), default='12 Weeks')
    comm_preference = db.Column(db.String(64), default='In-App Chat & Voice Notes')
    fulfilled_at = db.Column(db.DateTime, nullable=True)
    fulfilled_coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = db.relationship('ClientProfile', backref=db.backref('posts', lazy='dynamic', cascade='all, delete-orphan'))
    fulfilled_coach = db.relationship('CoachProfile', foreign_keys=[fulfilled_coach_id])

    @property
    def budget_display(self):
        if self.is_flexible_budget:
            return "Flexible Budget"
        curr = (self.currency or 'USD').upper()
        if self.min_budget and self.max_budget:
            return f"{curr} {self.min_budget:g} - {self.max_budget:g}"
        elif self.max_budget:
            return f"Up to {curr} {self.max_budget:g}"
        elif self.min_budget:
            return f"From {curr} {self.min_budget:g}"
        return self.budget or "Open / Flexible"

class FriendRequest(db.Model):
    __tablename__ = 'friend_requests'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(32), default='pending')  # 'pending', 'accepted', 'rejected'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], backref=db.backref('sent_friend_requests', lazy='dynamic', cascade='all, delete-orphan'))
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref=db.backref('received_friend_requests', lazy='dynamic', cascade='all, delete-orphan'))

class Community(db.Model):
    __tablename__ = 'communities'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('community', uselist=False))

class CommunityMember(db.Model):
    __tablename__ = 'community_members'
    id = db.Column(db.Integer, primary_key=True)
    community_id = db.Column(db.Integer, db.ForeignKey('communities.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    community = db.relationship('Community', backref=db.backref('members', lazy='dynamic', cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('community_memberships', lazy='dynamic', cascade='all, delete-orphan'))

class CommunityMessage(db.Model):
    __tablename__ = 'community_messages'
    id = db.Column(db.Integer, primary_key=True)
    community_id = db.Column(db.Integer, db.ForeignKey('communities.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=True)
    video_url = db.Column(db.String(255), nullable=True)
    voice_url = db.Column(db.String(255), nullable=True)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('community_messages.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    community = db.relationship('Community', backref=db.backref('messages', lazy='dynamic', cascade='all, delete-orphan'))
    sender = db.relationship('User', foreign_keys=[sender_id])
    reply_to = db.relationship('CommunityMessage', remote_side=[id], backref=db.backref('replies', lazy='dynamic'))





class CustomOffer(db.Model):
    __tablename__ = 'custom_offers'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(8), default='USD')
    duration_weeks = db.Column(db.Integer, default=4)
    payment_link = db.Column(db.String(512), nullable=True)
    status = db.Column(db.String(32), default='pending')  # 'pending', 'accepted', 'declined'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('custom_offers', lazy='dynamic'))
    client = db.relationship('ClientProfile', backref=db.backref('custom_offers', lazy='dynamic'))


class ClosedSupportChat(db.Model):
    __tablename__ = 'closed_support_chats'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    closed_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])


class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    id = db.Column(db.Integer, primary_key=True)
    ticket_ref = db.Column(db.String(32), unique=True, index=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    subject = db.Column(db.String(255), nullable=False, default='Platform Support Request')
    category = db.Column(db.String(64), default='general')
    description = db.Column(db.Text, nullable=True)
    attachment_url = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(32), default='pending')  # 'pending', 'active', 'closed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    accepted_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    closed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reopened_at = db.Column(db.DateTime, nullable=True)
    rating = db.Column(db.Integer, nullable=True)
    rating_feedback = db.Column(db.Text, nullable=True)
    rated_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('support_tickets', lazy='dynamic'))
    assigned_admin = db.relationship('User', foreign_keys=[assigned_admin_id])
    closed_by = db.relationship('User', foreign_keys=[closed_by_id])
    messages = db.relationship('TicketMessage', backref='ticket', lazy='dynamic', cascade='all, delete-orphan')
    support_rating = db.relationship('SupportRating', backref='ticket', uselist=False, cascade='all, delete-orphan')


class TicketMessage(db.Model):
    __tablename__ = 'ticket_messages'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_tickets.id', ondelete='CASCADE'), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_system = db.Column(db.Boolean, default=False)
    attachment_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id])


class SupportRating(db.Model):
    __tablename__ = 'support_ratings'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_tickets.id', ondelete='CASCADE'), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    feedback = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    admin = db.relationship('User', foreign_keys=[admin_id])


class CustomProgramOffer(db.Model):
    __tablename__ = 'custom_program_offers'
    id = db.Column(db.Integer, primary_key=True)
    offer_ref = db.Column(db.String(32), unique=True, index=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id'), nullable=True)
    post_id = db.Column(db.Integer, db.ForeignKey('client_posts.id'), nullable=True)
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(8), default='USD')
    duration_weeks = db.Column(db.Integer, default=4)
    frequency = db.Column(db.String(64), nullable=True)
    goals = db.Column(db.Text, nullable=True)
    instructions = db.Column(db.Text, nullable=True)
    terms = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(32), default='sent')  # 'draft', 'sent', 'viewed', 'accepted', 'paid', 'declined', 'expired', 'cancelled'
    payment_reference = db.Column(db.String(128), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    declined_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('program_offers', lazy='dynamic'))
    client = db.relationship('ClientProfile', backref=db.backref('program_offers', lazy='dynamic'))
    program = db.relationship('Program', foreign_keys=[program_id])
    post = db.relationship('ClientPost', foreign_keys=[post_id])


class AdminActivityLog(db.Model):
    __tablename__ = 'admin_activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50))  # 'user', 'coach', 'bug_report', etc
    target_id = db.Column(db.Integer)
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin = db.relationship('User', foreign_keys=[admin_id])

