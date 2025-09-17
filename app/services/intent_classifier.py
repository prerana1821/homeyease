"""
Intent classification service using keyword rules and OpenAI fallback.
"""
import re
from typing import List
from openai import OpenAI
from app.config.settings import settings

# the newest OpenAI model is "gpt-5" which was released August 7, 2025.
# do not change this unless explicitly requested by the user

class IntentClassifier:
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        
        # Keyword rules for intent classification
        self.intent_keywords = {
            "WHATSDINNER": [
                "what's for dinner", "whats for dinner", "what should I eat", 
                "meal suggestion", "suggest meal", "dinner ideas", "food suggestions",
                "what to cook", "cooking ideas", "meal ideas"
            ],
            "PLANWEEK": [
                "plan my week", "weekly plan", "meal plan", "weekly meal plan",
                "plan meals", "week plan", "7 day plan", "weekly menu"
            ],
            "UPLOAD_IMAGE": [
                "image", "photo", "picture", "ingredient", "ingredients",
                "what can I make", "recognize food"
            ],
            "MOOD": [
                "feeling", "mood", "craving", "want something", "in the mood for"
            ],
            "ONBOARDING": [
                "start", "begin", "setup", "preferences", "profile", "help"
            ]
        }
    
    async def classify_intent(self, text: str) -> str:
        """Classify user intent using keyword rules with OpenAI fallback."""
        text_lower = text.lower().strip()
        
        # First try keyword-based classification
        for intent, keywords in self.intent_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return intent
        
        # If no keyword match and OpenAI is available, use LLM fallback
        if self.openai_client:
            return await self._classify_with_openai(text)
        
        # Default to OTHER if no match and no OpenAI
        return "OTHER"
    
    async def _classify_with_openai(self, text: str) -> str:
        """Use OpenAI for intent classification fallback."""
        if not self.openai_client:
            return "OTHER"
            
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an intent classifier for a meal planning WhatsApp bot. "
                        "Classify the user's message into one of these intents: "
                        "WHATSDINNER, PLANWEEK, UPLOAD_IMAGE, MOOD, ONBOARDING, OTHER. "
                        "Return only the intent name."
                    },
                    {"role": "user", "content": text}
                ]
            )
            
            intent = response.choices[0].message.content.strip().upper() if response.choices[0].message.content else "OTHER"
            valid_intents = ["WHATSDINNER", "PLANWEEK", "UPLOAD_IMAGE", "MOOD", "ONBOARDING", "OTHER"]
            
            return intent if intent in valid_intents else "OTHER"
            
        except Exception as e:
            print(f"Error classifying intent with OpenAI: {e}")
            return "OTHER"