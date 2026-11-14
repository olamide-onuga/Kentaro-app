with open('app/__init__.py', 'r', encoding='utf-8') as f:
    code = f.read()

if 'from app.routes.support import support_bp' not in code:
    code = code.replace(
        "    from app.routes.social import social_bp\n    \n    app.register_blueprint(auth_bp, url_prefix='/auth')",
        "    from app.routes.social import social_bp\n    from app.routes.support import support_bp\n    \n    app.register_blueprint(auth_bp, url_prefix='/auth')"
    )
    code = code.replace(
        "    app.register_blueprint(social_bp)\n    \n    @socketio.on('connect')",
        "    app.register_blueprint(social_bp)\n    app.register_blueprint(support_bp)\n    \n    @socketio.on('connect')"
    )

ticket_socket_handlers = """
    @socketio.on('join_ticket')
    def handle_join_ticket(data):
        if not current_user.is_authenticated:
            return
        ticket_id = data.get('ticket_id')
        if ticket_id:
            join_room(f'ticket_{ticket_id}')

    @socketio.on('leave_ticket')
    def handle_leave_ticket(data):
        if not current_user.is_authenticated:
            return
        ticket_id = data.get('ticket_id')
        if ticket_id:
            leave_room(f'ticket_{ticket_id}')
"""

if 'def handle_join_ticket(' not in code:
    # insert before handle_chat_message
    code = code.replace(
        "    @socketio.on('chat_message')\n    def handle_chat_message(data):",
        ticket_socket_handlers + "\n    @socketio.on('chat_message')\n    def handle_chat_message(data):"
    )

with open('app/__init__.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Updated app/__init__.py with support_bp and ticket socket handlers")
