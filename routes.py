import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from app import db
from models import User, Bot, Subscription, KnowledgeBase, SubscriptionType, BotStatus, AdminBroadcast, BroadcastDelivery, Conversation, Message
from services.auth_service import AuthService
from services.ai_service import AIService
from services.telegram_service import TelegramService
from services.broadcast_service import BroadcastService
from functools import wraps
import logging

# Blueprint definitions
main = Blueprint('main', __name__)
auth = Blueprint('auth', __name__, url_prefix='/auth')
bots = Blueprint('bots', __name__, url_prefix='/bots')
subscriptions = Blueprint('subscriptions', __name__, url_prefix='/subscriptions')
admin = Blueprint('admin', __name__, url_prefix='/admin')

# Initialize services
auth_service = AuthService()
ai_service = AIService()
telegram_service = TelegramService()
broadcast_service = BroadcastService()

# Admin decorator
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Admin access required.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Main routes
@main.route('/')
def index():
    """Landing page"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')

@main.route('/set-language/<language>')
def set_language(language):
    """Set user language preference"""
    supported_languages = ['en', 'ru', 'uz']
    if language in supported_languages:
        session['language'] = language
        
        # Update user's language preference if logged in
        if current_user.is_authenticated:
            current_user.language = language
            db.session.commit()
    
    # Redirect back to previous page or dashboard
    return redirect(request.referrer or url_for('main.index'))

@main.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    user_bots = Bot.query.filter_by(user_id=current_user.id).all()
    subscription = Subscription.query.filter_by(user_id=current_user.id).first()
    
    # Create subscription if doesn't exist
    if not subscription:
        subscription = Subscription()
        subscription.user_id = current_user.id
        subscription.subscription_type = SubscriptionType.FREE
        subscription.max_bots = 1
        subscription.max_messages_per_month = 100
        db.session.add(subscription)
        db.session.commit()
    
    stats = {
        'total_bots': len(user_bots),
        'active_bots': len([bot for bot in user_bots if bot.status == BotStatus.ACTIVE]),
        'total_messages': sum(bot.total_messages for bot in user_bots),
        'total_users': sum(bot.total_users for bot in user_bots)
    }
    
    return render_template('dashboard.html', 
                         bots=user_bots[:5], 
                         subscription=subscription, 
                         stats=stats)

# Authentication routes
@auth.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please fill in all fields.', 'error')
            return render_template('login.html')
        
        user = auth_service.authenticate_user(username, password)
        if user:
            login_user(user, remember=bool(request.form.get('remember')))
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.get_full_name()}!', 'success')
            return redirect(next_page if next_page else url_for('main.dashboard'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        
        # Validation
        if not all([username, email, password, confirm_password]):
            flash('Please fill in all required fields.', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        
        if password and len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('register.html')
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('register.html')
        
        # Create user
        try:
            user = auth_service.create_user(username, email, password, first_name, last_name)
            login_user(user)
            flash(f'Welcome to BotFactory, {user.get_full_name()}!', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            flash('Registration failed. Please try again.', 'error')
            logging.error(f"Registration error: {e}")
    
    return render_template('register.html')

@auth.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('main.index'))

# Bot management routes
@bots.route('/')
@login_required
def list_bots():
    """List all user bots"""
    user_bots = Bot.query.filter_by(user_id=current_user.id).all()
    subscription = Subscription.query.filter_by(user_id=current_user.id).first()
    return render_template('bot_list.html', bots=user_bots, subscription=subscription)

@bots.route('/create', methods=['GET', 'POST'])
@login_required
def create_bot():
    """Create new bot"""
    subscription = Subscription.query.filter_by(user_id=current_user.id).first()
    
    if not subscription or not subscription.can_create_bot():
        flash('You have reached your bot limit. Please upgrade your subscription.', 'error')
        return redirect(url_for('subscriptions.plans'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        system_prompt = request.form.get('system_prompt', 'You are a helpful AI assistant.')
        
        if not name:
            flash('Bot name is required.', 'error')
            return render_template('bot_create.html')
        
        try:
            bot = Bot()
            bot.user_id = current_user.id
            bot.name = name
            bot.description = description
            bot.system_prompt = system_prompt
            db.session.add(bot)
            db.session.commit()
            
            flash(f'Bot "{name}" created successfully!', 'success')
            return redirect(url_for('bots.edit_bot', bot_id=bot.id))
        except Exception as e:
            flash('Failed to create bot. Please try again.', 'error')
            logging.error(f"Bot creation error: {e}")
    
    return render_template('bot_create.html')

@bots.route('/<int:bot_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_bot(bot_id):
    """Edit bot configuration"""
    bot = Bot.query.filter_by(id=bot_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_basic':
            bot.name = request.form.get('name', bot.name)
            bot.description = request.form.get('description', bot.description)
            bot.system_prompt = request.form.get('system_prompt', bot.system_prompt)
            
            try:
                db.session.commit()
                flash('Bot updated successfully!', 'success')
            except Exception as e:
                flash('Failed to update bot.', 'error')
                logging.error(f"Bot update error: {e}")
        
        elif action == 'setup_telegram':
            token = request.form.get('telegram_token')
            if token:
                try:
                    # Validate token and get bot info
                    bot_info = telegram_service.validate_token(token)
                    if bot_info:
                        bot.telegram_token = token
                        bot.telegram_username = bot_info.get('username')
                        bot.status = BotStatus.ACTIVE
                        db.session.commit()
                        
                        # Start the telegram bot
                        telegram_service.start_bot(bot)
                        flash('Telegram bot configured successfully!', 'success')
                    else:
                        flash('Invalid Telegram bot token.', 'error')
                except Exception as e:
                    flash('Failed to configure Telegram bot.', 'error')
                    logging.error(f"Telegram setup error: {e}")
        
        elif action == 'toggle_status':
            if bot.status == BotStatus.ACTIVE:
                bot.status = BotStatus.INACTIVE
                telegram_service.stop_bot(bot)
                flash('Bot deactivated.', 'info')
            else:
                if bot.telegram_token:
                    bot.status = BotStatus.ACTIVE
                    telegram_service.start_bot(bot)
                    flash('Bot activated.', 'success')
                else:
                    flash('Please configure Telegram token first.', 'error')
            
            try:
                db.session.commit()
            except Exception as e:
                flash('Failed to update bot status.', 'error')
                logging.error(f"Bot status update error: {e}")
    
    return render_template('bot_edit.html', bot=bot)

@bots.route('/<int:bot_id>/knowledge-base', methods=['GET', 'POST'])
@login_required
def knowledge_base(bot_id):
    """Manage bot knowledge base"""
    bot = Bot.query.filter_by(id=bot_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_text':
            title = request.form.get('title')
            content = request.form.get('content')
            image_url = request.form.get('image_url', '').strip()
            image_caption = request.form.get('image_caption', '').strip()
            
            if title and content:
                try:
                    kb = KnowledgeBase()
                    kb.bot_id = bot.id
                    kb.title = title
                    kb.content = content
                    kb.file_type = 'text'
                    if image_url:
                        kb.image_url = image_url
                    if image_caption:
                        kb.image_caption = image_caption
                    db.session.add(kb)
                    db.session.commit()
                    flash(_('Knowledge base entry added successfully!'), 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(_('Failed to add knowledge base entry.'), 'error')
                    logging.error(f"Knowledge base error: {e}")
        
        elif action == 'upload_file':
            if 'file' not in request.files:
                flash(_('No file selected.'), 'error')
            else:
                file = request.files['file']
                if file.filename == '':
                    flash(_('No file selected.'), 'error')
                elif file:
                    try:
                        filename = secure_filename(file.filename or 'unknown')
                        content = file.read().decode('utf-8')
                        
                        kb = KnowledgeBase()
                        kb.bot_id = bot.id
                        kb.title = filename
                        kb.content = content
                        kb.file_type = 'file'
                        kb.file_size = len(content)
                        db.session.add(kb)
                        db.session.commit()
                        flash(_('File "%(filename)s" uploaded successfully!', filename=filename), 'success')
                    except UnicodeDecodeError:
                        flash(_('File must be text-based (UTF-8 encoded).'), 'error')
                    except RequestEntityTooLarge:
                        flash(_('File too large. Maximum size is 16MB.'), 'error')
                    except Exception as e:
                        db.session.rollback()
                        flash(_('Failed to upload file.'), 'error')
                        logging.error(f"File upload error: {e}")
        
        elif action == 'edit_entry':
            entry_id = request.form.get('entry_id')
            title = request.form.get('title')
            content = request.form.get('content')
            image_url = request.form.get('image_url', '').strip()
            image_caption = request.form.get('image_caption', '').strip()
            
            if entry_id and title and content:
                try:
                    kb_entry = KnowledgeBase.query.filter_by(id=entry_id, bot_id=bot.id).first_or_404()
                    kb_entry.title = title
                    kb_entry.content = content
                    kb_entry.image_url = image_url if image_url else None
                    kb_entry.image_caption = image_caption if image_caption else None
                    kb_entry.updated_at = db.func.now()
                    db.session.commit()
                    flash(_('Knowledge base entry updated successfully!'), 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(_('Failed to update knowledge base entry.'), 'error')
                    logging.error(f"Knowledge base update error: {e}")
            else:
                flash(_('All fields are required.'), 'error')
    
    knowledge_entries = KnowledgeBase.query.filter_by(bot_id=bot.id).all()
    return render_template('knowledge_base.html', bot=bot, knowledge_entries=knowledge_entries)

@bots.route('/<int:bot_id>/knowledge-base/<int:kb_id>/delete', methods=['POST'])
@login_required
def delete_knowledge_entry(bot_id, kb_id):
    """Delete knowledge base entry"""
    bot = Bot.query.filter_by(id=bot_id, user_id=current_user.id).first_or_404()
    kb_entry = KnowledgeBase.query.filter_by(id=kb_id, bot_id=bot.id).first_or_404()
    
    try:
        db.session.delete(kb_entry)
        db.session.commit()
        flash(_('Knowledge base entry deleted successfully!'), 'success')
    except Exception as e:
        flash(_('Failed to delete entry.'), 'error')
        logging.error(f"Knowledge base deletion error: {e}")
    
    return redirect(url_for('bots.knowledge_base', bot_id=bot_id))

@bots.route('/<int:bot_id>/delete', methods=['POST'])
@login_required
def delete_bot(bot_id):
    """Delete bot"""
    bot = Bot.query.filter_by(id=bot_id, user_id=current_user.id).first_or_404()
    
    try:
        # Stop telegram bot if active
        if bot.status == BotStatus.ACTIVE:
            telegram_service.stop_bot(bot)
        
        # Delete bot and all related data (cascade)
        db.session.delete(bot)
        db.session.commit()
        
        flash(f'Bot "{bot.name}" deleted successfully!', 'success')
    except Exception as e:
        flash('Failed to delete bot.', 'error')
        logging.error(f"Bot deletion error: {e}")
    
    return redirect(url_for('bots.list_bots'))

@bots.route('/<int:bot_id>/conversations')
@login_required
def conversations(bot_id):
    """View bot conversations"""
    bot = Bot.query.filter_by(id=bot_id, user_id=current_user.id).first_or_404()
    
    # Get query parameters for filtering
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    # Build query
    conversations_query = Conversation.query.filter_by(bot_id=bot.id)
    
    # Apply search filter
    if search:
        conversations_query = conversations_query.filter(
            db.or_(
                Conversation.telegram_username.contains(search),
                Conversation.telegram_user_id.contains(search)
            )
        )
    
    # Order by latest message
    conversations_query = conversations_query.order_by(Conversation.last_message.desc())
    
    # Paginate results
    conversations_paginated = conversations_query.paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('conversations.html', 
                         bot=bot, 
                         conversations=conversations_paginated,
                         search=search)

@bots.route('/<int:bot_id>/conversations/<int:conversation_id>')
@login_required
def conversation_detail(bot_id, conversation_id):
    """View detailed conversation with messages"""
    bot = Bot.query.filter_by(id=bot_id, user_id=current_user.id).first_or_404()
    conversation = Conversation.query.filter_by(id=conversation_id, bot_id=bot.id).first_or_404()
    
    # Get all messages for this conversation
    messages = Message.query.filter_by(conversation_id=conversation.id)\
                           .order_by(Message.created_at.asc()).all()
    
    return render_template('conversation_detail.html', 
                         bot=bot, 
                         conversation=conversation,
                         messages=messages)

# Subscription routes
@subscriptions.route('/plans')
@login_required
def plans():
    """View subscription plans"""
    current_subscription = Subscription.query.filter_by(user_id=current_user.id).first()
    return render_template('subscriptions.html', current_subscription=current_subscription)

@subscriptions.route('/upgrade/<plan>')
@login_required
def upgrade_plan(plan):
    """Upgrade subscription plan"""
    subscription = Subscription.query.filter_by(user_id=current_user.id).first()
    
    if not subscription:
        subscription = Subscription()
        subscription.user_id = current_user.id
        db.session.add(subscription)
    
    if plan == 'basic':
        subscription.subscription_type = SubscriptionType.BASIC
        subscription.max_bots = 5
        subscription.max_messages_per_month = 1000
        flash('Upgraded to Basic plan!', 'success')
    elif plan == 'premium':
        subscription.subscription_type = SubscriptionType.PREMIUM
        subscription.max_bots = 25
        subscription.max_messages_per_month = 10000
        flash('Upgraded to Premium plan!', 'success')
    else:
        flash('Invalid plan selected.', 'error')
        return redirect(url_for('subscriptions.plans'))
    
    try:
        db.session.commit()
    except Exception as e:
        flash('Failed to upgrade subscription.', 'error')
        logging.error(f"Subscription upgrade error: {e}")
    
    return redirect(url_for('main.dashboard'))

# API endpoints for AJAX calls
@main.route('/api/bot/<int:bot_id>/test', methods=['POST'])
@login_required
def test_bot(bot_id):
    """Test bot response"""
    bot = Bot.query.filter_by(id=bot_id, user_id=current_user.id).first_or_404()
    
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'Message is required'}), 400
    
    try:
        response = ai_service.get_response(bot, data['message'])
        return jsonify({'response': response})
    except Exception as e:
        logging.error(f"Bot test error: {e}")
        return jsonify({'error': 'Failed to get response from AI service'}), 500

# Error handlers
@main.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@main.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# Admin Panel Routes
@admin.route('/')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    # Get statistics
    total_users = User.query.count()
    total_bots = Bot.query.count()
    active_bots = Bot.query.filter_by(status=BotStatus.ACTIVE).count()
    free_users = db.session.query(User).join(Subscription).filter(
        Subscription.subscription_type == SubscriptionType.FREE
    ).count()
    
    # Recent broadcasts
    recent_broadcasts = AdminBroadcast.query.order_by(
        AdminBroadcast.created_at.desc()
    ).limit(5).all()
    
    stats = {
        'total_users': total_users,
        'total_bots': total_bots,
        'active_bots': active_bots,
        'free_users': free_users
    }
    
    return render_template('admin/dashboard.html', 
                         stats=stats, 
                         recent_broadcasts=recent_broadcasts)

@admin.route('/broadcasts')
@admin_required
def broadcasts():
    """List all broadcasts"""
    page = request.args.get('page', 1, type=int)
    broadcasts = AdminBroadcast.query.order_by(
        AdminBroadcast.created_at.desc()
    ).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/broadcasts.html', broadcasts=broadcasts)

@admin.route('/broadcasts/create', methods=['GET', 'POST'])
@admin_required
def create_broadcast():
    """Create new broadcast"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message_text = request.form.get('message_text', '').strip()
        message_html = request.form.get('message_html', '').strip()
        allow_basic = bool(request.form.get('allow_basic'))
        allow_premium = bool(request.form.get('allow_premium'))
        
        if not title or not message_text:
            flash('Title and message are required.', 'error')
            return render_template('admin/create_broadcast.html')
        
        # Sanitize HTML if provided
        if message_html:
            message_html = broadcast_service.sanitize_html(message_html)
        
        # Create broadcast
        broadcast = broadcast_service.create_broadcast(
            admin_id=current_user.id,
            title=title,
            message_text=message_text,
            message_html=message_html,
            target_subscription=SubscriptionType.FREE,
            allow_basic=allow_basic,
            allow_premium=allow_premium
        )
        
        if broadcast:
            flash('Broadcast created successfully!', 'success')
            return redirect(url_for('admin.broadcast_detail', broadcast_id=broadcast.id))
        else:
            flash('Failed to create broadcast.', 'error')
    
    return render_template('admin/create_broadcast.html')

