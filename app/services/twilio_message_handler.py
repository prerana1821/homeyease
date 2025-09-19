# app/services/twilio_message_handler.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.services.twilio_client import TwilioClient
from app.config.settings import settings

logger = logging.getLogger(__name__)

# canonical response shape used by this module
# {
#   "ok": bool,
#   "provider": "twilio_whatsapp",
#   "action": "send_text" | "send_media" | "test_connection" | ...,
#   "details": {...},
#   "error": Optional[str],
#   "diagnostics": {...}
# }


class TwilioMessageHandler:

    def __init__(
        self, twilio_client: Optional[TwilioClient] = None, repo: Optional[Repo] = None
    ):
        """
        repo: optional DB repo implementing:
          - record_outgoing_message(user_id, to_phone, body, twilio_sid, status, raw_response)
          - update_user_last_active(user_id)
        """
        self.twilio_client = twilio_client or TwilioClient(repo=repo)
        self.repo = repo
        self.provider = "twilio_whatsapp"
        self.configured = bool(
            settings.twilio_account_sid
            and settings.twilio_auth_token
            and settings.twilio_phone_number
        )
        logger.debug("TwilioMessageHandler configured=%s", self.configured)

    async def _run_sync(self, fn, *args, **kwargs):
        """
        Run blocking sync function off the event loop in a thread.
        Uses asyncio.to_thread for clarity (Python 3.9+); falls back to run_in_executor if unavailable.
        """
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except AttributeError:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def send_text(
        self,
        to_phone: str,
        body: str,
        user_id: Optional[int] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """
        Send a WhatsApp text message.
        - user_id: optional DB user id to link outgoing event and update last_active.
        - persist: whether to persist outgoing event via repo (if repo passed into TwilioClient)
        Returns canonical response dict.
        """
        action = "send_text"
        if not self.configured:
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": "twilio_not_configured",
                "details": {},
                "diagnostics": {},
            }

        try:
            # run the sync Twilio call in a thread
            resp = await self._run_sync(
                self.twilio_client.send_whatsapp_message,
                to_phone,
                body,
                user_id if hasattr(self.twilio_client, "repo") else None,
                persist,
            )
            # TwilioClient returns dicts with 'ok' and diagnostics - normalize into canonical shape
            ok = bool(resp.get("ok"))
            details = resp.get("details") or {
                k: v for k, v in resp.items() if k not in ("ok", "error")
            }
            error = resp.get("error")
            diagnostics = {
                k: v for k, v in resp.items() if k not in ("ok", "details", "error")
            }
            return {
                "ok": ok,
                "provider": self.provider,
                "action": action,
                "details": details or {},
                "error": error,
                "diagnostics": diagnostics,
            }
        except Exception as exc:
            logger.exception("send_text failed to %s: %s", to_phone, exc)
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "details": {},
                "error": str(exc),
                "diagnostics": {},
            }

    async def send_media(
        self,
        to_phone: str,
        media_urls: List[str],
        body: Optional[str] = None,
        user_id: Optional[int] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """
        Send a media message. Runs Twilio client off the loop.
        """
        action = "send_media"
        if not self.configured:
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": "twilio_not_configured",
                "details": {},
                "diagnostics": {},
            }

        try:
            resp = await self._run_sync(
                self.twilio_client.send_media_message,
                to_phone,
                media_urls,
                body,
                user_id if hasattr(self.twilio_client, "repo") else None,
                persist,
            )
            # TwilioClient earlier returned {"ok": True/False, "details": {...}, ...}
            ok = bool(resp.get("ok"))
            details = resp.get("details") or resp.get("raw") or {}
            error = resp.get("error")
            diagnostics = {
                k: v for k, v in resp.items() if k not in ("ok", "details", "error")
            }
            return {
                "ok": ok,
                "provider": self.provider,
                "action": action,
                "details": details,
                "error": error,
                "diagnostics": diagnostics,
            }
        except Exception as exc:
            logger.exception("send_media error to %s: %s", to_phone, exc)
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "details": {},
                "error": str(exc),
                "diagnostics": {},
            }

    async def send_interactive(
        self,
        to_phone: str,
        interactive_payload: Dict[str, Any],
        user_id: Optional[int] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """
        Send an interactive message if Twilio client supports it.
        Interactive messages often require pre-approved templates on the WhatsApp Business API.
        """
        action = "send_interactive"
        if not self.configured:
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": "twilio_not_configured",
                "details": {},
                "diagnostics": {},
            }

        if not hasattr(self.twilio_client, "send_whatsapp_interactive"):
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "error": "interactive_not_supported",
                "details": {},
                "diagnostics": {},
            }

        try:
            resp = await self._run_sync(
                self.twilio_client.send_whatsapp_interactive,
                to_phone,
                interactive_payload,
                user_id if hasattr(self.twilio_client, "repo") else None,
                persist,
            )
            ok = bool(resp.get("ok"))
            details = resp.get("details", {})
            error = resp.get("error")
            diagnostics = {
                k: v for k, v in resp.items() if k not in ("ok", "details", "error")
            }
            return {
                "ok": ok,
                "provider": self.provider,
                "action": action,
                "details": details,
                "error": error,
                "diagnostics": diagnostics,
            }
        except Exception as exc:
            logger.exception("send_interactive failed to %s: %s", to_phone, exc)
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "details": {},
                "error": str(exc),
                "diagnostics": {},
            }

    async def test_connection(self) -> Dict[str, Any]:
        action = "test_connection"
        try:
            resp = await self._run_sync(self.twilio_client.test_connection)
            ok = bool(resp.get("ok"))
            return {
                "ok": ok,
                "provider": self.provider,
                "action": action,
                "details": resp if ok else {},
                "error": None if ok else resp.get("error"),
                "diagnostics": resp,
            }
        except Exception as exc:
            logger.exception("test_connection failed: %s", exc)
            return {
                "ok": False,
                "provider": self.provider,
                "action": action,
                "details": {},
                "error": str(exc),
                "diagnostics": {},
            }
