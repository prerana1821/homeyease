# app/services/meal_service.py
"""
Meal service for database operations using Supabase.

Key improvements:
- Consistent return shape: {'ok': bool, 'data': ..., 'diagnostics': {...}}
  so higher-level services can rely on predictable structures.
- Avoid blocking the event loop by executing sync supabase calls in a threadpool.
- Use logging instead of prints.
- Defensive queries (ilike/name/ingredients/tags) and fallbacks.
- Better error handling and diagnostics for easier debugging.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.config.supabase import supabase_client

logger = logging.getLogger(__name__)


def _safe_list(x: Optional[Any]) -> List[Any]:
    if not x:
        return []
    if isinstance(x, list):
        return x
    # if stored as comma-separated string in DB, split defensively
    if isinstance(x, str):
        return [p.strip() for p in x.split(",") if p.strip()]
    return [x]


class MealService:

    def __init__(self):
        # supabase_client is expected to be a thin wrapper exposing `.client` to PostgREST
        self.client = getattr(supabase_client, "client", None)
        if self.client is None:
            logger.warning("Supabase client not available. Meal operations will fail.")

    # -----------------------
    # Internal helpers
    # -----------------------
    async def _exec_in_thread(self, fn, *args, **kwargs):
        """
        Run blocking supabase calls in a threadpool to avoid blocking the event loop.
        Returns the function's result or raises the exception.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    def _ok_result(
        self, data: Any, diagnostics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return {"ok": True, "data": data, "diagnostics": diagnostics or {}}

    def _error_result(
        self, err: str, diagnostics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return {"ok": False, "error": err, "diagnostics": diagnostics or {}}

    # -----------------------
    # Public API
    # -----------------------
    async def create_meal(self, meal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new meal in the database.

        Returns:
            {"ok": True, "data": created_row, "diagnostics": {...}} on success
            {"ok": False, "error": "...", "diagnostics": {...}} on failure
        """
        if self.client is None:
            return self._error_result("supabase_client_unavailable")

        try:
            resp = await self._exec_in_thread(
                self.client.table("meals").insert(meal_data).select().execute
            )
            # Some SDKs return a Response-like object with .data or .json; handle defensively
            meals = getattr(resp, "data", None) or (
                resp.get("data") if isinstance(resp, dict) and "data" in resp else None
            )
            if meals:
                return self._ok_result(meals[0], {"insert_count": len(meals)})
            return self._error_result("no_data_returned", {"raw_response": str(resp)})
        except Exception as exc:
            logger.exception("create_meal failed: %s", exc)
            return self._error_result("create_failed", {"exception": str(exc)})

    async def get_meals_by_cuisine(self, cuisine: str) -> Dict[str, Any]:
        """Get all meals for a specific cuisine."""
        if self.client is None:
            return self._error_result("supabase_client_unavailable")

        try:
            resp = await self._exec_in_thread(
                self.client.table("meals").select("*").eq("cuisine", cuisine).execute
            )
            meals = (
                getattr(resp, "data", None)
                or (resp.get("data") if isinstance(resp, dict) else None)
                or []
            )
            return self._ok_result(meals, {"cuisine": cuisine, "count": len(meals)})
        except Exception as exc:
            logger.exception("get_meals_by_cuisine failed: %s", exc)
            return self._error_result(
                "query_failed", {"exception": str(exc), "cuisine": cuisine}
            )

    async def get_meals_by_diet(self, diet_type: str) -> Dict[str, Any]:
        """Get all meals for a specific diet type."""
        if self.client is None:
            return self._error_result("supabase_client_unavailable")

        try:
            resp = await self._exec_in_thread(
                self.client.table("meals")
                .select("*")
                .eq("diet_type", diet_type)
                .execute
            )
            meals = (
                getattr(resp, "data", None)
                or (resp.get("data") if isinstance(resp, dict) else None)
                or []
            )
            return self._ok_result(meals, {"diet_type": diet_type, "count": len(meals)})
        except Exception as exc:
            logger.exception("get_meals_by_diet failed: %s", exc)
            return self._error_result(
                "query_failed", {"exception": str(exc), "diet_type": diet_type}
            )

    async def search_meals(
        self, query: str, user_preferences: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Search meals based on query and user preferences.

        Returns:
            {"ok": True, "data": [meals], "diagnostics": {...}} on success
            {"ok": False, "error": "...", "diagnostics": {...}} on failure
        """
        if self.client is None:
            return self._error_result("supabase_client_unavailable")

        query = (query or "").strip()
        prefs = user_preferences or {}
        diagnostics: Dict[str, Any] = {"query": query, "preferences": prefs}

        try:
            # Build a base query builder object. This is PostgREST-style chaining.
            qb = self.client.table("meals").select("*")

            # Apply diet filter if provided
            diet = prefs.get("diet")
            if diet:
                if diet.lower() in ("veg", "vegetarian", "plant-based"):
                    qb = qb.eq("diet_type", "veg")
                    diagnostics["diet_filter_applied"] = "veg"
                elif diet.lower() in ("non-veg", "nonvegetarian", "non_veg"):
                    qb = qb.eq("diet_type", "non-veg")
                    diagnostics["diet_filter_applied"] = "non-veg"
                # 'both' -> no diet filter

            # Apply cuisine preference
            cuisine = prefs.get("cuisine_pref")
            if cuisine and cuisine != "surprise":
                qb = qb.eq("cuisine", cuisine)
                diagnostics["cuisine_filter_applied"] = cuisine

            # Execute the DB query (get a superset)
            resp = await self._exec_in_thread(qb.execute)
            raw_meals = (
                getattr(resp, "data", None)
                or (resp.get("data") if isinstance(resp, dict) else None)
                or []
            )
            diagnostics["fetched_count"] = len(raw_meals)

            # If query not provided, return results (later the caller may further filter)
            if not query:
                return self._ok_result(raw_meals, diagnostics)

            # Case-insensitive fuzzy matching on name/tags/ingredients.
            qlow = query.lower()
            filtered = []
            for meal in raw_meals:
                # Defensive extraction of fields
                name = (meal.get("name") or "").lower()
                ingredients = " ".join(
                    [str(i).lower() for i in _safe_list(meal.get("ingredients"))]
                )
                tags = " ".join([str(t).lower() for t in _safe_list(meal.get("tags"))])

                if qlow in name or qlow in ingredients or qlow in tags:
                    filtered.append(meal)
                    continue

                # Try word containment (split query into words)
                for token in qlow.split():
                    if token and (
                        token in name or token in ingredients or token in tags
                    ):
                        filtered.append(meal)
                        break

            diagnostics["filtered_count"] = len(filtered)
            return self._ok_result(filtered, diagnostics)
        except Exception as exc:
            logger.exception("search_meals failed: %s", exc)
            return self._error_result("search_failed", {"exception": str(exc)})

    # -----------------------
    # Utility: bulk populate
    # -----------------------
    async def populate_indian_meals(self) -> Dict[str, Any]:
        """Populate database with Indian meal options (idempotent).

        Returns dict with ok flag and diagnostics.
        """
        if self.client is None:
            return self._error_result("supabase_client_unavailable")

        # Keep the same dataset as before but only show diagnostics here
        indian_meals = [
            # (trimmed here for brevity in this code block — keep full list in real file)
            # ... same dicts as your previous population list ...
        ]

        try:
            # 1) fetch existing names to avoid duplicates
            resp_existing = await self._exec_in_thread(
                self.client.table("meals").select("name").execute
            )
            existing = (
                getattr(resp_existing, "data", None)
                or (
                    resp_existing.get("data")
                    if isinstance(resp_existing, dict)
                    else None
                )
                or []
            )
            existing_names = {m.get("name") for m in existing if m and m.get("name")}
            new_meals = [
                m for m in indian_meals if m.get("name')") not in existing_names
            ]  # defensive

            # If none to insert, return success
            if not new_meals:
                return self._ok_result(
                    [],
                    {"message": "no_new_meals", "existing_count": len(existing_names)},
                )

            # Insert new meals
            resp_insert = await self._exec_in_thread(
                self.client.table("meals").insert(new_meals).execute
            )
            inserted = (
                getattr(resp_insert, "data", None)
                or (resp_insert.get("data") if isinstance(resp_insert, dict) else None)
                or []
            )
            if inserted:
                return self._ok_result(inserted, {"inserted_count": len(inserted)})
            return self._error_result(
                "insert_failed", {"raw_response": str(resp_insert)}
            )
        except Exception as exc:
            logger.exception("populate_indian_meals failed: %s", exc)
            return self._error_result("populate_failed", {"exception": str(exc)})
