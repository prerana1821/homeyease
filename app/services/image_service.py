# app/services/image_service.py
"""
Image processing service for ingredient detection using Google Cloud Vision API.

Goals:
- Robust initialization from either JSON string or file path (no accidental secrets in logs).
- Run blocking Google client calls in a threadpool to avoid blocking the event loop.
- Use httpx.AsyncClient for downloads (async).
- Return consistent result shape: {"ok": bool, "ingredients": [...], "diagnostics": {...}}
- Provide helpful fallbacks and conservative confidence thresholds.
- Use logging instead of prints.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

import httpx
from google.cloud import vision
from google.oauth2 import service_account
from google.api_core.exceptions import GoogleAPICallError, RetryError

logger = logging.getLogger(__name__)

# Conservative thresholds
_LABEL_CONF_THRESHOLD = 0.65
_OBJECT_CONF_THRESHOLD = 0.5


class ImageService:
    def __init__(self) -> None:
        """
        Initialize ImageService.

        Expected credential sources (in order):
        1) GOOGLE_APPLICATION_CREDENTIALS env var containing a **JSON string** (not a path)
           - Useful in containerized envs where secrets are injected.
        2) GOOGLE_APPLICATION_CREDENTIALS_FILE env var containing a path to JSON file.
        3) Default environment (gcloud/gke service account, ADC).
        """
        self.client: Optional[vision.ImageAnnotatorClient] = None
        self._init_diagnostics: Dict[str, Any] = {}
        self._initialize_vision_client()

    def _initialize_vision_client(self) -> None:
        """Attempt to initialize google vision client from multiple credential sources."""
        try:
            # 1) JSON string in env
            creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_FILE")

            if creds_json:
                # If the env var contains JSON text (starts with '{'), use that
                try:
                    parsed = json.loads(creds_json)
                    creds = service_account.Credentials.from_service_account_info(
                        parsed
                    )
                    self.client = vision.ImageAnnotatorClient(credentials=creds)
                    self._init_diagnostics["method"] = "from_env_json"
                    logger.info(
                        "ImageService: initialized Vision client from JSON env var."
                    )
                    return
                except Exception as exc:
                    # fall through to other methods but record diagnostics
                    self._init_diagnostics["env_json_error"] = str(exc)
                    logger.debug(
                        "ImageService: failed to init from JSON env var: %s", exc
                    )

            # 2) Explicit file path
            if creds_file and os.path.exists(creds_file):
                try:
                    creds = service_account.Credentials.from_service_account_file(
                        creds_file
                    )
                    self.client = vision.ImageAnnotatorClient(credentials=creds)
                    self._init_diagnostics["method"] = "from_file_path"
                    logger.info(
                        "ImageService: initialized Vision client from credentials file."
                    )
                    return
                except Exception as exc:
                    self._init_diagnostics["file_path_error"] = str(exc)
                    logger.debug("ImageService: failed to init from file path: %s", exc)

            # 3) Default credentials (ADC)
            try:
                self.client = vision.ImageAnnotatorClient()
                self._init_diagnostics["method"] = "default_adc"
                logger.info("ImageService: initialized Vision client via ADC.")
                return
            except Exception as exc:
                self._init_diagnostics["adc_error"] = str(exc)
                logger.exception("ImageService: ADC initialization failed: %s", exc)

        except Exception as exc:
            logger.exception("ImageService: unexpected error during init: %s", exc)
            self._init_diagnostics["unexpected_init_error"] = str(exc)

        # If we reached here, client not available
        self.client = None
        logger.warning(
            "ImageService: Vision client not available; image ops will use fallback. init_diag=%s",
            self._init_diagnostics,
        )

    # -----------------------
    # Public API (consistent return shapes)
    # -----------------------
    async def detect_ingredients_from_url(self, image_url: str) -> Dict[str, Any]:
        """Download image and analyze; returns {'ok', 'ingredients', 'diagnostics'}."""
        diag: Dict[str, Any] = {"source": "url", "url": image_url}
        if not image_url:
            return {
                "ok": False,
                "ingredients": [],
                "diagnostics": {"error": "empty_url"},
            }

        # Download image content (async)
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                image_bytes = resp.content
                diag["download_bytes"] = len(image_bytes)
        except Exception as exc:
            logger.exception("Failed to download image from URL %s: %s", image_url, exc)
            diag["download_error"] = str(exc)
            return {"ok": False, "ingredients": [], "diagnostics": diag}

        return await self._analyze_image_content(image_bytes, diag)

    async def detect_ingredients_from_base64(self, image_base64: str) -> Dict[str, Any]:
        """Accept base64 image string and analyze."""
        diag: Dict[str, Any] = {"source": "base64"}
        if not image_base64:
            return {
                "ok": False,
                "ingredients": [],
                "diagnostics": {"error": "empty_base64"},
            }

        try:
            import base64

            image_bytes = base64.b64decode(image_base64)
            diag["decoded_bytes"] = len(image_bytes)
        except Exception as exc:
            logger.exception("Failed to decode base64 image: %s", exc)
            diag["decode_error"] = str(exc)
            return {"ok": False, "ingredients": [], "diagnostics": diag}

        return await self._analyze_image_content(image_bytes, diag)

    async def _analyze_image_content(
        self, image_content: bytes, diag: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Core analysis pipeline. Runs blocking Vision SDK calls in a threadpool."""
        diag = diag or {}
        if not image_content:
            diag["error"] = "empty_image_content"
            return {"ok": False, "ingredients": [], "diagnostics": diag}

        if self.client is None:
            # Provide fallback suggestions when Vision client isn't available
            diag["vision_client"] = "unavailable"
            logger.warning(
                "ImageService: Vision client unavailable; using fallback ingredients."
            )
            return {
                "ok": False,
                "ingredients": self._fallback_ingredients(),
                "diagnostics": diag,
            }

        loop = asyncio.get_event_loop()
        try:
            # Run label_detection and object_localization in threadpool
            def sync_detect():
                # create proto image
                image = vision.Image(content=image_content)
                labels = self.client.label_detection(image=image)
                objects = self.client.object_localization(image=image)
                return labels, objects

            labels_resp, objects_resp = await loop.run_in_executor(None, sync_detect)

            # Extract annotations defensively
            labels = getattr(labels_resp, "label_annotations", []) or []
            objects = getattr(objects_resp, "localized_object_annotations", []) or []

            diag["labels_count"] = len(labels)
            diag["objects_count"] = len(objects)

            detected_items: List[str] = []

            for label in labels:
                try:
                    score = float(getattr(label, "score", 0.0) or 0.0)
                    desc = getattr(label, "description", "") or ""
                    if score >= _LABEL_CONF_THRESHOLD and desc:
                        detected_items.append(desc.lower())
                except Exception:
                    continue

            for obj in objects:
                try:
                    score = float(getattr(obj, "score", 0.0) or 0.0)
                    name = getattr(obj, "name", "") or ""
                    if score >= _OBJECT_CONF_THRESHOLD and name:
                        detected_items.append(name.lower())
                except Exception:
                    continue

            diag["raw_detected_items_preview"] = detected_items[:20]

            # Map detected items to canonical ingredients and filter
            ingredients = self._filter_food_items(detected_items)
            diag["mapped_count"] = len(ingredients)

            if ingredients:
                logger.info("ImageService: detected ingredients: %s", ingredients)
                return {"ok": True, "ingredients": ingredients, "diagnostics": diag}

            # If nothing detected at high-confidence, return fallback (but keep diagnostics)
            logger.info(
                "ImageService: no high-confidence ingredients found; returning fallback."
            )
            diag["note"] = "no_high_confidence_detections"
            return {
                "ok": False,
                "ingredients": self._fallback_ingredients(),
                "diagnostics": diag,
            }

        except (GoogleAPICallError, RetryError) as gexc:
            logger.exception("Google Vision API error: %s", gexc)
            diag["vision_api_error"] = str(gexc)
            return {
                "ok": False,
                "ingredients": self._fallback_ingredients(),
                "diagnostics": diag,
            }
        except Exception as exc:
            logger.exception("Unexpected error analyzing image: %s", exc)
            diag["unexpected_error"] = str(exc)
            return {
                "ok": False,
                "ingredients": self._fallback_ingredients(),
                "diagnostics": diag,
            }

    # -----------------------
    # Mapping / filtering
    # -----------------------
    def _filter_food_items(self, detected_items: List[str]) -> List[str]:
        """
        Map detected free-text items to a canonical set of ingredients.
        Returns a deduplicated list.
        """
        # canonical mapping; keep keys lowercased
        food_mappings = {
            "carrot": {"carrot", "carrots"},
            "potato": {"potato", "potatoes", "aloo"},
            "onion": {"onion", "onions", "pyaz"},
            "tomato": {"tomato", "tomatoes"},
            "bell pepper": {"bell pepper", "capsicum", "capsicums"},
            "spinach": {"spinach", "palak", "greens"},
            "cauliflower": {"cauliflower", "gobi"},
            "broccoli": {"broccoli"},
            "cucumber": {"cucumber"},
            "eggplant": {"eggplant", "brinjal", "baingan"},
            "ginger": {"ginger"},
            "garlic": {"garlic"},
            "chili": {"chili", "chilli", "chile", "pepper"},
            "apple": {"apple", "apples"},
            "banana": {"banana", "bananas"},
            "lemon": {"lemon", "lime"},
            "mango": {"mango"},
            "chicken": {"chicken", "poultry"},
            "fish": {"fish", "seafood"},
            "egg": {"egg", "eggs"},
            "meat": {"meat", "beef", "mutton"},
            "shrimp": {"shrimp", "prawn"},
            "rice": {"rice", "basmati"},
            "wheat": {"wheat", "flour"},
            "bread": {"bread", "roti", "chapati"},
            "pasta": {"pasta"},
            "beans": {"beans", "legumes"},
            "lentil": {"lentils", "dal"},
            "chickpea": {"chickpeas", "chana"},
            "milk": {"milk"},
            "cheese": {"cheese", "paneer"},
            "yogurt": {"yogurt", "curd"},
            "butter": {"butter"},
            "cumin": {"cumin"},
            "coriander": {"coriander"},
            "turmeric": {"turmeric"},
            "mustard": {"mustard", "mustard seeds"},
            "oil": {"oil", "cooking oil"},
            "salt": {"salt"},
            "sauce": {"sauce", "soy sauce", "tomato sauce"},
        }

        normalized = set()
        lowered_items = [it.lower().strip() for it in (detected_items or []) if it]

        # direct and partial matching
        for it in lowered_items:
            for canonical, variants in food_mappings.items():
                # full token match or substring match (be conservative)
                if it in variants or any(v in it for v in variants):
                    normalized.add(canonical)
                    break

        return sorted(normalized)

    def _fallback_ingredients(self) -> List[str]:
        """Conservative fallback ingredient list."""
        return ["onion", "tomato", "garlic", "mixed vegetables", "spices"]

    # -----------------------
    # Convenience: suggestions using detected ingredients
    # -----------------------
    async def get_ingredient_suggestions(
        self, detected_ingredients: List[str]
    ) -> Dict[str, Any]:
        """
        Given a list of canonical ingredients, produce simple suggestions.
        Returns standardized dict: {"ok": bool, "ingredients": [...], "suggestions": [...], "diagnostics": {...}}
        """
        diag: Dict[str, Any] = {"input_count": len(detected_ingredients or [])}
        if not detected_ingredients:
            diag["note"] = "no_detected_ingredients"
            return {
                "ok": False,
                "ingredients": [],
                "suggestions": [],
                "diagnostics": diag,
                "message": "No ingredients detected. Could you tell me what you have?",
            }

        # Simple heuristics
        has_vegetables = any(
            i in detected_ingredients
            for i in [
                "carrot",
                "potato",
                "onion",
                "tomato",
                "spinach",
                "mixed vegetables",
            ]
        )
        has_protein = any(
            i in detected_ingredients
            for i in ["chicken", "fish", "egg", "meat", "paneer", "shrimp"]
        )
        has_grains = any(
            i in detected_ingredients for i in ["rice", "wheat", "bread", "pasta"]
        )

        suggestions: List[str] = []
        if has_vegetables and has_protein:
            suggestions.extend(
                [
                    "Vegetable curry with protein",
                    "Stir-fry with protein",
                    "Mixed vegetable rice bowl",
                ]
            )
        if has_vegetables and has_grains:
            suggestions.extend(
                ["Vegetable fried rice", "Vegetable pasta", "Curry with rice"]
            )
        if has_protein and has_grains:
            suggestions.extend(["Protein biryani", "Egg fried rice", "Curry with rice"])
        if "potato" in detected_ingredients:
            suggestions.extend(["Aloo curry", "Mashed potatoes", "Potato stir-fry"])
        if "egg" in detected_ingredients:
            suggestions.extend(["Scrambled eggs", "Egg curry", "Omelet with veggies"])

        if not suggestions:
            suggestions = [
                "Simple vegetable stir-fry",
                "Basic curry",
                "Mixed ingredient soup",
            ]

        diag["generated_suggestions"] = len(suggestions)
        return {
            "ok": True,
            "ingredients": detected_ingredients,
            "suggestions": suggestions[:6],
            "diagnostics": diag,
            "message": f'I can see {", ".join(detected_ingredients)}. Here are some meal ideas:',
        }
