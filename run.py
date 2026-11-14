import os
from app import create_app, socketio
from app.extensions import db
from app.models.user import User, Role, CoachProfile, ClientProfile
from app.models.calendar import CoachScheduleConfig, CoachAvailability, Appointment

app = create_app(os.getenv('FLASK_CONFIG') or 'default')

def make_shell_context():
    return dict(db=db, User=User, Role=Role, CoachProfile=CoachProfile, ClientProfile=ClientProfile)

app.shell_context_processor(make_shell_context)

@app.cli.command('create-superadmin')
def cli_create_superadmin():
    """Create or promote a superadmin user."""
    from create_superadmin import create_superadmin
    create_superadmin()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0' if os.environ.get('PORT') else '127.0.0.1')
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() in ('true', '1', 'yes')
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
