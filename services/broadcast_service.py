"""
Broadcast service for sending admin messages to user bots
"""
import asyncio
from datetime import datetime
from flask import current_app
from app import db
from models import Bot, User, Subscription, SubscriptionType, AdminBroadcast, BroadcastDelivery
from services.telegram_service import TelegramService
import html
import re


class BroadcastService:
    """Service for managing admin broadcast messages"""
    
    @staticmethod
    def create_broadcast(admin_id, title, message_text, message_html=None, 
                        target_subscription=SubscriptionType.FREE, 
                        allow_basic=False, allow_premium=False, scheduled_at=None):
        """Create a new broadcast message"""
        try:
            broadcast = AdminBroadcast(
                admin_id=admin_id,
                title=title,
                message_text=message_text,
                message_html=message_html,
                target_subscription=target_subscription,
                allow_basic=allow_basic,
                allow_premium=allow_premium,
                scheduled_at=scheduled_at,
                is_scheduled=scheduled_at is not None
            )
            
            db.session.add(broadcast)
            db.session.commit()
            
            return broadcast
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating broadcast: {str(e)}")
            return None
    
    @staticmethod
    def get_target_bots(broadcast):
        """Get list of bots that should receive the broadcast"""
        try:
            # Build subscription filter
            target_subscriptions = [broadcast.target_subscription]
            
            if broadcast.allow_basic:
                target_subscriptions.append(SubscriptionType.BASIC)
            if broadcast.allow_premium:
                target_subscriptions.append(SubscriptionType.PREMIUM)
            
            # Get users with target subscriptions
            target_users = db.session.query(User).join(Subscription).filter(
                Subscription.subscription_type.in_(target_subscriptions),
                Subscription.is_active == True,
                User.active == True
            ).all()
            
            # Get active bots for these users
            target_bots = []
            for user in target_users:
                user_bots = Bot.query.filter_by(
                    user_id=user.id,
                    is_active=True
                ).filter(
                    Bot.telegram_token.isnot(None)
                ).all()
                target_bots.extend(user_bots)
            
            return target_bots
        except Exception as e:
            current_app.logger.error(f"Error getting target bots: {str(e)}")
            return []
    
    @staticmethod
    def send_broadcast(broadcast_id):
        """Send broadcast message to all target bots"""
        try:
            broadcast = AdminBroadcast.query.get(broadcast_id)
            if not broadcast:
                return False, "Broadcast not found"
            
            if broadcast.is_sent:
                return False, "Broadcast already sent"
            
            target_bots = BroadcastService.get_target_bots(broadcast)
            broadcast.total_bots = len(target_bots)
            db.session.commit()
            
            successful_sends = 0
            failed_sends = 0
            
            for bot in target_bots:
                try:
                    # Create delivery log entry
                    delivery = BroadcastDelivery(
                        broadcast_id=broadcast.id,
                        bot_id=bot.id,
                        user_id=bot.user_id
                    )
                    
                    # Try to send message through bot
                    message_sent = BroadcastService._send_to_bot_users(bot, broadcast)
                    
                    if message_sent:
                        delivery.delivered = True
                        delivery.delivered_at = datetime.utcnow()
                        successful_sends += 1
                    else:
                        delivery.delivered = False
                        delivery.error_message = "Failed to send message"
                        failed_sends += 1
                    
                    db.session.add(delivery)
                    
                except Exception as e:
                    current_app.logger.error(f"Error sending to bot {bot.id}: {str(e)}")
                    delivery = BroadcastDelivery(
                        broadcast_id=broadcast.id,
                        bot_id=bot.id,
                        user_id=bot.user_id,
                        delivered=False,
                        error_message=str(e)
                    )
                    db.session.add(delivery)
                    failed_sends += 1
            
            # Update broadcast status
            broadcast.is_sent = True
            broadcast.sent_at = datetime.utcnow()
            broadcast.successful_sends = successful_sends
            broadcast.failed_sends = failed_sends
            
            db.session.commit()
            
            return True, f"Broadcast sent to {successful_sends} bots successfully, {failed_sends} failed"
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error sending broadcast: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def _send_to_bot_users(bot, broadcast):
        """Send broadcast message to all users of a specific bot"""
        try:
            if not bot.telegram_token:
                return False
            
            # Get all conversations for this bot (unique users)
            conversations = db.session.query(
                db.func.distinct(db.text('telegram_user_id'))
            ).select_from(db.text('conversations')).filter(
                db.text('bot_id = :bot_id')
            ).params(bot_id=bot.id).all()
            
            if not conversations:
                return True  # No users to send to, consider successful
            
            telegram_service = TelegramService()
            
            # Prepare message text
            message = broadcast.message_html if broadcast.message_html else broadcast.message_text
            
            # Add footer for free users
            if bot.owner.subscription and bot.owner.subscription.subscription_type == SubscriptionType.FREE:
                footer = "\n\n📢 " + ("Bu xabar BotFactory platformasi tomonidan yuborildi" if bot.owner.language == 'uz' 
                                       else "Это сообщение отправлено платформой BotFactory" if bot.owner.language == 'ru'
                                       else "This message is sent by BotFactory platform")
                message += footer
            
            success_count = 0
            for conv in conversations:
                try:
                    chat_id = conv[0]
                    
                    # Send message using bot's token
                    sent = telegram_service.send_broadcast_message(
                        bot.telegram_token, 
                        chat_id, 
                        message,
                        parse_mode='HTML' if broadcast.message_html else None
                    )
                    
                    if sent:
                        success_count += 1
                        
                except Exception as e:
                    current_app.logger.error(f"Error sending to chat {conv[0]}: {str(e)}")
                    continue
            
            return success_count > 0
            
        except Exception as e:
            current_app.logger.error(f"Error in _send_to_bot_users: {str(e)}")
            return False
    
    @staticmethod
    def get_broadcast_history(admin_id=None, limit=50):
        """Get broadcast history"""
        try:
            query = AdminBroadcast.query
            
            if admin_id:
                query = query.filter_by(admin_id=admin_id)
            
            broadcasts = query.order_by(AdminBroadcast.created_at.desc()).limit(limit).all()
            return broadcasts
        except Exception as e:
            current_app.logger.error(f"Error getting broadcast history: {str(e)}")
            return []
    
    @staticmethod
    def get_broadcast_stats(broadcast_id):
        """Get detailed statistics for a broadcast"""
        try:
            broadcast = AdminBroadcast.query.get(broadcast_id)
            if not broadcast:
                return None
            
            total_deliveries = BroadcastDelivery.query.filter_by(broadcast_id=broadcast_id).count()
            successful_deliveries = BroadcastDelivery.query.filter_by(
                broadcast_id=broadcast_id, 
                delivered=True
            ).count()
            failed_deliveries = BroadcastDelivery.query.filter_by(
                broadcast_id=broadcast_id, 
                delivered=False
            ).count()
            
            return {
                'broadcast': broadcast,
                'total_deliveries': total_deliveries,
                'successful_deliveries': successful_deliveries,
                'failed_deliveries': failed_deliveries,
                'success_rate': (successful_deliveries / total_deliveries * 100) if total_deliveries > 0 else 0
            }
        except Exception as e:
            current_app.logger.error(f"Error getting broadcast stats: {str(e)}")
            return None
    
    @staticmethod
    def check_and_send_scheduled_broadcasts():
        """Check for scheduled broadcasts that are ready to be sent"""
        try:
            current_time = datetime.utcnow()
            
            # Get scheduled broadcasts that are ready to send
            ready_broadcasts = AdminBroadcast.query.filter(
                AdminBroadcast.is_scheduled == True,
                AdminBroadcast.is_sent == False,
                AdminBroadcast.scheduled_at <= current_time
            ).all()
            
            results = []
            for broadcast in ready_broadcasts:
                success, message = BroadcastService.send_broadcast(broadcast.id)
                results.append({
                    'broadcast_id': broadcast.id,
                    'title': broadcast.title,
                    'success': success,
                    'message': message
                })
            
            return results
            
        except Exception as e:
            current_app.logger.error(f"Error checking scheduled broadcasts: {str(e)}")
            return []
    
    @staticmethod
    def get_scheduled_broadcasts(admin_id=None):
        """Get list of scheduled broadcasts"""
        try:
            query = AdminBroadcast.query.filter(
                AdminBroadcast.is_scheduled == True,
                AdminBroadcast.is_sent == False
            )
            
            if admin_id:
                query = query.filter_by(admin_id=admin_id)
            
            broadcasts = query.order_by(AdminBroadcast.scheduled_at.asc()).all()
            return broadcasts
        except Exception as e:
            current_app.logger.error(f"Error getting scheduled broadcasts: {str(e)}")
            return []
    
    @staticmethod
    def cancel_scheduled_broadcast(broadcast_id, admin_id=None):
        """Cancel a scheduled broadcast"""
        try:
            query = AdminBroadcast.query.filter_by(id=broadcast_id)
            if admin_id:
                query = query.filter_by(admin_id=admin_id)
            
            broadcast = query.first()
            if not broadcast:
                return False, "Broadcast not found"
            
            if broadcast.is_sent:
                return False, "Cannot cancel already sent broadcast"
            
            broadcast.is_scheduled = False
            broadcast.scheduled_at = None
            db.session.commit()
            
            return True, "Broadcast cancelled successfully"
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error cancelling broadcast: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def sanitize_html(html_content):
        """Sanitize HTML content for Telegram"""
        if not html_content:
            return html_content
        
        # Allowed tags for Telegram
        allowed_tags = ['b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'code', 'pre', 'a']
        
        # Simple HTML sanitization - remove disallowed tags
        clean_html = html_content
        for tag in re.findall(r'<[^>]+>', html_content):
            tag_name = tag.replace('<', '').replace('>', '').replace('/', '').split()[0].lower()
            if tag_name not in allowed_tags:
                clean_html = clean_html.replace(tag, '')
        
        return clean_html