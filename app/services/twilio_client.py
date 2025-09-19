# app/services/twilio_client.py
"""
Twilio client wrapper - Twilio (sync) client but returns structured primitives.
"""
import os
import logging
from typing import Dict, Any, List, Optional

from twilio.rest import Client
from twilio.base.exceptions import TwilioException, TwilioRestException
from app.config.settings import settings

logger = logging.getLogger(__name__)


class TwilioClient:

    def __init__(self):
        self._client = None
        self.from_number = settings.twilio_phone_number
        self._initialize_client()

    @property
    def client(self):
        """Public compatibility alias - some code expects .client attribute."""
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

    def test_connection(self) -> Dict[str, Any]:
        """Test Twilio connection and return a JSON-serializable dict."""
        if not self._client:
            return {"ok": False, "error": "no_client"}
        try:
            account = self._client.api.accounts(settings.twilio_account_sid).fetch()
            account_info = {
                "friendly_name": getattr(account, "friendly_name", None),
                "sid": getattr(account, "sid", None),
            }
            return {"ok": True, "account": account_info}
        except Exception as exc:
            logger.exception("Twilio test_connection failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def send_whatsapp_message(self, to_phone: str, message: str) -> Dict[str, Any]:
        """Send a WhatsApp text message using Twilio. Returns dict with parsed error on failure."""
        if not self._client or not self.from_number:
            return {"ok": False, "error": "twilio_not_configured"}

        try:
            from_ = (
                f"whatsapp:{self.from_number}"
                if not self.from_number.startswith("whatsapp:")
                else self.from_number
            )
            to_ = self._format_whatsapp_number(to_phone)
            logger.debug("Twilio send: from=%s to=%s", from_, to_)
            msg = self._client.messages.create(body=message, from_=from_, to=to_)
            return {
                "ok": True,
                "details": {
                    "sid": getattr(msg, "sid", None),
                    "status": getattr(msg, "status", None),
                },
            }
        except TwilioRestException as exc:
            # TwilioRestException exposes .code and .msg on some versions
            code = getattr(exc, "code", None)
            status = getattr(exc, "status", None)
            msg_text = str(exc)
            parsed = {
                "ok": False,
                "error": msg_text,
                "twilio_code": code,
                "http_status": status,
            }
            # Friendly hint for the common case 63007
            if code == 63007:
                parsed["hint"] = (
                    "From address is not a registered WhatsApp channel. Use the Twilio WhatsApp sandbox number or register your WhatsApp sender in the Twilio Console."
                )
            logger.warning(
                "TwilioRestException when sending WhatsApp message: %s", parsed
            )
            return parsed
        except Exception as exc:
            logger.exception("Unexpected error sending WhatsApp message: %s", exc)
            return {"ok": False, "error": str(exc)}

    def send_media_message(
        self, to_phone: str, media_urls: List[str], body: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send media via WhatsApp (Twilio). Returns dict."""
        if not self._client or not self.from_number:
            return {"ok": False, "error": "twilio_not_configured"}
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
                "details": {
                    "sid": getattr(msg, "sid", None),
                    "status": getattr(msg, "status", None),
                },
            }
        except TwilioException as exc:
            logger.exception("Twilio media send failed: %s", exc)
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("Error sending media message: %s", exc)
            return {"ok": False, "error": str(exc)}
