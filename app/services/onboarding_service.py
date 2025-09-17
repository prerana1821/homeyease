"""
Onboarding service for handling the 5-step WhatsApp onboarding flow.
"""
from typing import Dict, Any, Optional
from app.services.whatsapp_client import WhatsAppClient
from app.services.user_service import UserService

class OnboardingService:
    def __init__(self):
        self.whatsapp_client = WhatsAppClient()
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
        await self.whatsapp_client.send_name_question(whatsapp_id)
    
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
            await self.whatsapp_client.send_confirmation_message(user['whatsapp_id'], name)
            await self.whatsapp_client.send_diet_question(user['whatsapp_id'])
    
    async def _handle_diet_response(self, user: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Handle Q2 - Diet response."""
        if message.get("type") == "interactive":
            button_reply = message.get("interactive", {}).get("button_reply", {})
            diet_id = button_reply.get("id", "")
            
            # Map diet IDs to database values
            diet_mapping = {
                "DIET_veg": "veg",
                "DIET_nonveg": "non-veg", 
                "DIET_both": "both"
            }
            
            diet = diet_mapping.get(diet_id, "both")
            diet_labels = {
                "veg": "Veg 🌱",
                "non-veg": "Non-Veg 🍗",
                "both": "Both 🍴"
            }
            
            # Update user diet and move to step 2 in single operation
            await self.user_service.update_user_diet_and_onboarding_step(user['id'], diet, 2)
            
            # Send confirmation and Q3
            await self.whatsapp_client.send_diet_confirmation(user['whatsapp_id'], diet_labels[diet])
            await self.whatsapp_client.send_cuisine_question(user['whatsapp_id'])
    
    async def _handle_cuisine_response(self, user: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Handle Q3 - Cuisine response."""
        if message.get("type") == "interactive":
            list_reply = message.get("interactive", {}).get("list_reply", {})
            cuisine_id = list_reply.get("id", "")
            
            # Extract cuisine from ID (e.g., "CUISINE_north_indian" -> "north_indian")
            cuisine = cuisine_id.replace("CUISINE_", "") if cuisine_id.startswith("CUISINE_") else "surprise"
            
            # Update user cuisine and move to step 3 in single operation
            await self.user_service.update_user_cuisine_and_onboarding_step(user['id'], cuisine, 3)
            
            # Send confirmation and Q4
            await self.whatsapp_client.send_text_message(user['whatsapp_id'], f"Mambo ✅: Perfect — {cuisine.replace('_', ' ').title()} it is! I'll keep that in mind.")
            await self.whatsapp_client.send_allergies_question(user['whatsapp_id'])
    
    async def _handle_allergies_response(self, user: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Handle Q4 - Allergies response."""
        if message.get("type") == "interactive":
            list_reply = message.get("interactive", {}).get("list_reply", {})
            allergy_id = list_reply.get("id", "")
            
            if allergy_id == "ALLERGY_none":
                allergies = []
            elif allergy_id == "ALLERGY_other_type":
                # Ask user to type the allergy
                await self.whatsapp_client.send_text_message(user['whatsapp_id'], "Please type the allergy name (e.g., 'mustard', 'coconut')")
                return  # Wait for text response
            else:
                # Extract allergy from ID
                allergy = allergy_id.replace("ALLERGY_", "").replace("_", " ")
                allergies = [allergy]
            
            # Update user allergies and move to step 4 in single operation
            await self.user_service.update_user_allergies_and_onboarding_step(user['id'], allergies, 4)
            
            # Send Q5
            await self.whatsapp_client.send_household_question(user['whatsapp_id'])
        
        elif message.get("type") == "text" and user['onboarding_step'] == 3:
            # Handle custom allergy text input
            allergy_text = message.get("text", {}).get("body", "").strip()
            allergies = [allergy_text] if allergy_text else []
            
            # Update user allergies and move to step 4 in single operation
            await self.user_service.update_user_allergies_and_onboarding_step(user['id'], allergies, 4)
            
            # Send Q5
            await self.whatsapp_client.send_household_question(user['whatsapp_id'])
    
    async def _handle_household_response(self, user: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Handle Q5 - Household response."""
        if message.get("type") == "interactive":
            list_reply = message.get("interactive", {}).get("list_reply", {})
            household_id = list_reply.get("id", "")
            
            # Extract household size from ID
            household = household_id.replace("HOUSE_", "") if household_id.startswith("HOUSE_") else "single"
            
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
                await self.whatsapp_client.send_text_message(user['whatsapp_id'], completion_text)
            else:
                # Fallback message if update failed
                await self.whatsapp_client.send_text_message(user['whatsapp_id'], "Welcome! Your onboarding is complete. Ready for your first meal suggestion? Just ask 'What's for dinner?' 🍽️")