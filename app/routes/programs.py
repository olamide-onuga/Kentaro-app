from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.workout import Program, ProgramPhase, Workout, WorkoutExercise, Exercise

programs_bp = Blueprint('programs', __name__, url_prefix='/coach/programs')

@programs_bp.before_request
@login_required
def require_coach():
    if not current_user.is_coach or not current_user.coach_profile:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    from app.services.entitlements import has_feature_access
    if not has_feature_access(current_user.coach_profile.id, 'program_builder'):
        flash('The Program & Workout Builder feature is not included in your current subscription plan. Please upgrade your plan to unlock it.', 'warning')
        return redirect(url_for('coach.subscription'))

@programs_bp.route('/')
def index():
    programs = Program.query.filter_by(coach_id=current_user.coach_profile.id).order_by(Program.created_at.desc()).all()
    return render_template('coach/programs/index.html', programs=programs)

@programs_bp.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        initial_phase_name = request.form.get('initial_phase_name', '').strip() or 'Weekly Routine'
        
        if not name:
            flash('Program name is required.', 'danger')
            return redirect(url_for('programs.create'))

        program = Program(
            coach_id=current_user.coach_profile.id,
            name=name,
            description=description
        )
        db.session.add(program)
        db.session.commit()
        
        # Create initial Phase / Routine
        phase = ProgramPhase(program_id=program.id, name=initial_phase_name, order=1)
        db.session.add(phase)
        db.session.commit()

        # All 7 days of the week (Monday through Sunday) are automatically created
        all_weekdays = [
            ('Monday', 1, False, ''),
            ('Tuesday', 2, False, ''),
            ('Wednesday', 3, True, 'Rest & Active Recovery'),
            ('Thursday', 4, False, ''),
            ('Friday', 5, False, ''),
            ('Saturday', 6, False, ''),
            ('Sunday', 7, True, 'Full Rest Day'),
        ]

        for d_name, d_num, is_rest, d_notes in all_weekdays:
            w = Workout(
                phase_id=phase.id,
                name=d_name,
                day_name=d_name,
                week_number=1,
                day_number=d_num,
                scheduled_weekday=d_num,
                is_rest=is_rest,
                notes=d_notes
            )
            db.session.add(w)

        db.session.commit()
        flash(f'Routine "{name}" created with all 7 days of the week (Monday to Sunday)!', 'success')
        return redirect(url_for('programs.builder', program_id=program.id))
        
    return render_template('coach/programs/create.html')

@programs_bp.route('/<int:program_id>/builder')
def builder(program_id):
    program = Program.query.filter_by(id=program_id, coach_id=current_user.coach_profile.id).first_or_404()
    
    # Ensure all 7 days of the week exist in the phase
    phase = program.phases.order_by(ProgramPhase.order.asc()).first()
    if not phase:
        phase = ProgramPhase(program_id=program.id, name='Weekly Routine', order=1)
        db.session.add(phase)
        db.session.commit()

    day_map = {
        'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4,
        'friday': 5, 'saturday': 6, 'sunday': 7
    }
    weekday_names = {
        1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday',
        5: 'Friday', 6: 'Saturday', 7: 'Sunday'
    }
    existing_workouts = phase.workouts.all()
    existing_weekdays = set()

    for w in existing_workouts:
        if not w.scheduled_weekday:
            normalized_name = (w.day_name or w.name or '').strip().lower()
            matched_num = day_map.get(normalized_name, w.day_number)
            if 1 <= matched_num <= 7:
                w.scheduled_weekday = matched_num
                if not w.day_name or w.day_name.lower().startswith('day'):
                    w.day_name = weekday_names[matched_num]
        if w.scheduled_weekday:
            existing_weekdays.add(w.scheduled_weekday)

    for day_num in range(1, 8):
        if day_num not in existing_weekdays:
            day_name = weekday_names[day_num]
            is_rest = (day_num in [3, 7])
            notes = 'Rest & Active Recovery' if is_rest else ''
            new_w = Workout(
                phase_id=phase.id,
                name=day_name,
                day_name=day_name,
                week_number=1,
                day_number=day_num,
                scheduled_weekday=day_num,
                is_rest=is_rest,
                notes=notes
            )
            db.session.add(new_w)

    db.session.commit()

    exercises = Exercise.query.filter((Exercise.coach_id == current_user.coach_profile.id) | (Exercise.coach_id == None)).order_by(Exercise.name.asc()).all()
    return render_template('coach/programs/builder.html', program=program, exercises=exercises)

@programs_bp.route('/<int:program_id>/add-phase', methods=['POST'])
def add_phase(program_id):
    program = Program.query.filter_by(id=program_id, coach_id=current_user.coach_profile.id).first_or_404()
    phase_name = request.form.get('phase_name', '').strip()
    if phase_name:
        order = program.phases.count() + 1
        phase = ProgramPhase(program_id=program.id, name=phase_name, order=order)
        db.session.add(phase)
        db.session.commit()
        flash(f'Phase/Routine block "{phase_name}" added.', 'success')
    return redirect(url_for('programs.builder', program_id=program_id))

@programs_bp.route('/<int:program_id>/rename-phase/<int:phase_id>', methods=['POST'])
def rename_phase(program_id, phase_id):
    program = Program.query.filter_by(id=program_id, coach_id=current_user.coach_profile.id).first_or_404()
    phase = ProgramPhase.query.filter_by(id=phase_id, program_id=program.id).first_or_404()
    new_name = request.form.get('phase_name', '').strip()
    if new_name:
        phase.name = new_name
        db.session.commit()
        flash(f'Block renamed to "{new_name}".', 'success')
    return redirect(url_for('programs.builder', program_id=program_id))

