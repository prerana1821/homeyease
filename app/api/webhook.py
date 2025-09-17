"""
WhatsApp webhook endpoints for receiving and processing messages.
"""
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
from app.config.settings import settings
from app.services.message_handler import MessageHandler

router = APIRouter()
message_handler = MessageHandler()

@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token")
):
    """Verify webhook endpoint for WhatsApp Cloud API."""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge)
    else:
        raise HTTPException(status_code=403, detail="Invalid verification token")

@router.post("/whatsapp")
async def handle_webhook(request: Request):
    """Handle incoming WhatsApp messages."""
    try:
        body = await request.json()
        await message_handler.process_webhook(body)
        return {"status": "ok"}
    except Exception as e:
        print(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")