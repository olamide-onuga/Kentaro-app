from app import create_app, db, socketio
from app.models.user import User, ChatMessage

app = create_app()

with app.app_context():
    admin = User.query.filter_by(is_admin=True).first()
    client = User.query.filter_by(email='onanuga89@gmail.com').first()

    print(f"Admin: {admin.id} ({admin.email})")
    print(f"Client: {client.id} ({client.email})")

    # Connect client
    c_client = app.test_client()
    with c_client.session_transaction() as sess:
        sess['_user_id'] = str(client.id)
        sess['_fresh'] = True
    sock_client = socketio.test_client(app, flask_test_client=c_client)

    # Connect admin
    c_admin = app.test_client()
    with c_admin.session_transaction() as sess:
        sess['_user_id'] = str(admin.id)
        sess['_fresh'] = True
    sock_admin = socketio.test_client(app, flask_test_client=c_admin)

    print("Client connected:", sock_client.is_connected())
    print("Admin connected:", sock_admin.is_connected())

    # Admin sends message to Client
    sock_admin.emit('chat_message', {
        'target_user_id': client.id,
        'msg': 'Hello from Admin support desk!',
        'is_anonymous': True
    })

    # Check client received
    rec_client = sock_client.get_received()
    print("Client received events:")
    for ev in rec_client:
        print(" ", ev['name'], ev['args'])

    # Check admin received confirmation
    rec_admin = sock_admin.get_received()
    print("Admin received events:")
    for ev in rec_admin:
        print(" ", ev['name'], ev['args'])

    # Verify in DB
    msg = ChatMessage.query.filter_by(sender_id=admin.id, receiver_id=client.id, message='Hello from Admin support desk!').first()
    if msg:
        print("SUCCESS: Message saved in DB with ID", msg.id)
        db.session.delete(msg)
        db.session.commit()
    else:
        print("FAIL: Message NOT saved in DB!")
