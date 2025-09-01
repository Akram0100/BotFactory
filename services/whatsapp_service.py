import os
import logging
import requests
from typing import Optional, Dict, Any
import json

class WhatsAppService:
    """Service for WhatsApp Business API integration"""
    
    def __init__(self):
        self.access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
        self.phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
        self.app_secret = os.environ.get("WHATSAPP_APP_SECRET")
        self.api_version = "v18.0"
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
        self.api_available = bool(self.access_token and self.phone_number_id)
        
        if not self.api_available:
            logging.warning("WhatsApp API credentials not found. WhatsApp integration will be disabled.")
    
    def validate_credentials(self, access_token: str, phone_number_id: str) -> Optional[Dict[str, Any]]:
        """Validate WhatsApp Business credentials"""
        if not access_token or not phone_number_id:
            return None
            
        try:
            url = f"{self.base_url}/{phone_number_id}"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {"fields": "id,display_phone_number,verified_name"}
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            return {
                "id": data.get("id"),
                "phone_number": data.get("display_phone_number"),
                "verified_name": data.get("verified_name"),
                "is_valid": True
            }
            
        except requests.exceptions.RequestException as e:
            logging.error(f"WhatsApp credentials validation error: {e}")
            return None
    
    def send_message(self, recipient_phone: str, message: str, access_token: str, phone_number_id: str) -> bool:
        """Send WhatsApp message"""
        if not access_token or not phone_number_id:
            return False
            
        try:
            url = f"{self.base_url}/{phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient_phone,
                "type": "text",
                "text": {"body": message}
            }
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            return True
            
        except requests.exceptions.RequestException as e:
            logging.error(f"WhatsApp message send error: {e}")
            return False
    
    def get_webhook_verification(self, verify_token: str, challenge: str, mode: str) -> Optional[str]:
        """Handle WhatsApp webhook verification"""
        if mode == "subscribe" and verify_token == os.environ.get("WHATSAPP_VERIFY_TOKEN"):
            return challenge
        return None
    
    def process_webhook_data(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process incoming WhatsApp webhook data"""
        try:
            entry = webhook_data.get("entry", [])
            if not entry:
                return None
                
            changes = entry[0].get("changes", [])
            if not changes:
                return None
                
            change = changes[0]
            if change.get("field") != "messages":
                return None
                
            value = change.get("value", {})
            messages = value.get("messages", [])
            
            if not messages:
                return None
                
            message = messages[0]
            sender_phone = message.get("from")
            message_text = message.get("text", {}).get("body")
            
            if sender_phone and message_text:
                # Get contact info if available
                contacts = value.get("contacts", [])
                contact_name = ""
                if contacts:
                    contact_name = contacts[0].get("profile", {}).get("name", "")
                
                return {
                    "sender_id": sender_phone,
                    "sender_name": contact_name,
                    "message": message_text,
                    "platform": "whatsapp",
                    "timestamp": message.get("timestamp")
                }
                
        except Exception as e:
            logging.error(f"WhatsApp webhook processing error: {e}")
            
        return None
    
    def start_bot(self, bot):
        """Start WhatsApp bot (setup webhook)"""
        if not self.api_available or not bot.whatsapp_access_token:
            logging.warning(f"Cannot start WhatsApp bot {bot.name}: Missing credentials")
            return False
            
        try:
            # WhatsApp bots work via webhooks, not polling
            # Webhook setup is handled during bot configuration
            logging.info(f"WhatsApp bot {bot.name} is ready for webhook messages")
            return True
            
        except Exception as e:
            logging.error(f"Failed to start WhatsApp bot {bot.name}: {e}")
            return False
    
    def stop_bot(self, bot):
        """Stop WhatsApp bot"""
        try:
            # For WhatsApp, this would typically involve webhook cleanup
            logging.info(f"WhatsApp bot {bot.name} stopped")
            return True
            
        except Exception as e:
            logging.error(f"Failed to stop WhatsApp bot {bot.name}: {e}")
            return False
    
    def send_template_message(self, recipient_phone: str, template_name: str, 
                            language_code: str = "en_US", components: Optional[list] = None) -> bool:
        """Send WhatsApp template message"""
        if not self.api_available:
            return False
            
        try:
            url = f"{self.base_url}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code}
                }
            }
            
            if components:
                payload["template"]["components"] = components
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            return True
            
        except requests.exceptions.RequestException as e:
            logging.error(f"WhatsApp template message send error: {e}")
            return False