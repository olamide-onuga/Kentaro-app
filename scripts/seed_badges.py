import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from run import app
from app.extensions import db
from app.models.features import Badge

BADGES = [
    ('first_workout',   'First Workout',     'Completed your very first workout!',         '🏋️'),
    ('week_streak',     '7-Day Streak',      'Worked out 7 days in a row',                  '🔥'),
    ('month_streak',    '30-Day Streak',     'Incredible! 30 days straight',                '🌟'),
    ('first_checkin',   'First Check-In',    'Submitted your first weekly check-in',        '📋'),
    ('first_month',     'First Month Done',  'Completed your first month of coaching',      '🎯'),
    ('consistency',     'Consistency King',  'Logged nutrition for 7 days straight',        '🥗'),
    ('form_check',      'Form Check Pro',    'Submitted your first form check video',       '🎥'),
]

with app.app_context():
    for slug, name, desc, icon in BADGES:
        if not Badge.query.filter_by(slug=slug).first():
            db.session.add(Badge(slug=slug, name=name, description=desc, icon=icon))
    db.session.commit()
    print('Badges seeded!')
