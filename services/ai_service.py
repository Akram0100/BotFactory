import os
import logging
from google import genai
from google.genai import types
from models import KnowledgeBase

class AIService:
    """Service for AI-powered chatbot responses using Google Gemini"""
    
    def __init__(self):
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.model = "gemini-2.5-flash"
    
    def get_response(self, bot, user_message):
        """Generate AI response for user message"""
        try:
            # Get bot's knowledge base
            knowledge_entries = KnowledgeBase.query.filter_by(bot_id=bot.id).all()
            knowledge_context = ""
            
            if knowledge_entries:
                knowledge_context = "\n\nKnowledge Base:\n"
                for entry in knowledge_entries:
                    knowledge_context += f"- {entry.title}: {entry.content[:500]}...\n"
            
            # Detect language and set appropriate instructions
            language_instruction = self._detect_language_instruction(user_message)
            
            # Construct system prompt with language support
            system_instruction = f"""{bot.system_prompt}
            
You are a chatbot named "{bot.name}".
{f"Description: {bot.description}" if bot.description else ""}

IMPORTANT LANGUAGE RULE: {language_instruction}

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
                return response.text.strip()
            else:
                return "I apologize, but I couldn't generate a response. Please try again."
                
        except Exception as e:
            logging.error(f"AI Service error: {e}")
            return "I'm experiencing technical difficulties. Please try again later."
    
    def test_connection(self):
        """Test Gemini API connection"""
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
