"""
Twilio WhatsApp client wrapper.
- Wraps twilio.rest.Client but returns structured dicts.
- Exposes async-safe helpers (offload blocking calls to executor).
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional

from twilio.rest import Client
from twilio.base.exceptions import TwilioException, TwilioRestException
from app.config.settings import settings

logger = logging.getLogger(__name__)


class TwilioClient:

    def __init__(self):
        self._client = None
        self.from_number = settings.twilio_phone_number
        self.provider = "twilio_whatsapp"
        self._initialize_client()
        self.configured = bool(
            settings.twilio_account_sid
            and settings.twilio_auth_token
            and settings.twilio_phone_number
        )

    @property
    def client(self):
        """Compatibility alias for the raw Twilio SDK client."""
        return self._client

    def _initialize_client(self) -> None:
        try:
            sid = settings.twilio_account_sid
            token = settings.twilio_auth_token
            if not sid or not token:
                logger.warning("Twilio credentials not available")
                self._client = None
                return
            self._client = Client(sid, token)
            logger.info("Twilio client initialized")
        except Exception as exc:
            logger.exception("Failed to initialize Twilio client: %s", exc)
            self._client = None

    def _format_whatsapp_number(self, phone: str) -> str:
        """Return a string like 'whatsapp:+1234567890'"""
        phone_clean = phone.strip()
        if not phone_clean.startswith("whatsapp:"):
            phone_clean = f"whatsapp:{phone_clean}"
        return phone_clean

    # -------------------------
    # Connection check
    # -------------------------
    def test_connection(self) -> Dict[str, Any]:
        if not self._client:
            return {"ok": False, "error": "no_client", "provider": self.provider}
        try:
            account = self._client.api.accounts(settings.twilio_account_sid).fetch()
            account_info = {
                "friendly_name": getattr(account, "friendly_name", None),
                "sid": getattr(account, "sid", None),
            }
            return {
                "ok": True,
                "provider": self.provider,
                "details": {"account": account_info},
            }
        except Exception as exc:
            logger.exception("Twilio test_connection failed: %s", exc)
            return {"ok": False, "provider": self.provider, "error": str(exc)}

    async def async_test_connection(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.test_connection)

    # -------------------------
    # Message sending
    # -------------------------
    def send_whatsapp_message(self, to_phone: str, message: str) -> Dict[str, Any]:
        if not self._client or not self.from_number:
            return {
                "ok": False,
                "provider": self.provider,
                "error": "twilio_not_configured",
            }
        try:
            from_ = (
                f"whatsapp:{self.from_number}"
                if not self.from_number.startswith("whatsapp:")
                else self.from_number
            )
            to_ = self._format_whatsapp_number(to_phone)
            logger.debug("Twilio send text: from=%s to=%s", from_, to_)
            msg = self._client.messages.create(body=message, from_=from_, to=to_)
            return {
                "ok": True,
                "provider": self.provider,
                "details": {
                    "sid": getattr(msg, "sid", None),
                    "status": getattr(msg, "status", None),
                },
            }
        except TwilioRestException as exc:
            code = getattr(exc, "code", None)
            status = getattr(exc, "status", None)
            parsed = {
                "ok": False,
                "provider": self.provider,
                "error": str(exc),
                "twilio_code": code,
                "http_status": status,
            }
            if code == 63007:
                parsed["hint"] = (
                    "From address is not a registered WhatsApp channel. Use the Twilio WhatsApp sandbox number or register your sender."
                )
            logger.warning("TwilioRestException send_whatsapp_message: %s", parsed)
            return parsed
        except Exception as exc:
            logger.exception("Unexpected error sending WhatsApp message: %s", exc)
            return {"ok": False, "provider": self.provider, "error": str(exc)}

    async def async_send_text(self, to_phone: str, body: str) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.send_whatsapp_message(to_phone, body)
        )

    def send_media_message(
        self, to_phone: str, media_urls: List[str], body: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self._client or not self.from_number:
            return {
                "ok": False,
                "provider": self.provider,
                "error": "twilio_not_configured",
            }
        try:
            from_ = (
                f"whatsapp:{self.from_number}"
                if not self.from_number.startswith("whatsapp:")
                else self.from_number
            )
            to_ = self._format_whatsapp_number(to_phone)
            msg = self._client.messages.create(
                body=body or "", from_=from_, to=to_, media_url=media_urls
            )
            return {
                "ok": True,
                "provider": self.provider,
                "details": {
                    "sid": getattr(msg, "sid", None),
                    "status": getattr(msg, "status", None),
                },
            }
        except TwilioException as exc:
            logger.exception("Twilio media send failed: %s", exc)
            return {"ok": False, "provider": self.provider, "error": str(exc)}
        except Exception as exc:
            logger.exception("Error sending media message: %s", exc)
            return {"ok": False, "provider": self.provider, "error": str(exc)}

    async def async_send_media(
        self, to_phone: str, media_urls: List[str], body: Optional[str] = None
    ) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.send_media_message(to_phone, media_urls, body)
        )

    # -------------------------
    # Interactive (optional)
    # -------------------------
    def send_whatsapp_interactive(
        self, to_phone: str, interactive_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Only works if Twilio client/number is approved for interactive templates.
        Stub here so higher-level code can check.
        """
        return {
            "ok": False,
            "provider": self.provider,
            "error": "interactive_not_supported",
        }

    async def async_send_interactive(
        self, to_phone: str, interactive_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.send_whatsapp_interactive(to_phone, interactive_payload)
        )
