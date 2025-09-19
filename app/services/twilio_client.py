# app/services/twilio_client.py
"""
Twilio client wrapper - Twilio (sync) client but returns structured primitives.
Optional `repo` dependency: duck-typed object with:
  - record_outgoing_message(user_id, to_phone, body, twilio_sid, status, raw_response) -> dict
  - mark_incoming_message_processed(message_sid, metadata) -> dict
  - update_user_last_active(user_id) -> dict
If repo is not provided, the TwilioClient still works—just won't persist messaging events.
"""
import logging
import time
from typing import Dict, Any, List, Optional, Union, Callable

from twilio.rest import Client
from twilio.base.exceptions import TwilioException, TwilioRestException

from app.config.settings import settings

logger = logging.getLogger(__name__)


class TwilioClient:

    def __init__(
        self,
        repo: Optional[Any] = None,
        max_retries: int = 2,
        retry_backoff: float = 0.3,
    ):
        """
        repo (optional): object implementing the persistence methods described above.
        max_retries: number of times to retry transient Twilio errors
        retry_backoff: base seconds to wait between retries (exponential backoff applied)
        """
        self._client = None
        self.from_number = settings.twilio_phone_number
        self.repo = repo
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._initialize_client()

    @property
    def client(self):
        return self._client

    def _initialize_client(self) -> None:
        try:
            sid = settings.twilio_account_sid
            token = settings.twilio_auth_token
            if not sid or not token:
                logger.warning("Twilio credentials not provided - client disabled")
                self._client = None
                return
            self._client = Client(sid, token)
            logger.info("Twilio client initialized")
        except Exception as exc:
            logger.exception("Failed to initialize Twilio client: %s", exc)
            self._client = None

    def _format_whatsapp_number(self, phone: str) -> str:
        phone_clean = phone.strip()
        return (
            phone_clean
            if phone_clean.startswith("whatsapp:")
            else f"whatsapp:{phone_clean}"
        )

    def test_connection(self) -> Dict[str, Any]:
        if not self._client:
            return {"ok": False, "error": "no_client"}
        try:
            acc = self._client.api.accounts(settings.twilio_account_sid).fetch()
            return {
                "ok": True,
                "account": {
                    "friendly_name": getattr(acc, "friendly_name", None),
                    "sid": getattr(acc, "sid", None),
                },
            }
        except Exception as exc:
            logger.exception("Twilio test_connection failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def _persist_outgoing(
        self,
        user_id: Optional[int],
        to_phone: str,
        body: str,
        sid: Optional[str],
        status: Optional[str],
        raw: Any,
    ):
        """Attempt to record outgoing message in DB via repo if available. Non-fatal."""
        if not self.repo:
            return None
        try:
            # repo should handle transactions / auditing
            if hasattr(self.repo, "record_outgoing_message"):
                return self.repo.record_outgoing_message(
                    user_id=user_id,
                    to_phone=to_phone,
                    body=body,
                    twilio_sid=sid,
                    status=status,
                    raw_response=raw,
                )
            # fallback to session creation if user doesn't want outgoing table:
            if hasattr(self.repo, "create_session"):
                # treat outgoing message as a session entry with prompt empty and response=body
                return self.repo.create_session(
                    user_id=user_id, prompt="outgoing_message", response=body
                )
        except Exception:
            logger.exception("Failed to persist outgoing message to repo (non-fatal).")
        return None

    def _update_user_last_active(self, user_id: Optional[int]):
        if not self.repo or not user_id:
            return
        try:
            if hasattr(self.repo, "update_user_last_active"):
                return self.repo.update_user_last_active(user_id)
            # fallback: upsert_user_onboarding with last_active to avoid needing a specific method
            if hasattr(self.repo, "upsert_user_onboarding"):
                return self.repo.upsert_user_onboarding(
                    user_id, {"last_active": None}, action="outgoing_message"
                )
        except Exception:
            logger.exception("Failed to update user's last_active (non-fatal).")

    def send_whatsapp_message(
        self,
        to_phone: str,
        message: str,
        user_id: Optional[int] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """
        Send a text message to WhatsApp via Twilio.
        - user_id: optional DB user id for auditing
        - persist: whether to use repo to store outgoing message (if repo provided)
        Returns: dict with `ok` bool and detailed diagnostics
        """
        meta: Dict[str, Any] = {
            "ok": False,
            "action": "send_whatsapp_message",
            "to": to_phone,
            "attempts": 0,
        }
        if not self._client or not self.from_number:
            meta.update({"error": "twilio_not_configured"})
            logger.warning(
                "Twilio not configured when trying to send message to %s", to_phone
            )
            return meta

        from_ = (
            self.from_number
            if self.from_number.startswith("whatsapp:")
            else f"whatsapp:{self.from_number}"
        )
        to_ = self._format_whatsapp_number(to_phone)

        last_exc: Optional[Exception] = None
        for attempt in range(
            1, self.max_retries + 2
        ):  # e.g. max_retries=2 -> attempts 1..3
            meta["attempts"] = attempt
            try:
                logger.debug(
                    "Twilio send attempt=%s from=%s to=%s", attempt, from_, to_
                )
                msg = self._client.messages.create(body=message, from_=from_, to=to_)
                sid = getattr(msg, "sid", None)
                status = getattr(msg, "status", None)
                raw = {"sid": sid, "status": status}
                meta.update(
                    {"ok": True, "twilio_sid": sid, "twilio_status": status, "raw": raw}
                )
                # persist outgoing message
                if persist:
                    self._persist_outgoing(
                        user_id=user_id,
                        to_phone=to_phone,
                        body=message,
                        sid=sid,
                        status=status,
                        raw=raw,
                    )
                    self._update_user_last_active(user_id)
                return meta
            except TwilioRestException as exc:
                # Twilio-specific REST errors (400s, permissions, etc.)
                code = getattr(exc, "code", None)
                status = getattr(exc, "status", None)
                msg_text = str(exc)
                meta.update(
                    {
                        "ok": False,
                        "error": msg_text,
                        "twilio_code": code,
                        "http_status": status,
                    }
                )
                logger.warning("TwilioRestException sending WhatsApp message: %s", meta)
                # Some Twilio codes are not transient — bail early (e.g., 21614 invalid number)
                non_transient_codes = {21614, 63007}  # expand as you observe cases
                if code in non_transient_codes:
                    # persist failure if desired
                    if persist:
                        self._persist_outgoing(
                            user_id=user_id,
                            to_phone=to_phone,
                            body=message,
                            sid=None,
                            status=f"error:{code}",
                            raw={"error": msg_text},
                        )
                    return meta
                last_exc = exc
            except TwilioException as exc:
                # Twilio SDK generic errors; can retry
                last_exc = exc
                logger.warning(
                    "TwilioException (transient) sending message attempt=%s err=%s",
                    attempt,
                    exc,
                )
            except Exception as exc:
                last_exc = exc
                logger.exception(
                    "Unexpected error sending WhatsApp message on attempt=%s: %s",
                    attempt,
                    exc,
                )

            # backoff before retry (exponential)
            time.sleep(self.retry_backoff * (2 ** (attempt - 1)))

        # exhausted retries
        meta.update(
            {
                "ok": False,
                "error": "exhausted_retries",
                "last_error": str(last_exc) if last_exc else None,
            }
        )
        # persist final failure record if requested
        if persist:
            self._persist_outgoing(
                user_id=user_id,
                to_phone=to_phone,
                body=message,
                sid=None,
                status="exhausted_retries",
                raw={"last_error": str(last_exc)},
            )
        return meta

    def send_media_message(
        self,
        to_phone: str,
        media_urls: List[str],
        body: Optional[str] = None,
        user_id: Optional[int] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        if not self._client or not self.from_number:
            return {"ok": False, "error": "twilio_not_configured"}
        from_ = (
            self.from_number
            if self.from_number.startswith("whatsapp:")
            else f"whatsapp:{self.from_number}"
        )
        to_ = self._format_whatsapp_number(to_phone)

        try:
            msg = self._client.messages.create(
                body=body or "", from_=from_, to=to_, media_url=media_urls
            )
            sid = getattr(msg, "sid", None)
            status = getattr(msg, "status", None)
            raw = {"sid": sid, "status": status}
            if persist:
                self._persist_outgoing(
                    user_id=user_id,
                    to_phone=to_phone,
                    body=body or "",
                    sid=sid,
                    status=status,
                    raw=raw,
                )
                self._update_user_last_active(user_id)
            return {"ok": True, "details": {"sid": sid, "status": status}, "raw": raw}
        except TwilioException as exc:
            logger.exception("Twilio media send failed: %s", exc)
            if persist:
                self._persist_outgoing(
                    user_id=user_id,
                    to_phone=to_phone,
                    body=body or "",
                    sid=None,
                    status="error_twilio_exception",
                    raw={"error": str(exc)},
                )
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("Error sending media message: %s", exc)
            if persist:
                self._persist_outgoing(
                    user_id=user_id,
                    to_phone=to_phone,
                    body=body or "",
                    sid=None,
                    status="error_exception",
                    raw={"error": str(exc)},
                )
            return {"ok": False, "error": str(exc)}
