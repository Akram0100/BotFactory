import os
import logging
import threading
import time
from datetime import datetime
from telegram import Update, Bot as TelegramBot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from models import Bot, TelegramUser, Conversation
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
                logging.info(f"🔔 CALLBACK WRAPPER called for bot {bot.id}")
                try:
                    result = await self._handle_callback(update, context, bot)
                    logging.info(f"✅ Callback wrapper completed successfully")
                    return result
                except Exception as e:
                    logging.error(f"❌ Callback wrapper error: {e}")
                    import traceback
                    logging.error(f"Full traceback: {traceback.format_exc()}")
                    raise
            
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
            
            # Check if this is a new user (not in database)
            from app import app
            is_new_user = False
            try:
                with app.app_context():
                    telegram_user = TelegramUser.query.filter_by(telegram_user_id=user_id).first()
                    is_new_user = (telegram_user is None)
            except Exception as e:
                logging.error(f"Error checking user existence: {e}")
                is_new_user = True
            
            # Always show language selection for new users, or if no language preference
            if is_new_user:
                # Show language selection for new users
                await self._show_language_selection(update, bot)
            else:
                # Existing user - show current language and option to change
                user_lang = self._get_user_language(user_id)
                await self._show_welcome_with_language_option(update, bot, user_lang)
            
            # Send notification to admin about new user (only for truly new users)
            if is_new_user:
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
            user_lang = self._get_user_language(user_id)
            
            help_message = self._get_localized_help_message(bot.name, user_lang)
            
            await update.message.reply_text(help_message, parse_mode='Markdown')
            
        except Exception as e:
            logging.error(f"Help command error: {e}")
            try:
                if update and update.effective_user and update.message:
                    user_id = update.effective_user.id
                    user_lang = self._get_user_language(user_id)
                    error_msg = self._get_localized_text('error', user_lang)
                    await update.message.reply_text(error_msg)
            except:
                pass
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle regular text messages"""
        try:
            user = update.effective_user
            if not user or not update.message or not update.message.text:
                return
                
            user_message = update.message.text
            user_id = user.id
            chat_id = update.message.chat_id
            user_lang = self._get_user_language(user_id)
            
            # Track conversation for broadcast purposes
            self._track_conversation(bot.id, user_id, chat_id)
            
            # Send notification to admin about user message
            notification_text = f"💬 **Yangi xabar**\n"
            notification_text += f"👤 Foydalanuvchi: {user.first_name} (@{user.username or 'username yoq'})\n"
            notification_text += f"🆔 ID: {user.id}\n"
            notification_text += f"🌐 Til: {user_lang}\n"
            notification_text += f"📝 Xabar: {user_message}"
            
            await self._send_notification(bot, notification_text)
            
            # Get AI response with user's language preference
            logging.info(f"Requesting AI response for user {user_id} in language {user_lang}")
            ai_response = await self.ai_service.get_response(bot, user_message, user_language=user_lang)
            logging.info(f"AI response received: {ai_response[:100] if isinstance(ai_response, str) else str(ai_response)[:100]}..." if ai_response else "No AI response")
            
            # Send response to user
            if ai_response:
                # Ensure ai_response is a string
                if isinstance(ai_response, dict):
                    ai_response = str(ai_response)
                await update.message.reply_text(str(ai_response))
                
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
                user_lang = self._get_user_language(user_id) if user_id else 'uz'
                error_msg = self._get_localized_text('error', user_lang)
                await update.message.reply_text(error_msg)
    
    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
        """Handle callback queries from inline keyboards"""
        try:
            logging.info(f"=== CALLBACK HANDLER START ===")
            logging.info(f"Update type: {type(update)}")
            logging.info(f"Update data: {update}")
            
            query = update.callback_query
            if not query:
                logging.error("❌ No callback query in update")
                return
                
            logging.info(f"✅ Callback query found: {query}")
            logging.info(f"Query data: {query.data}")
            logging.info(f"Query from user: {query.from_user.id if query.from_user else 'Unknown'}")
            
            await query.answer()
            logging.info(f"✅ Callback query answered successfully")
            
            user = query.from_user
            if not user or not query.data:
                logging.error(f"Missing user or query.data: user={user}, data={query.data if query else None}")
                return
                
            callback_data = query.data
            user_id = user.id
            logging.info(f"Processing callback: {callback_data} from user {user_id}")
            
            # Send notification about callback
            notification_text = f"🔘 **Callback query**\n"
            notification_text += f"👤 Foydalanuvchi: {user.first_name} (@{user.username or 'username yoq'})\n"
            notification_text += f"🆔 ID: {user.id}\n"
            notification_text += f"🔗 Data: {callback_data}"
            
            await self._send_notification(bot, notification_text)
            
            # Handle language change request
            if callback_data == "change_language":
                logging.info(f"User {user_id} requested language change")
                # Show language selection menu by editing current message
                try:
                    # Create multilingual language selection message
                    welcome_text = "🌐 *Tilni tanlang / Выберите язык / Choose Language*\n\n"
                    welcome_text += f"🇺🇿 Salom {user.first_name}! Tilni tanlang.\n"
                    welcome_text += f"🇷🇺 Привет {user.first_name}! Выберите язык.\n" 
                    welcome_text += f"🇬🇧 Hello {user.first_name}! Choose your language.\n\n"
                    welcome_text += "👇 Muloqot uchun tilni tanlang:"
                    
                    # Create inline keyboard with language options
                    keyboard = [
                        [InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz")],
                        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
                        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
                    
                except Exception as e:
                    logging.error(f"Error showing language selection: {e}")

            # Handle language selection
            elif callback_data.startswith("lang_"):
                language = callback_data.split("_")[1]  # Extract language code
                logging.info(f"User {user_id} selected language: {language}")
                
                # Save language preference to database
                try:
                    logging.info(f"Attempting to save language {language} for user {user_id}")
                    self._set_user_language(user_id, language, user)
                    self.user_languages[user_id] = language
                    logging.info(f"Successfully saved language {language} for user {user_id}")
                except Exception as e:
                    logging.error(f"Error saving language preference: {e}")
                
                # Show welcome message in selected language
                try:
                    logging.info(f"Showing success message in language: {language}")
                    # Simple success message instead of complex welcome
                    success_messages = {
                        'uz': f"✅ Til tanlandi: O'zbek\n\n🎉 Salom! Menga savolingizni yuboring.",
                        'ru': f"✅ Язык выбран: Русский\n\n🎉 Привет! Отправьте мне ваш вопрос.",
                        'en': f"✅ Language selected: English\n\n🎉 Hello! Send me your question."
                    }
                    message = success_messages.get(language, success_messages['uz'])
                    await query.edit_message_text(message)
                    logging.info(f"Language {language} confirmed for user {user_id} - message sent")
                except Exception as e:
                    logging.error(f"Error showing welcome message: {e}")
                    # Fallback: send simple text
                    try:
                        await query.edit_message_text(f"Til tanlandi: {language} ✅")
                        logging.info(f"Sent fallback message for language {language}")
                    except Exception as e2:
                        logging.error(f"Error sending fallback message: {e2}")
                
            # Handle different callback actions
            elif callback_data == "help":
                await self._handle_help_command(update, context, bot)
            else:
                logging.info(f"Unhandled callback_data: {callback_data}")
                # Get user's language for response
                user_lang = self._get_user_language(user_id)
                response_msg = self._get_localized_text("selection_completed", user_lang)
                await query.edit_message_text(response_msg)
            
        except Exception as e:
            logging.error(f"Callback handling error: {e}")
            import traceback
            logging.error(f"Callback error traceback: {traceback.format_exc()}")
            try:
                if 'query' in locals() and query:
                    await query.answer("Xatolik yuz berdi / Ошибка / Error")
                    logging.error(f"Sent error response to callback query")
            except Exception as e2:
                logging.error(f"Error sending callback error response: {e2}")
    
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
            welcome_text = "🌐 *Tilni tanlang / Выберите язык / Choose Language*\n\n"
            welcome_text += f"🇺🇿 Salom {user.first_name}! Men {bot.name} botiman.\n"
            welcome_text += f"🇷🇺 Привет {user.first_name}! Я бот {bot.name}.\n" 
            welcome_text += f"🇬🇧 Hello {user.first_name}! I'm {bot.name} bot.\n\n"
            welcome_text += "👇 Muloqot uchun tilni tanlang:"
            
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
    
    async def _show_welcome_with_language_option(self, update, bot, language):
        """Show welcome message with language change option"""
        try:
            user = update.effective_user
            if not user:
                return
            
            # Get welcome message in current language
            welcome_msg = self._get_localized_welcome_message(user.first_name, bot.name, language)
            
            # Add language change option
            language_names = {
                'uz': "O'zbek",
                'ru': "Русский", 
                'en': "English"
            }
            
            current_lang_name = language_names.get(language, "O'zbek")
            
            if language == 'uz':
                welcome_msg += f"\n\n🔄 Hozirgi til: {current_lang_name}\nTilni o'zgartirish uchun quyidagi tugmani bosing:"
            elif language == 'ru':
                welcome_msg += f"\n\n🔄 Текущий язык: {current_lang_name}\nДля смены языка нажмите кнопку ниже:"
            else:  # English
                welcome_msg += f"\n\n🔄 Current language: {current_lang_name}\nTo change language, press the button below:"
            
            # Create inline keyboard with language change button
            keyboard = [[
                InlineKeyboardButton("🌐 Tilni o'zgartirish / Сменить язык / Change Language", 
                                   callback_data="change_language")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logging.error(f"Welcome with language option error: {e}")
    
    def _get_localized_welcome_message(self, user_name, bot_name, language):
        """Get welcome message in specified language"""
        messages = {
            'uz': {
                'welcome': f"🎉 *Salom {user_name}!* 👋\n\n"
                          f"✨ Men *{bot_name}* botiman. Sizga qanday yordam bera olaman?\n\n"
                          f"💬 Menga savolingizni yuboring va men sizga javob beraman!\n\n"
                          f"🔄 Tilni o'zgartirish uchun /start buyrug'ini qayta yuboring."
            },
            'ru': {
                'welcome': f"🎉 *Привет {user_name}!* 👋\n\n"
                          f"✨ Я бот *{bot_name}*. Как я могу вам помочь?\n\n"
                          f"💬 Отправьте мне ваш вопрос, и я отвечу!\n\n"
                          f"🔄 Чтобы изменить язык, отправьте команду /start снова."
            },
            'en': {
                'welcome': f"🎉 *Hello {user_name}!* 👋\n\n"
                          f"✨ I'm *{bot_name}* bot. How can I help you?\n\n"
                          f"💬 Send me your question and I'll respond!\n\n"
                          f"🔄 To change language, send /start command again."
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
                'help': f"ℹ️ *{bot_name} - Yordam*\n\n"
                       f"📋 *Qanday foydalanish:*\n"
                       f"💬 Menga oddiy matn yuboring\n"
                       f"🤖 Men sizga javob beraman\n"
                       f"🔄 /start - Botni qayta ishga tushirish\n"
                       f"❓ /help - Bu yordam habarini ko'rish\n\n"
                       f"🙋‍♂️ Savollar bormi? Menga yozing! 😊"
            },
            'ru': {
                'help': f"ℹ️ *{bot_name} - Помощь*\n\n"
                       f"📋 *Как использовать:*\n"
                       f"💬 Отправьте мне обычное сообщение\n"
                       f"🤖 Я отвечу вам\n"
                       f"🔄 /start - Перезапустить бота\n"
                       f"❓ /help - Показать это сообщение помощи\n\n"
                       f"🙋‍♂️ Есть вопросы? Пишите мне! 😊"
            },
            'en': {
                'help': f"ℹ️ *{bot_name} - Help*\n\n"
                       f"📋 *How to use:*\n"
                       f"💬 Send me a regular text message\n"
                       f"🤖 I will respond to you\n"
                       f"🔄 /start - Restart the bot\n"
                       f"❓ /help - Show this help message\n\n"
                       f"🙋‍♂️ Have questions? Write to me! 😊"
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
    
    def _get_user_language(self, telegram_user_id):
        """Get user's language preference from database or cache"""
        # Check cache first
        if telegram_user_id in self.user_languages:
            return self.user_languages[telegram_user_id]
        
        # Get from database
        try:
            from app import app
            with app.app_context():
                telegram_user = TelegramUser.query.filter_by(telegram_user_id=telegram_user_id).first()
                if telegram_user:
                    language = telegram_user.language
                    self.user_languages[telegram_user_id] = language  # Cache it
                    return language
                else:
                    # Default to Uzbek if no preference found
                    return 'uz'
        except Exception as e:
            logging.error(f"Error getting user language: {e}")
            return 'uz'
    
    def _set_user_language(self, telegram_user_id, language, user_data=None):
        """Set user's language preference in database"""
        try:
            from app import app
            with app.app_context():
                telegram_user = TelegramUser.query.filter_by(telegram_user_id=telegram_user_id).first()
                
                if telegram_user:
                    # Update existing user
                    telegram_user.language = language
                    if user_data:
                        telegram_user.username = user_data.username
                        telegram_user.first_name = user_data.first_name
                        telegram_user.last_name = user_data.last_name
                    logging.info(f"Updated existing user {telegram_user_id} language to {language}")
                else:
                    # Create new user
                    telegram_user = TelegramUser()
                    telegram_user.telegram_user_id = telegram_user_id
                    telegram_user.username = user_data.username if user_data else None
                    telegram_user.first_name = user_data.first_name if user_data else None
                    telegram_user.last_name = user_data.last_name if user_data else None
                    telegram_user.language = language
                    db.session.add(telegram_user)
                    logging.info(f"Created new user {telegram_user_id} with language {language}")
                
                db.session.commit()
                
                # Update cache
                self.user_languages[telegram_user_id] = language
                logging.info(f"Language {language} saved for user {telegram_user_id}")
            
        except Exception as e:
            logging.error(f"Error setting user language: {e}")
            try:
                db.session.rollback()
            except:
                pass
    
    def send_broadcast_message(self, token, chat_id, message, parse_mode=None):
        """Send broadcast message to a specific chat"""
        import asyncio
        import requests
        import json
        
        async def _send_message():
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                
                data = {
                    'chat_id': chat_id,
                    'text': message
                }
                
                if parse_mode:
                    data['parse_mode'] = parse_mode
                
                response = requests.post(url, data=data, timeout=10)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        logging.info(f"Broadcast message sent to {chat_id}")
                        return True
                    else:
                        logging.error(f"Telegram API error: {result.get('description', 'Unknown error')}")
                        return False
                else:
                    logging.error(f"HTTP error {response.status_code} sending to {chat_id}")
                    return False
                    
            except Exception as e:
                logging.error(f"Error sending broadcast message to {chat_id}: {e}")
                return False
        
        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, we need to use run_in_executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _send_message())
                    return future.result()
            else:
                return loop.run_until_complete(_send_message())
        except RuntimeError:
            # No event loop exists, create one
            return asyncio.run(_send_message())
    
    def _track_conversation(self, bot_id, telegram_user_id, chat_id):
        """Track user-bot conversation for broadcast purposes"""
        try:
            from app import app
            from models import Conversation
            with app.app_context():
                # Check if conversation already exists
                conversation = Conversation.query.filter_by(
                    bot_id=bot_id,
                    telegram_user_id=telegram_user_id
                ).first()
                
                if conversation:
                    # Update last message time
                    conversation.last_message_at = datetime.utcnow()
                    logging.info(f"Updated conversation for bot {bot_id} user {telegram_user_id}")
                else:
                    # Create new conversation record
                    conversation = Conversation()
                    conversation.bot_id = bot_id
                    conversation.telegram_user_id = telegram_user_id
                    conversation.chat_id = str(chat_id)
                    db.session.add(conversation)
                    logging.info(f"Created new conversation for bot {bot_id} user {telegram_user_id}")
                
                db.session.commit()
                
        except Exception as e:
            logging.error(f"Error tracking conversation: {e}")
            try:
                db.session.rollback()
            except:
                pass