from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
import enum

class SubscriptionType(enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"

class BotStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

class User(UserMixin, db.Model):
    """User model for authentication and account management"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)
    
    @property
    def is_active(self):
        """Property to maintain compatibility with Flask-Login"""
        return self.active
    
    # Relationships
    bots = db.relationship('Bot', backref='owner', lazy=True, cascade='all, delete-orphan')
    subscription = db.relationship('Subscription', backref='user', uselist=False, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def get_full_name(self):
        """Get user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    
    def __repr__(self):
        return f'<User {self.username}>'

class Subscription(db.Model):
    """Subscription model for user plans"""
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subscription_type = db.Column(db.Enum(SubscriptionType), default=SubscriptionType.FREE)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    max_bots = db.Column(db.Integer, default=1)
    max_messages_per_month = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def is_expired(self):
        """Check if subscription is expired"""
        if self.end_date:
            return datetime.utcnow() > self.end_date
        return False
    
    def can_create_bot(self):
        """Check if user can create more bots"""
        current_bots = Bot.query.filter_by(user_id=self.user_id).count()
        return current_bots < self.max_bots
    
    def __repr__(self):
        return f'<Subscription {self.subscription_type.value} for User {self.user_id}>'

class Bot(db.Model):
    """Bot model for chatbot instances"""
    __tablename__ = 'bots'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    telegram_token = db.Column(db.String(255), nullable=True)
    telegram_username = db.Column(db.String(100), nullable=True)
    system_prompt = db.Column(db.Text, default="You are a helpful AI assistant.")
    status = db.Column(db.Enum(BotStatus), default=BotStatus.INACTIVE)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Analytics fields
    total_messages = db.Column(db.Integer, default=0)
    total_users = db.Column(db.Integer, default=0)
    last_activity = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    knowledge_base = db.relationship('KnowledgeBase', backref='bot', lazy=True, cascade='all, delete-orphan')
    conversations = db.relationship('Conversation', backref='bot', lazy=True, cascade='all, delete-orphan')
    
    def increment_message_count(self):
        """Increment total messages count"""
        self.total_messages += 1
        self.last_activity = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<Bot {self.name}>'

class KnowledgeBase(db.Model):
    """Knowledge base documents for bots"""
    __tablename__ = 'knowledge_base'
    
    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey('bots.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    file_type = db.Column(db.String(50), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<KnowledgeBase {self.title}>'

class Conversation(db.Model):
    """Store conversation history"""
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey('bots.id'), nullable=False)
    telegram_user_id = db.Column(db.String(100), nullable=False)
    telegram_username = db.Column(db.String(100), nullable=True)
    message_count = db.Column(db.Integer, default=0)
    first_message = db.Column(db.DateTime, default=datetime.utcnow)
    last_message = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Conversation {self.telegram_user_id} with Bot {self.bot_id}>'

class Message(db.Model):
    """Individual messages in conversations"""
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Message {self.id}>'
