import os
import logging
import threading
import time
from telegram import Update, Bot as TelegramBot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from models import Bot, Conversation, Message
from app import db
from services.ai_service import AIService

class TelegramService:
    """Service for managing Telegram bot instances"""
    
    def __init__(self):
        self.ai_service = AIService()
        self.active_bots = {}  # Store active bot applications
        self.bot_threads = {}  # Store bot polling threads
    
    def validate_token(self, token):
        """Validate Telegram bot token and get bot info"""
        import asyncio
        
        async def _validate():
            try:
                telegram_bot = TelegramBot(token)
                bot_info = await telegram_bot.get_me()
                
                return {
                    'id': bot_info.id,
                    'username': bot_info.username,
                    'first_name': bot_info.first_name,
                    'is_bot': bot_info.is_bot
                }
            except Exception as e:
                logging.error(f"Token validation error: {e}")
                return None
        
        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, we need to use run_in_executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _validate())
                    return future.result()
            else:
                return loop.run_until_complete(_validate())
        except RuntimeError:
            # No event loop exists, create one
            return asyncio.run(_validate())
    
    def start_bot(self, bot):
        """Start a Telegram bot instance"""
        if not bot.telegram_token:
            logging.error(f"No Telegram token for bot {bot.id}")
            return False
        
        try:
            # Stop existing bot if running
            self.stop_bot(bot)
            
            # Create application
            application = Application.builder().token(bot.telegram_token).build()
            
            # Add handlers
            application.add_handler(CommandHandler("start", lambda u, c: self._handle_start_command(u, c, bot)))
            application.add_handler(CommandHandler("help", lambda u, c: self._handle_help_command(u, c, bot)))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, 
                                                 lambda u, c: self._handle_message(u, c, bot)))
            
            # Store application
            self.active_bots[bot.id] = application
            
            # Start polling in a separate thread with its own event loop
            def run_bot():
                import asyncio
                try:
                    # Create new event loop for this thread
                    asyncio.set_event_loop(asyncio.new_event_loop())
                    application.run_polling(allowed_updates=Update.ALL_TYPES)
                except Exception as e:
                    logging.error(f"Bot {bot.id} polling error: {e}")
                    # Clean up on error
                    if bot.id in self.active_bots:
                        del self.active_bots[bot.id]
                    if bot.id in self.bot_threads:
                        del self.bot_threads[bot.id]
            
            bot_thread = threading.Thread(target=run_bot, daemon=True)
            bot_thread.start()
            self.bot_threads[bot.id] = bot_thread
            
            logging.info(f"Started Telegram bot {bot.id} (@{bot.telegram_username})")
            return True
            
        except Exception as e:
            logging.error(f"Failed to start bot {bot.id}: {e}")
            return False
    
    def stop_bot(self, bot):
        """Stop a Telegram bot instance"""
        try:
            if bot.id in self.active_bots:
                application = self.active_bots[bot.id]
                try:
                    application.stop()
                except:
                    # If stop() fails, force cleanup
                    pass
                del self.active_bots[bot.id]
                
            if bot.id in self.bot_threads:
                # Thread will stop when application stops
                del self.bot_threads[bot.id]
            
            logging.info(f"Stopped Telegram bot {bot.id}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to stop bot {bot.id}: {e}")
            return False
    
    async def _handle_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle /start command"""
        user = update.effective_user
        
        welcome_message = f"Hello {user.first_name}! 👋\n\n"
        welcome_message += f"I'm {bot.name}, an AI-powered assistant.\n"
        
        if bot.description:
            welcome_message += f"{bot.description}\n\n"
        else:
            welcome_message += "I'm here to help answer your questions and assist you.\n\n"
        
        welcome_message += "Just send me a message and I'll do my best to help!"
        
        await update.message.reply_text(welcome_message)
        
        # Update conversation record
        await self._update_conversation(update, bot)
    
    async def _handle_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle /help command"""
        help_message = f"🤖 {bot.name} - AI Assistant\n\n"
        help_message += "Here's how to use me:\n"
        help_message += "• Just send me any message and I'll respond\n"
        help_message += "• Ask questions on any topic\n"
        help_message += "• I can help with information, advice, and general assistance\n\n"
        help_message += "Commands:\n"
        help_message += "/start - Get welcome message\n"
        help_message += "/help - Show this help message\n\n"
        help_message += "Feel free to ask me anything! 💬"
        
        await update.message.reply_text(help_message)
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle regular text messages"""
        try:
            user = update.effective_user
            user_message = update.message.text
            
            # Show typing indicator
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
            
            # Get AI response
            ai_response = self.ai_service.get_response(bot, user_message)
            
            # Send response
            await update.message.reply_text(ai_response)
            
            # Store conversation in database (in background)
            await self._store_message(update, bot, user_message, ai_response)
            
        except Exception as e:
            logging.error(f"Message handling error for bot {bot.id}: {e}")
            await update.message.reply_text(
                "I apologize, but I'm experiencing some technical difficulties. Please try again in a moment."
            )
    
    async def _update_conversation(self, update: Update, bot):
        """Update or create conversation record"""
        try:
            user = update.effective_user
            telegram_user_id = str(user.id)
            
            # Find or create conversation
            conversation = Conversation.query.filter_by(
                bot_id=bot.id,
                telegram_user_id=telegram_user_id
            ).first()
            
            if not conversation:
                conversation = Conversation(
                    bot_id=bot.id,
                    telegram_user_id=telegram_user_id,
                    telegram_username=user.username or user.first_name
                )
                db.session.add(conversation)
                
                # Update bot's total users count
                bot.total_users += 1
            
            conversation.last_message = db.func.now()
            db.session.commit()
            
        except Exception as e:
            logging.error(f"Conversation update error: {e}")
            db.session.rollback()
    
    async def _store_message(self, update: Update, bot, user_message, ai_response):
        """Store message in database"""
        try:
            user = update.effective_user
            telegram_user_id = str(user.id)
            
            # Find conversation
            conversation = Conversation.query.filter_by(
                bot_id=bot.id,
                telegram_user_id=telegram_user_id
            ).first()
            
            if not conversation:
                # Create conversation if it doesn't exist
                conversation = Conversation(
                    bot_id=bot.id,
                    telegram_user_id=telegram_user_id,
                    telegram_username=user.username or user.first_name
                )
                db.session.add(conversation)
                db.session.flush()  # Get ID
            
            # Create message record
            message = Message(
                conversation_id=conversation.id,
                user_message=user_message,
                bot_response=ai_response
            )
            db.session.add(message)
            
            # Update counts
            conversation.message_count += 1
            bot.total_messages += 1
            bot.last_activity = db.func.now()
            
            db.session.commit()
            
        except Exception as e:
            logging.error(f"Message storage error: {e}")
            db.session.rollback()
    
    def get_bot_stats(self, bot):
        """Get statistics for a bot"""
        try:
            conversations = Conversation.query.filter_by(bot_id=bot.id).all()
            total_messages = sum(conv.message_count for conv in conversations)
            
            return {
                'total_users': len(conversations),
                'total_messages': total_messages,
                'active_conversations': len([conv for conv in conversations if conv.last_message and 
                                           (db.func.now() - conv.last_message).days < 7]),
                'last_activity': bot.last_activity
            }
        except Exception as e:
            logging.error(f"Bot stats error: {e}")
            return {
                'total_users': 0,
                'total_messages': 0,
                'active_conversations': 0,
                'last_activity': None
            }
    
    def restart_all_active_bots(self):
        """Restart all active bots (useful for application restart)"""
        try:
            from models import Bot, BotStatus
            active_bots = Bot.query.filter_by(status=BotStatus.ACTIVE).all()
            
            for bot in active_bots:
                if bot.telegram_token:
                    self.start_bot(bot)
                    time.sleep(1)  # Small delay between starts
            
            logging.info(f"Restarted {len(active_bots)} active bots")
            
        except Exception as e:
            logging.error(f"Bot restart error: {e}")

# Initialize service instance
telegram_service = TelegramService()

# Auto-start active bots when service initializes
def auto_start_bots():
    """Auto-start all active bots on service initialization"""
    try:
        # Import here to avoid circular imports
        from models import Bot, BotStatus
        from app import create_app
        
        # Small delay to ensure database is ready
        time.sleep(2)
        
        # Create app context for database access
        app = create_app()
        with app.app_context():
            active_bots = Bot.query.filter_by(status=BotStatus.ACTIVE).all()
            for bot in active_bots:
                if bot.telegram_token:
                    telegram_service.start_bot(bot)
                    time.sleep(1)
            
            logging.info(f"Auto-started {len(active_bots)} active bots")
        
    except Exception as e:
        logging.error(f"Auto-start bots error: {e}")

# Start bots in a background thread
threading.Thread(target=auto_start_bots, daemon=True).start()
