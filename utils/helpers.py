import os
import hashlib
import secrets
import string
from datetime import datetime, timedelta
from flask import current_app
import logging

def generate_secure_token(length=32):
    """Generate a secure random token"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def hash_string(text):
    """Generate SHA-256 hash of a string"""
    return hashlib.sha256(text.encode()).hexdigest()

def format_datetime(dt):
    """Format datetime for display"""
    if not dt:
        return "Never"
    
    now = datetime.utcnow()
    diff = now - dt
    
    if diff.days > 365:
        return dt.strftime("%Y-%m-%d")
    elif diff.days > 30:
        return dt.strftime("%b %d, %Y")
    elif diff.days > 0:
        return f"{diff.days} days ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hours ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minutes ago"
    else:
        return "Just now"

def format_number(num):
    """Format number with thousand separators"""
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    else:
        return str(num)

def truncate_text(text, max_length=100, suffix="..."):
    """Truncate text to specified length"""
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def is_valid_email(email):
    """Basic email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_username(username):
    """Validate username format"""
    import re
    # Username: 3-30 characters, alphanumeric and underscore only
    pattern = r'^[a-zA-Z0-9_]{3,30}$'
    return re.match(pattern, username) is not None

def sanitize_filename(filename):
    """Sanitize filename for safe storage"""
    import re
    # Remove or replace unsafe characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove multiple underscores
    filename = re.sub(r'_{2,}', '_', filename)
    # Trim underscores from ends
    filename = filename.strip('_')
    
    if not filename:
        filename = f"file_{generate_secure_token(8)}"
    
    return filename

def get_file_size_mb(file_path):
    """Get file size in megabytes"""
    try:
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)
    except OSError:
        return 0

def validate_telegram_token(token):
    """Validate Telegram bot token format"""
    import re
    # Telegram bot token format: bot123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
    pattern = r'^\d{8,10}:[A-Za-z0-9_-]{35}$'
    return re.match(pattern, token) is not None

def log_user_action(user, action, details=None):
    """Log user actions for audit trail"""
    try:
        log_message = f"User {user.username} (ID: {user.id}) - {action}"
        if details:
            log_message += f" - {details}"
        
        current_app.logger.info(log_message)
        
    except Exception as e:
        logging.error(f"Failed to log user action: {e}")

def calculate_subscription_limits(subscription_type):
    """Calculate limits based on subscription type"""
    limits = {
        'free': {
            'max_bots': 1,
            'max_messages_per_month': 100,
            'max_knowledge_entries': 10,
            'max_file_size_mb': 1
        },
        'basic': {
            'max_bots': 5,
            'max_messages_per_month': 1000,
            'max_knowledge_entries': 50,
            'max_file_size_mb': 5
        },
        'premium': {
            'max_bots': 25,
            'max_messages_per_month': 10000,
            'max_knowledge_entries': 200,
            'max_file_size_mb': 16
        }
    }
    
    return limits.get(subscription_type.value if hasattr(subscription_type, 'value') else subscription_type, limits['free'])

def get_subscription_features(subscription_type):
    """Get features list for subscription type"""
    features = {
        'free': [
            '1 AI chatbot',
            '100 messages per month',
            'Basic knowledge base',
            'Telegram integration',
            'Community support'
        ],
        'basic': [
            '5 AI chatbots',
            '1,000 messages per month',
            'Advanced knowledge base',
            'Telegram integration',
            'Priority support',
            'Custom bot personalities'
        ],
        'premium': [
            '25 AI chatbots',
            '10,000 messages per month',
            'Unlimited knowledge base',
            'All integrations',
            'Priority support',
            'Custom bot personalities',
            'Analytics dashboard',
            'API access'
        ]
    }
    
    return features.get(subscription_type.value if hasattr(subscription_type, 'value') else subscription_type, features['free'])

def is_development():
    """Check if running in development mode"""
    return current_app.debug or os.environ.get('FLASK_ENV') == 'development'

def get_environment_info():
    """Get environment information for debugging"""
    return {
        'debug': current_app.debug,
        'environment': os.environ.get('FLASK_ENV', 'production'),
        'database_url': bool(os.environ.get('DATABASE_URL')),
        'gemini_api_key': bool(os.environ.get('GEMINI_API_KEY')),
        'session_secret': bool(os.environ.get('SESSION_SECRET')),
        'python_version': __import__('sys').version,
        'app_name': current_app.name
    }

class MessageProcessor:
    """Utility class for processing messages"""
    
    @staticmethod
    def clean_message(message):
        """Clean and sanitize user message"""
        if not message:
            return ""
        
        # Remove excessive whitespace
        message = " ".join(message.split())
        
        # Truncate very long messages
        if len(message) > 4000:
            message = message[:4000] + "... [truncated]"
        
        return message.strip()
    
    @staticmethod
    def extract_keywords(message, max_keywords=10):
        """Extract keywords from message"""
        import re
        
        # Simple keyword extraction
        words = re.findall(r'\b[a-zA-Z]{3,}\b', message.lower())
        
        # Filter out common words
        stop_words = {
            'the', 'is', 'at', 'which', 'on', 'and', 'a', 'to', 'are', 'as',
            'was', 'with', 'for', 'this', 'that', 'it', 'in', 'or', 'be',
            'an', 'will', 'not', 'can', 'have', 'has', 'had', 'you', 'your'
        }
        
        keywords = [word for word in words if word not in stop_words]
        
        # Count frequency and return most common
        from collections import Counter
        word_counts = Counter(keywords)
        
        return [word for word, count in word_counts.most_common(max_keywords)]

def register_template_filters(app):
    """Register custom template filters"""
    
    @app.template_filter('datetime')
    def datetime_filter(dt):
        return format_datetime(dt)
    
    @app.template_filter('number')
    def number_filter(num):
        return format_number(num)
    
    @app.template_filter('truncate')
    def truncate_filter(text, length=100):
        return truncate_text(text, length)

# Initialize filters when module is imported
try:
    from flask import current_app
    if current_app:
        register_template_filters(current_app)
except RuntimeError:
    # Not in app context, filters will be registered when app starts
    pass