@admin.route('/broadcasts/<int:broadcast_id>')
@admin_required
def broadcast_detail(broadcast_id):
    """View broadcast details"""
    broadcast = AdminBroadcast.query.get_or_404(broadcast_id)
    stats = broadcast_service.get_broadcast_stats(broadcast_id)
    
    return render_template('admin/broadcast_detail.html', 
                         broadcast=broadcast, 
                         stats=stats)

@admin.route('/broadcasts/<int:broadcast_id>/send', methods=['POST'])
@admin_required
def send_broadcast(broadcast_id):
    """Send broadcast to target users"""
    broadcast = AdminBroadcast.query.get_or_404(broadcast_id)
    
    if broadcast.is_sent:
        flash('Broadcast has already been sent.', 'error')
        return redirect(url_for('admin.broadcast_detail', broadcast_id=broadcast_id))
    
    # Send broadcast in background
    success, message = broadcast_service.send_broadcast(broadcast_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(f'Failed to send broadcast: {message}', 'error')
    
    return redirect(url_for('admin.broadcast_detail', broadcast_id=broadcast_id))

@admin.route('/broadcasts/<int:broadcast_id>/preview')
@admin_required
def preview_broadcast(broadcast_id):
    """Preview broadcast message"""
    broadcast = AdminBroadcast.query.get_or_404(broadcast_id)
    target_bots = broadcast_service.get_target_bots(broadcast)
    
    return render_template('admin/broadcast_preview.html', 
                         broadcast=broadcast, 
                         target_bots=target_bots[:10])  # Show first 10 for preview

@admin.route('/users')
@admin_required
def users():
    """List all users"""
    page = request.args.get('page', 1, type=int)
    users_query = User.query.order_by(User.created_at.desc())
    
    # Filter by subscription type if specified
    subscription_filter = request.args.get('subscription')
    if subscription_filter:
        users_query = users_query.join(Subscription).filter(
            Subscription.subscription_type == SubscriptionType(subscription_filter)
        )
    
    users_paginated = users_query.paginate(
        page=page, per_page=50, error_out=False
    )
    
    return render_template('admin/users.html', users=users_paginated)
