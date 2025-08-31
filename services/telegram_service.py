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
        """Handle /start command with language selection"""
        try:
            user = update.effective_user
            if not user:
                logging.error("No user in update")
                return
                
            user_id = user.id
            
            # Check if user already has language preference
            if user_id in self.user_languages:
                # User has language preference, show welcome in that language
                await self._show_welcome_message(update, bot, self.user_languages[user_id])
            else:
                # Show language selection
                await self._show_language_selection(update, bot)
            
            # Send notification to admin about new user
            await self._send_notification(bot, f"🆕 Yangi foydalanuvchi: {user.first_name} (@{user.username or 'username yoq'}) - ID: {user.id}")
            
            # Update bot statistics
            await self._update_bot_stats(bot)
            
        except Exception as e:
            logging.error(f"Start command error: {e}")
            # Fallback error message in multiple languages
            error_msg = "❌ Xatolik / Ошибка / Error\n\n"
            error_msg += "🇺🇿 Kechirasiz, xatolik yuz berdi.\n"
            error_msg += "🇷🇺 Извините, произошла ошибка.\n"
            error_msg += "🇬🇧 Sorry, an error occurred."
            if update and update.message:
                await update.message.reply_text(error_msg)
    
    async def _handle_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle /help command"""
        try:
            if not update.effective_user:
                return
            user_id = update.effective_user.id
            user_lang = self.user_languages.get(user_id, 'uz')
            
            help_message = self._get_localized_help_message(bot.name, user_lang)
            
            await update.message.reply_text(help_message, parse_mode='Markdown')
            
        except Exception as e:
            logging.error(f"Help command error: {e}")
            if update and update.effective_user and update.message:
                user_id = update.effective_user.id
                user_lang = self.user_languages.get(user_id, 'uz')
                error_msg = self._get_localized_text('error', user_lang)
                await update.message.reply_text(error_msg)
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle regular text messages"""
        try:
            user = update.effective_user
            if not user or not update.message or not update.message.text:
                return
                
            user_message = update.message.text
            user_id = user.id
            user_lang = self.user_languages.get(user_id, 'uz')
            
            # Send notification to admin about user message
            notification_text = f"💬 **Yangi xabar**\n"
            notification_text += f"👤 Foydalanuvchi: {user.first_name} (@{user.username or 'username yoq'})\n"
            notification_text += f"🆔 ID: {user.id}\n"
            notification_text += f"🌐 Til: {user_lang}\n"
            notification_text += f"📝 Xabar: {user_message}"
            
            await self._send_notification(bot, notification_text)
            
            # Get AI response with user's language preference
            ai_response = self.ai_service.get_response(bot, user_message, user_language=user_lang)
            
            # Send response to user
            if ai_response:
                await update.message.reply_text(ai_response)
                
                # Send AI response notification to admin
                response_notification = f"🤖 **Bot javobi**\n"
                response_notification += f"👤 Foydalanuvchi: {user.first_name}\n"
                response_notification += f"📤 Javob: {ai_response}"
                
                await self._send_notification(bot, response_notification)
            else:
                no_response_msg = self._get_localized_text('no_response', user_lang)
                await update.message.reply_text(no_response_msg)
            
            # Update bot statistics
            await self._update_bot_stats(bot)
            
        except Exception as e:
            logging.error(f"Message handling error: {e}")
            if update and update.message:
                user_id = update.effective_user.id if update.effective_user else None
                user_lang = self.user_languages.get(user_id, 'uz') if user_id else 'uz'
                error_msg = self._get_localized_text('error', user_lang)
                await update.message.reply_text(error_msg)
    
    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle callback queries from inline keyboards"""
        try:
            query = update.callback_query
            if not query:
                return
                
            await query.answer()
            
            user = query.from_user
            if not user or not query.data:
                return
                
            callback_data = query.data
            user_id = user.id
            
            # Send notification about callback
            notification_text = f"🔘 **Callback query**\n"
            notification_text += f"👤 Foydalanuvchi: {user.first_name} (@{user.username or 'username yoq'})\n"
            notification_text += f"🆔 ID: {user.id}\n"
            notification_text += f"🔗 Data: {callback_data}"
            
            await self._send_notification(bot, notification_text)
            
            # Handle language selection
            if callback_data.startswith("lang_"):
                language = callback_data.split("_")[1]  # Extract language code
                self.user_languages[user_id] = language
                
                # Show welcome message in selected language
                await self._show_welcome_message(query, bot, language, edit_message=True)
                
            # Handle different callback actions
            elif callback_data == "help":
                await self._handle_help_command(update, context, bot)
            else:
                # Get user's language for response
                user_lang = self.user_languages.get(user_id, 'uz')
                response_msg = self._get_localized_text("selection_completed", user_lang)
                await query.edit_message_text(response_msg)
            
        except Exception as e:
            logging.error(f"Callback handling error: {e}")
            if query:
                try:
                    await query.answer("Xatolik yuz berdi / Ошибка / Error")
                except:
                    pass
    
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
    
    async def _show_language_selection(self, update, bot):
        """Show language selection menu"""
        try:
            user = update.effective_user
            if not user or not update.message:
                return
            
            # Create multilingual welcome message
            welcome_text = "🌐 **Tilni tanlang / Выберите язык / Choose Language**\\n\\n"
            welcome_text += f"Salom {user.first_name}! Men {bot.name} botiman.\\n"
            welcome_text += f"Привет {user.first_name}! Я бот {bot.name}.\\n" 
            welcome_text += f"Hello {user.first_name}! I'm {bot.name} bot.\\n\\n"
            welcome_text += "Muloqot uchun tilni tanlang:"
            
            # Create inline keyboard with language options
            keyboard = [
                [InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz")],
                [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
                [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logging.error(f"Language selection error: {e}")
    
    async def _show_welcome_message(self, update_or_query, bot, language, edit_message=False):
        """Show welcome message in selected language"""
        try:
            if edit_message:
                # This is from callback query
                user = update_or_query.from_user
                if not user:
                    return
            else:
                # This is from regular update
                user = update_or_query.effective_user
                if not user or not update_or_query.message:
                    return
            
            welcome_msg = self._get_localized_welcome_message(user.first_name, bot.name, language)
            
            if edit_message:
                await update_or_query.edit_message_text(welcome_msg, parse_mode='Markdown')
            else:
                await update_or_query.message.reply_text(welcome_msg, parse_mode='Markdown')
                
        except Exception as e:
            logging.error(f"Welcome message error: {e}")
    
    def _get_localized_welcome_message(self, user_name, bot_name, language):
        """Get welcome message in specified language"""
        messages = {
            'uz': {
                'welcome': f"Salom {user_name}! 👋\\n\\n"
                          f"Men {bot_name} botiman. Sizga qanday yordam bera olaman?\\n\\n"
                          f"Menga savolingizni yuboring va men sizga javob beraman! 💬\\n\\n"
                          f"Tilni o'zgartirish uchun /start buyrug'ini qayta yuboring."
            },
            'ru': {
                'welcome': f"Привет {user_name}! 👋\\n\\n"
                          f"Я бот {bot_name}. Как я могу вам помочь?\\n\\n"
                          f"Отправьте мне ваш вопрос, и я отвечу! 💬\\n\\n"
                          f"Чтобы изменить язык, отправьте команду /start снова."
            },
            'en': {
                'welcome': f"Hello {user_name}! 👋\\n\\n"
                          f"I'm {bot_name} bot. How can I help you?\\n\\n"
                          f"Send me your question and I'll respond! 💬\\n\\n"
                          f"To change language, send /start command again."
            }
        }
        
        return messages.get(language, messages['uz'])['welcome']
    
    def _get_localized_text(self, key, language):
        """Get localized text for given key and language"""
        texts = {
            'selection_completed': {
                'uz': "Tanlov amalga oshirildi! ✅",
                'ru': "Выбор сделан! ✅", 
                'en': "Selection completed! ✅"
            },
            'error': {
                'uz': "Kechirasiz, xatolik yuz berdi.",
                'ru': "Извините, произошла ошибка.",
                'en': "Sorry, an error occurred."
            },
            'no_response': {
                'uz': "Kechirasiz, hozir javob bera olmayman. Keyinroq qaytib urinib ko'ring.",
                'ru': "Извините, не могу ответить сейчас. Попробуйте позже.",
                'en': "Sorry, I can't respond right now. Please try again later."
            }
        }
        
        return texts.get(key, {}).get(language, texts.get(key, {}).get('uz', 'Unknown'))
    
    def _get_localized_help_message(self, bot_name, language):
        """Get help message in specified language"""
        help_messages = {
            'uz': {
                'help': f"ℹ️ **{bot_name} - Yordam**\\n\\n"
                       f"**Qanday foydalanish:**\\n"
                       f"• Menga oddiy matn yuboring\\n"
                       f"• Men sizga javob beraman\\n"
                       f"• /start - Botni qayta ishga tushirish\\n"
                       f"• /help - Bu yordam habarini ko'rish\\n\\n"
                       f"Savollar bormi? Menga yozing! 😊"
            },
            'ru': {
                'help': f"ℹ️ **{bot_name} - Помощь**\\n\\n"
                       f"**Как использовать:**\\n"
                       f"• Отправьте мне обычное сообщение\\n"
                       f"• Я отвечу вам\\n"
                       f"• /start - Перезапустить бота\\n"
                       f"• /help - Показать это сообщение помощи\\n\\n"
                       f"Есть вопросы? Пишите мне! 😊"
            },
            'en': {
                'help': f"ℹ️ **{bot_name} - Help**\\n\\n"
                       f"**How to use:**\\n"
                       f"• Send me a regular text message\\n"
                       f"• I will respond to you\\n"
                       f"• /start - Restart the bot\\n"
                       f"• /help - Show this help message\\n\\n"
                       f"Have questions? Write to me! 😊"
            }
        }
        
        return help_messages.get(language, help_messages['uz'])['help']
    
    def get_active_bots(self):
        """Get list of currently active bot IDs"""
        return list(self.active_bots.keys())
    
    def is_bot_active(self, bot_id):
        """Check if a bot is currently active"""
        return bot_id in self.active_bots
    
    def restart_all_bots(self):
        """Restart all active bots"""
        try:
            # Get all active bots from database
            active_bots = Bot.query.filter_by(status='ACTIVE').all()
            
            for bot in active_bots:
                if bot.telegram_token:
                    self.start_bot(bot)
                    
            logging.info(f"Auto-started {len(active_bots)} active bots")
            
        except Exception as e:
            logging.error(f"Bot restart error: {e}")