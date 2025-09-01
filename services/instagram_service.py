import os
import logging
import requests
from typing import Optional, Dict, Any

class InstagramService:
    """Service for Instagram Business API integration"""
    
    def __init__(self):
        self.access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
        self.app_secret = os.environ.get("INSTAGRAM_APP_SECRET")
        self.api_version = "v18.0"
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
        self.api_available = bool(self.access_token and self.app_secret)
        
        if not self.api_available:
            logging.warning("Instagram API credentials not found. Instagram integration will be disabled.")
    
    def validate_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Validate Instagram access token and get account info"""
        if not access_token:
            return None
            
        try:
            url = f"{self.base_url}/me"
            params = {
                "fields": "id,username,account_type",
                "access_token": access_token
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Check if it's a business account
            if data.get("account_type") not in ["BUSINESS", "CREATOR"]:
                logging.warning(f"Instagram account {data.get('username')} is not a business/creator account")
                return None
            
            return {
                "id": data.get("id"),
                "username": data.get("username"),
                "account_type": data.get("account_type"),
                "is_valid": True
            }
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Instagram token validation error: {e}")
            return None
    
    def send_message(self, recipient_id: str, message: str, access_token: str) -> bool:
        """Send message via Instagram Direct"""
        if not self.api_available:
            return False
            
        try:
            url = f"{self.base_url}/me/messages"
            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": message},
                "access_token": access_token
            }
            
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            return True
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Instagram message send error: {e}")
            return False
    
    def get_webhook_verification(self, verify_token: str, challenge: str, mode: str) -> Optional[str]:
        """Handle Instagram webhook verification"""
        if mode == "subscribe" and verify_token == os.environ.get("INSTAGRAM_VERIFY_TOKEN"):
            return challenge
        return None
    
    def process_webhook_data(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process incoming Instagram webhook data"""
        try:
            entry = webhook_data.get("entry", [])
            if not entry:
                return None
                
            messaging = entry[0].get("messaging", [])
            if not messaging:
                return None
                
            message_data = messaging[0]
            sender_id = message_data.get("sender", {}).get("id")
            message_text = message_data.get("message", {}).get("text")
            
            if sender_id and message_text:
                return {
                    "sender_id": sender_id,
                    "message": message_text,
                    "platform": "instagram",
                    "timestamp": message_data.get("timestamp")
                }
                
        except Exception as e:
            logging.error(f"Instagram webhook processing error: {e}")
            
        return None
    
    def start_bot(self, bot):
        """Start Instagram bot (setup webhook)"""
        if not self.api_available or not bot.instagram_access_token:
            logging.warning(f"Cannot start Instagram bot {bot.name}: Missing credentials")
            return False
            
        try:
            # Instagram bots work via webhooks, not polling
            # Webhook setup is handled during bot configuration
            logging.info(f"Instagram bot {bot.name} is ready for webhook messages")
            return True
            
        except Exception as e:
            logging.error(f"Failed to start Instagram bot {bot.name}: {e}")
            return False
    
    def stop_bot(self, bot):
        """Stop Instagram bot"""
        try:
            # For Instagram, this would typically involve webhook cleanup
            logging.info(f"Instagram bot {bot.name} stopped")
            return True
            
        except Exception as e:
            logging.error(f"Failed to stop Instagram bot {bot.name}: {e}")
            return False