from app import create_app, db, socketio
from app.models.user import User, ChatMessage

app = create_app()

with app.app_context():
    admin = User.query.filter_by(is_admin=True).first()
    client = User.query.filter((User.is_admin == False) & (User.role.has(name='client'))).first()

    print(f"Admin: {admin.id} ({admin.email})")
    print(f"Client: {client.id} ({client.email})")

    # Clean existing test messages
    ChatMessage.query.filter_by(message='Hello from admin desk test!').delete()
    db.session.commit()

    # Create admin client
    admin_flask_client = app.test_client()
    with admin_flask_client.session_transaction() as sess:
        sess['_user_id'] = str(admin.id)
        sess['_fresh'] = True
    
    sock_admin = socketio.test_client(app, flask_test_client=admin_flask_client)
    print("Admin connected to socket:", sock_admin.is_connected())

    # Emit message from admin to client
    sock_admin.emit('chat_message', {
        'target_user_id': client.id,
        'msg': 'Hello from admin desk test!',
        'is_anonymous': True
    })

    # Check DB
    msg = ChatMessage.query.filter_by(sender_id=admin.id, receiver_id=client.id, message='Hello from admin desk test!').first()
    if msg:
        print(f"SUCCESS: Admin message saved in DB! ID={msg.id}, is_anon={msg.is_anonymous}")
        db.session.delete(msg)
        db.session.commit()
    else:
        print("FAIL: Admin message NOT found in DB!")
