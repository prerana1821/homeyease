"""
Message handler service for processing WhatsApp messages.
"""
import json
from typing import Dict, Any
from app.services.onboarding_service import OnboardingService
from app.services.intent_classifier import IntentClassifier
from app.services.whatsapp_client import WhatsAppClient

class MessageHandler:
    def __init__(self):
        self.onboarding_service = OnboardingService()
        self.intent_classifier = IntentClassifier()
        self.whatsapp_client = WhatsAppClient()
    
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
        
        if message_type == "text":
            text_content = message.get("text", {}).get("body", "")
            intent = await self.intent_classifier.classify_intent(text_content)
            # Handle based on intent
            # TODO: Implement intent-based message handling
        elif message_type == "image":
            # Handle image messages for ingredient detection
            # TODO: Implement image processing
            pass