# app/services/recommendation_service.py
"""
Meal recommendation service using user preferences and intelligent filtering.

Improvements:
- Defensive handling of external service return shapes (dict vs list vs exceptions).
- Explicit enforcement of diet & allergy filters.
- Better intent fallback and parsing if classifier fails.
- Optional verbose diagnostics (verbose=True) for debugging and observability.
- Clear behavior on edge cases (no user, no meals, DB errors).
"""
from __future__ import annotations

import logging
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.meal_service import MealService
from app.services.user_service import UserService
from app.services.intent_classifier import IntentClassifier

logger = logging.getLogger(__name__)

DEFAULT_MAX = 3


class RecommendationService:

    def __init__(self):
        self.meal_service = MealService()
        self.user_service = UserService()
        self.intent_classifier = IntentClassifier()

    # -----------------------
    # Helpers
    # -----------------------
    def _mask(self, s: Optional[str]) -> str:
        if not s:
            return "(empty)"
        return s if len(s) <= 8 else f"{s[:4]}...{s[-4:]}"

    def _normalize_user_row(self, maybe_user: Any) -> Optional[Dict[str, Any]]:
        """
        Normalize possible user_service return shapes (dict, list[dict], None).
        The UserService in your app often returns {'ok': True, 'user': {...}}.
        The caller of this helper should pass maybe_user = res.get("user") or res.
        """
        if not maybe_user:
            return None
        if isinstance(maybe_user, dict):
            return maybe_user
        if isinstance(maybe_user, list) and maybe_user:
            first = maybe_user[0]
            return first if isinstance(first, dict) else None
        return None

    def _apply_preferences_filter(
        self, meals: List[Dict[str, Any]], criteria: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Filter meals by diet and allergies. This is a defensive layer even if MealService supports filters."""
        diet = (criteria.get("diet") or "").lower() if criteria.get("diet") else None
        allergies = set([a.lower() for a in (criteria.get("allergies") or [])])

        def meal_allowed(meal: Dict[str, Any]) -> bool:
            # diet enforcement: if user veg and meal is non-veg, exclude
            meal_diet = (meal.get("diet_type") or meal.get("diet") or "").lower()
            if (
                diet
                and diet in ("veg", "vegetarian")
                and meal_diet
                and meal_diet not in ("veg", "vegetarian", "plant-based")
            ):
                return False
            # allergies: ensure none of the user's allergies are present in ingredient list or tags
            meal_ings = " ".join([str(x).lower() for x in meal.get("ingredients", [])])
            meal_tags = " ".join([str(x).lower() for x in meal.get("tags", [])])
            for a in allergies:
                if a and (a in meal_ings or a in meal_tags):
                    return False
            return True

        filtered = [m for m in meals if meal_allowed(m)]
        return filtered

    def _format_recommendation_text(self, rec: Dict[str, Any]) -> str:
        """Produce a user-friendly short text snippet for a single recommendation."""
        name = rec.get("name") or "Unknown"
        cuisine = (
            rec.get("cuisine", "").replace("_", " ").title()
            if rec.get("cuisine")
            else ""
        )
        time_part = (
            f" ({rec.get('estimated_time_min')} min)"
            if rec.get("estimated_time_min")
            else ""
        )
        extras = []
        if rec.get("diet_type"):
            extras.append(rec.get("diet_type"))
        if rec.get("tags"):
            extras.extend([t for t in rec.get("tags")[:2]])
        extras_text = f" — {', '.join(extras)}" if extras else ""
        return f"{name}{time_part}{' — ' + cuisine if cuisine else ''}{extras_text}"

    def _extract_ingredients_from_message(self, message: str) -> List[str]:
        """
        Slightly better extraction that looks for words and simple comma lists.
        This keeps the existing ingredient list but adds minor normalization.
        """
        message_lower = (message or "").lower()
        # tokenized by non-alpha characters, keep short tokens
        tokens = re.split(r"[^a-zA-Z]+", message_lower)
        tokens = [t for t in tokens if len(t) > 1]
        # known ingredients from domain list (could be DRYed out)
        common = {
            "chicken",
            "fish",
            "egg",
            "eggs",
            "paneer",
            "potato",
            "potatoes",
            "onion",
            "onions",
            "tomato",
            "tomatoes",
            "rice",
            "dal",
            "lentils",
            "spinach",
            "cauliflower",
            "beans",
            "peas",
            "carrot",
            "carrots",
            "ginger",
            "garlic",
            "chili",
            "pepper",
            "coconut",
            "yogurt",
            "bread",
            "roti",
            "chapati",
            "milk",
            "butter",
            "oil",
            "paneer",
        }
        found = list({t for t in tokens if t in common})
        return found

    def _simple_intent_fallback(self, message: str) -> str:
        """If intent classifier fails, pick a simple intent using keywords."""
        m = (message or "").lower()
        if any(
            w in m for w in ("recipe", "how to", "how do", "how can i make", "cook")
        ):
            return "RECIPE_REQUEST"
        if any(
            w in m
            for w in (
                "what's for dinner",
                "what for dinner",
                "whats for dinner",
                "what to eat",
                "what should i eat",
            )
        ):
            return "WHATSDINNER"
        if any(
            w in m
            for w in ("i have", "leftover", "leftovers", "in pantry", "ingredients")
        ):
            return "PANTRY_HELP"
        if any(w in m for w in ("plan week", "weekly", "meal plan", "plan my week")):
            return "PLANWEEK"
        if any(
            w in m
            for w in (
                "low carb",
                "keto",
                "vegan",
                "vegetarian",
                "gluten free",
                "dairy free",
            )
        ):
            return "DIETARY_QUERY"
        return "WHATSDINNER"

    # -----------------------
    # Public API (backwards-compatible)
    # -----------------------
    async def get_meal_recommendations(
        self,
        whatsapp_id: str,
        user_message: str,
        max_results: int = DEFAULT_MAX,
        verbose: bool = False,
    ) -> Any:
        """
        Returns either:
          - List[Dict] (legacy) if verbose=False
          - Dict {"recommendations": [...], "diagnostics": {...}} if verbose=True

        Diagnostics contains info about which branches were taken and why (useful for debugging).
        """
        diag: Dict[str, Any] = {
            "whatsapp_id_masked": self._mask(whatsapp_id),
            "max_results": max_results,
        }
        try:
            # 1) Fetch user row from user_service (defensive)
            try:
                ures = await self.user_service.get_user_by_whatsapp_id(whatsapp_id)
            except Exception as exc:
                logger.exception("user_service.get_user_by_whatsapp_id raised: %s", exc)
                ures = {
                    "ok": False,
                    "error": "user_service_exception",
                    "diagnostics": {"exception": str(exc)},
                }

            diag["user_service_raw"] = (
                ures if isinstance(ures, dict) else {"raw": str(ures)}
            )

            user_row = None
            if isinstance(ures, dict) and ures.get("ok"):
                user_row = self._normalize_user_row(
                    ures.get("user") or ures.get("result") or ures.get("data") or ures
                )
            # fallback: if user_service returned user directly (legacy)
            if not user_row:
                user_row = self._normalize_user_row(ures)

            if not user_row:
                diag["user_found"] = False
                # If no user, we still continue with default criteria
                criteria = {
                    "diet": None,
                    "cuisine_pref": None,
                    "allergies": [],
                    "household_size": None,
                }
            else:
                diag["user_found"] = True
                # pick keys carefully, allowing multiple naming variants
                criteria = {
                    "diet": user_row.get("diet")
                    or user_row.get("diet_pref")
                    or user_row.get("diet_type"),
                    "cuisine_pref": user_row.get("cuisine_pref")
                    or user_row.get("cuisine"),
                    "allergies": user_row.get("allergies")
                    or user_row.get("allergy_list")
                    or [],
                    "household_size": user_row.get("household_size")
                    or user_row.get("household"),
                }
                diag["criteria_from_user"] = criteria

            # 2) Get intent (defensive)
            intent = None
            try:
                intent_res = await self.intent_classifier.classify_intent(user_message)
                # Accept string return or dict with type field
                if isinstance(intent_res, dict):
                    intent = (
                        intent_res.get("intent")
                        or intent_res.get("type")
                        or intent_res.get("label")
                    )
                    diag["intent_raw"] = intent_res.get("diagnostics") or intent_res
                else:
                    intent = intent_res
                    diag["intent_raw"] = {"raw": str(intent_res)}
            except Exception as exc:
                logger.exception("intent_classifier.classify_intent raised: %s", exc)
                diag["intent_error"] = str(exc)

            if not intent:
                intent = self._simple_intent_fallback(user_message)
                diag["intent_fallback_used"] = True
            diag["intent"] = intent

            # 3) Generate recommendations
            recs, rec_diag = await self._generate_recommendations_with_diag(
                user_row, user_message, intent, criteria, max_results
            )
            diag.update(rec_diag)

            # return shape
            if verbose:
                return {"recommendations": recs, "diagnostics": diag}
            return recs
        except Exception as e:
            logger.exception("Unhandled error in get_meal_recommendations: %s", e)
            # final fallback
            fallback = await self._get_default_recommendations()
            if verbose:
                return {"recommendations": fallback, "diagnostics": {"error": str(e)}}
            return fallback

    # -----------------------
    # Recommendation generator with diagnostics
    # -----------------------
    async def _generate_recommendations_with_diag(
        self,
        user_row: Optional[Dict[str, Any]],
        message: str,
        intent: str,
        criteria: Dict[str, Any],
        max_results: int,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Returns (recommendations, diagnostics)
        """
        diag: Dict[str, Any] = {"intent_handled": intent}
        try:
            if intent == "MOOD":
                recs = await self._handle_mood_request(message, criteria, max_results)
            elif intent == "RECIPE_REQUEST":
                recs = await self._handle_recipe_request(message, criteria, max_results)
            elif intent == "PANTRY_HELP":
                recs = await self._handle_pantry_request(message, criteria, max_results)
            elif intent == "DIETARY_QUERY":
                recs = await self._handle_dietary_request(
                    message, criteria, max_results
                )
            elif intent == "PLANWEEK":
                recs = await self._handle_weekly_plan_request(criteria, max_results * 2)
            else:  # WHATSDINNER or OTHER
                recs = await self._handle_general_request(
                    message, criteria, max_results
                )

            # Enforce preferences defensively (even if meal_service accepted criteria)
            recs_filtered = self._apply_preferences_filter(recs, criteria)

            # If filtering removed everything, try a relaxed pass (only diet enforced)
            if not recs_filtered:
                diag["filtered_all_removed"] = True
                relaxed_criteria = dict(criteria)
                relaxed_criteria["allergies"] = (
                    []
                )  # relax allergy filtering only after logging
                recs_relaxed = self._apply_preferences_filter(recs, relaxed_criteria)
                if recs_relaxed:
                    diag["relaxed_pass_succeeded"] = True
                    recs_filtered = recs_relaxed
                else:
                    # If still nothing, attempt DB-wide search (ignore user criteria)
                    diag["attempting_db_wide_search"] = True
                    try:
                        db_all = await self.meal_service.search_meals("", {}) or []
                        recs_filtered = self._apply_preferences_filter(
                            db_all, {"diet": criteria.get("diet"), "allergies": []}
                        )
                    except Exception as exc:
                        logger.exception(
                            "meal_service.search_meals failed during fallback: %s", exc
                        )
                        recs_filtered = []

            # Limit and format
            final = (
                recs_filtered[:max_results] if isinstance(recs_filtered, list) else []
            )
            formatted = [self._format_single_meal(m) for m in final]
            diag["result_count"] = len(formatted)
            if not formatted:
                diag["empty_reason"] = "no_matching_meals"
                # return default suggestions when empty
                formatted = await self._get_default_recommendations()

            return formatted, diag
        except Exception as exc:
            logger.exception("Error in _generate_recommendations_with_diag: %s", exc)
            return await self._get_default_recommendations(), {"error": str(exc)}

    # -----------------------
    # Handlers (mostly same logic but defensive)
    # -----------------------
    async def _handle_mood_request(
        self, message: str, criteria: Dict[str, Any], max_results: int
    ) -> List[Dict[str, Any]]:
        message_lower = (message or "").lower()
        mood_tags = {
            "spicy": ["spicy", "hot"],
            "comfort": ["comfort", "creamy", "rich"],
            "light": ["light", "healthy", "steamed"],
            "quick": ["quick", "fast"],
            "sweet": ["sweet"],
            "filling": ["filling", "heavy", "protein-rich"],
            "healthy": ["healthy", "nutritious"],
            "traditional": ["traditional", "authentic", "homestyle"],
        }

        search_query = ""
        preferred_tags = []
        for mood, tags in mood_tags.items():
            if mood in message_lower:
                preferred_tags.extend(tags)
                search_query = mood
                break

        try:
            meals = await self.meal_service.search_meals(search_query, criteria) or []
        except Exception as exc:
            logger.exception(
                "meal_service.search_meals failed in mood handler: %s", exc
            )
            meals = []

        if preferred_tags:
            meals = self._prioritize_by_tags(meals, preferred_tags)

        return meals

    async def _handle_recipe_request(
        self, message: str, criteria: Dict[str, Any], max_results: int
    ) -> List[Dict[str, Any]]:
        m = (message or "").lower()
        # try to extract explicit dish names conservatively
        dish = ""
        if "recipe for" in m:
            dish = m.split("recipe for", 1)[1].strip()
        elif "how to make" in m:
            dish = m.split("how to make", 1)[1].strip()
        else:
            # pick last 3 words as candidate
            tokens = re.findall(r"[a-zA-Z]+", m)
            dish = " ".join(tokens[-3:]) if tokens else m

        dish = dish.replace("?", "").strip()
        # Try exact DB name match first
        try:
            exact = await self.meal_service.search_meals(dish, criteria)
            exact = exact or []
        except Exception as exc:
            logger.exception(
                "meal_service.search_meals error in recipe_request: %s", exc
            )
            exact = []

        if exact:
            return exact

        # Fallback: search by key words/ingredients
        # Try ingredient extraction, then broad search
        ingredients = self._extract_ingredients_from_message(message)
        if ingredients:
            # search meals containing any of these ingredients
            try:
                broad = (
                    await self.meal_service.search_meals(
                        " ".join(ingredients), criteria
                    )
                    or []
                )
            except Exception:
                broad = []
            if broad:
                return broad

        # final fallback: return DB-wide fuzzy-ish search
        try:
            fallback = await self.meal_service.search_meals("", {}) or []
            # naive filter by name containment
            matches = [m for m in fallback if dish in (m.get("name") or "").lower()]
            return matches or fallback[:max_results]
        except Exception:
            return []

    async def _handle_pantry_request(
        self, message: str, criteria: Dict[str, Any], max_results: int
    ) -> List[Dict[str, Any]]:
        ingredients = self._extract_ingredients_from_message(message)
        if not ingredients:
            return await self._handle_general_request(message, criteria, max_results)

        try:
            # prefer searching by ingredients
            meals = (
                await self.meal_service.search_meals(" ".join(ingredients), criteria)
                or []
            )
        except Exception as exc:
            logger.exception(
                "meal_service.search_meals failed in pantry handler: %s", exc
            )
            meals = []

        matching_meals = []
        for meal in meals:
            meal_ings = [str(x).lower() for x in meal.get("ingredients", [])]
            match_score = sum(
                1 for ing in ingredients if any(ing in mi for mi in meal_ings)
            )
            if match_score:
                meal_copy = dict(meal)
                meal_copy["ingredient_match_score"] = match_score
                matching_meals.append(meal_copy)

        matching_meals.sort(
            key=lambda x: (x.get("ingredient_match_score", 0), random.random()),
            reverse=True,
        )
        return matching_meals

    async def _handle_dietary_request(
        self, message: str, criteria: Dict[str, Any], max_results: int
    ) -> List[Dict[str, Any]]:
        m = (message or "").lower()
        dietary_filter = ""
        if "vegan" in m or "plant based" in m:
            criteria["diet"] = "veg"
            dietary_filter = "vegan"
        elif "vegetarian" in m:
            criteria["diet"] = "veg"
            dietary_filter = "vegetarian"
        elif "low carb" in m or "keto" in m:
            dietary_filter = "low-carb"
        elif "gluten free" in m:
            dietary_filter = "gluten-free"
        elif "dairy free" in m:
            dietary_filter = "dairy-free"
        else:
            dietary_filter = "healthy"

        try:
            meals = await self.meal_service.search_meals(dietary_filter, criteria) or []
        except Exception as exc:
            logger.exception(
                "meal_service.search_meals failed in dietary handler: %s", exc
            )
            meals = []

        return meals

    async def _handle_weekly_plan_request(
        self, criteria: Dict[str, Any], max_results: int
    ) -> List[Dict[str, Any]]:
        try:
            all_meals = await self.meal_service.search_meals("", criteria) or []
        except Exception as exc:
            logger.exception("meal_service.search_meals failed in weekly plan: %s", exc)
            all_meals = []

        if not all_meals:
            return []

        plan = self._create_diverse_weekly_plan(all_meals, max_results)
        return plan

    async def _handle_general_request(
        self, message: str, criteria: Dict[str, Any], max_results: int
    ) -> List[Dict[str, Any]]:
        query = self._extract_food_query(message)
        try:
            meals = await self.meal_service.search_meals(query, criteria) or []
        except Exception as exc:
            logger.exception(
                "meal_service.search_meals failed in general handler: %s", exc
            )
            meals = []

        if not meals:
            return []

        if len(meals) > max_results:
            random.shuffle(meals)
        return meals

    # -----------------------
    # Formatting & utility
    # -----------------------
    def _format_single_meal(self, meal: Dict[str, Any]) -> Dict[str, Any]:
        """Return a well-shaped recommendation dict consumed by downstream formatters/routers."""
        return {
            "name": meal.get("name"),
            "cuisine": meal.get("cuisine"),
            "diet_type": meal.get("diet_type") or meal.get("diet"),
            "estimated_time_min": meal.get("estimated_time_min"),
            "ingredients": meal.get("ingredients", []),
            "tags": meal.get("tags", []),
            "recipe_text": meal.get("recipe_text") or meal.get("instructions"),
            # metadata for debugging/display
            "_meta": {
                "source_id": meal.get("id"),
                "ingredient_count": len(meal.get("ingredients", [])),
                "tag_score": meal.get("tag_score", 0),
                "ingredient_match_score": meal.get("ingredient_match_score", 0),
            },
            # a short user-facing snippet
            "snippet": self._format_recommendation_text(meal),
        }

    def _prioritize_by_tags(
        self, meals: List[Dict[str, Any]], preferred_tags: List[str]
    ) -> List[Dict[str, Any]]:
        scored = []
        for meal in meals:
            meal_tags = [t.lower() for t in meal.get("tags", [])]
            score = sum(1 for tag in preferred_tags if tag in meal_tags)
            meal["_prior_score"] = score
            scored.append(meal)
        scored.sort(
            key=lambda x: (x.get("_prior_score", 0), random.random()), reverse=True
        )
        return scored

    def _create_diverse_weekly_plan(
        self, meals: List[Dict[str, Any]], num_days: int
    ) -> List[Dict[str, Any]]:
        if not meals:
            return []
        cuisine_groups = {}
        for meal in meals:
            cuisine = meal.get("cuisine") or "other"
            cuisine_groups.setdefault(cuisine, []).append(meal)
        selected = []
        cuisines = list(cuisine_groups.keys())
        for i in range(num_days):
            if not cuisines:
                break
            cuisine = cuisines[i % len(cuisines)]
            bucket = cuisine_groups.get(cuisine) or []
            if not bucket:
                continue
            choice = random.choice(bucket)
            selected.append(choice)
            bucket.remove(choice)
        return selected

    def _extract_food_query(self, message: str) -> str:
        message_lower = (message or "").lower()
        stop_words = {
            "what",
            "should",
            "can",
            "i",
            "eat",
            "cook",
            "make",
            "for",
            "suggest",
            "recommend",
            "please",
            "pls",
            "want",
        }
        words = [
            w
            for w in re.findall(r"[a-zA-Z]+", message_lower)
            if len(w) > 2 and w not in stop_words
        ]
        return " ".join(words[:3])

    # -----------------------
    # Default fallback
    # -----------------------
    async def _get_default_recommendations(self) -> List[Dict[str, Any]]:
        """Fallback recommendations when database is unavailable."""
        # Keep same fallback as before but ensure shape is identical to formatted output
        default_meals = [
            {
                "name": "Dal Rice",
                "cuisine": "indian",
                "diet_type": "veg",
                "estimated_time_min": 30,
                "ingredients": ["dal", "rice", "turmeric", "cumin"],
                "tags": ["comfort", "healthy", "simple"],
                "recipe_text": "Simple comfort meal with lentils and rice",
            },
            {
                "name": "Vegetable Stir Fry",
                "cuisine": "indo_chinese",
                "diet_type": "veg",
                "estimated_time_min": 20,
                "ingredients": ["mixed vegetables", "soy sauce", "garlic"],
                "tags": ["quick", "healthy", "colorful"],
                "recipe_text": "Quick stir-fried vegetables with Asian flavors",
            },
            {
                "name": "Egg Curry",
                "cuisine": "indian",
                "diet_type": "non-veg",
                "estimated_time_min": 25,
                "ingredients": ["eggs", "onion", "tomato", "spices"],
                "tags": ["protein-rich", "comforting"],
                "recipe_text": "Spiced egg curry with rich gravy",
            },
        ]
        # format defaults like normal meals
        return [self._format_single_meal(m) for m in default_meals]
