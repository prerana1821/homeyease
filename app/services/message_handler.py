"""
Message handler service for processing WhatsApp messages.
"""
import json
from typing import Dict, Any, List
from app.services.onboarding_service import OnboardingService
from app.services.intent_classifier import IntentClassifier
from app.services.twilio_client import TwilioClient
from app.services.recommendation_service import RecommendationService
from app.services.image_service import ImageService

class MessageHandler:
    def __init__(self):
        self.onboarding_service = OnboardingService()
        self.intent_classifier = IntentClassifier()
        self.twilio_client = TwilioClient()
        self.recommendation_service = RecommendationService()
        self.image_service = ImageService()
    
    async def process_webhook(self, webhook_data: Dict[str, Any]) -> None:
        """Process incoming webhook data from WhatsApp."""
        try:
            # Extract message data from webhook
            for entry in webhook_data.get("entry", []):
                for change in entry.get("changes", []):
                    if change.get("field") == "messages":
                        await self._handle_message_change(change["value"])
        except Exception as e:
            print(f"Error processing webhook: {e}")
            raise
    
    async def _handle_message_change(self, message_data: Dict[str, Any]) -> None:
        """Handle individual message changes."""
        # Extract messages
        messages = message_data.get("messages", [])
        
        for message in messages:
            await self._process_single_message(message)
    
    async def _process_single_message(self, message: Dict[str, Any]) -> None:
        """Process a single WhatsApp message."""
        # Extract basic message info
        sender_phone = message.get("from")
        message_type = message.get("type")
        
        if not sender_phone:
            return
        
        # Check if user is in onboarding flow
        user_onboarding_step = await self.onboarding_service.get_user_onboarding_step(sender_phone)
        
        if user_onboarding_step is not None and user_onboarding_step < 5:
            # User is in onboarding flow
            await self.onboarding_service.handle_onboarding_message(sender_phone, message)
        else:
            # User has completed onboarding, process normal messages
            await self._handle_post_onboarding_message(sender_phone, message)
    
    async def _handle_post_onboarding_message(self, sender_phone: str, message: Dict[str, Any]) -> None:
        """Handle messages after onboarding is complete."""
        message_type = message.get("type")
        
        try:
            if message_type == "text":
                await self._handle_text_message(sender_phone, message)
            elif message_type == "image":
                await self._handle_image_message(sender_phone, message)
            elif message_type == "interactive":
                await self._handle_interactive_message(sender_phone, message)
            else:
                # Send a helpful response for unsupported message types
                await self.twilio_client.send_sms(
                    sender_phone,
                    "Mambo 🤖: I can help with meal suggestions! Just ask me what you'd like to eat, send a food photo, or ask for recipes. What can I help you cook today?"
                )
        except Exception as e:
            print(f"Error handling post-onboarding message: {e}")
            await self.twilio_client.send_sms(
                sender_phone,
                "Mambo 😅: Sorry, I had a little hiccup. Could you try asking again? I'm here to help with your meals!"
            )
    
    async def _handle_text_message(self, sender_phone: str, message: Dict[str, Any]) -> None:
        """Handle text messages and provide meal recommendations."""
        text_content = message.get("text", {}).get("body", "").strip()
        
        if not text_content:
            return
        
        # Get meal recommendations based on message
        recommendations = await self.recommendation_service.get_meal_recommendations(
            sender_phone, text_content, max_results=3
        )
        
        # Format and send response
        await self._send_meal_recommendations(sender_phone, recommendations, text_content)
    
    async def _handle_image_message(self, sender_phone: str, message: Dict[str, Any]) -> None:
        """Handle image messages for ingredient detection."""
        try:
            # Extract image information from WhatsApp message
            image_info = message.get("image", {})
            image_id = image_info.get("id")
            
            if not image_id:
                await self.twilio_client.send_sms(
                    sender_phone,
                    "Mambo 📸: I couldn't process that image. Could you try sending it again or tell me what ingredients you have?"
                )
                return
            
            # Send immediate acknowledgment
            await self.twilio_client.send_sms(
                sender_phone,
                "Mambo 📸: Let me analyze your photo to identify ingredients... This might take a moment!"
            )
            
            # For now, since we can't directly access WhatsApp media without proper setup,
            # we'll use the fallback approach and ask for text description
            ingredient_suggestions = await self.image_service.get_ingredient_suggestions([])
            
            response_text = (
                "Mambo 🔍: I'm still learning to analyze photos directly! "
                "Could you tell me what ingredients you see in the image? "
                "For example: 'I have tomatoes, onions, and chicken' - "
                "then I can suggest some amazing meals you can make! 👨‍🍳"
            )
            
            await self.twilio_client.send_sms(sender_phone, response_text)
            
        except Exception as e:
            print(f"Error handling image message: {e}")
            await self.twilio_client.send_sms(
                sender_phone,
                "Mambo 📸: I had trouble with that image. Could you tell me what ingredients you have instead? I'll suggest some great meals!"
            )
    
    async def _handle_interactive_message(self, sender_phone: str, message: Dict[str, Any]) -> None:
        """Handle interactive button/list responses."""
        # This could be used for follow-up questions or meal selections
        await self.twilio_client.send_sms(
            sender_phone,
            "Mambo ✨: Got it! What else can I help you cook today?"
        )
    
    async def _send_meal_recommendations(self, sender_phone: str, recommendations: List[Dict[str, Any]], original_message: str) -> None:
        """Format and send meal recommendations to user."""
        if not recommendations:
            await self.twilio_client.send_sms(
                sender_phone,
                "Mambo 🤔: I'm still learning about your taste! Could you try asking for something specific like 'suggest dinner' or 'what can I make with rice'?"
            )
            return
        
        # Create response message
        context = recommendations[0].get('context', 'Here are some meal suggestions')
        response_text = f"Mambo 🍽️: {context}:\n\n"
        
        for i, meal in enumerate(recommendations, 1):
            name = meal.get('name', 'Unknown Dish')
            cuisine = meal.get('cuisine', '').replace('_', ' ').title()
            time_min = meal.get('estimated_time_min', 0)
            diet = meal.get('diet_type', '')
            
            # Format time
            time_text = f" ({time_min} min)" if time_min else ""
            
            # Format diet indicator
            diet_emoji = "🌱" if diet == "veg" else "🍗" if diet == "non-veg" else ""
            
            response_text += f"{i}. *{name}* {diet_emoji}\n"
            response_text += f"   {cuisine} cuisine{time_text}\n"
            
            # Add recipe hint if available
            recipe = meal.get('recipe_text', '')
            if recipe:
                recipe_short = recipe[:80] + "..." if len(recipe) > 80 else recipe
                response_text += f"   💡 {recipe_short}\n"
            
            response_text += "\n"
        
        # Add follow-up suggestion
        response_text += "Want the full recipe for any of these? Just ask 'recipe for [dish name]' 👨‍🍳"
        
        # Send the recommendation
        await self.twilio_client.send_sms(sender_phone, response_text)