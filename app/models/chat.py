from datetime import datetime
from app.extensions import db

from app.models.user import ChatMessage

# Alias Message to ChatMessage for backwards compatibility
Message = ChatMessage


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(64), nullable=False, default='chat_message')
    title = db.Column(db.String(255), nullable=True)
    text = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(512), nullable=True)
    target_type = db.Column(db.String(64), nullable=True)  # 'conversation', 'program', 'ticket', 'marketplace', 'offer'
    target_id = db.Column(db.Integer, nullable=True)
    is_seen = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic'))