@programs_bp.route('/<int:program_id>/delete-phase/<int:phase_id>', methods=['POST'])
def delete_phase(program_id, phase_id):
    program = Program.query.filter_by(id=program_id, coach_id=current_user.coach_profile.id).first_or_404()
    phase = ProgramPhase.query.filter_by(id=phase_id, program_id=program.id).first_or_404()
    phase_name = phase.name
    db.session.delete(phase)
    db.session.commit()
    flash(f'Phase "{phase_name}" deleted.', 'info')
    return redirect(url_for('programs.builder', program_id=program_id))

@programs_bp.route('/<int:program_id>/add-workout', methods=['POST'])
def add_workout(program_id):
    flash('All 7 days of the week (Monday to Sunday) are already in your routine. Days cannot be added.', 'info')
    return redirect(url_for('programs.builder', program_id=program_id))

@programs_bp.route('/<int:program_id>/workout/<int:workout_id>/toggle-rest', methods=['POST'])
def toggle_rest(program_id, workout_id):
    program = Program.query.filter_by(id=program_id, coach_id=current_user.coach_profile.id).first_or_404()
    workout = Workout.query.get_or_404(workout_id)
    workout.is_rest = not workout.is_rest
    if workout.is_rest and not workout.notes:
        workout.notes = "Rest & Active Recovery Day. Focus on mobility, hydration, and light stretching."
    db.session.commit()
    status_str = "marked as Rest Day" if workout.is_rest else "marked as Workout Training Day"
    flash(f'"{workout.name}" {status_str}.', 'info')
    return redirect(url_for('programs.builder', program_id=program_id))

@programs_bp.route('/<int:program_id>/workout/<int:workout_id>/edit-details', methods=['POST'])
def edit_workout_details(program_id, workout_id):
    program = Program.query.filter_by(id=program_id, coach_id=current_user.coach_profile.id).first_or_404()
    workout = Workout.query.get_or_404(workout_id)
    workout.is_rest = (request.form.get('is_rest') == '1' or request.form.get('is_rest') == 'on')
    workout.notes = request.form.get('notes', '').strip()
    db.session.commit()
    flash(f'Day "{workout.name}" updated.', 'success')
    return redirect(url_for('programs.builder', program_id=program_id))

@programs_bp.route('/<int:program_id>/workout/<int:workout_id>/delete', methods=['POST'])
def delete_workout(program_id, workout_id):
    flash('Days of the week cannot be deleted from the routine. You can mark this day as a Rest Day instead.', 'info')
    return redirect(url_for('programs.builder', program_id=program_id))

@programs_bp.route('/<int:program_id>/workout/<int:workout_id>')
def workout_detail(program_id, workout_id):
    program = Program.query.filter_by(id=program_id, coach_id=current_user.coach_profile.id).first_or_404()
    workout = Workout.query.get_or_404(workout_id)
    exercises = Exercise.query.filter((Exercise.coach_id == current_user.coach_profile.id) | (Exercise.coach_id == None)).order_by(Exercise.name.asc()).all()
    return render_template('coach/programs/workout_detail.html', program=program, workout=workout, exercises=exercises)

@programs_bp.route('/<int:program_id>/workout/<int:workout_id>/add-exercise', methods=['POST'])
def add_exercise(program_id, workout_id):
    program = Program.query.filter_by(id=program_id, coach_id=current_user.coach_profile.id).first_or_404()
    workout = Workout.query.get_or_404(workout_id)
    
    exercise_id = request.form.get('exercise_id')
    new_exercise_name = request.form.get('new_exercise_name', '').strip()
    
    # Check if coach created a brand new exercise inline
    if new_exercise_name and (not exercise_id or exercise_id == 'new'):
        muscle_group = request.form.get('new_muscle_group', 'Push')
        equipment = request.form.get('new_equipment', 'Bodyweight')
        new_ex = Exercise(
            coach_id=current_user.coach_profile.id,
            name=new_exercise_name,
            muscle_group=muscle_group,
            equipment=equipment,
            description=request.form.get('new_description', '')
        )
        db.session.add(new_ex)
        db.session.commit()
        exercise_id = new_ex.id
    elif not exercise_id:
        flash('Please select or create an exercise.', 'warning')
        return redirect(url_for('programs.builder', program_id=program_id))
    
    order = WorkoutExercise.query.filter_by(workout_id=workout_id).count() + 1
    we = WorkoutExercise(
        workout_id=workout_id,
        exercise_id=int(exercise_id),
        order=order,
        sets=request.form.get('sets', type=int) or None,
        reps=request.form.get('reps') or None,
        duration=request.form.get('duration') or None,
        rest=request.form.get('rest') or None,
        tempo=request.form.get('tempo') or None,
        weight=request.form.get('weight') or None,
        notes=request.form.get('notes') or None
    )
    db.session.add(we)
    db.session.commit()
    flash('Exercise added to workout routine!', 'success')
    return redirect(url_for('programs.builder', program_id=program_id))

@programs_bp.route('/<int:program_id>/delete', methods=['POST'])
def delete_program(program_id):
    program = Program.query.filter_by(id=program_id, coach_id=current_user.coach_profile.id).first_or_404()
    name = program.name
    db.session.delete(program)
    db.session.commit()
    flash(f'Program "{name}" deleted.', 'info')
    return redirect(url_for('programs.index'))

@programs_bp.route('/<int:program_id>/workout/<int:workout_id>/remove-exercise/<int:we_id>', methods=['POST'])
def remove_exercise(program_id, workout_id, we_id):
    we = WorkoutExercise.query.get_or_404(we_id)
    db.session.delete(we)
    db.session.commit()
    flash('Exercise removed from workout.', 'info')
    return redirect(url_for('programs.builder', program_id=program_id))
