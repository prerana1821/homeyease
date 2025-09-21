# app/api/twilio_webhook.py
"""
Twilio webhook endpoints for receiving WhatsApp messages via Twilio only.

- Defensive and compatible with UserService/standardized return shapes.
- Returns TwiML (empty) to Twilio by default.
- If ?debug=1 is added, returns verbose JSON diagnostics for local testing.
"""
from __future__ import annotations

import collections
import datetime
import logging
import time
from typing import Any, Deque, Dict, List, Optional

import asyncio
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, Response

from app.services.message_handler import MessageHandler
from app.config.supabase import supabase_client
from app.services.twilio_client import TwilioClient

logger = logging.getLogger(__name__)
router = APIRouter()

# singletons (keep simple for now)
message_handler = MessageHandler()
twilio_client = TwilioClient()


# In-memory deduper for quick Twilio retry protection
class InMemoryDeduper:

    def __init__(self, max_entries: int = 4096) -> None:
        self._max_entries = int(max_entries)
        self._queue: Deque[str] = collections.deque()
        self._set = set()

    def add(self, key: str) -> bool:
        if key in self._set:
            return False
        self._queue.append(key)
        self._set.add(key)
        if len(self._queue) > self._max_entries:
            old = self._queue.popleft()
            self._set.discard(old)
        return True

    def contains(self, key: str) -> bool:
        return key in self._set

    def count(self) -> int:
        return len(self._set)

    @property
    def capacity(self) -> int:
        return self._max_entries


deduper = InMemoryDeduper()


# -------------------------
# Helpers
# -------------------------
def _clean_phone(phone: Optional[str]) -> str:
    if not phone:
        return ""
    s = str(phone).strip()
    # Remove whatsapp: prefix and stray tokens
    s = s.replace("whatsapp:", "").replace("whatsapp", "").strip()
    s = s.replace(" ", "")
    # Add + if digits only (E.164 expectation)
    if s and not s.startswith("+") and s.isdigit():
        s = f"+{s}"
    return s


def _guess_mime_from_url(url: str) -> str:
    if not url:
        return "application/octet-stream"
    u = url.lower()
    if u.endswith(".jpg") or u.endswith(".jpeg"):
        return "image/jpeg"
    if u.endswith(".png"):
        return "image/png"
    if u.endswith(".gif"):
        return "image/gif"
    if u.endswith(".mp4") or u.endswith(".mov"):
        return "video/mp4"
    if u.endswith(".mp3") or u.endswith(".wav"):
        return "audio/mpeg"
    return "application/octet-stream"


