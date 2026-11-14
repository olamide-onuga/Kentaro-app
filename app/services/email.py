import traceback
from flask import current_app, render_template
from flask_mail import Message
from app.extensions import mail


def send_email(to, subject, template=None, html=None, **kwargs):
    """Send an email via Flask-Mail.

    Args:
        to: Recipient email or list of emails.
        subject: Email subject.
        template: Jinja2 template path (relative to templates/).
        html: Raw HTML body (used if template is None).
        **kwargs: Context vars for the template.
    Returns:
        bool: True on success.
    """
    if isinstance(to, str):
        to = [to]

    if html is None and template:
        try:
            html = render_template(template, **kwargs)
        except Exception as e:
            current_app.logger.error(
                "[email] Template render failed (%s): %s\n%s",
                template, e, traceback.format_exc()
            )
            return False

    if not html:
        current_app.logger.error("[email] No HTML body or template provided.")
        return False

    sender = (
        current_app.config.get("MAIL_DEFAULT_SENDER")
        or current_app.config.get("MAIL_USERNAME")
    )

    msg = Message(subject, recipients=to, sender=sender)
    msg.html = html

    try:
        mail.send(msg)
        current_app.logger.info("[email] Sent to %s — subject: %s", to, subject)
        return True
    except Exception as e:
        current_app.logger.error(
            "[email] Failed to send to %s: %s\n%s", to, e, traceback.format_exc()
        )
        return False


def send_enrollment_email(coach, client, package):
    """Notify coach when a client enrolls."""
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:auto">
      <h2 style="color:#111">New Client Enrolled 🎉</h2>
      <p>Hi Coach {coach.first_name},</p>
      <p><strong>{client.full_name}</strong> just enrolled in your <strong>{package.name}</strong> package.</p>
      <p>Log in to Kentaro to welcome them and get started.</p>
      <hr/><p style="color:#888;font-size:12px">Kentaro Coaching Platform</p>
    </div>"""
    return send_email(coach.user.email, f'New client enrolled: {client.full_name}', html=html)


def send_renewal_email(coach, client, package, months):
    """Notify coach when a client renews."""
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:auto">
      <h2 style="color:#111">Contract Renewed 🔄</h2>
      <p>Hi Coach {coach.first_name},</p>
      <p><strong>{client.full_name}</strong> renewed their <strong>{package.name}</strong> contract for <strong>{months} month(s)</strong>.</p>
      <hr/><p style="color:#888;font-size:12px">Kentaro Coaching Platform</p>
    </div>"""
    return send_email(coach.user.email, f'Contract renewed: {client.full_name}', html=html)


def send_termination_emails(coach, client, terminated_by, reason):
    """Notify both parties when contract is terminated."""
    terminator = 'the client' if terminated_by == 'client' else 'the coach'
    for recipient, name, email in [
        (coach, f'Coach {coach.first_name}', coach.user.email),
        (client, client.full_name, client.user.email),
    ]:
        html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto">
          <h2 style="color:#c00">Coaching Contract Ended</h2>
          <p>Hi {name},</p>
          <p>The coaching contract between <strong>{coach.first_name} {coach.last_name}</strong> and <strong>{client.full_name}</strong> has been ended by {terminator}.</p>
          {'<p><strong>Reason:</strong> ' + reason + '</p>' if reason else ''}
          <hr/><p style="color:#888;font-size:12px">Kentaro Coaching Platform</p>
        </div>"""
        send_email(email, 'Coaching contract ended', html=html)


def send_appointment_booked_email(coach, client, appointment):
    """Notify both parties when appointment is booked."""
    date_str = appointment.date.strftime('%A, %B %d %Y')
    time_str = appointment.start_time.strftime('%I:%M %p')
    for name, email in [(f'Coach {coach.first_name}', coach.user.email), (client.full_name, client.user.email)]:
        html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto">
          <h2 style="color:#111">Appointment Booked 📅</h2>
          <p>Hi {name},</p>
          <p>A coaching call has been scheduled:</p>
          <ul>
            <li><strong>Date:</strong> {date_str}</li>
            <li><strong>Time:</strong> {time_str}</li>
          </ul>
          <hr/><p style="color:#888;font-size:12px">Kentaro Coaching Platform</p>
        </div>"""
        send_email(email, f'Appointment booked: {date_str}', html=html)


