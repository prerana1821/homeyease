"""
Twilio webhook endpoints for receiving SMS and WhatsApp messages.
This provides an alternative to WhatsApp Cloud API for testing and fallback.
"""
from fastapi import APIRouter, Request, Form
from fastapi.responses import Response
from typing import Optional
from app.services.message_handler import MessageHandler
from app.services.twilio_message_adapter import TwilioMessageAdapter

router = APIRouter()
message_handler = MessageHandler()
twilio_adapter = TwilioMessageAdapter()

@router.post("/sms")
async def handle_sms_webhook(
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
    AccountSid: str = Form(...),
    NumMedia: Optional[str] = Form("0")
):
    """Handle incoming SMS messages from Twilio."""
    try:
        print(f"📱 Received SMS from {From}: {Body}")
        
        # Convert Twilio SMS to WhatsApp-like format
        whatsapp_message = twilio_adapter.convert_sms_to_whatsapp_format(
            from_phone=From,
            body=Body,
            message_sid=MessageSid,
            num_media=int(NumMedia or 0)
        )
        
        # Process using existing message handler
        await message_handler.process_webhook(whatsapp_message)
        
        # Return TwiML response (empty for now)
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml"
        )
        
    except Exception as e:
        print(f"Error processing SMS webhook: {e}")
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml"
        )

@router.post("/whatsapp")
async def handle_whatsapp_webhook(
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
    AccountSid: str = Form(...),
    NumMedia: Optional[str] = Form("0"),
    MediaUrl0: Optional[str] = Form(None)
):
    """Handle incoming WhatsApp messages from Twilio."""
    try:
        print(f"📱 Received WhatsApp from {From}: {Body}")
        
        # Convert Twilio WhatsApp to WhatsApp Cloud API format
        whatsapp_message = twilio_adapter.convert_whatsapp_to_whatsapp_format(
            from_phone=From,
            body=Body,
            message_sid=MessageSid,
            num_media=int(NumMedia or 0),
            media_url=MediaUrl0
        )
        
        # Process using existing message handler
        await message_handler.process_webhook(whatsapp_message)
        
        # Return TwiML response
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml"
        )
        
    except Exception as e:
        print(f"Error processing WhatsApp webhook: {e}")
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml"
        )

@router.get("/test")
async def test_twilio_webhook():
    """Test endpoint for Twilio webhook setup."""
    return {
        "message": "Twilio webhook endpoint is working",
        "endpoints": {
            "sms": "/webhook/twilio/sms",
            "whatsapp": "/webhook/twilio/whatsapp"
        }
    }