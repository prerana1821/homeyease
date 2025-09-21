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
            logger.debug("test_connection: no twilio client configured")
            return {"ok": False, "error": "no_client"}
        try:
            acc = self._client.api.accounts(settings.twilio_account_sid).fetch()
            logger.debug(
                "test_connection: fetched account %s", getattr(acc, "sid", None)
            )
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
            logger.debug("_persist_outgoing: no repo provided, skipping persistence")
            return None

        try:
            # Preferred: repo has proper audit method
            if hasattr(self.repo, "record_outgoing_message"):
                logger.debug(
                    "_persist_outgoing: calling repo.record_outgoing_message user_id=%s to=%s sid=%s",
                    user_id,
                    to_phone,
                    sid,
                )
                return self.repo.record_outgoing_message(
                    user_id=user_id,
                    to_phone=to_phone,
                    body=body,
                    twilio_sid=sid,
                    status=status,
                    raw_response=raw,
                )

            # Fallback: use sync wrapper
            if hasattr(self.repo, "create_session_sync"):
                logger.debug(
                    "_persist_outgoing: using repo.create_session_sync fallback"
                )
                return self.repo.create_session_sync(user_id, "outgoing_message", body)

            logger.warning("_persist_outgoing: no persistence method found on repo")
        except Exception as exc:
            logger.exception(
                "Failed to persist outgoing message to repo (non-fatal): %s", exc
            )
        return None

    def _update_user_last_active(self, user_id: Optional[int]):
        if not self.repo or not user_id:
            logger.debug("_update_user_last_active: no repo or no user_id; skipping")
            return
        try:
            if hasattr(self.repo, "update_user_last_active"):
                logger.debug(
                    "_update_user_last_active: calling repo.update_user_last_active(%s)",
                    user_id,
                )
                return self.repo.update_user_last_active(user_id)
            # fallback: upsert_user_onboarding with last_active to avoid needing a specific method
            if hasattr(self.repo, "upsert_user_onboarding"):
                logger.debug(
                    "_update_user_last_active: falling back to repo.upsert_user_onboarding"
                )
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
        logger.info(
            "send_whatsapp_message: to=%s user_id=%s persist=%s",
            to_phone,
            user_id,
            persist,
        )
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
                logger.info(
                    "Twilio send succeeded attempt=%s sid=%s status=%s",
                    attempt,
                    sid,
                    status,
                )
                # persist outgoing message
                if persist:
                    try:
                        self._persist_outgoing(
                            user_id=user_id,
                            to_phone=to_phone,
                            body=message,
                            sid=sid,
                            status=status,
                            raw=raw,
                        )
                    except Exception:
                        logger.exception(
                            "Persistence of outgoing message raised (non-fatal)."
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
                        try:
                            self._persist_outgoing(
                                user_id=user_id,
                                to_phone=to_phone,
                                body=message,
                                sid=None,
                                status=f"error:{code}",
                                raw={"error": msg_text},
                            )
                        except Exception:
                            logger.exception(
                                "Failed to persist outgoing error record (non-fatal)."
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
            sleep_for = self.retry_backoff * (2 ** (attempt - 1))
            logger.debug("Backing off for %.3fs before next attempt", sleep_for)
            time.sleep(sleep_for)

        # exhausted retries
        meta.update(
            {
                "ok": False,
                "error": "exhausted_retries",
                "last_error": str(last_exc) if last_exc else None,
            }
        )
        logger.error(
            "send_whatsapp_message exhausted retries to=%s last_error=%s",
            to_phone,
            meta.get("last_error"),
        )
        # persist final failure record if requested
        if persist:
            try:
                self._persist_outgoing(
                    user_id=user_id,
                    to_phone=to_phone,
                    body=message,
                    sid=None,
                    status="exhausted_retries",
                    raw={"last_error": str(last_exc)},
                )
            except Exception:
                logger.exception(
                    "Failed to persist final exhausted_retries record (non-fatal)."
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
        logger.info(
            "send_media_message: to=%s user_id=%s media_count=%s",
            to_phone,
            user_id,
            len(media_urls),
        )
        if not self._client or not self.from_number:
            logger.warning("send_media_message: twilio not configured")
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
            logger.info("send_media_message succeeded sid=%s status=%s", sid, status)
            if persist:
                try:
                    self._persist_outgoing(
                        user_id=user_id,
                        to_phone=to_phone,
                        body=body or "",
                        sid=sid,
                        status=status,
                        raw=raw,
                    )
                except Exception:
                    logger.exception("Failed to persist outgoing media (non-fatal).")
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
