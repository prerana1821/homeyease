# app/services/intent_classifier.py
"""
Intent classification service using deterministic rules first, OpenAI fallback second.

Design goals:
- Fast, high-precision rule matching (regex + keyword) to avoid LLM calls when possible.
- Robust LLM fallback with retries, executed off the event loop.
- Optional verbose diagnostics for debugging.
- Defensive parsing of LLM response and safe logging (no secrets leaked).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Dict, List, Optional, Pattern, Tuple, Union

try:
    # new-style client
    from openai import OpenAI
except Exception:
    OpenAI = None  # will be handled later

try:
    # older/newer SDKs sometimes expose exceptions in different modules
    from openai.error import OpenAIError, RateLimitError, AuthenticationError  # type: ignore
except Exception:
    try:
        # Some versions use direct attributes on package (rare), try guard
        OpenAIError = getattr(__import__("openai"), "OpenAIError", Exception)
        RateLimitError = getattr(__import__("openai"), "RateLimitError", Exception)
        AuthenticationError = getattr(
            __import__("openai"), "AuthenticationError", Exception
        )
    except Exception:
        # Last resort: alias to Exception so our error handling remains functional
        OpenAIError = Exception
        RateLimitError = Exception
        AuthenticationError = Exception

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _mask_key(k: Optional[str]) -> str:
    if not k:
        return "(none)"
    if len(k) <= 8:
        return k
    return f"{k[:4]}...{k[-4:]}"


class IntentClassifier:

    def __init__(self):
        # LLM client (may be None)
        self.openai_client: Optional[OpenAI] = None
        try:
            if OpenAI and getattr(settings, "openai_api_key", None):
                try:
                    self.openai_client = OpenAI(api_key=settings.openai_api_key)
                    logger.info("✅ OpenAI client created successfully")
                except Exception as exc:
                    logger.exception("❌ Failed creating OpenAI client: %s", exc)
                    self.openai_client = None
            else:
                logger.info("ℹ️ OpenAI client not configured or library missing.")
        except Exception as exc:
            # Should not crash the app; just log and continue
            logger.exception("Unexpected error initializing OpenAI client: %s", exc)
            self.openai_client = None

        # Model name configurable via settings (safe default: gpt-5)
        self.openai_model = getattr(settings, "openai_model", "gpt-5")

        # keyword lists (kept readable) — these will be compiled into regexes for efficiency
        self.intent_keywords: Dict[str, List[str]] = {
            "RECIPE_REQUEST": [
                r"recipe for",
                r"how to make",
                r"how do i cook",
                r"how to prepare",
                r"cooking method",
                r"cooking steps",
                r"preparation steps",
                r"ingredients needed for",
                r"cooking time for",
                r"cooking instructions for",
            ],
            "PANTRY_HELP": [
                r"what can i make with",
                r"using these ingredients",
                r"i have .* what can i",
                r"use up these",
                r"leftover .* what to",
                r"ingredients at home",
                r"with what i have",
                r"from my pantry",
                r"available ingredients .* make",
            ],
            "DIETARY_QUERY": [
                r"vegan option",
                r"vegetarian option",
                r"gluten free",
                r"dairy free",
                r"low carb",
                r"keto friendly",
                r"healthy option",
                r"diet food",
                r"low calorie",
                r"sugar free",
                r"allergy free",
                r"without dairy",
                r"substitute for",
                r"avoid .* because",
            ],
            "PLANWEEK": [
                r"plan my week",
                r"weekly plan",
                r"meal plan",
                r"weekly meal plan",
                r"plan meals for week",
                r"7 day plan",
                r"weekly menu",
                r"meal planning",
            ],
            "UPLOAD_IMAGE": [
                r"send photo",
                r"upload image",
                r"picture of food",
                r"food photo",
                r"recognize this",
                r"identify this",
                r"scan this",
                r"check this image",
                r"what('?s| is) in this (picture|photo|image)",
                r"analyze photo",
            ],
            "MOOD": [
                r"in the mood for",
                r"craving",
                r"fancy something",
                r"feel like eating",
                r"want something spicy",
                r"want something sweet",
                r"comfort food",
                r"something filling",
                r"something light",
                r"dying for",
            ],
            "WHATSDINNER": [
                r"what should i eat",
                r"meal suggestion",
                r"suggest (a )?meal",
                r"dinner ideas",
                r"food suggestions",
                r"what should i cook",
                r"suggest something to eat",
                r"what (for )?(dinner|lunch|breakfast)",
                r"cook something",
                r"make something to eat",
                r"cooking inspiration",
            ],
            "ONBOARDING": [
                r"getting started",
                r"how to use",
                r"setup preferences",
                r"configure profile",
                r"reset preferences",
                r"change settings",
                r"update profile",
                r"help me start",
                r"how does this work",
            ],
        }

        # Pre-compile regexes to patterns for speed and reduce per-call overhead
        self._compiled_patterns: List[Tuple[str, Pattern]] = []
        for intent, patterns in self.intent_keywords.items():
            for p in patterns:
                try:
                    # case-insensitive, multiline safe
                    compiled = re.compile(p, flags=re.IGNORECASE | re.UNICODE)
                    self._compiled_patterns.append((intent, compiled))
                except re.error:
                    logger.exception(
                        "Failed to compile pattern '%s' for intent %s", p, intent
                    )

        # Some fuzzy patterns for typos/variations (simple substring checks)
        self._fuzzy_patterns = {
            "WHATSDINNER": [
                "wat to eat",
                "wat should i eat",
                "food suggest",
                "meal suggest",
                "wat to cook",
                "wat for dinner",
            ],
            "MOOD": [
                "want spicy",
                "want sweet",
                "craving spic",
                "want hot food",
                "feel like eating",
            ],
            "PLANWEEK": ["plan week", "week plan", "meal plan week", "weekly food"],
        }

        # Hinglish regexes (compiled)
        self._hinglish_patterns: List[Tuple[str, Pattern]] = []
        hinglish_patterns = {
            "WHATSDINNER": [
                r"\b(aaj|aj)\s+(kya)\s+(banau|banao|pakau|pakao|khana)\b",
                r"\b(kya)\s+(banau|banao|pakau|pakao|khana)\b",
                r"\b(khane|khaane)\s+(mein|me)\s+kya\b",
                r"\bkuch\s+(suggest|bata|batao|karo)\b",
            ],
            "PANTRY_HELP": [
                r"\bmere\s+paas\s+.*\s+(hai|he)\s+.*\s+(kya)\s+(bana|banau|banao)\b",
                r"\byeh\s+ingredients\s+se\s+(kya)\s+(bana|banau|banao)\b",
            ],
            "RECIPE_REQUEST": [
                r"\b(kaise|kaise)\s+(banate|banaye|banau|banaate)\b",
                r"\brecipe\s+(batao|bata)\b",
            ],
        }
        for intent, patterns in hinglish_patterns.items():
            for p in patterns:
                try:
                    self._hinglish_patterns.append(
                        (intent, re.compile(p, flags=re.IGNORECASE | re.UNICODE))
                    )
                except re.error:
                    logger.exception(
                        "Failed to compile hinglish pattern '%s' for intent %s",
                        p,
                        intent,
                    )

    # Public API: returns string by default, or dict when verbose=True
    async def classify_intent(
        self, text: str, verbose: bool = False
    ) -> Union[str, Dict[str, object]]:
        text_str = (text or "").strip()
        text_lower = text_str.lower()
        diagnostics: Dict[str, object] = {"text_preview": text_str[:200]}

        # 1) rule-based pattern matching (compiled regexes) — highest priority
        pattern_result = self._pattern_match(text_str)
        if pattern_result:
            diagnostics["method"] = "pattern"
            diagnostics["intent"] = pattern_result
            return (
                {"intent": pattern_result, "diagnostics": diagnostics}
                if verbose
                else pattern_result
            )

        # 2) precise keyword matching (explicit word boundaries)
        keyword_result = self._precise_keyword_match(text_str)
        if keyword_result:
            diagnostics["method"] = "keyword"
            diagnostics["intent"] = keyword_result
            return (
                {"intent": keyword_result, "diagnostics": diagnostics}
                if verbose
                else keyword_result
            )

        # 3) hinglish (degraded but useful) patterns
        hinglish_result = self._hinglish_pattern_match(text_str)
        if hinglish_result:
            diagnostics["method"] = "hinglish"
            diagnostics["intent"] = hinglish_result
            return (
                {"intent": hinglish_result, "diagnostics": diagnostics}
                if verbose
                else hinglish_result
            )

        # 4) fuzzy substring matches
        fuzzy_result = self._fuzzy_keyword_match(text_lower)
        if fuzzy_result:
            diagnostics["method"] = "fuzzy"
            diagnostics["intent"] = fuzzy_result
            return (
                {"intent": fuzzy_result, "diagnostics": diagnostics}
                if verbose
                else fuzzy_result
            )

        # 5) LLM fallback (if configured)
        llm_intent = None
        if self.openai_client:
            try:
                llm_intent, llm_diag = await self._classify_with_openai(text_str)
                diagnostics["method"] = "openai"
                diagnostics["openai"] = llm_diag
                if llm_intent:
                    diagnostics["intent"] = llm_intent
                    return (
                        {"intent": llm_intent, "diagnostics": diagnostics}
                        if verbose
                        else llm_intent
                    )
            except Exception as exc:
                logger.exception("OpenAI fallback failed: %s", exc)
                diagnostics["openai_error"] = str(exc)

        # 6) final fallback simple heuristic
        final = self._simple_fallback(text_lower)
        diagnostics["method"] = "heuristic_fallback"
        diagnostics["intent"] = final
        return {"intent": final, "diagnostics": diagnostics} if verbose else final

    # --- pattern and keyword helpers ---
    def _precise_keyword_match(self, text: str) -> Optional[str]:
        """Try exact phrase / keyword matches using word boundaries for safety."""
        # Use the compiled patterns as primary; this step can be a lighter check: explicit phrase boundary checks
        for intent, pat in self._compiled_patterns:
            if pat.search(text):
                return intent
        return None

    def _fuzzy_keyword_match(self, text: str) -> Optional[str]:
        for intent, patterns in self._fuzzy_patterns.items():
            for p in patterns:
                if p in text:
                    return intent
        return None

    def _pattern_match(self, text: str) -> Optional[str]:
        # Highest-priority complex patterns (e.g. recipes, pantry)
        # Reuse compiled patterns (they capture many cases already)
        for intent, pat in self._compiled_patterns:
            if pat.search(text):
                return intent
        return None

    def _hinglish_pattern_match(self, text: str) -> Optional[str]:
        for intent, pat in self._hinglish_patterns:
            if pat.search(text):
                return intent
        return None

    def _simple_fallback(self, text_lower: str) -> str:
        """Basic fallback used when rules + LLM don't yield a confident intent."""
        if any(w in text_lower for w in ("recipe", "how to", "cook", "make")):
            return "RECIPE_REQUEST"
        if any(
            w in text_lower
            for w in (
                "what's for dinner",
                "what for dinner",
                "what to eat",
                "what should i eat",
                "what should i cook",
            )
        ):
            return "WHATSDINNER"
        if any(
            w in text_lower
            for w in ("i have", "leftover", "in my pantry", "ingredients")
        ):
            return "PANTRY_HELP"
        if any(
            w in text_lower
            for w in ("weekly", "plan my week", "meal plan", "plan week")
        ):
            return "PLANWEEK"
        return "OTHER"

    # --- OpenAI fallback (runs in threadpool to avoid blocking) ---
    async def _classify_with_openai(
        self, text: str
    ) -> Tuple[Optional[str], Dict[str, object]]:
        """
        Returns (intent or None, diagnostics).
        Implements a small retry/backoff on transient errors (rate limits etc.).
        """
        diagnostics: Dict[str, object] = {"model": self.openai_model}
        # Be conservative with retries
        max_attempts = 3
        backoff = 0.8

        # Build prompt carefully
        system_msg = (
            "You are a terse classifier for a WhatsApp cooking assistant called Mambo. "
            "Return only a single intent token (no punctuation). "
            "Valid intents: WHATSDINNER, PLANWEEK, UPLOAD_IMAGE, MOOD, RECIPE_REQUEST, PANTRY_HELP, DIETARY_QUERY, ONBOARDING, OTHER."
        )
        user_msg = text

        for attempt in range(1, max_attempts + 1):
            diagnostics[f"attempt_{attempt}"] = {"timestamp": time.time()}
            try:
                # run blocking client in threadpool
                loop = asyncio.get_event_loop()
                func = lambda: self.openai_client.chat.completions.create(
                    model=self.openai_model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=16,
                    temperature=0.0,
                )
                resp = await loop.run_in_executor(None, func)

                # Defensive parsing: support SDK objects and dict-like shapes
                content = None
                try:
                    # openai-python typically returns an object with .choices -> list -> message.content
                    if hasattr(resp, "choices"):
                        choice = resp.choices[0]
                        # some SDK versions: choice.message.content vs choice["message"]["content"]
                        if getattr(choice, "message", None) and getattr(
                            choice.message, "content", None
                        ):
                            content = choice.message.content
                        elif isinstance(choice, dict) and choice.get("message", {}).get(
                            "content"
                        ):
                            content = choice["message"]["content"]
                        elif getattr(choice, "text", None):
                            content = choice.text
                    elif isinstance(resp, dict):
                        # fallback structure
                        choices = resp.get("choices") or []
                        if choices and isinstance(choices[0], dict):
                            content = choices[0].get("message", {}).get(
                                "content"
                            ) or choices[0].get("text")
                except Exception:
                    logger.exception("Failed to parse OpenAI response structure")

                diagnostics[f"attempt_{attempt}"]["raw_resp_preview"] = str(resp)[:400]
                if not content:
                    diagnostics[f"attempt_{attempt}"]["warning"] = "no_content_returned"
                    # treat as transient and retry
                    raise OpenAIError("empty_content")

                intent_candidate = content.strip().upper()
                # sanitize: keep only known intents (otherwise OTHER)
                valid = {
                    "WHATSDINNER",
                    "PLANWEEK",
                    "UPLOAD_IMAGE",
                    "MOOD",
                    "RECIPE_REQUEST",
                    "PANTRY_HELP",
                    "DIETARY_QUERY",
                    "ONBOARDING",
                    "OTHER",
                }
                if intent_candidate in valid:
                    diagnostics["final_intent"] = intent_candidate
                    return intent_candidate, diagnostics
                else:
                    diagnostics[f"attempt_{attempt}"]["parsed"] = intent_candidate
                    diagnostics["final_intent"] = "OTHER"
                    return "OTHER", diagnostics

            except AuthenticationError as auth_exc:
                # Bad API key — log masked key info and abort (no retry)
                diagnostics["authentication_error"] = str(auth_exc)
                logger.error(
                    "OpenAI AuthenticationError: %s (key=%s)",
                    auth_exc,
                    _mask_key(getattr(settings, "openai_api_key", None)),
                )
                return None, diagnostics
            except RateLimitError as rl_exc:
                diagnostics[f"attempt_{attempt}"]["rate_limit"] = str(rl_exc)
                logger.warning("OpenAI rate-limited on attempt %d: %s", attempt, rl_exc)
                if attempt < max_attempts:
                    await asyncio.sleep(backoff * attempt)
                    continue
                return None, diagnostics
            except OpenAIError as oe:
                diagnostics[f"attempt_{attempt}"]["openai_error"] = str(oe)
                logger.warning("OpenAIError on attempt %d: %s", attempt, oe)
                if attempt < max_attempts:
                    await asyncio.sleep(backoff * attempt)
                    continue
                return None, diagnostics
            except Exception as exc:
                diagnostics[f"attempt_{attempt}"]["exception"] = str(exc)
                logger.exception(
                    "Unexpected exception during OpenAI call attempt %d: %s",
                    attempt,
                    exc,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(backoff * attempt)
                    continue
                return None, diagnostics

        return None, diagnostics
