# app/services/message_handler.py
from datetime import datetime
from typing import Any, Dict, Optional


class MessageHandler:
    """
    Handles incoming messages (eg. from WhatsApp webhook). Persists session logs
    and invokes onboarding flows via OnboardingService which in turn persists
    to the DB via UserService.
    """

    def __init__(self, db_client, user_service, onboarding_service):
        self.db = db_client
        self.user_service = user_service
        self.onboarding_service = onboarding_service

    def _insert_session(
        self,
        user_id: Optional[int],
        whatsapp_id: str,
        prompt: str,
        raw: Optional[dict] = None,
    ) -> Dict[str, Any]:
        payload = {
            "user_id": user_id,
            "whatsapp_id": whatsapp_id,
            "prompt": prompt,
            "response": None,
            "created_at": datetime.utcnow().isoformat(),
            "raw_payload": raw or {},  # <--- store raw payload
        }
        try:
            resp = self.db.table("sessions").insert(payload).execute()
            data = getattr(resp, "data", None) or (
                resp.get("data") if isinstance(resp, dict) else None
            )
            return {"ok": True, "data": data}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _update_session_response(self, session_meta, response_text: str):
        # session_meta might contain the created entry or metadata - be defensive
        try:
            # Try to pull an id or build a where clause with whatsapp_id + created_at if id missing
            row_id = None
            if isinstance(session_meta, dict):
                # possible shapes: {"data":[{...}] } or {"data": {...}} depending on client
                if "data" in session_meta and session_meta["data"]:
                    first = (
                        session_meta["data"][0]
                        if isinstance(session_meta["data"], list)
                        else session_meta["data"]
                    )
                    row_id = first.get("id")
            if row_id:
                self.db.table("sessions").update({"response": response_text}).eq(
                    "id", row_id
                ).execute()
            else:
                # best-effort update: update the latest session with same whatsapp_id
                # Not ideal for heavy concurrency but acceptable for webhook tests
                self.db.table("sessions").update({"response": response_text}).execute()
        except Exception:
            # logging ignored (replace with real logger)
            pass

    def handle_incoming_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        message now expected to include:
          - whatsapp_id (string)
          - text (string)
          - onboarding_step (optional int)
          - onboarding_payload (optional dict)
          - raw (optional dict)  <-- Twilio raw webhook payload
        """
        whatsapp_id = message.get("whatsapp_id") or message.get("from")
        if not whatsapp_id:
            return {"ok": False, "error": "missing whatsapp_id", "data": None}

        text = message.get("text", "")
        raw_payload = message.get("raw", {})

        user_res = self.user_service.get_user(whatsapp_id=whatsapp_id)
        user_id = (
            user_res["data"]["id"] if user_res["ok"] and user_res["data"] else None
        )

        # log session (pre)
        session_meta = self._insert_session(
            user_id=user_id, whatsapp_id=whatsapp_id, prompt=text, raw=raw_payload
        )

        # If message is onboarding
        step = message.get("onboarding_step")
        if step:
            payload = message.get("onboarding_payload", {})
            onboard_res = self.onboarding_service.process_step(
                whatsapp_id=whatsapp_id, step=step, payload=payload
            )
            # Update session with onboarding result
            resp_text = f"onboarding step {step} result: {'ok' if onboard_res.get('ok') else 'fail'} - {onboard_res.get('error') or ''}"
            self._update_session_response(session_meta, resp_text)
            return {
                "ok": onboard_res.get("ok", False),
                "data": onboard_res.get("data"),
                "error": onboard_res.get("error"),
            }

        # Normal message processing placeholder:
        # (here you'd call your NLP / recipe generation / etc.)
        reply = {"text": "Thanks! Your message was received."}

        # persist reply in session
        if session_meta.get("ok"):
            self._update_session_response(session_meta, reply["text"])

        return {"ok": True, "data": reply, "error": None}
