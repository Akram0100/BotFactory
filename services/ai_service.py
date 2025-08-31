import os
import logging
from google import genai
from google.genai import types
from models import KnowledgeBase

class AIService:
    """Service for AI-powered chatbot responses using Google Gemini"""
    
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
            self.model = "gemini-2.5-flash"
            self.api_available = True
        else:
            self.client = None
            self.model = "gemini-2.5-flash"
            self.api_available = False
            logging.warning("GEMINI_API_KEY not found. AI responses will be disabled.")
    
    async def get_response(self, bot, user_message, user_language='auto'):
        """Generate AI response for user message"""
        if not self.api_available or not self.client:
            return "AI service is currently unavailable. Please configure your GEMINI_API_KEY to enable AI responses."
        
        try:
            # Ensure we have Flask app context
            from app import app
            with app.app_context():
                # Get bot's knowledge base
                knowledge_entries = KnowledgeBase.query.filter_by(bot_id=bot.id).all()
                knowledge_context = ""
                
                if knowledge_entries:
                    knowledge_context = "\n\nKnowledge Base:\n"
                    for entry in knowledge_entries:
                        knowledge_context += f"- {entry.title}: {entry.content}"
                        # Add image information if available
                        if entry.image_url:
                            knowledge_context += f"\n  📸 Product Image: {entry.image_url}"
                            if entry.image_caption:
                                knowledge_context += f"\n  📝 Image Caption: {entry.image_caption}"
                            knowledge_context += "\n  💡 Note: You can send this image to users when they ask about this topic"
                        knowledge_context += "\n\n"
                
                # Set language instructions based on user preference or detection
                if user_language != 'auto':
                    language_instruction = self._get_language_instruction(user_language)
                else:
                    language_instruction = self._detect_language_instruction(user_message)
                
                # Construct system prompt with language support
                system_instruction = f"""{bot.system_prompt}
                
You are a chatbot named "{bot.name}".
{f"Description: {bot.description}" if bot.description else ""}

IMPORTANT LANGUAGE RULE: {language_instruction}

IMPORTANT FORMATTING RULES:
- Use emojis to make your responses friendly and engaging 😊
- NEVER use markdown symbols like *, **, ___, or ~~~ in your responses
- Use emojis instead of formatting symbols to emphasize points
- Keep responses clean and readable without any markdown formatting
- Use line breaks and emojis for better visual presentation

Please respond helpfully and naturally to user messages.
If you have relevant information in your knowledge base, use it to provide accurate answers.
If you don't know something, be honest about it.

{knowledge_context}"""
                
                # Generate response using Gemini
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[
                        types.Content(role="user", parts=[types.Part(text=user_message)])
                    ],
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.7,
                        max_output_tokens=1000,
                    )
                )
                
                if response.text:
                    ai_response = response.text.strip()
                    
                    # Check if AI wants to send an image based on the knowledge base context
                    relevant_image = self._find_relevant_image(user_message, knowledge_entries, ai_response)
                    if relevant_image:
                        return {
                            'text': ai_response,
                            'image_url': relevant_image['url'],
                            'image_caption': relevant_image['caption']
                        }
                    else:
                        return ai_response
                else:
                    return "I apologize, but I couldn't generate a response. Please try again."
                
        except Exception as e:
            logging.error(f"AI Service error: {e}")
            import traceback
            logging.error(f"AI Service traceback: {traceback.format_exc()}")
            return "I'm experiencing technical difficulties. Please try again later."
    
    def _find_relevant_image(self, user_message, knowledge_entries, ai_response):
        """Find relevant image based on user message and AI response context"""
        try:
            # Keywords that might indicate user wants to see a product/image
            image_keywords = [
                'rasm', 'surat', 'rasmini', 'picture', 'image', 'photo', 'show me', 'ko\'rsat',
                'qanday ko\'rinadi', 'ko\'rsating', 'фото', 'картинка', 'покажи', 'как выглядит'
            ]
            
            user_msg_lower = user_message.lower()
            
            # Check if user is asking for images/photos
            wants_image = any(keyword in user_msg_lower for keyword in image_keywords)
            
            if wants_image:
                # Look for knowledge entries with images that might be relevant
                for entry in knowledge_entries:
                    if entry.image_url:
                        # Simple keyword matching to find relevant products
                        entry_keywords = entry.title.lower().split() + entry.content.lower().split()
                        if any(word in user_msg_lower for word in entry_keywords if len(word) > 3):
                            return {
                                'url': entry.image_url,
                                'caption': entry.image_caption or entry.title
                            }
            
            return None
        except Exception as e:
            logging.error(f"Error finding relevant image: {e}")
            return None
    
    def test_connection(self):
        """Test Gemini API connection"""
        if not self.api_available or not self.client:
            return False
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents="Hello, please respond with 'API connection successful!'"
            )
            return response.text is not None
        except Exception as e:
            logging.error(f"Gemini API test failed: {e}")
            return False
    
    def analyze_message_sentiment(self, message):
        """Analyze sentiment of user message (for analytics)"""
        if not self.api_available or not self.client:
            return 'neutral'
        
        try:
            prompt = f"""Analyze the sentiment of this message and respond with just one word: positive, negative, or neutral.

Message: {message}"""
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            
            if response.text:
                sentiment = response.text.strip().lower()
                if sentiment in ['positive', 'negative', 'neutral']:
                    return sentiment
            
            return 'neutral'  # Default fallback
            
        except Exception as e:
            logging.error(f"Sentiment analysis error: {e}")
            return 'neutral'
    
    def summarize_conversation(self, messages):
        """Summarize a conversation (for analytics)"""
        if not self.api_available or not self.client:
            return "AI summarization is currently unavailable."
        
        try:
            if not messages:
                return "No conversation to summarize."
            
            conversation_text = "\n".join([f"User: {msg.user_message}\nBot: {msg.bot_response}" for msg in messages[-10:]])  # Last 10 messages
            
            prompt = f"""Summarize this conversation in 2-3 sentences, focusing on the main topics discussed:

{conversation_text}"""
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=150,
                    temperature=0.3,
                )
            )
            
            return response.text.strip() if response.text else "Unable to summarize conversation."
            
        except Exception as e:
            logging.error(f"Conversation summarization error: {e}")
            return "Unable to summarize conversation."
    
    def _detect_language_instruction(self, user_message):
        """Detect the language of user message and return appropriate instruction"""
        # Simple language detection based on common words and characters
        uzbek_words = ['salom', 'assalomu', 'alaykum', 'rahmat', 'yaxshi', 'qanday', 'nima', 'kim', 'qachon', 'qayer', 'nega', 'qancha', 'bormi', 'yoq', 'ha', 'men', 'sen', 'biz', 'siz', 'ular', 'bu', 'shu', 'o\'sha', 'kimsiz', 'nimalar']
        russian_words = ['привет', 'здравствуй', 'спасибо', 'как', 'что', 'где', 'когда', 'почему', 'сколько', 'да', 'нет', 'я', 'ты', 'мы', 'вы', 'они', 'это']
        
        message_lower = user_message.lower()
        
        # Check for Uzbek
        uzbek_count = sum(1 for word in uzbek_words if word in message_lower)
        russian_count = sum(1 for word in russian_words if word in message_lower)
        
        # Check for Cyrillic characters (Russian/Uzbek cyrillic)
        cyrillic_count = sum(1 for char in user_message if '\u0400' <= char <= '\u04FF')
        
        if uzbek_count > 0 or cyrillic_count > 0:
            if uzbek_count > russian_count:
                return "Always respond in UZBEK language (o'zbek tilida javob bering). Use Latin script for Uzbek."
            else:
                return "Always respond in RUSSIAN language (отвечайте на русском языке)."
        elif russian_count > 0:
            return "Always respond in RUSSIAN language (отвечайте на русском языке)."
        else:
            return "Respond in the same language as the user's message. If the message is in Uzbek, respond in Uzbek. If in Russian, respond in Russian. If in English, respond in English."
    
    def _get_language_instruction(self, language):
        """Get language instruction based on user's selected language"""
        if language == 'uz':
            return """MAJBURIY QOIDA - ENG MUHIM: 
- Barcha javoblaringizni FAQAT O'ZBEK TILIDA yozing
- Hech qanday ingliz, rus yoki boshqa tilda so'z ishlatmang
- Lotin yozuvidan foydalaning
- Agar tushunmasangiz ham, o'zbek tilida javob bering
- Bu eng muhim qoida - hech qachon buzilmasligi kerak"""
        elif language == 'ru':
            return """ОБЯЗАТЕЛЬНОЕ ПРАВИЛО - САМОЕ ВАЖНОЕ:
- Отвечайте ТОЛЬКО НА РУССКОМ ЯЗЫКЕ
- Не используйте английские, узбекские или другие слова
- Даже если не понимаете, отвечайте на русском
- Это самое важное правило - никогда не нарушайте его"""
        elif language == 'en':
            return """MANDATORY RULE - MOST IMPORTANT:
- Respond ONLY in ENGLISH language
- Do not use Russian, Uzbek or other language words
- Even if you don't understand, respond in English
- This is the most important rule - never break it"""
        else:
            return "Respond in the same language as the user's message."
