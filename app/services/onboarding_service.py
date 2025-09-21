# app/services/onboarding_service.py
"""
OnboardingService that drives a 5-step onboarding flow.
It no longer imports TwilioMessageHandler directly to avoid circular imports.
Instead it accepts a message_sender dependency (duck-typed) with methods:
  - send_text(to_phone, body) -> returns dict with status/diagnostics
  - send_media(to_phone, media_urls, body) -> same
  - send_interactive(to_phone, payload) -> same (optional)
This makes the service testable and breaks import cycles.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from app.services.user_service import UserService

logger = logging.getLogger(__name__)

# Onboarding steps
STEP_NAME = 0
STEP_DIET = 1
STEP_CUISINE = 2
STEP_ALLERGIES = 3
STEP_HOUSEHOLD = 4
STEP_COMPLETE = 5


class OnboardingService:

    def __init__(
        self,
        message_sender: Optional[Any] = None,
        user_service: Optional[UserService] = None,
    ) -> None:
        """
        message_sender: an object that implements send_text/send_media/send_interactive.
                        If None, OnboardingService will still operate but won't send messages.
        user_service: optional override for testing.
        """
        self.message_sender = message_sender
        self.user_service = user_service or UserService()

    # Small helper to call sender's send_text if available
    async def _send_text(self, to_phone: str, body: str) -> Dict[str, Any]:
        if not self.message_sender or not hasattr(self.message_sender,
                                                  "send_text"):
            logger.debug("No message sender available; dropping outbound: %s",
                         body[:80])
            return {"status": "error", "error": "no_sender_configured"}
        try:
            resp = await self.message_sender.send_text(to_phone, body)
            logger.info("Sent text to %s; provider_resp_ok=%s", to_phone,
                        bool(resp and resp.get("ok")))
            logger.debug("Sender response diagnostics: %s",
                         resp.get("diagnostics"))
            return resp
        except Exception as exc:
            logger.exception("Error sending text to %s: %s", to_phone, exc)
            return {"status": "error", "error": str(exc)}

    # Main public API
    async def get_user_onboarding_step(self,
                                       whatsapp_id: str) -> Optional[int]:
        """Return onboarding step for user, or None on error/not found."""
        res = await self.user_service.get_user_by_whatsapp_id(whatsapp_id)
        if not res.get("ok"):
            logger.debug("get_user_onboarding_step db failure: %s",
                         res.get("error"))
            return None
        user = res.get("user")
        if not user:
            logger.debug("get_user_onboarding_step: user not found for %s",
                         whatsapp_id)
            return None

        # Normalize user row (some clients return list)
        if isinstance(user, list) and user:
            user = user[0]

        step = user.get("onboarding_step")
        if step is None:
            # None signals completed onboarding in your schema; treat as complete
            return STEP_COMPLETE
        try:
            return int(step)
        except Exception:
            logger.warning("Unexpected onboarding_step type for user %s: %s",
                           whatsapp_id, step)
            return None

    async def start_onboarding(self, whatsapp_id: str) -> Dict[str, Any]:
        """
        Start onboarding for whatsapp_id: create user row and send the name prompt.
        """
        diag: Dict[str, Any] = {"actions": [], "errors": []}
        logger.info("Starting onboarding for %s", whatsapp_id)

        create_res = await self.user_service.create_user(whatsapp_id)
        diag["create_user"] = create_res.get("diagnostics")
        if not create_res.get("ok"):
            logger.error("create_user failed for %s: %s", whatsapp_id,
                         create_res.get("error"))
            diag["errors"].append(
                {"create_user_error": create_res.get("error")})
            return {"status": "error", "diagnostics": diag}

        user = create_res.get("user")
        if not user:
            logger.error("create_user returned no user object for %s",
                         whatsapp_id)
            diag["errors"].append({"create_user_error": "user_not_created"})
            return {"status": "error", "diagnostics": diag}

        # Normalize user if list
        if isinstance(user, list) and user:
            user = user[0]

        # set onboarding step to STEP_NAME
        try:
            set_step_res = await self.user_service.update_user_onboarding_step(
                user.get("id"), STEP_NAME)
            diag["set_step"] = set_step_res.get("diagnostics")
            if not set_step_res.get("ok"):
                logger.warning(
                    "update_user_onboarding_step failed for user %s: %s",
                    user.get("id"), set_step_res.get("error"))
                diag["errors"].append(
                    {"set_step_error": set_step_res.get("error")})
        except Exception as exc:
            logger.exception(
                "Exception while setting onboarding step for %s: %s",
                whatsapp_id, exc)
            diag["errors"].append({"set_step_error": str(exc)})

        # send the first question
        send_res = await self._send_text(
            whatsapp_id,
            "Mambo 🥘: Hi! I'm Mambo — what's your name? Reply with your first name or 'skip'.",
        )
        diag["sent_first_question"] = send_res
        return {"status": "ok", "next_step": STEP_NAME, "diagnostics": diag}

    async def handle_onboarding_message(self, whatsapp_id: str,
                                        message: Dict[str, Any],
                                        **kwargs) -> Dict[str, Any]:
        """Process an incoming onboarding message."""
        diag: Dict[str, Any] = {"steps": [], "errors": []}
        logger.info("handle_onboarding_message called for %s message_type=%s",
                    whatsapp_id, message.get("type"))

        user_res = await self.user_service.get_user_by_whatsapp_id(whatsapp_id)
        diag["user_fetch"] = user_res.get("diagnostics")
        if not user_res.get("ok"):
            logger.warning(
                "get_user_by_whatsapp_id failed; auto-starting onboarding for %s",
                whatsapp_id)
            start = await self.start_onboarding(whatsapp_id)
            diag["actions"] = {"auto_started": start}
            return {"status": "started", "diagnostics": diag}

        user = user_res.get("user")
        # Normalize user if list returned
        if isinstance(user, list) and user:
            user = user[0]

        if not user:
            logger.info("User not present; starting onboarding for %s",
                        whatsapp_id)
            start = await self.start_onboarding(whatsapp_id)
            diag["actions"] = {"auto_started": start}
            return {"status": "started", "diagnostics": diag}

        # Safely determine step; if None treat as complete
        raw_step = user.get("onboarding_step")
        if raw_step is None:
            step = STEP_COMPLETE
        else:
            try:
                step = int(raw_step)
            except Exception:
                logger.warning("Invalid onboarding_step for user %s: %s",
                               whatsapp_id, raw_step)
                step = STEP_NAME
        diag["current_step"] = step
        logger.debug("User %s current onboarding step=%s", whatsapp_id, step)

        # dispatch to handlers
        try:
            if step == STEP_NAME:
                result = await self._handle_name(user, message)
            elif step == STEP_DIET:
                result = await self._handle_diet(user, message)
            elif step == STEP_CUISINE:
                result = await self._handle_cuisine(user, message)
            elif step == STEP_ALLERGIES:
                result = await self._handle_allergies(user, message)
            elif step == STEP_HOUSEHOLD:
                result = await self._handle_household(user, message)
            else:
                result = {
                    "status": "complete",
                    "message": "onboarding complete"
                }
        except Exception as exc:
            logger.exception(
                "Unhandled exception in onboarding handler for %s: %s",
                whatsapp_id, exc)
            result = {"status": "error", "error": str(exc)}
        diag["step_result"] = result
        return {
            "status": result.get("status", "ok"),
            "diagnostics": diag,
            **{
                k: v
                for k, v in result.items() if k != "diagnostics"
            },
        }

    # ---- step implementations ----
    async def _handle_name(self, user: Dict[str, Any],
                           message: Dict[str, Any]) -> Dict[str, Any]:
        body = ""
        if message.get("type") == "text":
            body = (message.get("text") or {}).get("body", "").strip()
        elif message.get("type") == "interactive":
            body = ((message.get("interactive") or {}).get("list_reply",
                                                           {}).get("title")
                    or (message.get("interactive") or {}).get(
                        "button_reply", {}).get("title") or "")

        if not body:
            await self._send_text(
                user.get("whatsapp_id") or user.get("whatsapp", ""),
                "What should I call you? Reply with your name or 'skip'.",
            )
            return {"status": "ok", "message": "reasked"}

        name = "Guest" if body.lower() == "skip" else body[:64]
        up = await self.user_service.update_user_name_and_onboarding_step(
            user.get("id"), name, STEP_DIET)
        if not up.get("ok"):
            logger.warning(
                "Failed update_user_name_and_onboarding_step for user %s: %s",
                user.get("id"), up.get("error"))
            return {"status": "error", "error": up.get("error")}

        # Normalize updated user representation if present
        updated = up.get("result") or up.get("user") or user
        if isinstance(updated, list) and updated:
            updated = updated[0]

        # Persist outgoing messages and session
        await self._send_text(
            updated.get("whatsapp_id") or user.get("whatsapp_id"),
            f"Lovely — Hi {name}! I'll remember that.")
        await self._send_text(
            updated.get("whatsapp_id") or user.get("whatsapp_id"),
            "What's your diet preference? Reply:\n1 - Veg 🌱\n2 - Non-Veg 🍗\n3 - Both 🍽️"
        )
        # best-effort create session (may return diagnostics)
        try:
            await self.user_service.create_session(
                updated.get("id") or user.get("id"),
                prompt="onboarding_name",
                response_text=f"name={name}")
        except Exception:
            logger.exception("create_session failed (non-fatal) for user %s",
                             user.get("id"))

        return {"status": "ok", "next_step": STEP_DIET}

    async def _handle_diet(self, user: Dict[str, Any],
                           message: Dict[str, Any]) -> Dict[str, Any]:
        body = ""
        if message.get("type") == "text":
            body = (message.get("text") or {}).get("body", "").strip()
        elif message.get("type") == "interactive":
            body = ((message.get("interactive") or {}).get("button_reply",
                                                           {}).get("id")
                    or (message.get("interactive") or {}).get(
                        "list_reply", {}).get("id") or "")

        mapping = {
            "1": "veg",
            "2": "non-veg",
            "3": "both",
            "veg": "veg",
            "non-veg": "non-veg",
            "both": "both",
        }
        diet = mapping.get(body.lower(), "both")
        up = await self.user_service.update_user_diet_and_onboarding_step(
            user.get("id"), diet, STEP_CUISINE)
        if not up.get("ok"):
            logger.warning(
                "Failed update_user_diet_and_onboarding_step for user %s: %s",
                user.get("id"), up.get("error"))
            return {"status": "error", "error": up.get("error")}
        await self._send_text(user.get("whatsapp_id"),
                              f"Noted — {diet}. Which cuisine do you prefer?")
        # present cuisines (simple text fallback)
        cuisines = "\n".join([
            f"{i+1}. {c}" for i, c in enumerate([
                "North Indian",
                "South Indian",
                "Chinese",
                "Italian",
                "Punjabi",
                "Gujarati",
                "Bengali",
                "International",
                "Surprise",
            ])
        ])
        await self._send_text(user.get("whatsapp_id"), cuisines)
        return {"status": "ok", "next_step": STEP_CUISINE}

    async def _handle_cuisine(self, user: Dict[str, Any],
                              message: Dict[str, Any]) -> Dict[str, Any]:
        body = ""
        if message.get("type") == "text":
            body = (message.get("text") or {}).get("body", "").strip()
        elif message.get("type") == "interactive":
            body = ((message.get("interactive") or {}).get("list_reply",
                                                           {}).get("id")
                    or (message.get("interactive") or {}).get(
                        "list_reply", {}).get("title") or "")

        mapping = {
            str(i + 1): val
            for i, val in enumerate([
                "north_indian",
                "south_indian",
                "chinese",
                "italian",
                "punjabi",
                "gujarati",
                "bengali",
                "international",
                "surprise",
            ])
        }
        cuisine = mapping.get(body) or (body.lower().replace(" ", "_")
                                        if body else "surprise")
        up = await self.user_service.update_user_cuisine_and_onboarding_step(
            user.get("id"), cuisine, STEP_ALLERGIES)
        if not up.get("ok"):
            logger.warning(
                "Failed update_user_cuisine_and_onboarding_step for user %s: %s",
                user.get("id"), up.get("error"))
            return {"status": "error", "error": up.get("error")}
        await self._send_text(
            user.get("whatsapp_id"),
            f"Great — I'll prioritize {cuisine.replace('_',' ').title()}. Any allergies I should know about? Reply numbers or text."
        )
        return {"status": "ok", "next_step": STEP_ALLERGIES}

    async def _handle_allergies(self, user: Dict[str, Any],
                                message: Dict[str, Any]) -> Dict[str, Any]:
        body = ""
        if message.get("type") == "text":
            body = (message.get("text") or {}).get("body", "").strip()
        elif message.get("type") == "interactive":
            body = ((message.get("interactive") or {}).get("list_reply",
                                                           {}).get("id")
                    or (message.get("interactive") or {}).get(
                        "list_reply", {}).get("title") or "")

        # Parse numeric choices or comma separated list
        allergies: List[str] = []
        if not body or body.strip() == "1" or "none" in body.lower():
            allergies = []
        else:
            parts = [
                p.strip() for p in body.replace(",", " ").split() if p.strip()
            ]
            mapping = {
                "2": "dairy",
                "3": "eggs",
                "4": "peanut",
                "5": "tree_nuts",
                "6": "wheat_gluten",
                "7": "soy",
                "8": "fish",
                "9": "shellfish",
            }
            for p in parts:
                allergies.append(mapping.get(p, p.lower()))

        up = await self.user_service.update_user_allergies_and_onboarding_step(
            user.get("id"), allergies, STEP_HOUSEHOLD)
        if not up.get("ok"):
            logger.warning(
                "Failed update_user_allergies_and_onboarding_step for user %s: %s",
                user.get("id"), up.get("error"))
            return {"status": "error", "error": up.get("error")}
        await self._send_text(
            user.get("whatsapp_id"),
            "Thanks — who are you usually cooking for? Reply:\n1-Just me\n2-Couple\n3-Small family(3-4)\n4-Big family(5+)\n5-Shared"
        )
        return {"status": "ok", "next_step": STEP_HOUSEHOLD}

    async def _handle_household(self, user: Dict[str, Any],
                                message: Dict[str, Any]) -> Dict[str, Any]:
        body = ""
        if message.get("type") == "text":
            body = (message.get("text") or {}).get("body", "").strip()
        elif message.get("type") == "interactive":
            body = ((message.get("interactive") or {}).get("list_reply",
                                                           {}).get("id")
                    or (message.get("interactive") or {}).get(
                        "list_reply", {}).get("title") or "")

        mapping = {
            "1": "single",
            "2": "couple",
            "3": "small_family",
            "4": "big_family",
            "5": "shared",
        }
        household = mapping.get(body) or (body.lower().replace(" ", "_")
                                          if body else "single")

        up = await self.user_service.update_user_household_and_complete_onboarding(
            user.get("id"), household)
        if not up.get("ok"):
            logger.warning(
                "Failed update_user_household_and_complete_onboarding for user %s: %s",
                user.get("id"), up.get("error"))
            # best-effort: still notify user
            await self._send_text(
                user.get("whatsapp_id"),
                "Thanks — your onboarding should be complete. Try asking 'What's for dinner?'"
            )
            return {"status": "error", "error": up.get("error")}

        # Normalize returned updated user
        updated_user = up.get("result") or up.get("user") or user
        if isinstance(updated_user, list) and updated_user:
            updated_user = updated_user[0]

        # ensure we have a dict
        if not isinstance(updated_user, dict):
            updated_user = user

        # build summary safely
        name = updated_user.get("name") or updated_user.get(
            "whatsapp_id") or user.get("name") or "Guest"
        diet = updated_user.get("diet") or updated_user.get(
            "diet_pref") or "both"
        cuisine = updated_user.get("cuisine_pref") or updated_user.get(
            "cuisine") or "surprise"
        allergies = updated_user.get("allergies") or []
        household_size = updated_user.get(
            "household_size") or updated_user.get("household") or "unknown"

        summary = (
            f"Mambo ✨: Your profile is complete!\n\n"
            f"• Name: {name}\n"
            f"• Diet: {diet}\n"
            f"• Cuisine: {cuisine.replace('_',' ').title()}\n"
            f"• Allergies: {', '.join(allergies) if allergies else 'None'}\n"
            f"• Household: {household_size}\n\n"
            "Ready for your first meal suggestion? Just ask 'What's for dinner?' 🍽️"
        )
        await self._send_text(user.get("whatsapp_id"), summary)
        return {
            "status": "ok",
            "next_step": STEP_COMPLETE,
            "user": updated_user
        }
