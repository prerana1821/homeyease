# app/api/twilio_webhook.py
"""
Twilio webhook endpoints for receiving WhatsApp messages via Twilio only.

- No external adapter dependency.
- No SMS routes.
- Returns TwiML (empty) to Twilio by default.
- If ?debug=1 is added, returns verbose JSON diagnostics for local testing.
"""
from __future__ import annotations

import collections
import logging
import time
from typing import Any, Deque, Dict, List, Optional

import asyncio
import datetime
import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, Response

from app.services.message_handler import MessageHandler
from app.config.settings import settings
from app.config.supabase import supabase_client
from app.services.twilio_client import TwilioClient

logger = logging.getLogger(__name__)
router = APIRouter()

# Singletons
message_handler = MessageHandler()
twilio_client = TwilioClient()


# Deduper for Twilio retries (MessageSid)
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
    # Remove leading 'whatsapp:' prefix and stray text
    s = s.replace("whatsapp:", "").replace("whatsapp", "").strip()
    # Remove any spaces
    s = s.replace(" ", "")
    # Ensure leading plus for E.164 numbers (if number contains country code)
    if s and not s.startswith("+"):
        if s.isdigit():
            s = f"+{s}"
    return s


def _guess_mime_from_url(url: str) -> str:
    if not url:
        return "application/octet-stream"
    url = url.lower()
    if any(ext in url for ext in (".jpg", ".jpeg")):
        return "image/jpeg"
    if ".png" in url:
        return "image/png"
    if ".gif" in url:
        return "image/gif"
    if any(ext in url for ext in (".mp4", ".mov")):
        return "video/mp4"
    if any(ext in url for ext in (".mp3", ".wav")):
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
    num_media = declared_num_media or int(form.get("NumMedia") or 0)

    message: Dict[str, Any] = {
        "from": from_phone,
        "id": msg_id,
        "timestamp": str(int(time.time())),
        "type": "text",
        "text": {
            "body": body_text
        } if body_text else None,
        "raw": {
            k: form.get(k)
            for k in form.keys() if k
        },
    }

    # Media handling
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
            message["image"] = {
                "urls": urls,
                "mime_type": mime,
                "count": len(urls)
            }
        elif mime.startswith("video/"):
            message["type"] = "video"
            message["media"] = {
                "urls": urls,
                "mime_type": mime,
                "count": len(urls)
            }
        else:
            message["type"] = "media"
            message["media"] = {
                "urls": urls,
                "mime_type": mime,
                "count": len(urls)
            }

    return message


