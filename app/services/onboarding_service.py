# app/services/onboarding_service.py
"""
OnboardingService that drives a 5-step onboarding flow.

Design goals (improvements vs previous):
- Defensive handling of DB responses (list vs dict, missing keys).
- Centralized message body extraction (text vs interactive).
- Structured diagnostics returned for every public call so callers can debug.
- Better, actionable user-facing messages when failures occur.
- Clear logging and graceful handling of sender failures without crashing the flow.
- Small utilities to normalize user rows and produce masked diagnostics for logs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from app.services.user_service import UserService

logger = logging.getLogger(__name__)

# Onboarding steps
STEP_NAME = 0
STEP_DIET = 1
STEP_CUISINE = 2
STEP_ALLERGIES = 3
STEP_HOUSEHOLD = 4
STEP_COMPLETE = 5

# Default messages (single source of truth)
MESSAGES = {
    "ask_name": "Mambo 🥘: Hi! I'm Mambo — what's your name? Reply with your first name or 'skip'.",
    "ask_what_call": "What should I call you? Reply with your name or 'skip'.",
    "ask_diet": "What's your diet preference? Reply:\n1 - Veg 🌱\n2 - Non-Veg 🍗\n3 - Both 🍽️",
    "ask_cuisine": "Which cuisine do you prefer? Reply with a number or text.",
    "ask_allergies": "Any allergies I should know about? Reply numbers (e.g. 2,3) or text (e.g. peanuts). Reply 'none' if none.",
    "ask_household": "Who are you usually cooking for? Reply:\n1-Just me\n2-Couple\n3-Small family(3-4)\n4-Big family(5+)\n5-Shared",
    "onboarding_complete_hint": "Ready for your first meal suggestion? Just ask 'What's for dinner?' 🍽️",
    "generic_send_failure": "Sorry — I'm having trouble sending messages right now. Please try again in a minute.",
    "internal_error_user": "Sorry — something went wrong while updating your profile. Please try again in a minute.",
}

# Helper typing
Diag = Dict[str, Any]


class OnboardingService:
    def __init__(
        self,
        message_sender: Optional[Any] = None,
        user_service: Optional[UserService] = None,
    ) -> None:
        """
        Args:
            message_sender: object implementing send_text(to, body) -> dict,
                            send_media(to, urls, body) -> dict (async).
            user_service: optional override for testing.
        """
        self.message_sender = message_sender
        self.user_service = user_service or UserService()

    # -----------------------
    # Helper utilities
    # -----------------------
    def _mask_key(self, s: Optional[str]) -> str:
        """Mask a long secret-like string for safe logs/diagnostics."""
        if not s:
            return "(empty)"
        if len(s) <= 8:
            return s
        return f"{s[:4]}...{s[-4:]}"

    def _normalize_user_row(self, user_row: Any) -> Optional[Dict[str, Any]]:
        """
        Ensure user_row is a dict (not a list) and return it.
        Accepts: None, dict, list[dict]
        """
        if not user_row:
            return None
        if isinstance(user_row, list):
            if not user_row:
                return None
            # prefer first row
            first = user_row[0]
            return first if isinstance(first, dict) else None
        if isinstance(user_row, dict):
            return user_row
        # unknown shape
        return None

    def _extract_body(self, message: Dict[str, Any]) -> str:
        """
        Extract text body from incoming message dict, handling interactive shapes.
        Always returns a trimmed string (possibly empty).
        """
        if not isinstance(message, dict):
            return ""
        mtype = message.get("type")
        if mtype == "text":
            return ((message.get("text") or {}).get("body") or "").strip()
        if mtype == "interactive":
            interactive = message.get("interactive") or {}
            # list_reply has id/title; button_reply has id/title
            lr = interactive.get("list_reply") or {}
            br = interactive.get("button_reply") or {}
            # prefer title then id
            return (
                lr.get("title") or br.get("title") or lr.get("id") or br.get("id") or ""
            ).strip()
        # fallback: try body-like fields
        return (message.get("body") or message.get("text") or "").strip()

    async def _send_text(self, to_phone: str, body: str) -> Dict[str, Any]:
        """
        Wrapper around message_sender.send_text with extra diagnostics and fail-safe behavior.
        Returns a dict: {status: 'ok'|'error', ok: bool, diagnostics: {...}}
        """
        diag: Diag = {"attempted": True, "body_preview": body[:160]}
        if not self.message_sender or not hasattr(self.message_sender, "send_text"):
            logger.debug(
                "No message sender available; dropping outbound: %s", body[:80]
            )
            return {
                "status": "error",
                "ok": False,
                "error": "no_sender_configured",
                "diagnostics": diag,
            }

        try:
            resp = await self.message_sender.send_text(to_phone, body)
            # Defensive normalization
            if not isinstance(resp, dict):
                resp = {"ok": False, "diagnostics": {"raw_resp": str(resp)}}
            diag["provider_ok"] = bool(resp.get("ok"))
            diag["provider_diag"] = resp.get("diagnostics")
            logger.info(
                "Sent text to %s; provider_ok=%s", to_phone, diag["provider_ok"]
            )
            return {
                "status": "ok" if resp.get("ok") else "error",
                "ok": bool(resp.get("ok")),
                "diagnostics": diag,
                **resp,
            }
        except Exception as exc:
            logger.exception("Error sending text to %s: %s", to_phone, exc)
            diag["exception"] = str(exc)
            return {
                "status": "error",
                "ok": False,
                "error": str(exc),
                "diagnostics": diag,
            }

    # -----------------------
    # Public API
    # -----------------------
    async def get_user_onboarding_step(self, whatsapp_id: str) -> Optional[int]:
        """Return onboarding step for user, or None on error/not found."""
        try:
            res = await self.user_service.get_user_by_whatsapp_id(whatsapp_id)
        except Exception as exc:
            logger.exception("user_service.get_user_by_whatsapp_id raised: %s", exc)
            return None

        if not isinstance(res, dict):
            logger.debug("get_user_by_whatsapp_id returned non-dict: %s", type(res))
            return None

        if not res.get("ok"):
            logger.debug("get_user_onboarding_step db failure: %s", res.get("error"))
            return None

        user_row = self._normalize_user_row(res.get("user"))
        if not user_row:
            logger.debug("get_user_onboarding_step: user not found for %s", whatsapp_id)
            return None

        step = user_row.get("onboarding_step")
        if step is None:
            return STEP_COMPLETE
        try:
            return int(step)
        except Exception:
            logger.warning(
                "Unexpected onboarding_step type for user %s: %s", whatsapp_id, step
            )
            return None

    async def start_onboarding(self, whatsapp_id: str) -> Dict[str, Any]:
        """
        Start onboarding for whatsapp_id: create user row and send the name prompt.
        Returns structured diagnostics for caller debugging.
        """
        diag: Diag = {"actions": [], "errors": []}
        logger.info("Starting onboarding for %s", whatsapp_id)

        try:
            create_res = await self.user_service.create_user(whatsapp_id)
        except Exception as exc:
            logger.exception("create_user threw for %s: %s", whatsapp_id, exc)
            diag["errors"].append({"create_user_exception": str(exc)})
            return {"status": "error", "diagnostics": diag}

        diag["create_user"] = (
            create_res.get("diagnostics")
            if isinstance(create_res, dict)
            else {"raw": str(create_res)}
        )
        if not create_res.get("ok"):
            err = create_res.get("error") or "create_user_failed"
            logger.error("create_user failed for %s: %s", whatsapp_id, err)
            diag["errors"].append({"create_user_error": err})
            return {"status": "error", "diagnostics": diag}

        user = self._normalize_user_row(create_res.get("user"))
        if not user:
            logger.error("create_user returned no user object for %s", whatsapp_id)
            diag["errors"].append({"create_user_error": "user_not_created"})
            return {"status": "error", "diagnostics": diag}

        # set onboarding step to STEP_NAME (best-effort)
        try:
            set_step_res = await self.user_service.update_user_onboarding_step(
                user.get("id"), STEP_NAME
            )
            diag["set_step"] = (
                set_step_res.get("diagnostics")
                if isinstance(set_step_res, dict)
                else {"raw": str(set_step_res)}
            )
            if not set_step_res.get("ok"):
                logger.warning(
                    "update_user_onboarding_step failed for user %s: %s",
                    user.get("id"),
                    set_step_res.get("error"),
                )
                diag["errors"].append({"set_step_error": set_step_res.get("error")})
        except Exception as exc:
            logger.exception(
                "Exception while setting onboarding step for %s: %s", whatsapp_id, exc
            )
            diag["errors"].append({"set_step_error": str(exc)})

        # send the first question and return diagnostics (do not fail flow if sending fails)
        send_res = await self._send_text(whatsapp_id, MESSAGES["ask_name"])
        diag["sent_first_question"] = send_res
        if not send_res.get("ok"):
            # user-visible fallback and logged diagnostics
            logger.warning(
                "Failed to send first question to %s: %s",
                whatsapp_id,
                send_res.get("diagnostics"),
            )
            # still return ok because user row exists; caller can retry sending later
            return {"status": "ok", "next_step": STEP_NAME, "diagnostics": diag}

        return {"status": "ok", "next_step": STEP_NAME, "diagnostics": diag}

    async def handle_onboarding_message(
        self, whatsapp_id: str, message: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Process an incoming onboarding message.
        Returns a dictionary with:
          - status: started|ok|error|complete
          - diagnostics: structured diagnostic info useful for debugging
          - next_step: suggested next step if applicable
        """
        diag: Diag = {
            "steps": [],
            "errors": [],
            "incoming_msg_preview": self._extract_body(message)[:200],
        }
        logger.info(
            "handle_onboarding_message called for %s message_type=%s",
            whatsapp_id,
            message.get("type"),
        )

        try:
            user_res = await self.user_service.get_user_by_whatsapp_id(whatsapp_id)
        except Exception as exc:
            logger.exception(
                "get_user_by_whatsapp_id raised for %s: %s", whatsapp_id, exc
            )
            # Attempt to auto-start onboarding as fallback
            start = await self.start_onboarding(whatsapp_id)
            diag["user_fetch"] = {"error": str(exc)}
            diag["actions"] = {"auto_started": start}
            return {"status": "started", "diagnostics": diag}

        diag["user_fetch"] = (
            user_res.get("diagnostics")
            if isinstance(user_res, dict)
            else {"raw": str(user_res)}
        )
        if not user_res.get("ok"):
            logger.warning(
                "get_user_by_whatsapp_id failed; auto-starting onboarding for %s",
                whatsapp_id,
            )
            start = await self.start_onboarding(whatsapp_id)
            diag["actions"] = {"auto_started": start}
            return {"status": "started", "diagnostics": diag}

        user = self._normalize_user_row(user_res.get("user"))
        if not user:
            logger.info("User not present; starting onboarding for %s", whatsapp_id)
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
                logger.warning(
                    "Invalid onboarding_step for user %s: %s", whatsapp_id, raw_step
                )
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
                result = {"status": "complete", "message": "onboarding complete"}
        except Exception as exc:
            logger.exception(
                "Unhandled exception in onboarding handler for %s: %s", whatsapp_id, exc
            )
            result = {"status": "error", "error": str(exc)}
        # attach handler result and bubble diagnostics
        diag["step_result"] = result
        response = {"status": result.get("status", "ok"), "diagnostics": diag}
        # attach other keys except diagnostics
        for k, v in result.items():
            if k == "diagnostics":
                continue
            response[k] = v
        return response

    # ---- step implementations ----
    async def _handle_name(
        self, user: Dict[str, Any], message: Dict[str, Any]
    ) -> Dict[str, Any]:
        body = self._extract_body(message)
        if not body:
            send_res = await self._send_text(
                user.get("whatsapp_id") or user.get("whatsapp") or "",
                MESSAGES["ask_what_call"],
            )
            return {
                "status": "ok",
                "message": "reasked",
                "diagnostics": {"send": send_res},
            }

        name = "Guest" if body.lower() == "skip" else body[:64]
        try:
            up = await self.user_service.update_user_name_and_onboarding_step(
                user.get("id"), name, STEP_DIET
            )
        except Exception as exc:
            logger.exception(
                "update_user_name_and_onboarding_step failed for user %s: %s",
                user.get("id"),
                exc,
            )
            return {"status": "error", "error": "db_update_failed"}

        if not up.get("ok"):
            logger.warning(
                "Failed update_user_name_and_onboarding_step for user %s: %s",
                user.get("id"),
                up.get("error"),
            )
            return {
                "status": "error",
                "error": up.get("error"),
                "diagnostics": {"update_resp": up.get("diagnostics")},
            }

        # Normalize updated user representation if present
        updated = self._normalize_user_row(up.get("result") or up.get("user") or user)
        updated_id = (updated or {}).get("id") or user.get("id")

        # Persist outgoing messages and session
        send1 = await self._send_text(
            updated.get("whatsapp_id") if updated else user.get("whatsapp_id"),
            f"Lovely — Hi {name}! I'll remember that.",
        )
        send2 = await self._send_text(
            updated.get("whatsapp_id") if updated else user.get("whatsapp_id"),
            MESSAGES["ask_diet"],
        )

        # best-effort create session; don't fail flow if session creation fails
        session_diag = None
        try:
            sess = await self.user_service.create_session(
                updated_id, prompt="onboarding_name", response_text=f"name={name}"
            )
            session_diag = (
                sess.get("diagnostics")
                if isinstance(sess, dict)
                else {"raw": str(sess)}
            )
        except Exception:
            logger.exception(
                "create_session failed (non-fatal) for user %s", user.get("id")
            )

        return {
            "status": "ok",
            "next_step": STEP_DIET,
            "diagnostics": {"sends": [send1, send2], "session": session_diag},
        }

    async def _handle_diet(
        self, user: Dict[str, Any], message: Dict[str, Any]
    ) -> Dict[str, Any]:
        body = self._extract_body(message)
        mapping = {
            "1": "veg",
            "2": "non-veg",
            "3": "both",
            "veg": "veg",
            "non-veg": "non-veg",
            "both": "both",
        }
        diet = mapping.get(body.lower(), "both")
        try:
            up = await self.user_service.update_user_diet_and_onboarding_step(
                user.get("id"), diet, STEP_CUISINE
            )
        except Exception as exc:
            logger.exception(
                "update_user_diet_and_onboarding_step failed for %s: %s",
                user.get("id"),
                exc,
            )
            return {"status": "error", "error": "db_update_failed"}

        if not up.get("ok"):
            logger.warning(
                "Failed update_user_diet_and_onboarding_step for user %s: %s",
                user.get("id"),
                up.get("error"),
            )
            return {"status": "error", "error": up.get("error")}

        send1 = await self._send_text(
            user.get("whatsapp_id"), f"Noted — {diet}. Which cuisine do you prefer?"
        )
        cuisines = "\n".join(
            [
                f"{i+1}. {c}"
                for i, c in enumerate(
                    [
                        "North Indian",
                        "South Indian",
                        "Chinese",
                        "Italian",
                        "Punjabi",
                        "Gujarati",
                        "Bengali",
                        "International",
                        "Surprise",
                    ]
                )
            ]
        )
        send2 = await self._send_text(user.get("whatsapp_id"), cuisines)
        return {
            "status": "ok",
            "next_step": STEP_CUISINE,
            "diagnostics": {"sends": [send1, send2]},
        }

    async def _handle_cuisine(
        self, user: Dict[str, Any], message: Dict[str, Any]
    ) -> Dict[str, Any]:
        body = self._extract_body(message)
        mapping = {
            str(i + 1): val
            for i, val in enumerate(
                [
                    "north_indian",
                    "south_indian",
                    "chinese",
                    "italian",
                    "punjabi",
                    "gujarati",
                    "bengali",
                    "international",
                    "surprise",
                ]
            )
        }
        cuisine = mapping.get(body) or (
            body.lower().replace(" ", "_") if body else "surprise"
        )
        try:
            up = await self.user_service.update_user_cuisine_and_onboarding_step(
                user.get("id"), cuisine, STEP_ALLERGIES
            )
        except Exception as exc:
            logger.exception(
                "update_user_cuisine_and_onboarding_step failed for %s: %s",
                user.get("id"),
                exc,
            )
            return {"status": "error", "error": "db_update_failed"}

        if not up.get("ok"):
            logger.warning(
                "Failed update_user_cuisine_and_onboarding_step for user %s: %s",
                user.get("id"),
                up.get("error"),
            )
            return {"status": "error", "error": up.get("error")}

        send = await self._send_text(
            user.get("whatsapp_id"),
            f"Great — I'll prioritize {cuisine.replace('_',' ').title()}. {MESSAGES['ask_allergies']}",
        )
        return {
            "status": "ok",
            "next_step": STEP_ALLERGIES,
            "diagnostics": {"sends": [send]},
        }

    async def _handle_allergies(
        self, user: Dict[str, Any], message: Dict[str, Any]
    ) -> Dict[str, Any]:
        body = self._extract_body(message)
        allergies: List[str] = []
        if not body or body.strip() == "1" or "none" in body.lower():
            allergies = []
        else:
            parts = [p.strip() for p in body.replace(",", " ").split() if p.strip()]
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

        try:
            up = await self.user_service.update_user_allergies_and_onboarding_step(
                user.get("id"), allergies, STEP_HOUSEHOLD
            )
        except Exception as exc:
            logger.exception(
                "update_user_allergies_and_onboarding_step failed for %s: %s",
                user.get("id"),
                exc,
            )
            return {"status": "error", "error": "db_update_failed"}

        if not up.get("ok"):
            logger.warning(
                "Failed update_user_allergies_and_onboarding_step for user %s: %s",
                user.get("id"),
                up.get("error"),
            )
            return {"status": "error", "error": up.get("error")}

        send = await self._send_text(user.get("whatsapp_id"), MESSAGES["ask_household"])
        return {
            "status": "ok",
            "next_step": STEP_HOUSEHOLD,
            "diagnostics": {"sends": [send]},
        }

    async def _handle_household(
        self, user: Dict[str, Any], message: Dict[str, Any]
    ) -> Dict[str, Any]:
        body = self._extract_body(message)
        mapping = {
            "1": "single",
            "2": "couple",
            "3": "small_family",
            "4": "big_family",
            "5": "shared",
        }
        household = mapping.get(body) or (
            body.lower().replace(" ", "_") if body else "single"
        )

        try:
            up = await self.user_service.update_user_household_and_complete_onboarding(
                user.get("id"), household
            )
        except Exception as exc:
            logger.exception(
                "update_user_household_and_complete_onboarding failed for %s: %s",
                user.get("id"),
                exc,
            )
            # best-effort: still notify user
            await self._send_text(
                user.get("whatsapp_id"), MESSAGES["internal_error_user"]
            )
            return {"status": "error", "error": "db_update_failed"}

        if not up.get("ok"):
            logger.warning(
                "Failed update_user_household_and_complete_onboarding for user %s: %s",
                user.get("id"),
                up.get("error"),
            )
            await self._send_text(
                user.get("whatsapp_id"), MESSAGES["internal_error_user"]
            )
            return {"status": "error", "error": up.get("error")}

        # Normalize returned updated user; fallback to original user
        updated_user = (
            self._normalize_user_row(up.get("result") or up.get("user")) or user
        )

        # Normalize fields safely and build a friendly summary
        name = (
            updated_user.get("name")
            or updated_user.get("whatsapp_id")
            or user.get("name")
            or "Guest"
        )
        diet = updated_user.get("diet") or updated_user.get("diet_pref") or "both"
        cuisine = (
            updated_user.get("cuisine_pref")
            or updated_user.get("cuisine")
            or "surprise"
        )
        allergies = updated_user.get("allergies") or []
        household_size = (
            updated_user.get("household_size")
            or updated_user.get("household")
            or "unknown"
        )

        summary = (
            f"Mambo ✨: Your profile is complete!\n\n"
            f"• Name: {name}\n"
            f"• Diet: {diet}\n"
            f"• Cuisine: {cuisine.replace('_',' ').title()}\n"
            f"• Allergies: {', '.join(allergies) if allergies else 'None'}\n"
            f"• Household: {household_size}\n\n"
            f"{MESSAGES['onboarding_complete_hint']}"
        )

        send_res = await self._send_text(user.get("whatsapp_id"), summary)
        return {
            "status": "ok",
            "next_step": STEP_COMPLETE,
            "user": updated_user,
            "diagnostics": {"send": send_res},
        }
