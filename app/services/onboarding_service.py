"""
Onboarding service for handling the 5-step WhatsApp onboarding flow.
"""
from typing import Dict, Any, Optional
from app.services.twilio_client import TwilioClient
from app.services.user_service import UserService

class OnboardingService:
    def __init__(self):
        self.twilio_client = TwilioClient()
        self.user_service = UserService()
    
    async def get_user_onboarding_step(self, whatsapp_id: str) -> Optional[int]:
        """Get the current onboarding step for a user."""
        user = await self.user_service.get_user_by_whatsapp_id(whatsapp_id)
        return user['onboarding_step'] if user else None
    
    async def handle_onboarding_message(self, whatsapp_id: str, message: Dict[str, Any]) -> None:
        """Handle messages during the onboarding flow."""
        user = await self.user_service.get_user_by_whatsapp_id(whatsapp_id)
        if not user:
            # New user, start onboarding
            await self.start_onboarding(whatsapp_id)
            return
        
        user_step = user['onboarding_step']
        
        if user_step == 0:  # Q1 - Name
            await self._handle_name_response(user, message)
        elif user_step == 1:  # Q2 - Diet
            await self._handle_diet_response(user, message)
        elif user_step == 2:  # Q3 - Cuisine
            await self._handle_cuisine_response(user, message)
        elif user_step == 3:  # Q4 - Allergies
            await self._handle_allergies_response(user, message)
        elif user_step == 4:  # Q5 - Household
            await self._handle_household_response(user, message)
    
    async def start_onboarding(self, whatsapp_id: str) -> None:
        """Start the onboarding flow for a new user."""
        # Create user with onboarding step 0
        user = await self.user_service.create_user(whatsapp_id)
        # Send Q1 - Name question
        await self.twilio_client.send_onboarding_question_sms(whatsapp_id, 'name')
    
    async def _handle_name_response(self, user: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Handle Q1 - Name response."""
        if message.get("type") == "text":
            name_text = message.get("text", {}).get("body", "").strip()
            
            if name_text.lower() == "skip":
                name = "Guest"
            else:
                # Basic sanitization
                name = name_text[:50]  # Limit length
            
            # Update user name and move to step 1 in single operation
            await self.user_service.update_user_name_and_onboarding_step(user['id'], name, 1)
            
            # Send confirmation and Q2
            confirmation_msg = f"Mambo ✨: Lovely — Hi {name}! I'll remember that. Ready for a couple quick preferences so I can tailor your meals? (Yes / No)"
            await self.twilio_client.send_sms(user['whatsapp_id'], confirmation_msg)
            await self.twilio_client.send_onboarding_question_sms(user['whatsapp_id'], 'diet', name)
    
    async def _handle_diet_response(self, user: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Handle Q2 - Diet response (SMS numeric: 1-Veg, 2-Non-veg, 3-Both)."""
        if message.get("type") == "text":
            text_response = message.get("text", {}).get("body", "").strip()
            
            # Map numeric responses to database values
            diet_mapping = {
                "1": "veg",
                "2": "non-veg", 
                "3": "both"
            }
            
            diet = diet_mapping.get(text_response, "both")
            diet_labels = {
                "veg": "Veg 🌱",
                "non-veg": "Non-Veg 🍗",
                "both": "Both 🍴"
            }
            
            # Update user diet and move to step 2 in single operation
            await self.user_service.update_user_diet_and_onboarding_step(user['id'], diet, 2)
            
            # Send confirmation and Q3
            confirmation_msg = f"Mambo ✅: Noted — you prefer *{diet_labels[diet]}*. I'll avoid suggesting meals that don't match this. Next up: pick a cuisine vibe."
            await self.twilio_client.send_sms(user['whatsapp_id'], confirmation_msg)
            await self.twilio_client.send_onboarding_question_sms(user['whatsapp_id'], 'cuisine')
    
    async def _handle_cuisine_response(self, user: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Handle Q3 - Cuisine response (SMS numeric: 1-9)."""
        if message.get("type") == "text":
            text_response = message.get("text", {}).get("body", "").strip()
            
            # Map numeric responses to database values (matching SMS options)
            cuisine_mapping = {
                "1": "north_indian",
                "2": "south_indian", 
                "3": "chinese",
                "4": "italian",
                "5": "punjabi",
                "6": "gujarati",
                "7": "bengali",
                "8": "international",
                "9": "surprise"
            }
            
            cuisine = cuisine_mapping.get(text_response, "surprise")
            
            # Update user cuisine and move to step 3 in single operation
            await self.user_service.update_user_cuisine_and_onboarding_step(user['id'], cuisine, 3)
            
            # Send confirmation and Q4
            await self.twilio_client.send_sms(user['whatsapp_id'], f"Mambo ✅: Perfect — {cuisine.replace('_', ' ').title()} it is! I'll keep that in mind.")
            await self.twilio_client.send_onboarding_question_sms(user['whatsapp_id'], 'allergies')
    
    async def _handle_allergies_response(self, user: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Handle Q4 - Allergies response (SMS numeric: 1-10, can be multiple)."""
        if message.get("type") == "text":
            text_response = message.get("text", {}).get("body", "").strip()
            
            # Handle special case of "10" (Other) - ask for text input
            if text_response == "10":
                await self.twilio_client.send_sms(user['whatsapp_id'], "Please type the allergy name (e.g., 'mustard', 'coconut')")
                return  # Wait for text response
            
            # Map numeric responses to allergies (can be multiple like "2,3,5")
            allergy_mapping = {
                "1": [],  # None
                "2": ["dairy"],
                "3": ["eggs"],
                "4": ["peanut"],
                "5": ["tree nuts"],
                "6": ["wheat/gluten"],
                "7": ["soy"],
                "8": ["fish"],
                "9": ["shellfish"]
            }
            
            allergies = []
            # Handle multiple selections (e.g., "2,3,5" or "2 3 5")
            selections = text_response.replace(",", " ").replace("  ", " ").split()
            for selection in selections:
                if selection in allergy_mapping:
                    allergies.extend(allergy_mapping[selection])
            
            # Update user allergies and move to step 4 in single operation
            await self.user_service.update_user_allergies_and_onboarding_step(user['id'], allergies, 4)
            
            # Send Q5
            await self.twilio_client.send_onboarding_question_sms(user['whatsapp_id'], 'household')
        
        elif message.get("type") == "text" and user['onboarding_step'] == 3 and not message.get("text", {}).get("body", "").strip().isdigit():
            # Handle custom allergy text input (when user types allergy name after selecting "10")
            allergy_text = message.get("text", {}).get("body", "").strip()
            allergies = [allergy_text] if allergy_text else []
            
            # Update user allergies and move to step 4 in single operation
            await self.user_service.update_user_allergies_and_onboarding_step(user['id'], allergies, 4)
            
            # Send Q5
            await self.twilio_client.send_onboarding_question_sms(user['whatsapp_id'], 'household')
    
    async def _handle_household_response(self, user: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Handle Q5 - Household response (SMS numeric: 1-5)."""
        if message.get("type") == "text":
            text_response = message.get("text", {}).get("body", "").strip()
            
            # Map numeric responses to household values
            household_mapping = {
                "1": "single",
                "2": "couple",
                "3": "small_family",
                "4": "big_family",
                "5": "shared"
            }
            
            household = household_mapping.get(text_response, "single")
            
            # Update user household and complete onboarding in single operation
            updated_user = await self.user_service.update_user_household_and_complete_onboarding(user['id'], household)
            
            if updated_user:
                # Send onboarding completion message using fresh user data
                completion_text = (
                    f"Mambo ✨: Perfect! Your profile is complete:\n\n"
                    f"• Name: {updated_user['name']}\n"
                    f"• Diet: {updated_user['diet']}\n"
                    f"• Cuisine: {updated_user['cuisine_pref']}\n"
                    f"• Allergies: {', '.join(updated_user['allergies']) if updated_user['allergies'] else 'None'}\n"
                    f"• Household: {household.replace('_', ' ').title()}\n\n"
                    f"Ready for your first meal suggestion? Just ask 'What's for dinner?' 🍽️"
                )
                await self.twilio_client.send_sms(user['whatsapp_id'], completion_text)
            else:
                # Fallback message if update failed
                await self.twilio_client.send_sms(user['whatsapp_id'], "Welcome! Your onboarding is complete. Ready for your first meal suggestion? Just ask 'What's for dinner?' 🍽️")