import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.services.twilio_client import TwilioClient
from app.config.settings import settings

logger = logging.getLogger(__name__)


class TwilioMessageHandler:

    def __init__(
        self, twilio_client: Optional[TwilioClient] = None, repo: Optional[Any] = None
    ):
        self.twilio_client = twilio_client or TwilioClient(repo=repo)
        self.repo = repo
        self.provider = "twilio_whatsapp"
        self.configured = bool(
            settings.twilio_account_sid
            and settings.twilio_auth_token
            and settings.twilio_phone_number
        )
        logger.info(
            "TwilioMessageHandler initialized configured=%s repo=%s",
            self.configured,
            "present" if repo else "none",
        )

    async def _run_sync(self, fn, *args, **kwargs):
        logger.debug("Running sync function %s in thread", fn.__name__)
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except AttributeError:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def send_text(
        self, to_phone, body, user_id=None, persist=True
    ) -> Dict[str, Any]:
        action = "send_text"
        logger.info("Preparing to send_text to=%s body=%s", to_phone, body[:80])
        if not self.configured:
            logger.error("Twilio not configured, cannot send_text")
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": "twilio_not_configured",
            }
        try:
            resp = await self._run_sync(
                self.twilio_client.send_whatsapp_message,
                to_phone,
                body,
                user_id,
                persist,
            )
            logger.debug("Raw TwilioClient send_text response: %s", resp)
            return {
                "ok": bool(resp.get("ok")),
                "provider": self.provider,
                "action": action,
                "details": resp.get("details")
                or {k: v for k, v in resp.items() if k not in ("ok", "error")},
                "error": resp.get("error"),
                "diagnostics": resp,
            }
        except Exception as exc:
            logger.exception("send_text failed to %s: %s", to_phone, exc)
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": str(exc),
            }

    async def send_media(
        self, to_phone, media_urls, body=None, user_id=None, persist=True
    ) -> Dict[str, Any]:
        action = "send_media"
        logger.info(
            "Preparing to send_media to=%s media_count=%s", to_phone, len(media_urls)
        )
        if not self.configured:
            logger.error("Twilio not configured, cannot send_media")
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": "twilio_not_configured",
            }
        try:
            resp = await self._run_sync(
                self.twilio_client.send_media_message,
                to_phone,
                media_urls,
                body,
                user_id,
                persist,
            )
            logger.debug("Raw TwilioClient send_media response: %s", resp)
            return {
                "ok": bool(resp.get("ok")),
                "provider": self.provider,
                "action": action,
                "details": resp.get("details") or resp.get("raw") or {},
                "error": resp.get("error"),
                "diagnostics": resp,
            }
        except Exception as exc:
            logger.exception("send_media failed to %s: %s", to_phone, exc)
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": str(exc),
            }

    async def send_interactive(
        self, to_phone, payload, user_id=None, persist=True
    ) -> Dict[str, Any]:
        action = "send_interactive"
        logger.info("Preparing to send_interactive to=%s", to_phone)
        if not self.configured:
            logger.error("Twilio not configured, cannot send_interactive")
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": "twilio_not_configured",
            }
        if not hasattr(self.twilio_client, "send_whatsapp_interactive"):
            logger.warning("Interactive send not supported by TwilioClient")
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": "interactive_not_supported",
            }
        try:
            resp = await self._run_sync(
                self.twilio_client.send_whatsapp_interactive,
                to_phone,
                payload,
                user_id,
                persist,
            )
            logger.debug("Raw TwilioClient send_interactive response: %s", resp)
            return {
                "ok": bool(resp.get("ok")),
                "provider": self.provider,
                "action": action,
                "details": resp.get("details", {}),
                "error": resp.get("error"),
                "diagnostics": resp,
            }
        except Exception as exc:
            logger.exception("send_interactive failed to %s: %s", to_phone, exc)
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": str(exc),
            }

    async def test_connection(self) -> Dict[str, Any]:
        action = "test_connection"
        logger.info("Testing TwilioMessageHandler connection...")
        try:
            resp = await self._run_sync(self.twilio_client.test_connection)
            logger.debug("Raw TwilioClient test_connection response: %s", resp)
            return {
                "ok": bool(resp.get("ok")),
                "provider": self.provider,
                "action": action,
                "details": resp if resp.get("ok") else {},
                "error": None if resp.get("ok") else resp.get("error"),
                "diagnostics": resp,
            }
        except Exception as exc:
            logger.exception("test_connection failed: %s", exc)
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": str(exc),
            }
