from datetime import datetime
from app.extensions import db

class ClientProgram(db.Model):
    """Links a client to an assigned program."""
    __tablename__ = 'client_programs'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(32), default='sent')  # 'sent', 'viewed', 'accepted', 'active', 'archived'
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('ClientProfile', backref=db.backref('client_programs', lazy='dynamic'))
    program = db.relationship('Program', backref=db.backref('client_programs', lazy='dynamic'))

class WorkoutCompletion(db.Model):
    """Records when a client completes a workout."""
    __tablename__ = 'workout_completions'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    workout_id = db.Column(db.Integer, db.ForeignKey('workouts.id'), nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    client_notes = db.Column(db.Text)
    perceived_effort = db.Column(db.Integer)  # 1-10 RPE scale
    video_filename = db.Column(db.String(255), nullable=True)
    coach_feedback = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    client = db.relationship('ClientProfile', backref=db.backref('completions', lazy='dynamic'))
    workout = db.relationship('Workout', backref=db.backref('completions', lazy='dynamic'))

class ExerciseCompletion(db.Model):
    """Records exercise-level data logged by the client during a workout."""
    __tablename__ = 'exercise_completions'
    id = db.Column(db.Integer, primary_key=True)
    workout_completion_id = db.Column(db.Integer, db.ForeignKey('workout_completions.id'), nullable=False)
    workout_exercise_id = db.Column(db.Integer, db.ForeignKey('workout_exercises.id'), nullable=False)
    actual_sets = db.Column(db.Integer)
    actual_reps = db.Column(db.String(32))
    actual_weight = db.Column(db.String(32))
    set_details = db.Column(db.Text, nullable=True)  # JSON string of set-by-set logs
    notes = db.Column(db.Text)

    workout_completion = db.relationship('WorkoutCompletion', backref=db.backref('exercise_completions', lazy='dynamic'))
    workout_exercise = db.relationship('WorkoutExercise')

class BodyweightLog(db.Model):
    """Tracks client bodyweight entries over time."""
    __tablename__ = 'bodyweight_logs'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(8), default='lbs')
    date = db.Column(db.Date, default=datetime.utcnow().date)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('ClientProfile', backref=db.backref('bodyweight_logs', lazy='dynamic', cascade='all, delete-orphan'))

class ProgressPhoto(db.Model):
    """Tracks client physique progress photos."""
    __tablename__ = 'progress_photos'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    photo_filename = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(32), default='front')  # front, side, back, other
    date = db.Column(db.Date, default=datetime.utcnow().date)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('ClientProfile', backref=db.backref('progress_photos', lazy='dynamic', cascade='all, delete-orphan'))

class FormCheckSubmission(db.Model):
    """Client submissions of exercise form check videos for coach review."""
    __tablename__ = 'form_check_submissions'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client_profiles.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=True)
    exercise_name = db.Column(db.String(128), nullable=True)
    video_filename = db.Column(db.String(255), nullable=False)
    client_notes = db.Column(db.Text, nullable=True)
    coach_feedback = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), default='pending')  # pending, reviewed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    client = db.relationship('ClientProfile', backref=db.backref('form_checks', lazy='dynamic', cascade='all, delete-orphan'))
    exercise = db.relationship('Exercise')
