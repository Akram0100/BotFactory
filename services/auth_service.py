import logging
from models import User, Subscription, SubscriptionType
from app import db

class AuthService:
    """Service for user authentication and management"""
    
    def authenticate_user(self, username, password):
        """Authenticate user with username and password"""
        try:
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                if not user.is_active:
                    logging.warning(f"Inactive user login attempt: {username}")
                    return None
                return user
            return None
        except Exception as e:
            logging.error(f"Authentication error for {username}: {e}")
            return None
    
    def create_user(self, username, email, password, first_name=None, last_name=None):
        """Create a new user account"""
        try:
            # Create user
            user = User()
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.set_password(password)
            
            db.session.add(user)
            db.session.flush()  # Get user ID
            
            # Create default subscription
            subscription = Subscription()
            subscription.user_id = user.id
            subscription.subscription_type = SubscriptionType.FREE
            subscription.max_bots = 1
            subscription.max_messages_per_month = 100
            
            db.session.add(subscription)
            db.session.commit()
            
            logging.info(f"Created new user: {username} ({email})")
            return user
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"User creation error: {e}")
            raise e
    
    def update_user_profile(self, user, **kwargs):
        """Update user profile information"""
        try:
            for key, value in kwargs.items():
                if hasattr(user, key) and value is not None:
                    setattr(user, key, value)
            
            db.session.commit()
            logging.info(f"Updated profile for user {user.username}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Profile update error for user {user.username}: {e}")
            return False
    
    def change_password(self, user, old_password, new_password):
        """Change user password"""
        try:
            if not user.check_password(old_password):
                return False, "Current password is incorrect"
            
            if len(new_password) < 6:
                return False, "New password must be at least 6 characters long"
            
            user.set_password(new_password)
            db.session.commit()
            
            logging.info(f"Password changed for user {user.username}")
            return True, "Password changed successfully"
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Password change error for user {user.username}: {e}")
            return False, "Failed to change password"
    
    def deactivate_user(self, user):
        """Deactivate user account"""
        try:
            user.is_active = False
            db.session.commit()
            
            logging.info(f"Deactivated user {user.username}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"User deactivation error for {user.username}: {e}")
            return False
    
    def reactivate_user(self, user):
        """Reactivate user account"""
        try:
            user.is_active = True
            db.session.commit()
            
            logging.info(f"Reactivated user {user.username}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"User reactivation error for {user.username}: {e}")
            return False
    
    def get_user_stats(self, user):
        """Get user statistics"""
        try:
            from models import Bot
            
            user_bots = Bot.query.filter_by(user_id=user.id).all()
            total_messages = sum(bot.total_messages for bot in user_bots)
            
            return {
                'total_bots': len(user_bots),
                'active_bots': len([bot for bot in user_bots if bot.is_active]),
                'total_messages': total_messages,
                'account_age_days': (db.func.now() - user.created_at).days if user.created_at else 0
            }
            
        except Exception as e:
            logging.error(f"User stats error for {user.username}: {e}")
            return {
                'total_bots': 0,
                'active_bots': 0,
                'total_messages': 0,
                'account_age_days': 0
            }
