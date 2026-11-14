# Kentaro Online Fitness Coaching Platform - Development Status & Continuation Guide

## 1. Project Overview & Current Architecture
Kentaro is a multi-role online fitness coaching web application built with:
- **Backend**: Python 3.12, Flask, Flask-SQLAlchemy, Flask-Migrate (Alembic), Flask-Login, Flask-SocketIO
- **Database**: SQLite (managed by Flask-SQLAlchemy at instance/kentaro.db)
- **Frontend**: Jinja2 HTML5 templates styled with TailwindCSS (responsive layouts, modern cards, and interactive navigation)
- **Real-Time Communication**: Socket.IO for in-app chat notifications, voice call signaling, and appointment alerts
- **User Roles**:
  - dmin / superadmin: Access to Admin Dashboard (/admin/dashboard), system statistics, and video management (/admin/videos)
  - coach: Client roster, weekly schedules, workout programs, exercise library, package management with Paystack link configuration
  - client: Workout logging, video form check submissions, bodyweight & photo tracking, coaching session booking, package checkout

---

## 2. Recent Implementation Checkpoints (Current State)

### A. Admin Authentication & Management
- Added route guard and login page: /admin/login
- Added comprehensive Admin Dashboard: /admin/dashboard
- Seeded default admin account:
  - **Email**: dmin@kentaro.test
  - **Password**: dmin123
- Added Video Manager view: /admin/videos with thumbnail preview and deletion capability.

### B. Profile Completion Guard
- In pp/models/user.py, CoachProfile.is_complete verifies that all core coach details (first name, last name, photo, bio, specialization, experience, location, timezone, currency, YouTube link) are populated (all except instagram_url).
- In pp/routes/main.py, /coaches directory only exposes coaches who have marked is_complete == True.
- In /coach/<id>, visitors viewing an incomplete profile receive a user-friendly status page (pp/templates/public/coach_incomplete.html).

### C. Coach & Client Profile Deletion (Cascade)
- **Coach Deletion** (POST /coach/delete_profile):
  - Safely unlinks active clients (coach_id=None, ctive_package_id=None)
  - Deletes all coach appointments (Appointment)
  - Deletes availability rules & meeting configs (CoachAvailability, CoachScheduleConfig)
  - Deletes packages (CoachingPackage)
  - Deletes coach-created workout programs and exercises
  - Deletes associated chat messages and logs out user.
- **Client Deletion** (POST /client/delete_profile):
  - Deletes workout completions and exercise completion records
  - Deletes bodyweight logs, progress photos, and video form checks
  - Deletes appointments and program assignments
  - Deletes chat messages and permanently removes client record.

### D. Package Management & Paystack Dummy Flow
- Added column payment_link to CoachingPackage (Alembic migration applied).
- Coaches can input custom Paystack payment links (or leave blank to use the test simulation).
- Package selection (/client/select-package/<id>) redirects to the secure checkout simulation (/client/dummy-payment/<id>).
- If a package has no custom link, a test link https://example.com/pay is displayed alongside an instant **Complete Payment & Onboard** button.
- On simulated completion (/client/payment-success/<id>), the package is assigned, the coach is notified via Socket.IO, and the client is redirected to their dashboard.

### E. Styling & Responsiveness
- All dashboard navigation links use unified Tailwind styling: 	ext-blue-600 hover:underline transition-colors.
- The global navigation bar (pp/templates/base.html) features a responsive mobile hamburger drawer with quick navigation links for Admin, Coach, and Client roles.
- All dashboard views utilize responsive flex/grid layouts (grid-cols-1 md:grid-cols-2 lg:grid-cols-3).

---

## 3. Instructions for Continuing Development with Another Antigravity / Git Workspace

If you pull this repository into another environment or continue with another Antigravity account:

### 1. Clone & Set Up Python Environment
`powershell
# Clone the repository
git clone <YOUR_REPO_URL>
cd kentaro

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
`

### 2. Environment Variables (.env)
Create or verify your .env file at the project root:
`ini
FLASK_APP=run.py
FLASK_ENV=development
SECRET_KEY=dev-secret-key-change-in-production
DATABASE_URL=sqlite:///instance/kentaro.db
UPLOAD_FOLDER=app/static/uploads
`

### 3. Database Migration Status
The SQLite database file resides at instance/kentaro.db.
If pulling fresh code into an empty database, run:
`powershell
flask db upgrade
`
To seed the test admin user:
`powershell
python -c from app import create_app, db; from app.models.user import User, Role; app = create_app(); app.app_context().push(); r = Role.query.filter_by(name='admin').first() or Role(name='admin'); db.session.add(r); db.session.commit(); u = User.query.filter_by(email='admin@kentaro.test').first() or User(email='admin@kentaro.test', role=r); u.password = 'admin123'; db.session.add(u); db.session.commit(); print('Admin account ready: admin@kentaro.test / admin123')
`

### 4. Running the Development Server
`powershell
python run.py
`
Default URL: http://localhost:5000

---

## 4. Key Directory & File Map
- pp/models/: Database models (user.py, coaching.py, workout.py, progress.py, calendar.py)
- pp/routes/: Route controllers (uth.py, main.py, dmin.py, coach.py, client.py, programs.py, exercises.py)
- pp/templates/:
  - ase.html: Global layout, responsive navbar, flash notifications, Socket.IO call listeners
  - dmin/: login.html, dashboard.html, ideos.html
  - coach/: dashboard.html, packages.html, clients.html, schedule.html, onboarding.html
  - client/: dashboard.html, dummy_payment.html, select_package.html, progress.html, ppointments.html
  - public/: coaches.html, coach_profile.html, coach_incomplete.html
