# app/services/user_service.py
"""
User service for database operations using Supabase.

Design goals / changes:
- Standardized return shape for every public method:
    {"ok": bool, "data": ..., "error": "...", "diagnostics": {...}}
  This makes composition and testing predictable.
- Use asyncio.to_thread (via helper) for all blocking supabase SDK calls so the event loop
  is never blocked.
- More defensive parsing of Supabase SDK responses (object with .data OR dict with "data").
- Improved idempotency handling for incoming messages (uses maybe_single where supported).
- Added `process_onboarding_step` convenience orchestration to translate incoming message
  content to an onboarding update (name/diet/cuisine/allergies/household).
- Clear logging and richer diagnostics returned in 'diagnostics'.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.config.supabase import supabase_client

logger = logging.getLogger(__name__)


# -----------------------
# Utility helpers
# -----------------------
def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _normalize_ingredient(ing: str) -> str:
    if not ing:
        return ""
    s = ing.strip().lower()
    s = re.sub(r"[^\w\s\-&]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _parse_supabase_response(resp: Any) -> Dict[str, Any]:
    """
    Turn Supabase SDK responses (object with .data or dict) into a predictable dict.
    Returns {ok, data, status_code, raw}
    """
    if resp is None:
        return {"ok": False, "data": None, "status_code": None, "raw": None}

    # SDK object that exposes .data (common)
    if hasattr(resp, "data"):
        data = getattr(resp, "data")
        status_code = getattr(resp, "status_code", None)
        ok = True if data is not None else False
        return {"ok": ok, "data": data, "status_code": status_code, "raw": resp}

    # dict-like fallback
    if isinstance(resp, dict):
        data = resp.get("data", resp.get("result", resp.get("records", None)))
        status_code = resp.get(
            "status_code", resp.get("statusCode", resp.get("status", None))
        )
        ok = True if data is not None else False
        return {"ok": ok, "data": data, "status_code": status_code, "raw": resp}

    # unexpected type
    return {"ok": False, "data": None, "status_code": None, "raw": str(resp)}


# We run blocking DB calls inside this thread helper to keep async context responsive.
async def _run_blocking(fn: Callable, *args, **kwargs) -> Any:
    return await asyncio.to_thread(lambda: fn(*args, **kwargs))


def _make_result(
    ok: bool,
    data: Any = None,
    error: Optional[str] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    res: Dict[str, Any] = {"ok": ok}
    if ok:
        res["data"] = data
    else:
        res["error"] = error or "unknown_error"
    res["diagnostics"] = diagnostics or {}
    return res


# -----------------------
# UserService
# -----------------------
class UserService:

    def __init__(self):
        self.client = getattr(supabase_client, "client", None)
        if self.client is None:
            logger.warning(
                "UserService: Supabase client not available. DB operations will fail."
            )
        else:
            logger.debug("UserService: initialized with Supabase client")

    async def _call_db(self, fn: Callable, *args, **kwargs) -> Dict[str, Any]:
        """
        Run blocking DB function in a thread and normalize response.
        `fn` should be a callable that invokes supabase SDK and returns its raw response.
        """
        if self.client is None:
            return _make_result(False, error="no_supabase_client", diagnostics={})
        try:
            logger.debug(
                "DB call: %s args=%s kwargs_keys=%s",
                getattr(fn, "__name__", str(fn)),
                args,
                list(kwargs.keys()),
            )
            raw = await _run_blocking(fn, *args, **kwargs)
            parsed = _parse_supabase_response(raw)
            diagnostics = {
                "called": getattr(fn, "__name__", str(fn)),
                "raw_preview": str(parsed.get("raw"))[:1000],
            }
            return _make_result(
                parsed.get("ok", False),
                data=parsed.get("data"),
                diagnostics=diagnostics,
                error=None if parsed.get("ok") else "db_no_data",
            )
        except Exception as exc:
            logger.exception("DB call raised exception: %s", exc)
            return _make_result(
                False,
                error=str(exc),
                diagnostics={"fn": getattr(fn, "__name__", str(fn))},
            )

    # -----------------------
    # Incoming messages (idempotency)
    # -----------------------
    async def record_incoming_message(
        self,
        message_sid: str,
        user_id: Optional[int],
        from_phone: str,
        raw_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Insert an incoming message row idempotently. If unique constraint violation occurs,
        try to select the existing row. Returns normalized result with 'data' being the row(s).
        """
        logger.info(
            "record_incoming_message sid=%s from=%s user=%s",
            message_sid,
            from_phone,
            user_id,
        )
        if self.client is None:
            return _make_result(False, error="no_supabase_client")

        now = _now_iso()

        def _fn(mid, uid, frm, raw):
            tbl = self.client.table("incoming_messages")
            try:
                # maybe_single is preferred if supported to get a single row back
                return tbl.insert(
                    {
                        "message_sid": mid,
                        "user_id": uid,
                        "from_phone": frm,
                        "raw_payload": raw,
                        "processed": False,
                        "created_at": now,
                    }
                ).execute()
            except Exception:
                # best-effort: return existing row if insert failed due to unique constraint
                try:
                    return (
                        tbl.select("*").eq("message_sid", mid).maybe_single().execute()
                    )
                except Exception:
                    return tbl.select("*").eq("message_sid", mid).limit(1).execute()

        res = await self._call_db(_fn, message_sid, user_id, from_phone, raw_payload)
        return res

    async def mark_incoming_processed(self, message_sid: str) -> Dict[str, Any]:
        logger.info("mark_incoming_processed sid=%s", message_sid)
        if self.client is None:
            return _make_result(False, error="no_supabase_client")

        now = _now_iso()

        def _fn(mid, processed_at):
            return (
                self.client.table("incoming_messages")
                .update({"processed": True, "processed_at": processed_at})
                .eq("message_sid", mid)
                .execute()
            )

        return await self._call_db(_fn, message_sid, now)

    # -----------------------
    # Users
    # -----------------------
    async def get_user_by_whatsapp_id(self, whatsapp_id: str) -> Dict[str, Any]:
        logger.info("get_user_by_whatsapp_id: %s", whatsapp_id)
        if self.client is None:
            return _make_result(False, error="no_supabase_client")

        def _fn(wid):
            tbl = self.client.table("users")
            try:
                return tbl.select("*").eq("whatsapp_id", wid).maybe_single().execute()
            except Exception:
                # older SDK or DB config may not support maybe_single
                return tbl.select("*").eq("whatsapp_id", wid).limit(1).execute()

        res = await self._call_db(_fn, whatsapp_id)
        # normalize user into res["user"]
        if res.get("ok") and res.get("data"):
            data = res.get("data")
            user = data[0] if isinstance(data, list) and data else data
            return _make_result(True, data=user, diagnostics=res.get("diagnostics"))
        return _make_result(
            False, error="user_not_found", diagnostics=res.get("diagnostics")
        )

    async def create_user(
        self, whatsapp_id: str, name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create or upsert a user row by whatsapp_id.

        Guarantees a normalized return:
          {
            "ok": bool,
            "data": <raw response data or []>,
            "user": <single user dict or None>,
            "diagnostics": {...},
            "error": <error msg if any>
          }

        This method is defensive: if upsert/insert returns no user row we do a
        follow-up SELECT by whatsapp_id to fetch the row (common with certain
        supabase client versions).
        """
        logger.info("create_user: whatsapp_id=%s name=%s", whatsapp_id, name)
        if self.client is None:
            logger.warning("create_user: no supabase client")
            return {
                "ok": False,
                "error": "no_supabase_client",
                "user": None,
                "data": None,
                "diagnostics": {},
            }

        user_data = {
            "whatsapp_id": whatsapp_id,
            "name": name or "Guest",
            "onboarding_step": 0,
            "created_at": _now_iso(),
            "last_active": _now_iso(),
        }

        # Attempt upsert/insert (wrap to support older/newer client signatures)
        def _fn(data):
            tbl = self.client.table("users")
            try:
                # Prefer upsert with on_conflict if supported
                return tbl.upsert(data, on_conflict="whatsapp_id").execute()
            except TypeError:
                # client doesn't support on_conflict kw
                try:
                    return tbl.upsert(data).execute()
                except Exception:
                    # fallback to insert
                    return tbl.insert(data).execute()
            except Exception:
                # last resort: attempt insert (some clients raise unexpected)
                return tbl.insert(data).execute()

        res = await self._call_db(_fn, user_data)

        # Ensure diagnostics exist
        diagnostics = res.get("diagnostics", {})
        diagnostics["create_user_attempt"] = getattr(_fn, "__name__", "upsert/insert")

        # Normalize returned data -> try to extract a user row
        user_row = None
        raw_data = res.get("data")

        if raw_data:
            if isinstance(raw_data, list) and len(raw_data) > 0:
                user_row = raw_data[0]
            elif isinstance(raw_data, dict):
                # Some clients return single dict as response.data
                user_row = raw_data

        # If we couldn't get a user row from the upsert/insert response,
        # try a follow-up SELECT by whatsapp_id (covering driver oddities).
        if not user_row:
            logger.debug(
                "create_user: upsert returned no rows, attempting SELECT fallback for %s",
                whatsapp_id,
            )
            try:

                def _fn_select(wid):
                    return (
                        self.client.table("users")
                        .select("*")
                        .eq("whatsapp_id", wid)
                        .maybe_single()
                        .execute()
                    )

                select_res = await self._call_db(_fn_select, whatsapp_id)
                diagnostics["create_user_select_fallback"] = select_res.get(
                    "diagnostics"
                )
                sel_data = select_res.get("data")
                if sel_data:
                    # maybe_single returns single dict or list depending on client — normalize
                    if isinstance(sel_data, list) and len(sel_data) > 0:
                        user_row = sel_data[0]
                    elif isinstance(sel_data, dict):
                        user_row = sel_data
            except Exception as exc:
                logger.exception("create_user: SELECT fallback failed: %s", exc)
                diagnostics["create_user_select_error"] = str(exc)

        # Build final normalized response
        out = {
            "ok": bool(user_row is not None),
            "data": raw_data,
            "user": user_row,
            "diagnostics": diagnostics,
        }

        if not user_row:
            out["error"] = "user_not_created"
            logger.warning("create_user returned no user object for %s", whatsapp_id)
        else:
            logger.debug("create_user: created/fetched user id=%s", user_row.get("id"))

        return out

    async def upsert_user(
        self, whatsapp_id: str, user_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(
            "upsert_user whatsapp_id=%s keys=%s", whatsapp_id, list(user_data.keys())
        )
        if self.client is None:
            return _make_result(False, error="no_supabase_client")

        payload = {**user_data, "whatsapp_id": whatsapp_id, "last_active": _now_iso()}

        def _fn(data):
            tbl = self.client.table("users")
            try:
                return tbl.upsert(data, on_conflict="whatsapp_id").execute()
            except Exception:
                return tbl.upsert(data).execute()

        res = await self._call_db(_fn, payload)
        if res.get("ok") and res.get("data"):
            d = res.get("data")
            user = d[0] if isinstance(d, list) and d else d
            return _make_result(True, data=user, diagnostics=res.get("diagnostics"))
        return _make_result(
            False, error="upsert_failed", diagnostics=res.get("diagnostics")
        )

    async def update_user_fields(
        self, user_id: int, patch: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(
            "update_user_fields user_id=%s keys=%s", user_id, list(patch.keys())
        )
        if self.client is None:
            return _make_result(False, error="no_supabase_client")

        payload = {**patch, "last_active": _now_iso()}

        def _fn(uid, data):
            return self.client.table("users").update(data).eq("id", uid).execute()

        res = await self._call_db(_fn, user_id, payload)
        if res.get("ok"):
            return _make_result(
                True, data=res.get("data"), diagnostics=res.get("diagnostics")
            )
        return _make_result(
            False, error="update_failed", diagnostics=res.get("diagnostics")
        )

    # -----------------------
    # Sessions / Pantry / Meal Plans
    # -----------------------
    async def create_session(
        self, user_id: int, prompt: str, response_text: str
    ) -> Dict[str, Any]:
        logger.debug("create_session user_id=%s prompt=%s", user_id, prompt)
        if self.client is None:
            return _make_result(False, error="no_supabase_client")

        row = {
            "user_id": user_id,
            "prompt": prompt,
            "response": response_text,
            "created_at": _now_iso(),
        }

        def _fn(data):
            return self.client.table("sessions").insert(data).execute()

        res = await self._call_db(_fn, row)
        return res

    def create_session_sync(self, user_id: int, prompt: str, response_text: str):
        """
        Sync helper for contexts that are not async-aware.
        Returns the same normalized result dict as create_session (but executed synchronously).
        """
        try:
            # If there's an event loop running, run the coroutine in a thread to avoid loop conflicts.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(
                    self.create_session(user_id, prompt, response_text), loop
                )
                return fut.result()
            else:
                return asyncio.run(self.create_session(user_id, prompt, response_text))
        except Exception as exc:
            logger.exception("create_session_sync failed: %s", exc)
            return _make_result(False, error=str(exc))

    async def upsert_user_pantry_items(
        self, user_id: int, items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        logger.info(
            "upsert_user_pantry_items user_id=%s count=%s",
            user_id,
            len(items) if items else 0,
        )
        if self.client is None:
            return _make_result(False, error="no_supabase_client")
        if not items:
            return _make_result(True, data=[], diagnostics={"note": "no_items"})

        normalized = []
        seen = set()
        for it in items:
            ing_raw = it.get("ingredient") if isinstance(it, dict) else it
            ing = _normalize_ingredient(ing_raw or "")
            if not ing or ing in seen:
                continue
            seen.add(ing)
            normalized.append(
                {
                    "ingredient": ing,
                    "quantity": it.get("quantity"),
                    "last_seen": _now_iso(),
                    "user_id": user_id,
                }
            )

        ingredient_list = [i["ingredient"] for i in normalized]

        def _fn(uid, ings, rows):
            tbl = self.client.table("user_pantry")
            try:
                if ings:
                    tbl.delete().eq("user_id", uid).in_("ingredient", ings).execute()
            except Exception:
                # fallback: delete each individually if batch delete not supported
                for ing in ings:
                    tbl.delete().eq("user_id", uid).eq("ingredient", ing).execute()
            if rows:
                return tbl.insert(rows).execute()
            return {"data": []}

        res = await self._call_db(_fn, user_id, ingredient_list, normalized)
        if res.get("ok") and res.get("data"):
            return _make_result(
                True, data=res.get("data"), diagnostics=res.get("diagnostics")
            )
        return _make_result(
            False, error="pantry_upsert_failed", diagnostics=res.get("diagnostics")
        )

    async def create_meal_plan(
        self, user_id: int, plan_json: Dict[str, Any], pdf_url: Optional[str] = None
    ) -> Dict[str, Any]:
        logger.info("create_meal_plan user_id=%s", user_id)
        if self.client is None:
            return _make_result(False, error="no_supabase_client")

        row = {
            "user_id": user_id,
            "plan_json": plan_json,
            "pdf_url": pdf_url,
            "created_at": _now_iso(),
        }

        def _fn(data):
            return self.client.table("meal_plans").insert(data).execute()

        res = await self._call_db(_fn, row)
        return res

    # -----------------------
    # Onboarding helpers (thin wrappers that return normalized results)
    # -----------------------
    async def update_user_onboarding_step(
        self, user_or_whatsapp: Any, step: Optional[int]
    ) -> Dict[str, Any]:
        """
        Update the user's onboarding_step.
        Accepts either numeric user id or whatsapp_id string.
        Returns normalized result (ok/data/diagnostics).
        """
        logger.info("update_user_onboarding_step id=%s step=%s", user_or_whatsapp, step)
        if self.client is None:
            return _make_result(False, error="no_supabase_client")

        if isinstance(user_or_whatsapp, int):
            # update by id
            return await self.update_user_fields(
                user_or_whatsapp, {"onboarding_step": step}
            )

        whatsapp_id = str(user_or_whatsapp)

        def _fn(wid, step_val):
            return (
                self.client.table("users")
                .update({"onboarding_step": step_val})
                .eq("whatsapp_id", wid)
                .execute()
            )

        res = await self._call_db(_fn, whatsapp_id, step)
        return res

    async def update_user_name_and_onboarding_step(
        self, user_id: int, name: str, step: int
    ) -> Dict[str, Any]:
        return await self.update_user_fields(
            user_id, {"name": name, "onboarding_step": step}
        )

    async def update_user_diet_and_onboarding_step(
        self, user_id: int, diet: str, step: int
    ) -> Dict[str, Any]:
        return await self.update_user_fields(
            user_id, {"diet": diet, "onboarding_step": step}
        )

    async def update_user_cuisine_and_onboarding_step(
        self, user_id: int, cuisine: str, step: int
    ) -> Dict[str, Any]:
        return await self.update_user_fields(
            user_id, {"cuisine_pref": cuisine, "onboarding_step": step}
        )

    async def update_user_allergies_and_onboarding_step(
        self, user_id: int, allergies: List[str], step: int
    ) -> Dict[str, Any]:
        return await self.update_user_fields(
            user_id, {"allergies": allergies, "onboarding_step": step}
        )

    async def update_user_household_and_complete_onboarding(
        self, user_id: int, household: str
    ) -> Dict[str, Any]:
        return await self.update_user_fields(
            user_id, {"household_size": household, "onboarding_step": None}
        )

    # -----------------------
    # High-level orchestration helper
    # -----------------------
    async def process_onboarding_step(
        self, whatsapp_id: str, incoming_message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        High-level convenience that:
         - fetches the user (or creates one),
         - inspects the user's onboarding_step,
         - extracts body from incoming_message (supports 'text' and 'interactive'),
         - dispatches to the appropriate update_* helper.
        Returns: normalized dict with debug diagnostics and the handler result.
        """
        diag: Dict[str, Any] = {"whatsapp_id": whatsapp_id}
        # get or create user
        user_res = await self.get_user_by_whatsapp_id(whatsapp_id)
        if not user_res.get("ok"):
            # try to create user
            create_res = await self.create_user(whatsapp_id)
            diag["user_created"] = create_res.get("ok")
            if not create_res.get("ok"):
                diag["error"] = "failed_to_get_or_create_user"
                return _make_result(False, error="user_missing", diagnostics=diag)
            user = create_res.get("data")
        else:
            user = user_res.get("data")

        diag["user_id"] = user.get("id")
        # determine step (None -> complete)
        raw_step = user.get("onboarding_step")
        try:
            step = int(raw_step) if raw_step is not None else None
        except Exception:
            logger.warning(
                "Invalid onboarding_step for user %s: %s", whatsapp_id, raw_step
            )
            step = 0

        # extract body
        body = ""
        msg_type = incoming_message.get("type")
        if msg_type == "text":
            body = (incoming_message.get("text") or {}).get("body", "") or ""
        elif msg_type == "interactive":
            interactive = incoming_message.get("interactive") or {}
            body = (
                (interactive.get("list_reply") or {}).get("title")
                or (interactive.get("button_reply") or {}).get("title")
                or ""
            )
        else:
            body = incoming_message.get("body") or ""

        body = (body or "").strip()
        diag["raw_body_preview"] = body[:200]
        # dispatch according to step
        try:
            if step is None:
                return _make_result(True, data={"status": "complete"}, diagnostics=diag)
            if step == 0:
                # name
                name = "Guest" if body.lower() == "skip" else (body[:64] or "Guest")
                res = await self.update_user_name_and_onboarding_step(
                    user.get("id"), name, 1
                )
                diag["action"] = "name"
                diag["name_handled"] = name
                return _make_result(
                    res.get("ok", False),
                    data=res.get("data"),
                    diagnostics=diag,
                    error=res.get("error"),
                )
            if step == 1:
                # diet
                mapping = {"1": "veg", "2": "non-veg", "3": "both"}
                diet = mapping.get(body.lower(), body.lower() if body else "both")
                res = await self.update_user_diet_and_onboarding_step(
                    user.get("id"), diet, 2
                )
                diag["action"] = "diet"
                diag["diet_set"] = diet
                return _make_result(
                    res.get("ok", False),
                    data=res.get("data"),
                    diagnostics=diag,
                    error=res.get("error"),
                )
            if step == 2:
                cuisine = (body or "").lower().replace(" ", "_") if body else "surprise"
                res = await self.update_user_cuisine_and_onboarding_step(
                    user.get("id"), cuisine, 3
                )
                diag["action"] = "cuisine"
                diag["cuisine_set"] = cuisine
                return _make_result(
                    res.get("ok", False),
                    data=res.get("data"),
                    diagnostics=diag,
                    error=res.get("error"),
                )
            if step == 3:
                # parse allergies: simple comma/space split + map numbers
                allergies = []
                if not body or body.strip() == "1" or "none" in body.lower():
                    allergies = []
                else:
                    parts = [p.strip() for p in re.split(r"[,\s]+", body) if p.strip()]
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
                res = await self.update_user_allergies_and_onboarding_step(
                    user.get("id"), allergies, 4
                )
                diag["action"] = "allergies"
                diag["allergies_set"] = allergies
                return _make_result(
                    res.get("ok", False),
                    data=res.get("data"),
                    diagnostics=diag,
                    error=res.get("error"),
                )
            if step == 4:
                mapping = {
                    "1": "single",
                    "2": "couple",
                    "3": "small_family",
                    "4": "big_family",
                    "5": "shared",
                }
                household = mapping.get(
                    body.lower(), body.lower().replace(" ", "_") if body else "single"
                )
                res = await self.update_user_household_and_complete_onboarding(
                    user.get("id"), household
                )
                diag["action"] = "household"
                diag["household_set"] = household
                return _make_result(
                    res.get("ok", False),
                    data=res.get("data"),
                    diagnostics=diag,
                    error=res.get("error"),
                )
            # unexpected step - treat as reset to name
            logger.warning(
                "Unexpected onboarding step %s for user %s; resetting to 0",
                step,
                whatsapp_id,
            )
            await self.update_user_onboarding_step(user.get("id"), 0)
            diag["reset_to_step"] = 0
            return _make_result(False, error="unexpected_step_reset", diagnostics=diag)
        except Exception as exc:
            logger.exception("process_onboarding_step failed: %s", exc)
            diag["exception"] = str(exc)
            return _make_result(False, error=str(exc), diagnostics=diag)
