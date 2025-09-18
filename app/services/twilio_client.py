"""
Twilio client for SMS/WhatsApp messaging as an alternative to WhatsApp Cloud API.
This provides a fallback communication channel and can be used for testing.
"""
import os
from typing import Dict, Any, Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioException
from app.config.settings import settings

class TwilioClient:
    def __init__(self):
        self.client = None
        self.from_number = settings.twilio_phone_number
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Twilio client."""
        try:
            if not settings.twilio_account_sid or not settings.twilio_auth_token:
                print("⚠️ Twilio credentials not available")
                return
            
            self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            print("✅ Twilio client initialized")
            
        except Exception as e:
            print(f"❌ Failed to initialize Twilio client: {e}")
            self.client = None
    
    async def send_sms(self, to_phone: str, message: str) -> bool:
        """Send SMS message via Twilio."""
        if not self.client or not self.from_number:
            print("❌ Twilio client or phone number not available")
            return False
        
        try:
            message = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_phone
            )
            print(f"✅ SMS sent successfully. SID: {message.sid}")
            return True
            
        except TwilioException as e:
            print(f"❌ Twilio error: {e}")
            return False
        except Exception as e:
            print(f"❌ Error sending SMS: {e}")
            return False
    
    async def send_whatsapp_message(self, to_phone: str, message: str) -> bool:
        """Send WhatsApp message via Twilio (requires WhatsApp Business API setup)."""
        if not self.client or not self.from_number:
            print("❌ Twilio client or phone number not available")
            return False
        
        try:
            # Format phone numbers for WhatsApp
            whatsapp_from = f"whatsapp:{self.from_number}"
            whatsapp_to = f"whatsapp:{to_phone}"
            
            message = self.client.messages.create(
                body=message,
                from_=whatsapp_from,
                to=whatsapp_to
            )
            print(f"✅ WhatsApp message sent successfully. SID: {message.sid}")
            return True
            
        except TwilioException as e:
            print(f"❌ Twilio WhatsApp error: {e}")
            return False
        except Exception as e:
            print(f"❌ Error sending WhatsApp message: {e}")
            return False
    
    async def send_meal_recommendations_sms(self, to_phone: str, recommendations: list) -> bool:
        """Send meal recommendations via SMS with proper formatting."""
        if not recommendations:
            message = "Mambo 🤔: I'm still learning about your taste! Could you try asking for something specific?"
            return await self.send_sms(to_phone, message)
        
        # Format recommendations for SMS
        context = recommendations[0].get('context', 'Here are some meal suggestions')
        message = f"Mambo 🍽️: {context}:\n\n"
        
        for i, meal in enumerate(recommendations[:3], 1):  # Limit to 3 for SMS
            name = meal.get('name', 'Unknown Dish')
            cuisine = meal.get('cuisine', '').replace('_', ' ').title()
            time_min = meal.get('estimated_time_min', 0)
            diet = meal.get('diet_type', '')
            
            # Format time
            time_text = f" ({time_min} min)" if time_min else ""
            
            # Format diet indicator
            diet_emoji = "🌱" if diet == "veg" else "🍗" if diet == "non-veg" else ""
            
            message += f"{i}. {name} {diet_emoji}\n"
            message += f"   {cuisine} cuisine{time_text}\n\n"
        
        # Add follow-up suggestion
        message += "Reply 'recipe [dish name]' for full recipe! 👨‍🍳"
        
        return await self.send_sms(to_phone, message)
    
    async def send_onboarding_question_sms(self, to_phone: str, question_type: str, user_name: str = None) -> bool:
        """Send onboarding questions via SMS."""
        messages = {
            "name": "Mambo 🥘: Hey! I'm Mambo — your kitchen sidekick. What should I call you? (Just reply with your name or 'skip')",
            "diet": f"Mambo 🌿🍗: Hi {user_name or 'there'}! What's your food base? Reply:\n1 - Veg 🌱\n2 - Non-Veg 🍗\n3 - Both 🍴",
            "cuisine": "Mambo 🍽️: Pick your kitchen vibe! Reply with number:\n1-North Indian 2-South Indian 3-Chinese 4-Italian 5-Punjabi 6-Gujarati 7-Bengali 8-International 9-Surprise me",
            "allergies": "Mambo 🩺: Any allergies I should avoid? Reply with number(s):\n1-None 2-Dairy 3-Eggs 4-Peanut 5-Tree nuts 6-Wheat/Gluten 7-Soy 8-Fish 9-Shellfish 10-Other",
            "household": "Mambo 🏡: Who are you cooking for? Reply:\n1-Just me 2-Couple 3-Small family(3-4) 4-Big family(5+) 5-Shared/Varies"
        }
        
        message = messages.get(question_type, "Mambo: Please provide your preference.")
        return await self.send_sms(to_phone, message)
    
    def format_phone_number(self, phone: str) -> str:
        """Format phone number for Twilio (ensure E.164 format)."""
        # Remove any non-digit characters except +
        cleaned = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        # Add + if not present
        if not cleaned.startswith('+'):
            # Assume US number if no country code
            if len(cleaned) == 10:
                cleaned = '+1' + cleaned
            else:
                cleaned = '+' + cleaned
        
        return cleaned
    
    async def test_connection(self) -> bool:
        """Test Twilio connection."""
        if not self.client:
            return False
        
        try:
            # Try to fetch account info
            account = self.client.api.accounts(settings.twilio_account_sid).fetch()
            print(f"✅ Twilio connection test successful. Account: {account.friendly_name}")
            return True
        except Exception as e:
            print(f"❌ Twilio connection test failed: {e}")
            return False