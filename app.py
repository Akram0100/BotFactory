import os
import logging
from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_babel import Babel, get_locale
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
babel = Babel()

def create_app():
    # Create Flask app
    app = Flask(__name__)
    
    # Configuration
    app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///botfactory.db")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file upload
    
    # Babel configuration
    app.config["LANGUAGES"] = {
        'en': 'English',
        'ru': 'Русский',
        'uz': 'O\'zbek'
    }
    app.config["BABEL_DEFAULT_LOCALE"] = 'en'
    app.config["BABEL_DEFAULT_TIMEZONE"] = 'UTC'
    
    # Proxy fix for deployment
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Configure Babel locale selector
    def get_locale():
        # 1. If user is logged in, use their preferred language
        from flask_login import current_user
        if current_user.is_authenticated and hasattr(current_user, 'language') and current_user.language:
            return current_user.language
        
        # 2. If language is in session, use that
        if 'language' in session:
            return session['language']
        
        # 3. Use browser's preferred language if supported
        return request.accept_languages.best_match(app.config['LANGUAGES'].keys()) or 'en'
    
    babel.init_app(app, locale_selector=get_locale)
    
    # Custom template filters
    @app.template_filter('number')
    def number_filter(value):
        """Format number with commas"""
        if value is None:
            return '0'
        return f"{int(value):,}"
    
    @app.template_filter('datetime')
    def datetime_filter(value):
        """Format datetime for display"""
        if value is None:
            return 'Unknown'
        if hasattr(value, 'strftime'):
            return value.strftime('%B %d, %Y at %I:%M %p')
        return str(value)
    
    # Make functions available to templates
    @app.context_processor
    def inject_template_vars():
        from flask_babel import get_locale
        return dict(get_locale=get_locale)
    
    # Configure Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))
    
    
    # Import and register routes
    from routes import main, auth, bots, subscriptions, admin
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(bots)
    app.register_blueprint(subscriptions)
    app.register_blueprint(admin)
    
    # Create database tables
    with app.app_context():
        import models  # noqa: F401
        db.create_all()
        logging.info("Database tables created")
        
        # TODO: Initialize notification templates after fixing Unicode encoding
        # from services.notification_service import NotificationService
        # NotificationService.initialize_templates()
    
    return app

# Create app instance
app = create_app()
