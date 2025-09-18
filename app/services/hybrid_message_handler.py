"""
Hybrid message handler that can work with both WhatsApp Cloud API and Twilio.
This allows seamless switching between communication channels.
"""
from typing import Dict, Any, List, Optional
from app.services.message_handler import MessageHandler
from app.services.whatsapp_client import WhatsAppClient
from app.services.twilio_client import TwilioClient
from app.config.settings import settings

class HybridMessageHandler(MessageHandler):
    def __init__(self):
        super().__init__()
        self.whatsapp_client = WhatsAppClient()
        self.twilio_client = TwilioClient()
        
        # Determine which client to use based on available credentials
        self.use_whatsapp = bool(settings.whatsapp_token and settings.whatsapp_phone_number_id)
        self.use_twilio = bool(settings.twilio_account_sid and settings.twilio_auth_token)
        
        print(f"📱 Communication channels: WhatsApp={self.use_whatsapp}, Twilio={self.use_twilio}")
    
    async def send_message_via_best_channel(self, phone: str, message: str) -> bool:
        """Send message via the best available channel."""
        # Try WhatsApp Cloud API first if available
        if self.use_whatsapp:
            success = await self.whatsapp_client.send_text_message(phone, message)
            if success:
                return True
            print("⚠️ WhatsApp Cloud API failed, trying Twilio...")
        
        # Fallback to Twilio SMS
        if self.use_twilio:
            success = await self.twilio_client.send_sms(phone, message)
            if success:
                return True
            print("⚠️ Twilio SMS failed, trying Twilio WhatsApp...")
            
            # Try Twilio WhatsApp as last resort
            success = await self.twilio_client.send_whatsapp_message(phone, message)
            return success
        
        print("❌ No communication channels available")
        return False
    
    async def send_onboarding_question(self, phone: str, question_type: str, **kwargs) -> bool:
        """Send onboarding question via best available channel."""
        if self.use_whatsapp:
            # Use rich interactive messages for WhatsApp Cloud API
            if question_type == "name":
                return await self.whatsapp_client.send_name_question(phone)
            elif question_type == "diet":
                return await self.whatsapp_client.send_diet_question(phone)
            elif question_type == "cuisine":
                return await self.whatsapp_client.send_cuisine_question(phone)
            elif question_type == "allergies":
                return await self.whatsapp_client.send_allergies_question(phone)
            elif question_type == "household":
                return await self.whatsapp_client.send_household_question(phone)
        
        # Fallback to Twilio with simplified text-based questions
        if self.use_twilio:
            user_name = kwargs.get('user_name')
            return await self.twilio_client.send_onboarding_question_sms(phone, question_type, user_name)
        
        return False
    
    async def send_meal_recommendations(self, phone: str, recommendations: List[Dict[str, Any]]) -> bool:
        """Send meal recommendations via best available channel."""
        if self.use_whatsapp:
            # Use existing WhatsApp formatting
            await self._send_meal_recommendations(phone, recommendations, "")
            return True
        
        if self.use_twilio:
            # Use Twilio-optimized formatting
            return await self.twilio_client.send_meal_recommendations_sms(phone, recommendations)
        
        return False
    
    async def _handle_post_onboarding_message(self, sender_phone: str, message: Dict[str, Any]) -> None:
        """Override to use hybrid messaging."""
        message_type = message.get("type")
        
        try:
            if message_type == "text":
                await self._handle_text_message_hybrid(sender_phone, message)
            elif message_type == "image":
                await self._handle_image_message_hybrid(sender_phone, message)
            elif message_type == "interactive":
                await self._handle_interactive_message_hybrid(sender_phone, message)
            else:
                # Send helpful response via best channel
                await self.send_message_via_best_channel(
                    sender_phone,
                    "Mambo 🤖: I can help with meal suggestions! Just ask me what you'd like to eat, send a food photo, or ask for recipes. What can I help you cook today?"
                )
        except Exception as e:
            print(f"Error handling post-onboarding message: {e}")
            await self.send_message_via_best_channel(
                sender_phone,
                "Mambo 😅: Sorry, I had a little hiccup. Could you try asking again? I'm here to help with your meals!"
            )
    
    async def _handle_text_message_hybrid(self, sender_phone: str, message: Dict[str, Any]) -> None:
        """Handle text messages with hybrid messaging."""
        text_content = message.get("text", {}).get("body", "").strip()
        
        if not text_content:
            return
        
        # Get meal recommendations
        recommendations = await self.recommendation_service.get_meal_recommendations(
            sender_phone, text_content, max_results=3
        )
        
        # Send via best available channel
        await self.send_meal_recommendations(sender_phone, recommendations)
    
    async def _handle_image_message_hybrid(self, sender_phone: str, message: Dict[str, Any]) -> None:
        """Handle image messages with hybrid messaging."""
        try:
            # Send acknowledgment
            await self.send_message_via_best_channel(
                sender_phone,
                "Mambo 📸: Let me analyze your photo to identify ingredients... This might take a moment!"
            )
            
            # For now, ask for text description (same as original logic)
            response_text = (
                "Mambo 🔍: I'm still learning to analyze photos directly! "
                "Could you tell me what ingredients you see in the image? "
                "For example: 'I have tomatoes, onions, and chicken' - "
                "then I can suggest some amazing meals you can make! 👨‍🍳"
            )
            
            await self.send_message_via_best_channel(sender_phone, response_text)
            
        except Exception as e:
            print(f"Error handling image message: {e}")
            await self.send_message_via_best_channel(
                sender_phone,
                "Mambo 📸: I had trouble with that image. Could you tell me what ingredients you have instead? I'll suggest some great meals!"
            )
    
    async def _handle_interactive_message_hybrid(self, sender_phone: str, message: Dict[str, Any]) -> None:
        """Handle interactive messages with hybrid messaging."""
        await self.send_message_via_best_channel(
            sender_phone,
            "Mambo ✨: Got it! What else can I help you cook today?"
        )
    
    async def get_channel_status(self) -> Dict[str, Any]:
        """Get status of all communication channels."""
        status = {
            "whatsapp_cloud_api": {
                "available": self.use_whatsapp,
                "configured": bool(settings.whatsapp_token and settings.whatsapp_phone_number_id)
            },
            "twilio_sms": {
                "available": self.use_twilio,
                "configured": bool(settings.twilio_account_sid and settings.twilio_auth_token)
            },
            "twilio_whatsapp": {
                "available": self.use_twilio,
                "configured": bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_phone_number)
            }
        }
        
        # Test connections
        if self.use_twilio:
            status["twilio_connection_test"] = await self.twilio_client.test_connection()
        
        return status