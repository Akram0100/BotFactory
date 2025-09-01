from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
import enum

class SubscriptionType(enum.Enum):
    FREE = "free"
    STARTER = "starter"
    BASIC = "basic"
    PREMIUM = "premium"

class BotStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

class PlatformType(enum.Enum):
    TELEGRAM = "telegram"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"

class User(UserMixin, db.Model):
    """User model for authentication and account management"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    language = db.Column(db.String(5), default='en', nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
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
    
    # Platform access permissions
    telegram_enabled = db.Column(db.Boolean, default=True)
    instagram_enabled = db.Column(db.Boolean, default=False)  # Only for paid plans
    whatsapp_enabled = db.Column(db.Boolean, default=False)   # Only for paid plans
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
    
    # Platform selection
    platform_type = db.Column(db.Enum(PlatformType), default=PlatformType.TELEGRAM, nullable=False)
    
    # Telegram integration
    telegram_token = db.Column(db.String(255), nullable=True)
    telegram_username = db.Column(db.String(100), nullable=True)
    
    # Instagram integration  
    instagram_access_token = db.Column(db.String(500), nullable=True)
    instagram_username = db.Column(db.String(100), nullable=True)
    instagram_account_id = db.Column(db.String(100), nullable=True)
    
    # WhatsApp integration
    whatsapp_access_token = db.Column(db.String(500), nullable=True)
    whatsapp_phone_number_id = db.Column(db.String(100), nullable=True)
    whatsapp_phone_number = db.Column(db.String(50), nullable=True)
    whatsapp_verified_name = db.Column(db.String(100), nullable=True)
    
    system_prompt = db.Column(db.Text, default="You are a helpful AI assistant.")
    status = db.Column(db.Enum(BotStatus), default=BotStatus.INACTIVE)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Analytics fields
    total_messages = db.Column(db.Integer, default=0)
    total_users = db.Column(db.Integer, default=0)
    last_activity = db.Column(db.DateTime, nullable=True)
    
    # Notification settings
    admin_chat_id = db.Column(db.String(100), nullable=True)  # Admin chat ID for notifications
    notification_channel = db.Column(db.String(100), nullable=True)  # Telegram channel for notifications
    
    # Relationships
    knowledge_base = db.relationship('KnowledgeBase', backref='bot', lazy=True, cascade='all, delete-orphan')
    
    def increment_message_count(self):
        """Increment total messages count"""
        self.total_messages += 1
        self.last_activity = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<Bot {self.name}>'

class TelegramUser(db.Model):
    """Model to store Telegram user preferences"""
    __tablename__ = 'telegram_users'
    
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, unique=True, nullable=False)  # Telegram user ID
    username = db.Column(db.String(100), nullable=True)  # Telegram username
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    language = db.Column(db.String(5), default='uz', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<TelegramUser {self.telegram_user_id}>'

class Conversation(db.Model):
    """Model to track user-bot interactions"""
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey('bots.id'), nullable=False)
    telegram_user_id = db.Column(db.BigInteger, nullable=False)
    chat_id = db.Column(db.String(100), nullable=False)
    last_message_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    bot = db.relationship('Bot', backref='conversations')
    
    def __repr__(self):
        return f'<Conversation bot:{self.bot_id} user:{self.telegram_user_id}>'

class KnowledgeBase(db.Model):
    """Knowledge base documents for bots"""
    __tablename__ = 'knowledge_base'
    
    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey('bots.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    file_type = db.Column(db.String(50), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)  # Mahsulot rasmi URL
    image_caption = db.Column(db.String(200), nullable=True)  # Rasm tavsifi
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<KnowledgeBase {self.title}>'


class AdminBroadcast(db.Model):
    """Admin broadcast messages to free users"""
    __tablename__ = 'admin_broadcasts'
    
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    message_html = db.Column(db.Text, nullable=True)  # HTML formatted version
    target_subscription = db.Column(db.Enum(SubscriptionType), default=SubscriptionType.FREE)
    allow_basic = db.Column(db.Boolean, default=False)
    allow_premium = db.Column(db.Boolean, default=False)
    is_sent = db.Column(db.Boolean, default=False)
    sent_at = db.Column(db.DateTime, nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=True)  # For scheduling broadcasts
    is_scheduled = db.Column(db.Boolean, default=False)
    total_bots = db.Column(db.Integer, default=0)
    successful_sends = db.Column(db.Integer, default=0)
    failed_sends = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    admin = db.relationship('User', backref='broadcasts')
    delivery_logs = db.relationship('BroadcastDelivery', backref='broadcast', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<AdminBroadcast {self.title}>'

class BroadcastDelivery(db.Model):
    """Track delivery status of broadcast messages"""
    __tablename__ = 'broadcast_deliveries'
    
    id = db.Column(db.Integer, primary_key=True)
    broadcast_id = db.Column(db.Integer, db.ForeignKey('admin_broadcasts.id'), nullable=False)
    bot_id = db.Column(db.Integer, db.ForeignKey('bots.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    telegram_chat_id = db.Column(db.String(100), nullable=True)
    delivered = db.Column(db.Boolean, default=False)
    error_message = db.Column(db.Text, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    bot = db.relationship('Bot')
    user = db.relationship('User')
    
    def __repr__(self):
        return f'<BroadcastDelivery {self.id}>'

class NotificationType(enum.Enum):
    TRIAL_EXPIRING_3_DAYS = "trial_expiring_3_days"
    TRIAL_EXPIRED = "trial_expired"
    SUBSCRIPTION_EXPIRING_1_DAY = "subscription_expiring_1_day"
    SUBSCRIPTION_EXPIRED = "subscription_expired"

class NotificationTemplate(db.Model):
    """Templates for automatic notifications"""
    __tablename__ = 'notification_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    notification_type = db.Column(db.Enum(NotificationType), nullable=False, unique=True)
    message_uz = db.Column(db.Text, nullable=False)
    message_ru = db.Column(db.Text, nullable=False)
    message_en = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_message(self, language='en'):
        """Get message text for specified language"""
        if language == 'uz':
            return self.message_uz
        elif language == 'ru':
            return self.message_ru
        else:
            return self.message_en
    
    def __repr__(self):
        return f'<NotificationTemplate {self.notification_type.value}>'

class UserNotification(db.Model):
    """Track notifications sent to users"""
    __tablename__ = 'user_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    notification_type = db.Column(db.Enum(NotificationType), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    is_sent = db.Column(db.Boolean, default=False)
    sent_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='notifications')
    
    def __repr__(self):
        return f'<UserNotification {self.notification_type.value} for User {self.user_id}>'
