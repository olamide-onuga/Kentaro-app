from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models.workout import Exercise

exercises_bp = Blueprint('exercises', __name__, url_prefix='/coach/exercises')

@exercises_bp.before_request
@login_required
def require_coach():
    if not current_user.is_coach or not current_user.coach_profile:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    from app.services.entitlements import has_feature_access
    if not has_feature_access(current_user.coach_profile.id, 'exercise_library'):
        flash('The Exercise Library feature is not included in your current subscription plan. Please upgrade your plan to unlock it.', 'warning')
        return redirect(url_for('coach.subscription'))

@exercises_bp.route('/')
def index():
    exercises = Exercise.query.filter_by(coach_id=current_user.coach_profile.id).order_by(Exercise.name.asc()).all()
    global_exercises = Exercise.query.filter_by(coach_id=None).order_by(Exercise.name.asc()).all()
    return render_template('coach/exercises/index.html', exercises=exercises, global_exercises=global_exercises)

@exercises_bp.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        muscle_group = request.form.get('muscle_group', '').strip()
        equipment = request.form.get('equipment', '').strip()
        difficulty = request.form.get('difficulty', '').strip()
        video_url = request.form.get('video_url', '').strip()
        instructions = request.form.get('instructions', '').strip()
        
        if not name:
            flash('Exercise name is required.', 'danger')
            return redirect(url_for('exercises.create'))

        exercise = Exercise(
            coach_id=current_user.coach_profile.id,
            name=name,
            description=description,
            muscle_group=muscle_group,
            equipment=equipment,
            difficulty=difficulty,
            video_url=video_url,
            instructions=instructions
        )
        db.session.add(exercise)
        db.session.commit()
        flash(f'Exercise "{name}" added to your calisthenics library!', 'success')
        return redirect(url_for('exercises.index'))
        
    return render_template('coach/exercises/create.html')

@exercises_bp.route('/delete/<int:exercise_id>', methods=['POST'])
def delete(exercise_id):
    exercise = Exercise.query.filter_by(id=exercise_id, coach_id=current_user.coach_profile.id).first_or_404()
    name = exercise.name
    db.session.delete(exercise)
    db.session.commit()
    flash(f'Exercise "{name}" removed from library.', 'info')
    return redirect(url_for('exercises.index'))