def _make_json_serializable(obj: Any) -> Any:
    """Convert objects (including Supabase APIResponse) to JSON-safe primitives."""
    if obj is None or isinstance(obj, (str, bool, int, float)):
        return obj
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_make_json_serializable(v) for v in obj]

    # Handle Supabase APIResponse-like objects
    if hasattr(obj, "data") or hasattr(obj, "status_code") or hasattr(
            obj, "error"):
        try:
            return {
                "data": getattr(obj, "data", None),
                "status_code": getattr(obj, "status_code", None),
                "error": getattr(obj, "error", None),
            }
        except Exception:
            pass

    try:
        return str(obj)  # last resort fallback
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
    """Twilio webhook for WhatsApp. Use ?debug=1 for verbose JSON diagnostics."""
    start_ts = time.time()
    diagnostics: Dict[str, Any] = {"steps": [], "errors": []}
    from app.services.user_service import UserService  # local import to avoid cycles

    try:
        form = await request.form()
        logger.info("Received Twilio webhook request form; keys=%s",
                    list(form.keys()))
        diagnostics["steps"].append("form_received")

        # parse num_media defensively
        try:
            num_media = int(NumMedia or form.get("NumMedia") or 0)
        except Exception:
            num_media = 0
            logger.debug("Failed to parse NumMedia; defaulting to 0")

        media_urls: List[str] = []
        if num_media > 0:
            for i in range(num_media):
                key = f"MediaUrl{i}"
                if key in form:
                    media_urls.append(str(form.get(key)))
            logger.debug("Detected media URLs: count=%d", len(media_urls))

        # Message SID determination
        message_sid = MessageSid or str(form.get("MessageSid") or "")
        if not message_sid:
            message_sid = f"tw-{int(time.time() * 1000)}"
            logger.debug("No MessageSid provided; synthesized id=%s",
                         message_sid)
        diagnostics["message_sid"] = message_sid

        # Dedupe check (in-memory)
        if deduper.contains(message_sid):
            logger.info("Duplicate webhook detected via in-memory deduper: %s",
                        message_sid)
            diagnostics["steps"].append("deduplicated_in_memory")
            if debug:
                return JSONResponse({
                    "status": "ignored",
                    "reason": "duplicate",
                    "diagnostics": diagnostics
                })
            return Response(
                content=
                '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml")

        # Build internal message representation
        incoming_message = _build_internal_message_from_twilio_form(
            form, declared_num_media=num_media, media_urls=media_urls)
        logger.info(
            "Converted incoming Twilio form to internal message id=%s from=%s type=%s",
            incoming_message.get("id"), incoming_message.get("from"),
            incoming_message.get("type"))
        logger.debug("Internal message (truncated): %s", {
            k: incoming_message.get(k)
            for k in ("id", "from", "type", "text")
        })
        diagnostics["steps"].append("converted_to_internal")

        # Persist incoming message in DB for idempotency
        user_service = UserService()

        # --- try to resolve user_id from whatsapp id BEFORE inserting incoming row
        phone_clean = _clean_phone(form.get("From") or From)
        diagnostics["resolved_from"] = phone_clean
        try:
            user_res = await user_service.get_user_by_whatsapp_id(phone_clean)
            if user_res.get("ok") and user_res.get("user"):
                resolved_user_id = user_res["user"].get("id")
                diagnostics["resolved_user_id"] = resolved_user_id
                logger.debug("Resolved user for incoming phone=%s id=%s",
                             phone_clean, resolved_user_id)
            else:
                resolved_user_id = None
                logger.debug("No user found for incoming phone=%s",
                             phone_clean)
        except Exception as exc:
            resolved_user_id = None
            logger.exception("Error resolving user by phone %s: %s",
                             phone_clean, exc)

        try:
            rec = await user_service.record_incoming_message(
                message_sid=message_sid,
                user_id=resolved_user_id,
                from_phone=phone_clean,
                raw_payload=dict(form),
            )

            logger.info("Recorded incoming_message sid=%s created=%s",
                        message_sid, rec.get("created"))
            logger.debug("record_incoming_message diagnostics: %s",
                         rec.get("diagnostics"))
            diagnostics["incoming_record"] = _make_json_serializable(rec)
        except Exception as exc:
            logger.exception(
                "Failed to record incoming_message before processing: %s", exc)
            diagnostics["errors"].append(f"record_incoming_failed:{str(exc)}")
            rec = {"ok": False, "created": False}

        # If DB says it existed already, check processed flag; only short-circuit
        # if that existing row is already processed. If not processed, CONTINUE processing.
        if rec.get("ok") and not rec.get("created"):
            existing_row = rec.get("data") or rec.get("row")
            processed_flag = False
            # support several shapes
            if isinstance(existing_row, dict):
                processed_flag = bool(
                    existing_row.get("processed")
                    or (existing_row.get("processed") is True))
            logger.info(
                "Incoming message sid=%s already exists in DB (created=False) processed=%s",
                message_sid, processed_flag)
            diagnostics["incoming_existing_processed"] = processed_flag
            if processed_flag:
                diagnostics["steps"].append(
                    "duplicate_detected_db_already_processed")
                if debug:
                    return JSONResponse(
                        _make_json_serializable({
                            "status": "ok",
                            "message_sid": message_sid,
                            "diagnostics": diagnostics,
                        }))
                return Response(
                    content=
                    '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                    media_type="application/xml")
            # else: existing row found but not processed -> continue processing (do NOT short-circuit)
            logger.info(
                "Existing DB row for sid=%s not yet processed; continuing processing",
                message_sid)

        # Add to in-memory deduper (prevents immediate re-processing)
        added = deduper.add(message_sid)
        logger.debug("Added message_sid to in-memory deduper=%s (was_new=%s)",
                     message_sid, added)

        # Build webhook payload and hand to message handler
        webhook_payload = {
            "entry": [{
                "id":
                "twilio_entry",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [incoming_message]
                    }
                }],
            }]
        }

        # Process message via message_handler
        try:
            logger.info(
                "Dispatching payload to MessageHandler.process_webhook sid=%s",
                message_sid)
            proc_res = await message_handler.process_webhook(webhook_payload)
            logger.info("MessageHandler.process_webhook completed for sid=%s",
                        message_sid)
            diagnostics["steps"].append("processed")
            diagnostics["process_result"] = _make_json_serializable(proc_res)
            logger.debug(
                "process_result (ok): %s",
                bool(proc_res.get("ok"))
                if isinstance(proc_res, dict) else None)
        except Exception as exc:
            logger.exception("Error processing webhook payload for sid=%s: %s",
                             message_sid, exc)
            diagnostics["errors"].append(str(exc))
            # Don't mark processed; return TwiML or debug JSON
            if debug:
                return JSONResponse(_make_json_serializable({
                    "status":
                    "error",
                    "message_sid":
                    message_sid,
                    "diagnostics":
                    diagnostics,
                }),
                                    status_code=500)
            return Response(
                content=
                '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml")

        # Mark incoming processed now that handling succeeded
        try:
            mproc = await user_service.mark_incoming_processed(message_sid)
            logger.info("Marked incoming_message processed sid=%s ok=%s",
                        message_sid, mproc.get("ok"))
            diagnostics["incoming_mark_processed"] = _make_json_serializable(
                mproc)
        except Exception as exc:
            logger.exception("Failed to mark incoming processed for %s: %s",
                             message_sid, exc)
            diagnostics["errors"].append("mark_incoming_processed_failed")

        # If debug requested, return detailed diagnostics
        if debug:
            elapsed = round(time.time() - start_ts, 3)
            diagnostics["elapsed_seconds"] = elapsed
            return JSONResponse(
                _make_json_serializable({
                    "status": "ok",
                    "message_sid": message_sid,
                    "diagnostics": diagnostics,
                }))

        # Normal TwiML empty response to acknowledge Twilio
        return Response(
            content=
            '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml")

    except Exception as exc:
        diagnostics["errors"].append(str(exc))
        logger.exception("Unhandled exception in Twilio webhook: %s", exc)
        if debug:
            return JSONResponse(_make_json_serializable({
                "status":
                "error",
                "message_sid":
                locals().get("message_sid", "<unknown>"),
                "diagnostics":
                diagnostics,
            }),
                                status_code=500)
        return Response(
            content=
            '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml")


# -------------------------
# Test endpoint
# -------------------------
@router.get("/test")
async def test_twilio_webhook(request: Request):
    """Diagnostics for Supabase + Twilio + environment flags."""
    diagnostics: Dict[str, Any] = {}
    start = asyncio.get_running_loop().time()
    diagnostics["timestamp"] = datetime.datetime.now(
        datetime.timezone.utc).isoformat()

    # Supabase health
    try:
        loop = asyncio.get_running_loop()
        db_ok = await asyncio.wait_for(loop.run_in_executor(
            None, supabase_client.health_check),
                                       timeout=5.0)
        diagnostics["supabase"] = {"healthy": bool(db_ok)}
        logger.debug("Supabase health_check returned: %s", bool(db_ok))
    except Exception as exc:
        diagnostics["supabase"] = {"healthy": False, "error": str(exc)}
        logger.exception("Supabase health check failed: %s", exc)

    # Twilio health
    try:
        diag = twilio_client.test_connection()
        diagnostics["twilio"] = _make_json_serializable(diag)
        logger.debug("Twilio test_connection: %s", diagnostics["twilio"])
    except Exception as exc:
        diagnostics["twilio"] = {"ok": False, "error": str(exc)}
        logger.exception("Twilio test_connection failed: %s", exc)

    # Environment flags
    diagnostics["env"] = {
        "supabase_url_set": bool(os.getenv("SUPABASE_URL")),
        "supabase_key_set": bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        "twilio_sid_set": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        "twilio_token_set": bool(os.getenv("TWILIO_AUTH_TOKEN")),
        "twilio_number_set": bool(os.getenv("TWILIO_PHONE_NUMBER")),
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
    }

    diagnostics["service"] = {"name": "mambo-bot", "version": "1.0.0"}
    diagnostics["uptime_estimate_seconds"] = round(
        asyncio.get_running_loop().time() - start, 3)

    logger.info("/webhook/test requested; returning diagnostics")
    return JSONResponse(content=_make_json_serializable(diagnostics))
