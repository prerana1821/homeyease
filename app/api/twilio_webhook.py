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
from fastapi.encoders import jsonable_encoder

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
    return str(phone).replace("whatsapp:", "").strip()


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
        "text": {"body": body_text} if body_text else None,
        "raw": {k: form.get(k) for k in form.keys() if k},
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
            message["image"] = {"urls": urls, "mime_type": mime, "count": len(urls)}
        elif mime.startswith("video/"):
            message["type"] = "video"
            message["media"] = {"urls": urls, "mime_type": mime, "count": len(urls)}
        else:
            message["type"] = "media"
            message["media"] = {"urls": urls, "mime_type": mime, "count": len(urls)}

    return message


def _make_json_serializable(obj: Any) -> Any:
    """Convert objects to JSON-serializable primitives recursively."""
    if obj is None or isinstance(obj, (str, bool, int, float)):
        return obj
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_make_json_serializable(v) for v in obj]
    try:
        return jsonable_encoder(obj)
    except Exception:
        return str(obj)


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
    Use ?debug=1 to get JSON diagnostics instead of TwiML.
    """
    start_ts = time.time()
    diagnostics: Dict[str, Any] = {"steps": [], "errors": []}

    try:
        form = await request.form()
        diagnostics["steps"].append("form_received")

        try:
            num_media = int(NumMedia or form.get("NumMedia") or 0)
        except Exception:
            num_media = 0

        media_urls: List[str] = []
        if num_media > 0:
            for i in range(num_media):
                key = f"MediaUrl{i}"
                if key in form:
                    media_urls.append(str(form.get(key)))

        message_sid = MessageSid or str(form.get("MessageSid") or "")
        if not message_sid:
            message_sid = f"tw-{int(time.time() * 1000)}"
        diagnostics["message_sid"] = message_sid

        if deduper.contains(message_sid):
            diagnostics["steps"].append("deduplicated")
            if debug:
                return JSONResponse(
                    {
                        "status": "ignored",
                        "reason": "duplicate",
                        "diagnostics": diagnostics,
                    }
                )
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml",
            )
        deduper.add(message_sid)

        incoming_message = _build_internal_message_from_twilio_form(
            form, declared_num_media=num_media, media_urls=media_urls
        )
        diagnostics["steps"].append("converted_to_internal")

        webhook_payload = {
            "entry": [
                {
                    "id": "twilio_entry",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {"messages": [incoming_message]},
                        }
                    ],
                }
            ]
        }

        try:
            await message_handler.process_webhook(webhook_payload)
            diagnostics["steps"].append("processed")
        except Exception as exc:
            diagnostics["errors"].append(str(exc))
            logger.exception("Error processing webhook payload")
            if debug:
                return JSONResponse(
                    {"status": "error", "error": str(exc), "diagnostics": diagnostics},
                    status_code=500,
                )
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml",
            )

        if debug:
            return JSONResponse(
                {"status": "ok", "message_sid": message_sid, "diagnostics": diagnostics}
            )

        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )
    except Exception as exc:
        diagnostics["errors"].append(str(exc))
        logger.exception("Unhandled exception in Twilio webhook")
        if debug:
            return JSONResponse(
                {"status": "error", "error": str(exc), "diagnostics": diagnostics},
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
    """Diagnostics for Supabase + Twilio + environment flags."""
    diagnostics: Dict[str, Any] = {}
    start = asyncio.get_running_loop().time()
    diagnostics["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Supabase health
    try:
        loop = asyncio.get_running_loop()
        db_ok = await asyncio.wait_for(
            loop.run_in_executor(None, supabase_client.health_check), timeout=5.0
        )
        diagnostics["supabase"] = {"healthy": bool(db_ok)}
    except Exception as exc:
        diagnostics["supabase"] = {"healthy": False, "error": str(exc)}

    # Twilio health
    try:
        diag = await twilio_client.test_connection()
        diagnostics["twilio"] = _make_json_serializable(diag)
    except Exception as exc:
        diagnostics["twilio"] = {"ok": False, "error": str(exc)}

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
        asyncio.get_running_loop().time() - start, 3
    )

    return JSONResponse(content=_make_json_serializable(diagnostics))
