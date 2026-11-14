from app import create_app
from app.models.user import User, Role, ChatMessage
from app.models.features import Notification, ClosedSupportChat
from app.models.workout import Program, ClientProgram
from app.models.marketplace import ClientPost

app = create_app()
with app.app_context():
    print('Notification columns:', [c.name for c in Notification.__table__.columns])
    print('ChatMessage columns:', [c.name for c in ChatMessage.__table__.columns])
    print('Total users:', User.query.count())
    print('Total notifications:', Notification.query.count())
    sample_notifs = Notification.query.order_by(Notification.id.desc()).limit(15).all()
    for n in sample_notifs:
        print(f"Notif {n.id}: user_id={n.user_id}, type={n.type}, title={n.title}, link={getattr(n, 'link', None)}")
