"""
WhatsApp Cloud API client for sending interactive messages.
"""
import json
import requests
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
            response = requests.post(self.base_url, headers=self.headers, json=payload)
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
    
    # TODO: Add methods for allergies and household questions