def _build_internal_message_from_twilio_form(
    form: Dict[str, Any],
    declared_num_media: int = 0,
    media_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Convert Twilio form data into an internal WhatsApp-like message dict."""
    from_phone = _clean_phone(form.get("From") or form.get("from") or "")
    msg_id = str(form.get("MessageSid") or f"tw-{int(time.time() * 1000)}")
    body_text = str(form.get("Body") or "").strip()
    try:
        num_media = int(declared_num_media or int(form.get("NumMedia") or 0))
    except Exception:
        num_media = 0

    message: Dict[str, Any] = {
        "from": from_phone,
        "id": msg_id,
        "timestamp": str(int(time.time())),
        "type": "text",
        "text": {"body": body_text} if body_text else None,
        "raw": {k: form.get(k) for k in form.keys()},
    }

    urls = media_urls or []
    if not urls and num_media > 0:
        for i in range(num_media):
            key = f"MediaUrl{i}"
            if key in form:
                urls.append(str(form.get(key)))

    if urls:
        mime = _guess_mime_from_url(urls[0])
        if not body_text:
            message.pop("text", None)
        if mime.startswith("image/"):
            message["type"] = "image"
            message["image"] = {"urls": urls, "mime_type": mime, "count": len(urls)}
        elif mime.startswith("video/"):
            message["type"] = "video"
            message["media"] = {"urls": urls, "mime_type": mime, "count": len(urls)}
        else:
            message["type"] = "media"
            message["media"] = {"urls": urls, "mime_type": mime, "count": len(urls)}

    return message


def _make_json_serializable(obj: Any) -> Any:
    """Convert objects to JSON-safe primitives for debug output."""
    import datetime as _dt

    if obj is None or isinstance(obj, (str, bool, int, float)):
        return obj
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_make_json_serializable(v) for v in obj]
    # handle Supabase-like objects with .data
    if hasattr(obj, "data") or hasattr(obj, "status_code") or hasattr(obj, "error"):
        try:
            return {
                "data": getattr(obj, "data", None),
                "status_code": getattr(obj, "status_code", None),
                "error": getattr(obj, "error", None),
            }
        except Exception:
            pass
    try:
        return str(obj)
    except Exception:
        return "<unserializable>"


# -------------------------
# Webhook
# -------------------------
@router.post("/whatsapp")
async def handle_whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    To: str = Form(...),
    Body: Optional[str] = Form(None),
    MessageSid: Optional[str] = Form(None),
    NumMedia: Optional[str] = Form("0"),
    debug: Optional[bool] = False,
) -> Response:
    """
    Twilio webhook for WhatsApp.

    Debug mode (?debug=1) returns detailed JSON diagnostics.
    Normal mode returns minimal TwiML empty <Response/> for Twilio.
    """
    start_ts = time.time()
    diagnostics: Dict[str, Any] = {"steps": [], "errors": []}

    from app.services.user_service import UserService  # local import to avoid cycles

    try:
        form = await request.form()
        form = dict(form)
        logger.info("Received Twilio webhook; form keys=%s", list(form.keys()))
        diagnostics["steps"].append("form_received")

        # parse NumMedia defensively (prefer explicit param)
        try:
            num_media = int(NumMedia or form.get("NumMedia") or 0)
        except Exception:
            num_media = 0
            logger.debug("Failed to parse NumMedia; defaulting to 0")
        diagnostics["num_media"] = num_media

        # collect media urls from form if present
        media_urls: List[str] = []
        if num_media > 0:
            for i in range(num_media):
                key = f"MediaUrl{i}"
                if key in form:
                    media_urls.append(str(form.get(key)))
            logger.debug("Detected media URLs: %d", len(media_urls))
        diagnostics["media_urls_count"] = len(media_urls)

        # determine message sid
        message_sid = MessageSid or str(form.get("MessageSid") or "")
        if not message_sid:
            message_sid = f"tw-{int(time.time() * 1000)}"
            logger.debug("No MessageSid provided; synthesized id=%s", message_sid)
        diagnostics["message_sid"] = message_sid

        # dedupe via in-memory first
        if deduper.contains(message_sid):
            logger.info(
                "Duplicate webhook detected via in-memory deduper: %s", message_sid
            )
            diagnostics["steps"].append("deduplicated_in_memory")
            if debug:
                return JSONResponse(
                    {
                        "status": "ignored",
                        "reason": "duplicate_in_memory",
                        "diagnostics": diagnostics,
                    }
                )
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml",
            )

        # convert to internal message shape
        incoming_message = _build_internal_message_from_twilio_form(
            form, declared_num_media=num_media, media_urls=media_urls
        )
        logger.info(
            "Converted incoming message id=%s from=%s type=%s",
            incoming_message.get("id"),
            incoming_message.get("from"),
            incoming_message.get("type"),
        )
        diagnostics["steps"].append("converted_to_internal")
        diagnostics["incoming_preview"] = {
            "id": incoming_message.get("id"),
            "from": incoming_message.get("from"),
            "type": incoming_message.get("type"),
        }

        # Persist incoming message for idempotency
        user_service = UserService()

        phone_clean = _clean_phone(form.get("From") or From)
        diagnostics["resolved_from"] = phone_clean

        # Try to resolve user BEFORE inserting (best-effort)
        resolved_user_id: Optional[int] = None
        try:
            user_res = await user_service.get_user_by_whatsapp_id(phone_clean)
            # user_res follows standardized shape: {"ok": bool, "data": ...}
            if user_res.get("ok") and user_res.get("data"):
                resolved_user = user_res.get("data")
                resolved_user_id = resolved_user.get("id")
                diagnostics["resolved_user_id"] = resolved_user_id
                logger.debug(
                    "Resolved user for phone=%s id=%s", phone_clean, resolved_user_id
                )
            else:
                diagnostics["resolved_user_id"] = None
                logger.debug("No user found for phone=%s", phone_clean)
        except Exception as exc:
            resolved_user_id = None
            logger.exception("Error resolving user by phone %s: %s", phone_clean, exc)
            diagnostics["errors"].append(f"user_resolve_error:{str(exc)}")

        # Record incoming message (idempotent)
        try:
            rec = await user_service.record_incoming_message(
                message_sid=message_sid,
                user_id=resolved_user_id,
                from_phone=phone_clean,
                raw_payload=incoming_message.get("raw") or incoming_message,
            )
            diagnostics["incoming_record_raw"] = _make_json_serializable(
                rec.get("diagnostics") if isinstance(rec, dict) else rec
            )
        except Exception as exc:
            logger.exception("Failed to record incoming_message: %s", exc)
            diagnostics["errors"].append(f"record_incoming_failed:{str(exc)}")
            rec = {"ok": False}

        # Interpret returned record shape:
        # user_service.record_incoming_message returns normalized {"ok": bool, "data": <row> or list}
        existing_row = None
        processed_flag = False
        if rec.get("ok") and rec.get("data"):
            existing_row = rec.get("data")
            # sometimes the SDK returns list of rows, sometimes single row; normalize
            if isinstance(existing_row, list) and existing_row:
                existing_row = existing_row[0]
            if isinstance(existing_row, dict):
                processed_flag = bool(existing_row.get("processed") is True)
        diagnostics["incoming_row_present"] = bool(existing_row)
        diagnostics["incoming_row_processed"] = processed_flag
        logger.info("Incoming message recorded; processed=%s", processed_flag)

        # If DB indicates it was already processed, short-circuit (safe)
        if existing_row and processed_flag:
            diagnostics["steps"].append("short_circuit_db_already_processed")
            if debug:
                diagnostics["elapsed_seconds"] = round(time.time() - start_ts, 3)
                return JSONResponse(
                    {
                        "status": "ignored",
                        "reason": "already_processed",
                        "message_sid": message_sid,
                        "diagnostics": diagnostics,
                    }
                )
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml",
            )

        # add to in-memory deduper to prevent immediate reprocessing
        deduper.add(message_sid)
        diagnostics["deduper_count"] = deduper.count()

        # Build webhook payload in the format MessageHandler expects
        webhook_payload = {
            "entry": [
                {
                    "id": "twilio_entry",
                    "changes": [
                        {"field": "messages", "value": {"messages": [incoming_message]}}
                    ],
                }
            ]
        }

        # Dispatch to message handler
        try:
            logger.info(
                "Dispatching payload to MessageHandler.process_webhook sid=%s",
                message_sid,
            )
            proc_res = await message_handler.process_webhook(webhook_payload)
            diagnostics["process_result"] = _make_json_serializable(proc_res)
            diagnostics["steps"].append("processed")
            logger.info(
                "MessageHandler.process_webhook completed for sid=%s", message_sid
            )
        except Exception as exc:
            logger.exception(
                "Error processing webhook payload sid=%s: %s", message_sid, exc
            )
            diagnostics["errors"].append(f"process_webhook_failed:{str(exc)}")
            # Do not mark processed; return TwiML or debug JSON
            if debug:
                diagnostics["elapsed_seconds"] = round(time.time() - start_ts, 3)
                return JSONResponse(
                    {
                        "status": "error",
                        "message_sid": message_sid,
                        "diagnostics": diagnostics,
                    },
                    status_code=500,
                )
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml",
            )

        # Mark incoming processed now that handling succeeded (best-effort)
        try:
            mproc = await user_service.mark_incoming_processed(message_sid)
            diagnostics["incoming_mark_processed"] = _make_json_serializable(mproc)
        except Exception as exc:
            logger.exception(
                "Failed to mark incoming processed for %s: %s", message_sid, exc
            )
            diagnostics["errors"].append(f"mark_incoming_processed_failed:{str(exc)}")

        # Debug response if requested
        if debug:
            elapsed = round(time.time() - start_ts, 3)
            diagnostics["elapsed_seconds"] = elapsed
            return JSONResponse(
                {"status": "ok", "message_sid": message_sid, "diagnostics": diagnostics}
            )

        # Normal Twilio acknowledgement (empty TwiML)
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )

    except Exception as exc:
        logger.exception("Unhandled exception in Twilio webhook: %s", exc)
        diagnostics["errors"].append(str(exc))
        if debug:
            return JSONResponse(
                {
                    "status": "error",
                    "message_sid": locals().get("message_sid", "<unknown>"),
                    "diagnostics": diagnostics,
                },
                status_code=500,
            )
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )


# -------------------------
# Test endpoint
# -------------------------
@router.get("/test")
async def test_twilio_webhook(request: Request):
    """Health & diagnostics for Supabase + Twilio + environment flags."""
    diagnostics: Dict[str, Any] = {}
    start = asyncio.get_running_loop().time()
    diagnostics["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Supabase health (run in executor)
    try:
        loop = asyncio.get_running_loop()
        ok = await asyncio.wait_for(
            loop.run_in_executor(None, supabase_client.health_check), timeout=5.0
        )
        diagnostics["supabase"] = {"healthy": bool(ok)}
    except Exception as exc:
        diagnostics["supabase"] = {"healthy": False, "error": str(exc)}
        logger.exception("Supabase health check failed: %s", exc)

    # Twilio test
    try:
        diag = await asyncio.get_running_loop().run_in_executor(
            None, twilio_client.test_connection
        )
        diagnostics["twilio"] = _make_json_serializable(diag)
    except Exception as exc:
        diagnostics["twilio"] = {"ok": False, "error": str(exc)}
        logger.exception("Twilio test_connection failed: %s", exc)

    diagnostics["env"] = {
        "supabase_url_set": bool(__import__("os").environ.get("SUPABASE_URL")),
        "supabase_key_set": bool(
            __import__("os").environ.get("SUPABASE_SERVICE_ROLE_KEY")
        ),
        "twilio_sid_set": bool(__import__("os").environ.get("TWILIO_ACCOUNT_SID")),
        "twilio_token_set": bool(__import__("os").environ.get("TWILIO_AUTH_TOKEN")),
        "twilio_number_set": bool(__import__("os").environ.get("TWILIO_PHONE_NUMBER")),
        "openai_key_set": bool(__import__("os").environ.get("OPENAI_API_KEY")),
    }

    diagnostics["service"] = {"name": "mambo-bot", "version": "1.0.0"}
    diagnostics["uptime_estimate_seconds"] = round(
        asyncio.get_running_loop().time() - start, 3
    )

    logger.info("/whatsapp/test requested; returning diagnostics")
    return JSONResponse(content=_make_json_serializable(diagnostics))
