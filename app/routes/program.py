from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Program, ProgramDay, Workout, Exercise, CoachProfile

program_bp = Blueprint('program', __name__, url_prefix='/coach/program')

# ------------------------------------------------------------------
# Helper – ensure coach profile exists
# ------------------------------------------------------------------
def _coach():
    coach = current_user.coach_profile
    if not coach:
        flash('Coach profile required.', 'danger')
    return coach

# ------------------------------------------------------------------
# List programs
# ------------------------------------------------------------------
@program_bp.route('/')
@login_required
def index():
    coach = _coach()
    if not coach:
        return redirect(url_for('coach.dashboard'))
    programs = coach.programs
    return render_template('coach/programs.html', programs=programs, coach=coach)

# ------------------------------------------------------------------
# Create a new program (title/description)
# ------------------------------------------------------------------
@program_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    coach = _coach()
    if not coach:
        return redirect(url_for('coach.dashboard'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        if not title:
            flash('Title is required.', 'danger')
        else:
            prog = Program(coach_id=coach.id, title=title, description=description)
            db.session.add(prog)
            db.session.commit()
            flash('Program created.', 'success')
            return redirect(url_for('program.edit', program_id=prog.id))
    return render_template('coach/program_create.html', coach=coach)

# ------------------------------------------------------------------
# Edit a program – add days (individual or bulk via weekdays)
# ------------------------------------------------------------------
@program_bp.route('/<int:program_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(program_id):
    coach = _coach()
    program = Program.query.filter_by(id=program_id, coach_id=coach.id).first_or_404()

    if request.method == 'POST':
        # ---- Bulk weekday creation ------------------------------------------------
        if 'generate_days' in request.form:
            selected = request.form.getlist('weekdays')  # e.g. ['Monday', 'Tuesday']
            if not selected:
                flash('Select at least one day.', 'danger')
            else:
                # keep order based on calendar week
                weekday_order = {
                    'Monday': 1, 'Tuesday': 2, 'Wednesday': 3, 'Thursday': 4,
                    'Friday': 5, 'Saturday': 6, 'Sunday': 7
                }
                existing_names = {d.name for d in program.days}
                # sort selected days by weekday order
                for day_name in sorted(selected, key=lambda d: weekday_order.get(d, 99)):
                    if day_name in existing_names:
                        continue
                    order = len(program.days) + 1
                    new_day = ProgramDay(program_id=program.id, order=order, name=day_name)
                    db.session.add(new_day)
                    existing_names.add(day_name)
                db.session.commit()
                flash('Selected days added.', 'success')
            return redirect(url_for('program.edit', program_id=program.id))

        # ---- Add a single day (fallback) ------------------------------------------
        if 'add_day' in request.form:
            name = request.form.get('day_name', '').strip() or f"Day {len(program.days)+1}"
            day = ProgramDay(program_id=program.id, order=len(program.days)+1, name=name,
                             is_rest=('rest' in request.form))
            db.session.add(day)
            db.session.commit()
            flash(f'Day "{name}" added.', 'success')
            return redirect(url_for('program.edit', program_id=program.id))

        # ---- Delete a day ----------------------------------------------------------
        if 'delete_day' in request.form:
            day_id = int(request.form['day_id'])
            ProgramDay.query.filter_by(id=day_id, program_id=program.id).delete()
            # re‑order remaining days
            remaining = ProgramDay.query.filter_by(program_id=program.id).order_by(ProgramDay.order).all()
            for idx, d in enumerate(remaining, start=1):
                d.order = idx
            db.session.commit()
            flash('Day removed.', 'info')
            return redirect(url_for('program.edit', program_id=program.id))

    return render_template('coach/program_edit.html', program=program, coach=coach,
                           exercises=coach.exercises)

# ------------------------------------------------------------------
# Add a workout to a day
# ------------------------------------------------------------------
@program_bp.route('/day/<int:day_id>/add_workout', methods=['POST'])
@login_required
def add_workout(day_id):
    coach = _coach()
    day = ProgramDay.query.join(Program).filter(
        ProgramDay.id == day_id,
        Program.coach_id == coach.id
    ).first_or_404()

    exercise_id = int(request.form['exercise_id'])
    # verify exercise belongs to this coach
    exercise = Exercise.query.filter_by(id=exercise_id, coach_id=coach.id).first_or_404()

    sets = request.form.get('sets') or None
    reps = request.form.get('reps') or None
    duration = request.form.get('duration') or None

    wk = Workout(
        day_id=day.id,
        exercise_id=exercise.id,
        sets=int(sets) if sets else None,
        reps=int(reps) if reps else None,
        duration_seconds=int(duration) if duration else None,
        notes=request.form.get('notes', '').strip()
    )
    db.session.add(wk)
    db.session.commit()
    flash('Workout added.', 'success')
    return redirect(url_for('program.edit', program_id=day.program_id))

# ------------------------------------------------------------------
# Delete a workout
# ------------------------------------------------------------------
@program_bp.route('/workout/<int:workout_id>/delete', methods=['POST'])
@login_required
def delete_workout(workout_id):
    coach = _coach()
    wk = Workout.query.join(ProgramDay).join(Program).filter(
        Workout.id == workout_id,
        Program.coach_id == coach.id
    ).first_or_404()
    prog_id = wk.day.program_id
    db.session.delete(wk)
    db.session.commit()
    flash('Workout removed.', 'info')
    return redirect(url_for('program.edit', program_id=prog_id))
