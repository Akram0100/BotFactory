#!/usr/bin/env python3
"""
Bot Monitor - Keeps Telegram bots running
"""
import threading
import time
import logging
from app import app, db
from models import Bot, BotStatus
from services.telegram_service import TelegramService

def monitor_bots():
    """Monitor and restart dead bots"""
    with app.app_context():
        try:
            telegram_service = TelegramService()
            
            # Get active bots from database
            active_bots = Bot.query.filter_by(status=BotStatus.ACTIVE).all()
            
            for bot in active_bots:
                # Check if bot is actually running
                if bot.id not in telegram_service.active_bots:
                    logging.warning(f"Bot {bot.name} is not running, restarting...")
                    try:
                        telegram_service.start_bot(bot)
                        logging.info(f"Restarted bot: {bot.name}")
                    except Exception as e:
                        logging.error(f"Failed to restart bot {bot.name}: {e}")
                else:
                    # Check if bot application is still running
                    app_instance = telegram_service.active_bots[bot.id]
                    if not app_instance.running or not app_instance.updater.running:
                        logging.warning(f"Bot {bot.name} application stopped, restarting...")
                        try:
                            telegram_service.stop_bot(bot)
                            telegram_service.start_bot(bot)
                            logging.info(f"Restarted bot application: {bot.name}")
                        except Exception as e:
                            logging.error(f"Failed to restart bot application {bot.name}: {e}")
                            
        except Exception as e:
            logging.error(f"Bot monitor error: {e}")

def start_monitor():
    """Start bot monitoring in background"""
    def monitor_loop():
        while True:
            try:
                monitor_bots()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logging.error(f"Monitor loop error: {e}")
                time.sleep(10)  # Wait before retrying
    
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True, name="BotMonitor")
    monitor_thread.start()
    logging.info("Bot monitor started")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    start_monitor()
    
    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Bot monitor stopped")