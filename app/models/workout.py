from datetime import datetime
from app.extensions import db

class Exercise(db.Model):
    __tablename__ = 'exercises'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=True) # Null for global exercises
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    muscle_group = db.Column(db.String(64))
    equipment = db.Column(db.String(64))
    difficulty = db.Column(db.String(32))
    instructions = db.Column(db.Text)
    video_url = db.Column(db.String(255))
    thumbnail_url = db.Column(db.String(255))
    coach_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    coach = db.relationship('CoachProfile', backref=db.backref('exercises', lazy='dynamic'))

class Program(db.Model):
    __tablename__ = 'programs'
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach_profiles.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    coach = db.relationship('CoachProfile', backref=db.backref('programs', lazy='dynamic'))
    phases = db.relationship('ProgramPhase', backref='program', lazy='dynamic', cascade='all, delete-orphan')

class ProgramPhase(db.Model):
    __tablename__ = 'program_phases'
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    order = db.Column(db.Integer, nullable=False, default=1)
    
    workouts = db.relationship('Workout', backref='phase', lazy='dynamic', cascade='all, delete-orphan')

class Workout(db.Model):
    __tablename__ = 'workouts'
    id = db.Column(db.Integer, primary_key=True)
    phase_id = db.Column(db.Integer, db.ForeignKey('program_phases.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    day_name = db.Column(db.String(64), nullable=True) # e.g. "Monday", "Tuesday", "Day 1"
    week_number = db.Column(db.Integer, nullable=False, default=1)
    day_number = db.Column(db.Integer, nullable=False, default=1)
    scheduled_weekday = db.Column(db.Integer, nullable=True)  # 1=Mon ... 7=Sun
    is_rest = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    
    workout_exercises = db.relationship('WorkoutExercise', backref='workout', lazy='dynamic', cascade='all, delete-orphan')

class WorkoutExercise(db.Model):
    __tablename__ = 'workout_exercises'
    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(db.Integer, db.ForeignKey('workouts.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=False)
    order = db.Column(db.Integer, nullable=False, default=1)
    sets = db.Column(db.Integer)
    reps = db.Column(db.String(32)) # Could be "8-10" or "Failure"
    duration = db.Column(db.String(32)) # e.g. "60 sec"
    rest = db.Column(db.String(32)) # e.g. "90 sec"
    tempo = db.Column(db.String(32))
    weight = db.Column(db.String(32))
    distance = db.Column(db.String(32))
    notes = db.Column(db.Text)
    
    exercise = db.relationship('Exercise')
