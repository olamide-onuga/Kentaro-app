from datetime import datetime, time
from app.extensions import db

class CoachScheduleConfig(db.Model):
    """Configuration for coach booking window, slot duration, and meeting platform."""
    __tablename__ = 'coach_schedule_configs'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), unique=True, nullable=False)
    slot_duration = db.Column(db.Integer, default=30)  # minutes (15, 30, 45, 60)
    buffer_minutes = db.Column(db.Integer, default=15)
    meeting_platform = db.Column(db.String(32), default='in_app')  # 'in_app' or 'google_meet'
    google_meet_url = db.Column(db.String(255), nullable=True)
    booking_window_days = db.Column(db.Integer, default=14)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('schedule_config', uselist=False))

class CoachAvailability(db.Model):
    """Weekly available working hours by day of week (0=Monday ... 6=Sunday)."""
    __tablename__ = 'coach_availabilities'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 1=Tuesday, ... 6=Sunday
    start_time = db.Column(db.Time, nullable=False, default=time(9, 0))
    end_time = db.Column(db.Time, nullable=False, default=time(17, 0))
    is_active = db.Column(db.Boolean, default=True)

    coach = db.relationship('CoachProfile', backref=db.backref('availabilities', lazy='dynamic', cascade='all, delete-orphan'))

class Appointment(db.Model):
    """Booked 1-on-1 coaching or review appointment."""
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    title = db.Column(db.String(128), default='1-on-1 Coaching Call')
    client_notes = db.Column(db.Text, nullable=True)
    meeting_platform = db.Column(db.String(32), default='in_app')  # 'in_app' or 'google_meet'
    meeting_url = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(32), default='scheduled')  # 'scheduled', 'completed', 'cancelled'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('CoachProfile', backref=db.backref('appointments', lazy='dynamic'))
    client = db.relationship('ClientProfile', backref=db.backref('appointments', lazy='dynamic'))

    def __repr__(self):
        return f'<Appointment {self.date} {self.start_time} - {self.status}>'


# Backward compatibility alias
CoachAppointment = Appointment
