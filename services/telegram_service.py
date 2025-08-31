import os
import logging
import threading
import time
from telegram import Update, Bot as TelegramBot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from models import Bot
from app import db
from services.ai_service import AIService

class TelegramService:
    """Service for managing Telegram bot instances"""
    
    def __init__(self):
        self.ai_service = AIService()
        self.active_bots = {}  # Store active bot applications
        self.bot_threads = {}  # Store bot polling threads
        self.user_languages = {}  # Store user language preferences
    
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
            
            # Add handlers with proper async wrapper
            async def start_wrapper(update, context):
                return await self._handle_start_command(update, context, bot)
            
            async def help_wrapper(update, context):
                return await self._handle_help_command(update, context, bot)
            
            async def message_wrapper(update, context):
                return await self._handle_message(update, context, bot)
            
            async def callback_wrapper(update, context):
                return await self._handle_callback(update, context, bot)
            
            application.add_handler(CommandHandler("start", start_wrapper))
            application.add_handler(CommandHandler("help", help_wrapper))
            application.add_handler(CallbackQueryHandler(callback_wrapper))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_wrapper))
            
            # Store application
            self.active_bots[bot.id] = application
            
            # Start polling in a separate thread with proper async setup
            def run_bot():
                import asyncio
                try:
                    # Create and set new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Run the application
                    loop.run_until_complete(application.initialize())
                    loop.run_until_complete(application.start())
                    loop.run_until_complete(application.updater.start_polling())
                    
                    # Keep the loop running
                    loop.run_forever()
                    
                except Exception as e:
                    logging.error(f"Bot {bot.id} polling error: {e}")
                    # Clean up on error
                    if bot.id in self.active_bots:
                        del self.active_bots[bot.id]
                    if bot.id in self.bot_threads:
                        del self.bot_threads[bot.id]
                finally:
                    if 'loop' in locals():
                        loop.close()
            
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
                    # Try to stop the application gracefully
                    import asyncio
                    
                    # Create a task to stop the application
                    async def stop_app():
                        try:
                            await application.updater.stop()
                            await application.stop()
                            await application.shutdown()
                        except Exception as e:
                            logging.error(f"Error during app shutdown: {e}")
                    
                    # Run the stop task in a new event loop if needed
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Schedule the stop task
                            asyncio.create_task(stop_app())
                        else:
                            loop.run_until_complete(stop_app())
                    except RuntimeError:
                        # No loop exists, create one
                        asyncio.run(stop_app())
                        
                except Exception as e:
                    logging.error(f"Error stopping application: {e}")
                    # Force cleanup even if stop fails
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
        try:
            user = update.effective_user
            welcome_message = f"Salom {user.first_name}! 👋\n\n"
            welcome_message += f"Men {bot.name} botiman. Sizga qanday yordam bera olaman?\n\n"
            welcome_message += "Menga savolingizni yuboring va men sizga javob beraman! 💬"
            
            # Send notification to admin about new user
            await self._send_notification(bot, f"🆕 Yangi foydalanuvchi: {user.first_name} (@{user.username or 'username yoq'}) - ID: {user.id}")
            
            # Update bot statistics
            await self._update_bot_stats(bot)
            
            await update.message.reply_text(welcome_message)
            
        except Exception as e:
            logging.error(f"Start command error: {e}")
            await update.message.reply_text("Kechirasiz, xatolik yuz berdi.")
    
    async def _handle_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle /help command"""
        try:
            help_message = f"ℹ️ **{bot.name} - Yordam**\n\n"
            help_message += "**Qanday foydalanish:**\n"
            help_message += "• Menga oddiy matn yuboring\n"
            help_message += "• Men sizga javob beraman\n"
            help_message += "• /start - Botni qayta ishga tushirish\n"
            help_message += "• /help - Bu yordam habarini ko'rish\n\n"
            help_message += "Savollar bormi? Menga yozing! 😊"
            
            await update.message.reply_text(help_message, parse_mode='Markdown')
            
        except Exception as e:
            logging.error(f"Help command error: {e}")
            await update.message.reply_text("Yordam habarini yuklashda xatolik yuz berdi.")
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle regular text messages"""
        try:
            user = update.effective_user
            user_message = update.message.text
            
            # Send notification to admin about user message
            notification_text = f"💬 **Yangi xabar**\n"
            notification_text += f"👤 Foydalanuvchi: {user.first_name} (@{user.username or 'username yoq'})\n"
            notification_text += f"🆔 ID: {user.id}\n"
            notification_text += f"📝 Xabar: {user_message}"
            
            await self._send_notification(bot, notification_text)
            
            # Get AI response
            ai_response = self.ai_service.get_response(bot, user_message)
            
            # Send response to user
            if ai_response:
                await update.message.reply_text(ai_response)
                
                # Send AI response notification to admin
                response_notification = f"🤖 **Bot javobi**\n"
                response_notification += f"👤 Foydalanuvchi: {user.first_name}\n"
                response_notification += f"📤 Javob: {ai_response}"
                
                await self._send_notification(bot, response_notification)
            else:
                await update.message.reply_text("Kechirasiz, hozir javob bera olmayman. Keyinroq qaytib urinib ko'ring.")
            
            # Update bot statistics
            await self._update_bot_stats(bot)
            
        except Exception as e:
            logging.error(f"Message handling error: {e}")
            await update.message.reply_text("Kechirasiz, xatolik yuz berdi.")
    
    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle callback queries from inline keyboards"""
        try:
            query = update.callback_query
            await query.answer()
            
            user = query.from_user
            callback_data = query.data
            
            # Send notification about callback
            notification_text = f"🔘 **Callback query**\n"
            notification_text += f"👤 Foydalanuvchi: {user.first_name} (@{user.username or 'username yoq'})\n"
            notification_text += f"🆔 ID: {user.id}\n"
            notification_text += f"🔗 Data: {callback_data}"
            
            await self._send_notification(bot, notification_text)
            
            # Handle different callback actions
            if callback_data == "help":
                await self._handle_help_command(update, context, bot)
            else:
                await query.edit_message_text("Tanlov amalga oshirildi!")
            
        except Exception as e:
            logging.error(f"Callback handling error: {e}")
    
    async def _send_notification(self, bot, message):
        """Send notification to admin chat or channel"""
        try:
            # Create a new bot instance for sending notifications
            if bot.telegram_token:
                notification_bot = TelegramBot(bot.telegram_token)
                
                # Send to admin chat if configured
                if bot.admin_chat_id:
                    try:
                        await notification_bot.send_message(
                            chat_id=bot.admin_chat_id,
                            text=message,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logging.error(f"Failed to send notification to admin chat {bot.admin_chat_id}: {e}")
                
                # Send to notification channel if configured
                if bot.notification_channel:
                    try:
                        await notification_bot.send_message(
                            chat_id=bot.notification_channel,
                            text=message,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logging.error(f"Failed to send notification to channel {bot.notification_channel}: {e}")
                        
        except Exception as e:
            logging.error(f"Notification error: {e}")
    
    async def _update_bot_stats(self, bot):
        """Update bot statistics"""
        try:
            from app import app
            with app.app_context():
                # Update message count and last activity
                bot.total_messages += 1
                bot.last_activity = db.func.now()
                db.session.commit()
                
        except Exception as e:
            logging.error(f"Bot stats update error: {e}")
            try:
                db.session.rollback()
            except:
                pass
    
    def get_active_bots(self):
        """Get list of currently active bot IDs"""
        return list(self.active_bots.keys())
    
    def is_bot_active(self, bot_id):
        """Check if a bot is currently active"""
        return bot_id in self.active_bots
    
    def restart_all_bots(self):
        """Restart all active bots"""
        try:
            from app import app
            with app.app_context():
                # Get all active bots from database
                active_bots = Bot.query.filter_by(status='ACTIVE').all()
                
                for bot in active_bots:
                    if bot.telegram_token:
                        self.start_bot(bot)
                        
                logging.info(f"Auto-started {len(active_bots)} active bots")
                
        except Exception as e:
            logging.error(f"Bot restart error: {e}")