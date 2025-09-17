"""
WhatsApp Cloud API client for sending interactive messages.
"""
import json
import httpx
from typing import Dict, Any, List
from app.config.settings import settings

class WhatsAppClient:
    def __init__(self):
        self.base_url = f"https://graph.facebook.com/v17.0/{settings.whatsapp_phone_number_id}/messages"
        self.headers = {
            "Authorization": f"Bearer {settings.whatsapp_token}",
            "Content-Type": "application/json"
        }
    
    async def send_message(self, to_phone: str, payload: Dict[str, Any]) -> bool:
        """Send a message using WhatsApp Cloud API."""
        try:
            payload["to"] = to_phone
            async with httpx.AsyncClient() as client:
                response = await client.post(self.base_url, headers=self.headers, json=payload)
                response.raise_for_status()
            return True
        except Exception as e:
            print(f"Error sending WhatsApp message: {e}")
            return False
    
    async def send_text_message(self, to_phone: str, text: str) -> bool:
        """Send a simple text message."""
        payload = {
            "messaging_product": "whatsapp",
            "type": "text",
            "text": {"body": text}
        }
        return await self.send_message(to_phone, payload)
    
    async def send_name_question(self, to_phone: str) -> bool:
        """Send Q1 - Name question."""
        payload = {
            "messaging_product": "whatsapp",
            "type": "text",
            "text": {
                "body": "Mambo 🥘: Hey! I'm Mambo — your kitchen sidekick. What should I call you? (Just type your name — or reply 'skip' if you prefer.)"
            }
        }
        return await self.send_message(to_phone, payload)
    
    async def send_diet_question(self, to_phone: str) -> bool:
        """Send Q2 - Diet question with interactive buttons."""
        payload = {
            "messaging_product": "whatsapp",
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": "Mambo 🌿🍗: Tell me your food base — what do you usually eat? Tap one."
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "DIET_veg",
                                "title": "Veg 🌱"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "DIET_nonveg",
                                "title": "Non-Veg 🍗"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "DIET_both",
                                "title": "Both 🍴"
                            }
                        }
                    ]
                }
            }
        }
        return await self.send_message(to_phone, payload)
    
    async def send_cuisine_question(self, to_phone: str) -> bool:
        """Send Q3 - Cuisine question with interactive list."""
        # This is the exact payload from your requirements
        payload = {
            "messaging_product": "whatsapp",
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": "Mambo 🍽️: Pick your kitchen vibe — pick one so I make suggestions you'll actually love."
                },
                "action": {
                    "button": "Choose cuisine",
                    "sections": [
                        {
                            "title": "Popular",
                            "rows": [
                                {"id": "CUISINE_north_indian", "title": "North Indian", "description": "Gravies, rotis, biryani"},
                                {"id": "CUISINE_south_indian", "title": "South Indian", "description": "Dosa, idli, sambar"},
                                {"id": "CUISINE_indo_chinese", "title": "Chinese / Indo-Chinese", "description": "Quick & spicy wok dishes"},
                                {"id": "CUISINE_italian", "title": "Italian", "description": "Pasta, pizzas, simple flavors"}
                            ]
                        },
                        {
                            "title": "Regional & Other",
                            "rows": [
                                {"id": "CUISINE_punjabi", "title": "Punjabi", "description": "Tandoori, makki/saag, rich curries"},
                                {"id": "CUISINE_gujarati", "title": "Gujarati", "description": "Sweet-savory, vegetarian"},
                                {"id": "CUISINE_bengali", "title": "Bengali / East Indian", "description": "Fish & subtle spices"},
                                {"id": "CUISINE_international", "title": "International / Fusion", "description": "Thai, Mexican, Middle-Eastern..."}
                            ]
                        },
                        {
                            "title": "Fun",
                            "rows": [
                                {"id": "CUISINE_surprise", "title": "Surprise me 🎲", "description": "I'll pick something new for you"}
                            ]
                        }
                    ]
                }
            }
        }
        return await self.send_message(to_phone, payload)
    
    async def send_allergies_question(self, to_phone: str) -> bool:
        """Send Q4 - Allergies question with interactive list."""
        payload = {
            "messaging_product": "whatsapp",
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": "Mambo 🩺: Any allergies I should avoid when suggesting meals? Tap any that apply (or choose None)."
                },
                "action": {
                    "button": "Choose allergies",
                    "sections": [
                        {
                            "title": "Common allergies",
                            "rows": [
                                {"id": "ALLERGY_none", "title": "None ✅", "description": "No known food allergies"},
                                {"id": "ALLERGY_milk_dairy", "title": "Milk / Dairy 🥛", "description": "Milk, paneer, ghee"},
                                {"id": "ALLERGY_egg", "title": "Eggs 🥚", "description": "Egg white / yolk"},
                                {"id": "ALLERGY_peanut", "title": "Peanut 🥜", "description": "Peanuts or peanut oil"},
                                {"id": "ALLERGY_tree_nuts", "title": "Tree nuts (cashew/almond)", "description": "Cashew, almond, walnut"}
                            ]
                        },
                        {
                            "title": "Other common ones",
                            "rows": [
                                {"id": "ALLERGY_gluten_wheat", "title": "Wheat / Gluten 🌾", "description": "Roti, bread, pasta"},
                                {"id": "ALLERGY_soy", "title": "Soy 🌱", "description": "Soy products, sauces"},
                                {"id": "ALLERGY_fish", "title": "Fish 🐟", "description": "Coastal/seafood items"},
                                {"id": "ALLERGY_shellfish", "title": "Shellfish (prawn/shrimp)", "description": "Prawns, crabs"}
                            ]
                        },
                        {
                            "title": "Other / Regional",
                            "rows": [
                                {"id": "ALLERGY_sesame", "title": "Sesame", "description": "Til / sesame seeds or oil"},
                                {"id": "ALLERGY_other_type", "title": "Other (type it)", "description": "I'll ask you to type the allergy"}
                            ]
                        }
                    ]
                }
            }
        }
        return await self.send_message(to_phone, payload)
    
    async def send_household_question(self, to_phone: str) -> bool:
        """Send Q5 - Household question with interactive list."""
        payload = {
            "messaging_product": "whatsapp",
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": "Mambo 🏡: Who are you usually cooking for? This helps me scale recipes right."
                },
                "action": {
                    "button": "Choose household",
                    "sections": [
                        {
                            "title": "Quick pick",
                            "rows": [
                                {"id": "HOUSE_single", "title": "Just me 👤", "description": "Single serving / quick recipes"},
                                {"id": "HOUSE_couple", "title": "Couple / 2 people 👩‍❤️‍👨", "description": "Portions for two"},
                                {"id": "HOUSE_small_family", "title": "Small family (3–4) 🍲", "description": "Family-friendly portions"},
                                {"id": "HOUSE_big_family", "title": "Big family (5+) 👨‍👩‍👧‍👦", "description": "Bigger batches"},
                                {"id": "HOUSE_shared_flat", "title": "Shared flat / Varies 🎲", "description": "Portions vary / host occasionally"}
                            ]
                        }
                    ]
                }
            }
        }
        return await self.send_message(to_phone, payload)
    
    async def send_confirmation_message(self, to_phone: str, name: str) -> bool:
        """Send name confirmation message."""
        text = f"Mambo ✨: Lovely — Hi {name}! I'll remember that. Ready for a couple quick preferences so I can tailor your meals? (Yes / No)"
        return await self.send_text_message(to_phone, text)
    
    async def send_diet_confirmation(self, to_phone: str, diet_label: str) -> bool:
        """Send diet preference confirmation."""
        text = f"Mambo ✅: Noted — you prefer *{diet_label}*. I'll avoid suggesting meals that don't match this. Next up: pick a cuisine vibe."
        return await self.send_text_message(to_phone, text)