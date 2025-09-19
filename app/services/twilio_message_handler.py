"""
Twilio-focused message handler that wraps TwilioClient.
This module intentionally does NOT import app.services.message_handler to avoid circular imports.
It provides an interface used by OnboardingService and MessageHandler.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services.twilio_client import TwilioClient
from app.config.settings import settings

logger = logging.getLogger(__name__)


class TwilioMessageHandler:
    """
    Thin Twilio-specific message sender used by higher-level services.

    Public methods return structured dicts:
      {"status": "ok"|"error", "provider": "twilio", "details": {...}, "error": "..." }
    """

    def __init__(self, twilio_client: Optional[TwilioClient] = None) -> None:
        self.twilio_client = twilio_client or TwilioClient()
        self.provider = "twilio_whatsapp"
        self.configured = bool(
            settings.twilio_account_sid
            and settings.twilio_auth_token
            and settings.twilio_phone_number
        )
        logger.debug("TwilioMessageHandler configured=%s", self.configured)

    async def send_text(self, to_phone: str, body: str):
        """Send a WhatsApp text message via Twilio."""
        try:
            resp = self.twilio_client.send_whatsapp_message(to_phone, body)
            if not resp.get("ok"):
                logger.error("Failed to send text to %s: %s", to_phone, resp)
            return resp
        except Exception as e:
            logger.exception("Error sending text message to %s: %s", to_phone, e)
            return {"ok": False, "error": str(e)}

    async def send_media(
        self, to_phone: str, media_urls: List[str], body: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a media message (image/video) via Twilio."""
        if not self.configured:
            return {
                "status": "error",
                "provider": self.provider,
                "error": "twilio_not_configured",
                "details": {},
            }
        try:
            resp = await self.twilio_client.send_media_message(
                to_phone, media_urls, body=body
            )
            if resp.get("status") == "ok":
                return {
                    "status": "ok",
                    "provider": self.provider,
                    "details": resp.get("details", {}),
                    "error": None,
                }
            return {
                "status": "error",
                "provider": self.provider,
                "details": resp.get("details", {}),
                "error": resp.get("error"),
            }
        except Exception as exc:
            logger.exception("send_media error to %s: %s", to_phone, exc)
            return {
                "status": "error",
                "provider": self.provider,
                "error": str(exc),
                "details": {},
            }

    async def send_interactive(
        self, to_phone: str, interactive_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send an interactive message (list/buttons) via Twilio if supported.
        Note: WhatsApp interactive messages often require pre-approved templates.
        """
        # fallback if Twilio client doesn't support interactive or not configured
        if not self.configured:
            return {
                "status": "error",
                "provider": self.provider,
                "error": "twilio_not_configured",
                "details": {},
            }
        if not hasattr(self.twilio_client, "send_whatsapp_interactive"):
            return {
                "status": "error",
                "provider": self.provider,
                "error": "interactive_not_supported",
                "details": {},
            }
        try:
            resp = await self.twilio_client.send_whatsapp_interactive(
                to_phone, interactive_payload
            )
            if resp.get("status") == "ok":
                return {
                    "status": "ok",
                    "provider": self.provider,
                    "details": resp.get("details", {}),
                    "error": None,
                }
            return {
                "status": "error",
                "provider": self.provider,
                "details": resp.get("details", {}),
                "error": resp.get("error"),
            }
        except Exception as exc:
            logger.exception("send_interactive error to %s: %s", to_phone, exc)
            return {
                "status": "error",
                "provider": self.provider,
                "error": str(exc),
                "details": {},
            }

    async def test_connection(self) -> Dict[str, Any]:
        """Return diagnostics about Twilio configuration/connection."""
        try:
            diag = await self.twilio_client.test_connection()
            return {
                "status": "ok" if diag.get("ok") else "error",
                "provider": self.provider,
                "details": diag,
            }
        except Exception as exc:
            logger.exception("test_connection failed: %s", exc)
            return {"status": "error", "provider": self.provider, "error": str(exc)}
