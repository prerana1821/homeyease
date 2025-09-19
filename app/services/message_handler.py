# app/services/message_handler.py
"""
Message handler service for processing WhatsApp messages.
- Records incoming Twilio webhooks idempotently in Supabase
- Delegates onboarding messages to OnboardingService
- Handles post-onboarding messages with intent classification, recommendations, etc.
- Persists sessions and outgoing messages for audit
"""

import logging
from typing import Dict, Any, List

from app.services.twilio_message_handler import TwilioMessageHandler
from app.services.onboarding_service import OnboardingService
from app.services.intent_classifier import IntentClassifier
from app.services.twilio_client import TwilioClient
from app.services.recommendation_service import RecommendationService
from app.services.image_service import ImageService
from app.services.user_service import UserService
import datetime
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)


class MessageHandler:

    def __init__(self):
        # DB layer
        self.user_service = UserService()
        # Twilio sender with repo-aware persistence
        self.twilio_sender = TwilioMessageHandler(repo=self.user_service)
        # Inject Twilio sender into onboarding service
        self.onboarding_service = OnboardingService(
            message_sender=self.twilio_sender, user_service=self.user_service)
        # Other services
        self.intent_classifier = IntentClassifier()
        self.twilio_client = TwilioClient(
            repo=self.user_service
        )  # low-level client still available if needed
        self.recommendation_service = RecommendationService()
        self.image_service = ImageService()

    @staticmethod
    def _safe_json(obj):
        """Convert objects to JSON-safe primitives (no APIResponse leaking)."""
        import datetime
        from fastapi.encoders import jsonable_encoder

        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: MessageHandler._safe_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [MessageHandler._safe_json(v) for v in obj]
        try:
            return jsonable_encoder(obj)
        except Exception:
            return str(obj)

    async def process_webhook(self, webhook_data: Dict[str,
                                                       Any]) -> Dict[str, Any]:
        """
        Entry point for WhatsApp webhook payloads (from Meta API).
        Ensures idempotency and records all DB operations.
        """
        diagnostics = {"processed": 0, "results": [], "errors": []}
        try:
            for entry in webhook_data.get("entry", []):
                for change in entry.get("changes", []):
                    if change.get("field") == "messages":
                        res = await self._handle_message_change(change["value"]
                                                                )
                        diagnostics["processed"] += 1
                        diagnostics["results"].append(res)
            return {"ok": True, "diagnostics": diagnostics}
        except Exception as e:
            logger.exception("Error processing webhook: %s", e)
            diagnostics["errors"].append(str(e))
            return {"ok": False, "error": str(e), "diagnostics": diagnostics}

    async def _handle_message_change(
            self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        results = []
        for message in message_data.get("messages", []):
            r = await self._process_single_message(message)
            results.append(r)
        return {"ok": True, "results": results}

    async def _process_single_message(
            self, message: Dict[str, Any]) -> Dict[str, Any]:
        sender_phone = message.get("from")
        if not sender_phone:
            return {"ok": False, "error": "no_sender"}

        # Only keep keys onboarding cares about
        allowed_keys = {"type", "text", "interactive", "image", "media"}
        clean_msg = {k: v for k, v in message.items() if k in allowed_keys}

        user_step = await self.onboarding_service.get_user_onboarding_step(
            sender_phone)
        try:
            if user_step is None or (isinstance(user_step, int)
                                     and user_step < 5):
                res = await self.onboarding_service.handle_onboarding_message(
                    sender_phone, clean_msg)
                return {
                    "ok": True,
                    "path": "onboarding",
                    "result": self._safe_json(res),
                }

            else:
                await self._handle_post_onboarding_message(
                    sender_phone, clean_msg)
                return {"ok": True, "path": "post_onboarding"}
        except Exception as exc:
            logger.exception("Error processing single message: %s", exc)
            return {"ok": False, "error": str(exc)}

    # ------------------- POST-onboarding handlers -------------------

    async def _handle_post_onboarding_message(
            self, sender_phone: str, message: Dict[str,
                                                   Any]) -> Dict[str, Any]:
        mtype = message.get("type")
        if mtype == "text":
            return await self._handle_text_message(sender_phone, message)
        elif mtype in ("image", "media"):
            return await self._handle_image_message(sender_phone, message)
        elif mtype == "interactive":
            return await self._handle_interactive_message(
                sender_phone, message)
        else:
            return await self.twilio_sender.send_text(
                sender_phone,
                "Mambo 🤖: I can help with meal suggestions! Ask what you'd like to eat or send a photo.",
            )

    async def _handle_text_message(self, sender_phone: str,
                                   message: Dict[str, Any]) -> Dict[str, Any]:
        text_content = (message.get("text") or {}).get("body", "").strip()
        if not text_content:
            return await self.twilio_sender.send_text(
                sender_phone,
                "I didn't get that — please type what you'd like.")

        # classify intent
        try:
            intent = await self.intent_classifier.classify_intent(text_content)
        except Exception:
            intent = None

        recommendations = await self.recommendation_service.get_meal_recommendations(
            sender_phone, text_content, max_results=3)

        if not recommendations:
            return await self.twilio_sender.send_text(
                sender_phone,
                "I couldn't find suggestions — try giving ingredients.")

        # Build reply
        lines, media = [], []
        for i, r in enumerate(recommendations[:4], 1):
            name = r.get("name") or r.get("title") or "Dish"
            cuisine = (r.get("cuisine") or "").replace("_", " ").title()
            time_min = r.get("estimated_time_min")
            lines.append(f"{i}. {name} — {cuisine}" +
                         (f" ({time_min} min)" if time_min else ""))
            if not media and r.get("image_url"):
                media.append(r.get("image_url"))

        text_body = ("Here are some meal ideas:\n" + "\n".join(lines) +
                     "\nReply 'recipe [name]' for full recipe.")

        if media:
            return await self.twilio_sender.send_media(sender_phone,
                                                       media,
                                                       body=text_body)
        return await self.twilio_sender.send_text(sender_phone, text_body)

    async def _handle_image_message(self, sender_phone: str,
                                    message: Dict[str, Any]) -> Dict[str, Any]:
        return await self.twilio_sender.send_text(
            sender_phone,
            "Nice photo! Would you like me to try analyzing it? Reply 'yes' or tell me the ingredients.",
        )

    async def _handle_interactive_message(
            self, sender_phone: str, message: Dict[str,
                                                   Any]) -> Dict[str, Any]:
        return await self.twilio_sender.send_text(
            sender_phone,
            "Got your selection — I'll update your preferences.",
        )
