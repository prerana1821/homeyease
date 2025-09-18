"""
Adapter to convert Twilio message format to WhatsApp Cloud API format.
This allows reusing existing message processing logic with Twilio.
"""
from typing import Dict, Any, Optional
import re

class TwilioMessageAdapter:
    def __init__(self):
        pass
    
    def convert_sms_to_whatsapp_format(
        self, 
        from_phone: str, 
        body: str, 
        message_sid: str, 
        num_media: int = 0
    ) -> Dict[str, Any]:
        """Convert Twilio SMS format to WhatsApp Cloud API format."""
        
        # Clean phone number (remove whatsapp: prefix if present)
        clean_phone = from_phone.replace("whatsapp:", "")
        
        # Create WhatsApp-like message structure
        message = {
            "from": clean_phone,
            "id": message_sid,
            "timestamp": str(int(__import__('time').time())),
            "type": "text",
            "text": {
                "body": body
            }
        }
        
        # Handle media messages
        if num_media > 0:
            message["type"] = "image"  # Assume image for now
            message["image"] = {
                "id": f"media_{message_sid}",
                "mime_type": "image/jpeg"  # Default
            }
        
        # Wrap in WhatsApp Cloud API webhook format
        webhook_data = {
            "entry": [{
                "id": "twilio_entry",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": clean_phone,
                            "phone_number_id": "twilio_adapter"
                        },
                        "messages": [message]
                    }
                }]
            }]
        }
        
        return webhook_data
    
    def convert_whatsapp_to_whatsapp_format(
        self, 
        from_phone: str, 
        body: str, 
        message_sid: str, 
        num_media: int = 0,
        media_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convert Twilio WhatsApp format to WhatsApp Cloud API format."""
        
        # Clean phone number
        clean_phone = from_phone.replace("whatsapp:", "")
        
        # Create message structure
        message = {
            "from": clean_phone,
            "id": message_sid,
            "timestamp": str(int(__import__('time').time())),
            "type": "text",
            "text": {
                "body": body
            }
        }
        
        # Handle media messages
        if num_media > 0 and media_url:
            message["type"] = "image"
            message["image"] = {
                "id": f"media_{message_sid}",
                "mime_type": self._guess_mime_type(media_url)
            }
            # Remove text if it's a media message
            if "text" in message:
                del message["text"]
        
        # Handle interactive responses (button clicks, list selections)
        if self._is_interactive_response(body):
            interactive_data = self._parse_interactive_response(body)
            if interactive_data:
                message["type"] = "interactive"
                message["interactive"] = interactive_data
                if "text" in message:
                    del message["text"]
        
        # Wrap in WhatsApp Cloud API webhook format
        webhook_data = {
            "entry": [{
                "id": "twilio_whatsapp_entry",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": clean_phone,
                            "phone_number_id": "twilio_whatsapp_adapter"
                        },
                        "messages": [message]
                    }
                }]
            }]
        }
        
        return webhook_data
    
    def _guess_mime_type(self, url: str) -> str:
        """Guess MIME type from URL."""
        if not url:
            return "application/octet-stream"
        
        url_lower = url.lower()
        if any(ext in url_lower for ext in ['.jpg', '.jpeg']):
            return "image/jpeg"
        elif '.png' in url_lower:
            return "image/png"
        elif '.gif' in url_lower:
            return "image/gif"
        elif any(ext in url_lower for ext in ['.mp4', '.mov']):
            return "video/mp4"
        elif any(ext in url_lower for ext in ['.mp3', '.wav']):
            return "audio/mpeg"
        else:
            return "application/octet-stream"
    
    def _is_interactive_response(self, body: str) -> bool:
        """Check if the message body looks like an interactive response."""
        # Check for numbered responses (1, 2, 3, etc.)
        if re.match(r'^\d+$', body.strip()):
            return True
        
        # Check for button-like responses
        button_patterns = [
            r'^(yes|no)$',
            r'^(veg|non-veg|both)$',
            r'^(skip)$'
        ]
        
        body_lower = body.lower().strip()
        return any(re.match(pattern, body_lower) for pattern in button_patterns)
    
    def _parse_interactive_response(self, body: str) -> Optional[Dict[str, Any]]:
        """Parse interactive response and convert to WhatsApp format."""
        body_clean = body.strip().lower()
        
        # Handle numbered responses for onboarding
        if body_clean.isdigit():
            number = int(body_clean)
            
            # Map numbers to common onboarding responses
            # This is a simplified mapping - in practice, you'd need context
            # about which question was asked
            
            # Diet preferences (assuming this is the context)
            if number in [1, 2, 3]:
                diet_mapping = {1: "DIET_veg", 2: "DIET_nonveg", 3: "DIET_both"}
                return {
                    "type": "button_reply",
                    "button_reply": {
                        "id": diet_mapping.get(number, "DIET_both"),
                        "title": f"Option {number}"
                    }
                }
            
            # Cuisine preferences
            elif number in range(1, 10):
                cuisine_mapping = {
                    1: "CUISINE_north_indian",
                    2: "CUISINE_south_indian", 
                    3: "CUISINE_indo_chinese",
                    4: "CUISINE_italian",
                    5: "CUISINE_punjabi",
                    6: "CUISINE_gujarati",
                    7: "CUISINE_bengali",
                    8: "CUISINE_international",
                    9: "CUISINE_surprise"
                }
                return {
                    "type": "list_reply",
                    "list_reply": {
                        "id": cuisine_mapping.get(number, "CUISINE_surprise"),
                        "title": f"Cuisine {number}"
                    }
                }
        
        # Handle text-based responses
        elif body_clean in ["yes", "no"]:
            return {
                "type": "button_reply",
                "button_reply": {
                    "id": f"CONFIRM_{body_clean}",
                    "title": body_clean.title()
                }
            }
        
        elif body_clean in ["veg", "non-veg", "both"]:
            diet_mapping = {"veg": "DIET_veg", "non-veg": "DIET_nonveg", "both": "DIET_both"}
            return {
                "type": "button_reply",
                "button_reply": {
                    "id": diet_mapping[body_clean],
                    "title": body_clean.title()
                }
            }
        
        return None
    
    def convert_onboarding_response(self, body: str, question_type: str) -> Optional[Dict[str, Any]]:
        """Convert SMS response to appropriate interactive format based on question type."""
        body_clean = body.strip().lower()
        
        if question_type == "diet":
            if body_clean in ["1", "veg"]:
                return {"type": "button_reply", "button_reply": {"id": "DIET_veg", "title": "Veg"}}
            elif body_clean in ["2", "non-veg", "nonveg"]:
                return {"type": "button_reply", "button_reply": {"id": "DIET_nonveg", "title": "Non-Veg"}}
            elif body_clean in ["3", "both"]:
                return {"type": "button_reply", "button_reply": {"id": "DIET_both", "title": "Both"}}
        
        elif question_type == "cuisine":
            cuisine_mapping = {
                "1": "CUISINE_north_indian",
                "2": "CUISINE_south_indian",
                "3": "CUISINE_indo_chinese", 
                "4": "CUISINE_italian",
                "5": "CUISINE_punjabi",
                "6": "CUISINE_gujarati",
                "7": "CUISINE_bengali",
                "8": "CUISINE_international",
                "9": "CUISINE_surprise"
            }
            if body_clean in cuisine_mapping:
                return {"type": "list_reply", "list_reply": {"id": cuisine_mapping[body_clean], "title": f"Cuisine {body_clean}"}}
        
        elif question_type == "household":
            household_mapping = {
                "1": "HOUSE_single",
                "2": "HOUSE_couple", 
                "3": "HOUSE_small_family",
                "4": "HOUSE_big_family",
                "5": "HOUSE_shared_flat"
            }
            if body_clean in household_mapping:
                return {"type": "list_reply", "list_reply": {"id": household_mapping[body_clean], "title": f"Household {body_clean}"}}
        
        return None