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
        logger.info("Initializing MessageHandler...")
        # DB layer
        self.user_service = UserService()
        # Twilio sender with repo-aware persistence
        self.twilio_sender = TwilioMessageHandler(repo=self.user_service)
        # Inject Twilio sender into onboarding service
        self.onboarding_service = OnboardingService(
            message_sender=self.twilio_sender, user_service=self.user_service
        )
        # Other services
        self.intent_classifier = IntentClassifier()
        self.twilio_client = TwilioClient(repo=self.user_service)
        self.recommendation_service = RecommendationService()
        self.image_service = ImageService()
        logger.info("MessageHandler initialized successfully")

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

    async def process_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Entry point for WhatsApp webhook payloads (from Meta API).
        Ensures idempotency and records all DB operations.
        """
        logger.info(
            "Processing webhook with entry count=%d", len(webhook_data.get("entry", []))
        )
        diagnostics = {"processed": 0, "results": [], "errors": []}
        try:
            for entry in webhook_data.get("entry", []):
                for change in entry.get("changes", []):
                    if change.get("field") == "messages":
                        logger.debug(
                            "Handling message change: %s",
                            list(change.get("value", {}).keys()),
                        )
                        res = await self._handle_message_change(change["value"])
                        diagnostics["processed"] += 1
                        diagnostics["results"].append(res)
            logger.info(
                "Webhook processing complete: processed=%d", diagnostics["processed"]
            )
            return {"ok": True, "diagnostics": diagnostics}
        except Exception as e:
            logger.exception("Error processing webhook: %s", e)
            diagnostics["errors"].append(str(e))
            return {"ok": False, "error": str(e), "diagnostics": diagnostics}

    async def _handle_message_change(
        self, message_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        results = []
        logger.debug(
            "Message change contains %d messages", len(message_data.get("messages", []))
        )
        for message in message_data.get("messages", []):
            logger.info(
                "Dispatching single message id=%s from=%s type=%s",
                message.get("id"),
                message.get("from"),
                message.get("type"),
            )
            r = await self._process_single_message(message)
            results.append(r)
        return {"ok": True, "results": results}

    async def _process_single_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        sender_phone = message.get("from")
        if not sender_phone:
            logger.warning("Received message with no sender: %s", message)
            return {"ok": False, "error": "no_sender"}

        # Only keep keys onboarding cares about
        allowed_keys = {"type", "text", "interactive", "image", "media"}
        clean_msg = {k: v for k, v in message.items() if k in allowed_keys}
        logger.debug(
            "Cleaned message keys for %s: %s", sender_phone, list(clean_msg.keys())
        )

        user_step = await self.onboarding_service.get_user_onboarding_step(sender_phone)
        logger.info("User %s onboarding step=%s", sender_phone, user_step)

        try:
            if user_step is None or (isinstance(user_step, int) and user_step < 5):
                logger.info("Routing message from %s to onboarding flow", sender_phone)
                res = await self.onboarding_service.handle_onboarding_message(
                    sender_phone, clean_msg
                )
                logger.debug(
                    "Onboarding result for %s: %s", sender_phone, self._safe_json(res)
                )
                return {
                    "ok": True,
                    "path": "onboarding",
                    "result": self._safe_json(res),
                }
            else:
                logger.info(
                    "Routing message from %s to post-onboarding flow", sender_phone
                )
                await self._handle_post_onboarding_message(sender_phone, clean_msg)
                return {"ok": True, "path": "post_onboarding"}
        except Exception as exc:
            logger.exception(
                "Error processing single message from %s: %s", sender_phone, exc
            )
            return {"ok": False, "error": str(exc)}

    # ------------------- POST-onboarding handlers -------------------

    async def _handle_post_onboarding_message(
        self, sender_phone: str, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        mtype = message.get("type")
        logger.info(
            "Handling post-onboarding message from=%s type=%s", sender_phone, mtype
        )

        if mtype == "text":
            return await self._handle_text_message(sender_phone, message)
        elif mtype in ("image", "media"):
            return await self._handle_image_message(sender_phone, message)
        elif mtype == "interactive":
            return await self._handle_interactive_message(sender_phone, message)
        else:
            logger.warning(
                "Unknown message type=%s from=%s; sending fallback", mtype, sender_phone
            )
            return await self.twilio_sender.send_text(
                sender_phone,
                "Mambo 🤖: I can help with meal suggestions! Ask what you'd like to eat or send a photo.",
            )

    async def _handle_text_message(
        self, sender_phone: str, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        text_content = (message.get("text") or {}).get("body", "").strip()
        logger.info("Text message from %s: '%s'", sender_phone, text_content)

        if not text_content:
            logger.debug("Empty text body from %s", sender_phone)
            return await self.twilio_sender.send_text(
                sender_phone, "I didn't get that — please type what you'd like."
            )

        # classify intent
        try:
            intent = await self.intent_classifier.classify_intent(text_content)
            logger.info("Classified intent for %s: %s", sender_phone, intent)
        except Exception as e:
            logger.warning("Intent classification failed for %s: %s", sender_phone, e)
            intent = None

        recommendations = await self.recommendation_service.get_meal_recommendations(
            sender_phone, text_content, max_results=3
        )
        logger.info(
            "Generated %d recommendations for %s",
            len(recommendations or []),
            sender_phone,
        )

        if not recommendations:
            return await self.twilio_sender.send_text(
                sender_phone, "I couldn't find suggestions — try giving ingredients."
            )

        # Build reply
        lines, media = [], []
        for i, r in enumerate(recommendations[:4], 1):
            name = r.get("name") or r.get("title") or "Dish"
            cuisine = (r.get("cuisine") or "").replace("_", " ").title()
            time_min = r.get("estimated_time_min")
            lines.append(
                f"{i}. {name} — {cuisine}" + (f" ({time_min} min)" if time_min else "")
            )
            if not media and r.get("image_url"):
                media.append(r.get("image_url"))

        text_body = (
            "Here are some meal ideas:\n"
            + "\n".join(lines)
            + "\nReply 'recipe [name]' for full recipe."
        )
        logger.debug("Reply body for %s: %s", sender_phone, text_body)

        if media:
            logger.info("Sending media response to %s", sender_phone)
            return await self.twilio_sender.send_media(
                sender_phone, media, body=text_body
            )
        logger.info("Sending text response to %s", sender_phone)
        return await self.twilio_sender.send_text(sender_phone, text_body)

    async def _handle_image_message(
        self, sender_phone: str, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info("Handling image message from %s", sender_phone)
        return await self.twilio_sender.send_text(
            sender_phone,
            "Nice photo! Would you like me to try analyzing it? Reply 'yes' or tell me the ingredients.",
        )

    async def _handle_interactive_message(
        self, sender_phone: str, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(
            "Handling interactive message from %s: %s",
            sender_phone,
            message.get("interactive"),
        )
        return await self.twilio_sender.send_text(
            sender_phone,
            "Got your selection — I'll update your preferences.",
        )
