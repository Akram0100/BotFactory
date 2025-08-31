"""
Automatic notification service for trial and subscription reminders
"""
import logging
from datetime import datetime, timedelta
from flask import current_app
from app import db
from models import User, Subscription, SubscriptionType, NotificationType, NotificationTemplate, UserNotification, Bot
from services.telegram_service import TelegramService

class NotificationService:
    """Service for managing automatic notifications"""
    
    @staticmethod
    def initialize_templates():
        """Initialize default notification templates"""
        templates = [
            {
                'type': NotificationType.TRIAL_EXPIRING_3_DAYS,
                'uz': "Diqqat! Sizning bepul sinov muddatingiz 3 kun ichida tugaydi. Bot ishlashini davom etish uchun pullik obunaga o'ting! Pullik obuna afzalliklari: Cheksiz xabarlar, Premium qollab-quvvatlash, Qoshimcha botlar. Obuna bolish uchun: /subscription",
                'ru': "Внимание! Ваш бесплатный пробный период заканчивается через 3 дня. Для продолжения работы бота оформите платную подписку! Преимущества платной подписки: Безлимитные сообщения, Премиум поддержка, Дополнительные боты. Для подписки: /subscription",
                'en': "Attention! Your free trial expires in 3 days. Subscribe to a paid plan to continue using your bot! Paid subscription benefits: Unlimited messages, Premium support, Additional bots. To subscribe: /subscription"
            },
            {
                'type': NotificationType.TRIAL_EXPIRED,
                'uz': "Sizning bepul sinovingiz tugadi. Bot vaqtincha toxtatildi. Ishlashini davom etish uchun obuna boling! Obuna bolish uchun: /subscription",
                'ru': "Ваш бесплатный пробный период закончился. Бот временно приостановлен. Для продолжения работы оформите подписку! Для подписки: /subscription", 
                'en': "Your free trial has ended. Your bot is temporarily suspended. Subscribe to continue! To subscribe: /subscription"
            },
            {
                'type': NotificationType.SUBSCRIPTION_EXPIRING_1_DAY,
                'uz': "Sizning obunangiz ertaga tugaydi! Bot ishlashini davom etish uchun tolovni yangilang. Tolov qilish uchun: /subscription",
                'ru': "Ваша подписка заканчивается завтра! Обновите платеж для продолжения работы бота. Для оплаты: /subscription",
                'en': "Your subscription expires tomorrow! Renew your payment to continue using your bot. To pay: /subscription"
            },
            {
                'type': NotificationType.SUBSCRIPTION_EXPIRED,
                'uz': "Sizning obunangiz tugadi. Bot toxtatildi. Qayta faollashtirish uchun tolov qiling! Tolov qilish uchun: /subscription",
                'ru': "Ваша подписка истекла. Бот остановлен. Произведите оплату для возобновления! Для оплаты: /subscription",
                'en': "Your subscription has expired. Bot is stopped. Make a payment to reactivate! To pay: /subscription"
            }
        ]
        
        for template_data in templates:
            existing = NotificationTemplate.query.filter_by(
                notification_type=template_data['type']
            ).first()
            
            if not existing:
                template = NotificationTemplate(
                    notification_type=template_data['type'],
                    message_uz=template_data['uz'],
                    message_ru=template_data['ru'],
                    message_en=template_data['en']
                )
                db.session.add(template)
        
        try:
            db.session.commit()
            logging.info("Notification templates initialized")
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error initializing notification templates: {str(e)}")
    
    @staticmethod
    def check_and_send_notifications():
        """Check for users who need notifications and send them"""
        try:
            current_time = datetime.utcnow()
            
            # Check trial expiring in 3 days
            NotificationService._check_trial_expiring_3_days(current_time)
            
            # Check expired trials
            NotificationService._check_expired_trials(current_time)
            
            # Check subscription expiring in 1 day
            NotificationService._check_subscription_expiring_1_day(current_time)
            
            # Check expired subscriptions
            NotificationService._check_expired_subscriptions(current_time)
            
        except Exception as e:
            logging.error(f"Error in notification check: {str(e)}")
    
    @staticmethod
    def _check_trial_expiring_3_days(current_time):
        """Check for free trials expiring in 3 days"""
        three_days_from_now = current_time + timedelta(days=3)
        
        # Get free users whose trial expires in ~3 days (within 1 hour window)
        users = db.session.query(User).join(Subscription).filter(
            Subscription.subscription_type == SubscriptionType.FREE,
            Subscription.end_date.isnot(None),
            Subscription.end_date >= three_days_from_now - timedelta(hours=1),
            Subscription.end_date <= three_days_from_now + timedelta(hours=1),
            Subscription.is_active == True,
            User.active == True
        ).all()
        
        for user in users:
            # Check if notification already sent today
            existing = UserNotification.query.filter_by(
                user_id=user.id,
                notification_type=NotificationType.TRIAL_EXPIRING_3_DAYS
            ).filter(
                UserNotification.created_at >= current_time.date()
            ).first()
            
            if not existing:
                NotificationService._send_notification(user, NotificationType.TRIAL_EXPIRING_3_DAYS)
    
    @staticmethod
    def _check_expired_trials(current_time):
        """Check for expired free trials"""
        users = db.session.query(User).join(Subscription).filter(
            Subscription.subscription_type == SubscriptionType.FREE,
            Subscription.end_date.isnot(None),
            Subscription.end_date <= current_time,
            Subscription.is_active == True,
            User.active == True
        ).all()
        
        for user in users:
            # Check if notification already sent today
            existing = UserNotification.query.filter_by(
                user_id=user.id,
                notification_type=NotificationType.TRIAL_EXPIRED
            ).filter(
                UserNotification.created_at >= current_time.date()
            ).first()
            
            if not existing:
                NotificationService._send_notification(user, NotificationType.TRIAL_EXPIRED)
                # Deactivate user's bots
                NotificationService._deactivate_user_bots(user.id)
    
    @staticmethod
    def _check_subscription_expiring_1_day(current_time):
        """Check for paid subscriptions expiring in 1 day"""
        one_day_from_now = current_time + timedelta(days=1)
        
        users = db.session.query(User).join(Subscription).filter(
            Subscription.subscription_type.in_([SubscriptionType.BASIC, SubscriptionType.PREMIUM]),
            Subscription.end_date.isnot(None),
            Subscription.end_date >= one_day_from_now - timedelta(hours=1),
            Subscription.end_date <= one_day_from_now + timedelta(hours=1),
            Subscription.is_active == True,
            User.active == True
        ).all()
        
        for user in users:
            existing = UserNotification.query.filter_by(
                user_id=user.id,
                notification_type=NotificationType.SUBSCRIPTION_EXPIRING_1_DAY
            ).filter(
                UserNotification.created_at >= current_time.date()
            ).first()
            
            if not existing:
                NotificationService._send_notification(user, NotificationType.SUBSCRIPTION_EXPIRING_1_DAY)
    
    @staticmethod
    def _check_expired_subscriptions(current_time):
        """Check for expired paid subscriptions"""
        users = db.session.query(User).join(Subscription).filter(
            Subscription.subscription_type.in_([SubscriptionType.BASIC, SubscriptionType.PREMIUM]),
            Subscription.end_date.isnot(None),
            Subscription.end_date <= current_time,
            Subscription.is_active == True,
            User.active == True
        ).all()
        
        for user in users:
            existing = UserNotification.query.filter_by(
                user_id=user.id,
                notification_type=NotificationType.SUBSCRIPTION_EXPIRED
            ).filter(
                UserNotification.created_at >= current_time.date()
            ).first()
            
            if not existing:
                NotificationService._send_notification(user, NotificationType.SUBSCRIPTION_EXPIRED)
                # Deactivate subscription and user's bots
                user.subscription.is_active = False
                NotificationService._deactivate_user_bots(user.id)
                db.session.commit()
    
    @staticmethod
    def _send_notification(user, notification_type):
        """Send notification to user's bots"""
        try:
            # Get notification template
            template = NotificationTemplate.query.filter_by(
                notification_type=notification_type,
                is_active=True
            ).first()
            
            if not template:
                logging.error(f"No template found for {notification_type}")
                return False
            
            message_text = template.get_message(user.language)
            
            # Create notification record
            notification = UserNotification(
                user_id=user.id,
                notification_type=notification_type,
                message_text=message_text
            )
            db.session.add(notification)
            
            # Send to all user's active bots
            user_bots = Bot.query.filter_by(
                user_id=user.id,
                is_active=True
            ).filter(
                Bot.telegram_token.isnot(None)
            ).all()
            
            if not user_bots:
                notification.is_sent = True
                notification.sent_at = datetime.utcnow()
                notification.error_message = "No active bots found"
                db.session.commit()
                return True
            
            telegram_service = TelegramService()
            sent_count = 0
            
            for bot in user_bots:
                try:
                    # Get bot's conversations (unique users)
                    conversations = db.session.execute(
                        "SELECT DISTINCT telegram_user_id FROM conversations WHERE bot_id = :bot_id",
                        {"bot_id": bot.id}
                    ).fetchall()
                    
                    for conv in conversations:
                        try:
                            chat_id = conv[0]
                            sent = telegram_service.send_broadcast_message(
                                bot.telegram_token,
                                chat_id,
                                message_text
                            )
                            if sent:
                                sent_count += 1
                        except Exception as e:
                            logging.error(f"Error sending notification to chat {conv[0]}: {str(e)}")
                            continue
                            
                except Exception as e:
                    logging.error(f"Error processing bot {bot.id}: {str(e)}")
                    continue
            
            # Update notification status
            notification.is_sent = True
            notification.sent_at = datetime.utcnow()
            if sent_count == 0:
                notification.error_message = "No messages sent successfully"
            
            db.session.commit()
            logging.info(f"Sent {notification_type.value} notification to user {user.id}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error sending notification: {str(e)}")
            return False
    
    @staticmethod
    def _deactivate_user_bots(user_id):
        """Deactivate all bots for a user"""
        try:
            bots = Bot.query.filter_by(user_id=user_id, is_active=True).all()
            for bot in bots:
                bot.is_active = False
            db.session.commit()
            logging.info(f"Deactivated {len(bots)} bots for user {user_id}")
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error deactivating bots for user {user_id}: {str(e)}")
    
    @staticmethod
    def get_user_notifications(user_id, limit=20):
        """Get notification history for a user"""
        try:
            notifications = UserNotification.query.filter_by(
                user_id=user_id
            ).order_by(
                UserNotification.created_at.desc()
            ).limit(limit).all()
            return notifications
        except Exception as e:
            logging.error(f"Error getting user notifications: {str(e)}")
            return []