"""
Message handler service for processing WhatsApp messages.
Constructs TwilioMessageHandler first and injects it into OnboardingService
to avoid circular imports.
"""

import json
import logging
from typing import Dict, Any, List

from app.services.twilio_message_handler import TwilioMessageHandler
from app.services.onboarding_service import OnboardingService
from app.services.intent_classifier import IntentClassifier
from app.services.twilio_client import TwilioClient
from app.services.recommendation_service import RecommendationService
from app.services.image_service import ImageService

logger = logging.getLogger(__name__)


class MessageHandler:

    def __init__(self):
        # Initialize Twilio-aware sender first to inject into onboarding service
        self.twilio_sender = TwilioMessageHandler()
        # OnboardingService receives the sender instance (duck-typed)
        self.onboarding_service = OnboardingService(message_sender=self.twilio_sender)
        # Other services (they may be network-bound; instantiate after sender)
        self.intent_classifier = IntentClassifier()
        self.twilio_client = (
            TwilioClient()
        )  # low-level client still available if needed
        self.recommendation_service = RecommendationService()
        self.image_service = ImageService()

    async def process_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming webhook data from WhatsApp.

        Returns structured diagnostics so the caller (webhook) can include debug info.
        """
        diagnostics = {"processed": 0, "errors": []}
        try:
            for entry in webhook_data.get("entry", []):
                for change in entry.get("changes", []):
                    if change.get("field") == "messages":
                        res = await self._handle_message_change(change["value"])
                        diagnostics["processed"] += 1
                        if res:
                            diagnostics.setdefault("results", []).append(res)
            return {"ok": True, "diagnostics": diagnostics}
        except Exception as e:
            logger.exception("Error processing webhook: %s", e)
            diagnostics["errors"].append(str(e))
            return {"ok": False, "error": str(e), "diagnostics": diagnostics}

    async def _handle_message_change(
        self, message_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        messages = message_data.get("messages", [])
        results = []
        for message in messages:
            r = await self._process_single_message(message)
            results.append(r)
        return {"ok": True, "results": results}

    async def _process_single_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        sender_phone = message.get("from")
        message_type = message.get("type")
        if not sender_phone:
            return {"ok": False, "error": "no_sender"}
        # Ask onboarding service for step
        user_step = await self.onboarding_service.get_user_onboarding_step(sender_phone)
        # If user_step is None -> not in DB or error; onboarding_service.handle will auto-start
        try:
            if user_step is None or (isinstance(user_step, int) and user_step < 5):
                # user is in onboarding (or missing) -> let onboarding service handle it
                res = await self.onboarding_service.handle_onboarding_message(
                    sender_phone, message
                )
                return {"ok": True, "path": "onboarding", "result": res}
            else:
                # post-onboarding flow
                await self._handle_post_onboarding_message(sender_phone, message)
                return {"ok": True, "path": "post_onboarding"}
        except Exception as exc:
            logger.exception("Error processing single message: %s", exc)
            return {"ok": False, "error": str(exc)}

    # POST-onboarding handlers (delegate to twilio_sender when replying)
    async def _handle_post_onboarding_message(
        self, sender_phone: str, message: Dict[str, Any]
    ) -> None:
        mtype = message.get("type")
        try:
            if mtype == "text":
                await self._handle_text_message(sender_phone, message)
            elif mtype in ("image", "media"):
                await self._handle_image_message(sender_phone, message)
            elif mtype == "interactive":
                await self._handle_interactive_message(sender_phone, message)
            else:
                await self.twilio_sender.send_text(
                    sender_phone,
                    "Mambo 🤖: I can help with meal suggestions! Ask what you'd like to eat or send a photo.",
                )
        except Exception as exc:
            logger.exception("post_onboarding handler failed: %s", exc)
            await self.twilio_sender.send_text(
                sender_phone, "Sorry — something went wrong. Try again in a moment."
            )

    async def _handle_text_message(
        self, sender_phone: str, message: Dict[str, Any]
    ) -> None:
        text_content = (message.get("text") or {}).get("body", "").strip()
        if not text_content:
            await self.twilio_sender.send_text(
                sender_phone, "I didn't get that — please type what you'd like."
            )
            return
        # classify intent (best-effort)
        try:
            intent = await self.intent_classifier.classify_intent(text_content)
        except Exception:
            intent = None
        # If user asks for recipe or pantry, call recommendation service
        recommendations = await self.recommendation_service.get_meal_recommendations(
            sender_phone, text_content, max_results=3
        )
        # Format and send compact message (use twilio_sender)
        if not recommendations:
            await self.twilio_sender.send_text(
                sender_phone, "I couldn't find suggestions — try giving ingredients."
            )
            return

        # Compose short message and attach first image if available
        lines = []
        media = []
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
        if media:
            await self.twilio_sender.send_media(sender_phone, media, body=text_body)
        else:
            await self.twilio_sender.send_text(sender_phone, text_body)

    async def _handle_image_message(
        self, sender_phone: str, message: Dict[str, Any]
    ) -> None:
        await self.twilio_sender.send_text(
            sender_phone,
            "Nice photo! Would you like me to try analyzing it? Reply 'yes' or tell me the ingredients.",
        )
        # further processing could be added here

    async def _handle_interactive_message(
        self, sender_phone: str, message: Dict[str, Any]
    ) -> None:
        await self.twilio_sender.send_text(
            sender_phone, "Got your selection — I'll update your preferences."
        )