def send_appointment_cancelled_email(coach, client, appointment, cancelled_by):
    """Notify both parties when appointment is cancelled."""
    date_str = appointment.date.strftime('%A, %B %d %Y')
    for name, email in [(f'Coach {coach.first_name}', coach.user.email), (client.full_name, client.user.email)]:
        html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto">
          <h2 style="color:#c00">Appointment Cancelled</h2>
          <p>Hi {name},</p>
          <p>The coaching call on <strong>{date_str}</strong> has been cancelled by {cancelled_by}.</p>
          <hr/><p style="color:#888;font-size:12px">Kentaro Coaching Platform</p>
        </div>"""
        send_email(email, f'Appointment cancelled: {date_str}', html=html)


def send_checkin_email(coach, client, checkin):
    """Notify coach when client submits a check-in."""
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:auto">
      <h2 style="color:#111">New Check-In from {client.full_name} 📋</h2>
      <p>Hi Coach {coach.first_name},</p>
      <p>{client.full_name} submitted their weekly check-in:</p>
      <ul>
        <li><strong>Energy:</strong> {checkin.energy}/10</li>
        <li><strong>Sleep:</strong> {checkin.sleep_hours} hours</li>
        <li><strong>Mood:</strong> {checkin.mood}/10</li>
        {'<li><strong>Weight:</strong> ' + str(checkin.weight) + ' ' + checkin.weight_unit + '</li>' if checkin.weight else ''}
        {'<li><strong>Notes:</strong> ' + checkin.notes + '</li>' if checkin.notes else ''}
      </ul>
      <p>Log in to Kentaro to reply.</p>
      <hr/><p style="color:#888;font-size:12px">Kentaro Coaching Platform</p>
    </div>"""
    return send_email(coach.user.email, f'New check-in: {client.full_name}', html=html)


def send_session_note_email(coach, client, note):
    """Notify client when coach writes a session note."""
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:auto">
      <h2 style="color:#111">New Session Note from Coach {coach.first_name} 📝</h2>
      <p>Hi {client.full_name},</p>
      <p>Your coach left a session note for {note.session_date.strftime('%B %d')}:</p>
      {'<p><strong>Summary:</strong> ' + note.summary + '</p>' if note.summary else ''}
      {'<p><strong>Homework:</strong> ' + note.homework + '</p>' if note.homework else ''}
      {'<p><strong>Next Goal:</strong> ' + note.next_goal + '</p>' if note.next_goal else ''}
      <p>Log in to Kentaro to view the full note.</p>
      <hr/><p style="color:#888;font-size:12px">Kentaro Coaching Platform</p>
    </div>"""
    return send_email(client.user.email, f'Session note from Coach {coach.first_name}', html=html)


def send_contract_expiry_warning(client, days_remaining):
    """Warn client that contract is expiring soon."""
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:auto">
      <h2 style="color:#c00">Your Coaching Access Expires in {days_remaining} Day{'s' if days_remaining != 1 else ''} ⚠️</h2>
      <p>Hi {client.full_name},</p>
      <p>Your coaching contract expires in <strong>{days_remaining} day{'s' if days_remaining != 1 else ''}</strong>. Renew now to keep your access to your coach and program.</p>
      <p><a href="https://kentaro.app/client/renew-contract" style="background:#000;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none">Renew Now</a></p>
      <hr/><p style="color:#888;font-size:12px">Kentaro Coaching Platform</p>
    </div>"""
    return send_email(client.user.email, f'Your coaching expires in {days_remaining} day{"s" if days_remaining != 1 else ""}', html=html)
