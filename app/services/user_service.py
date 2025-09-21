# app/services/user_service.py
"""
User service for database operations using Supabase.

Extended to cover:
 - users (get/create/upsert/update)
 - sessions (create)
 - user_pantry (upsert / normalize)
 - meal_plans (create)
 - incoming_messages (idempotency)
 - outgoing_messages (audit)
 - high-level orchestration: process_onboarding_step
 - onboarding step helpers (update_* methods)

All blocking Supabase calls run in a background thread via asyncio.to_thread.
Responses are normalized for easy diagnostics by higher layers.
"""
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import asyncio
import logging
import re

from app.config.supabase import supabase_client

logger = logging.getLogger(__name__)


def _parse_supabase_response(resp: Any) -> Dict[str, Any]:
    if resp is None:
        return {"ok": False, "data": None, "status_code": None, "raw": resp}
    if hasattr(resp, "data"):
        data = getattr(resp, "data")
        status_code = getattr(resp, "status_code", None)
        ok = True if data is not None else False
        return {"ok": ok, "data": data, "status_code": status_code, "raw": resp}
    try:
        if isinstance(resp, dict):
            data = resp.get("data", resp.get("result", resp.get("records", None)))
            status_code = resp.get(
                "status_code", resp.get("statusCode", resp.get("status", None))
            )
            ok = True if data is not None else False
            return {"ok": ok, "data": data, "status_code": status_code, "raw": resp}
    except Exception:
        pass
    return {"ok": False, "data": None, "status_code": None, "raw": resp}


def _run_db(fn: Callable, *args, **kwargs):
    return fn(*args, **kwargs)


def _now_iso():
    return datetime.utcnow().isoformat()


def _normalize_ingredient(ing: str) -> str:
    if not ing:
        return ""
    s = ing.strip().lower()
    s = re.sub(r"[^\w\s\-&]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


class UserService:

    def __init__(self):
        self.client = supabase_client.client
        if self.client is None:
            logger.warning("Supabase client not available. DB operations will fail.")
        else:
            logger.debug("UserService initialized with Supabase client")

    async def _call_db(self, fn: Callable, *args, **kwargs) -> Dict[str, Any]:
        if self.client is None:
            logger.debug("_call_db: no supabase client available")
            return {"ok": False, "error": "no_supabase_client", "diagnostics": {}}
        try:
            logger.debug(
                "Running DB function %s args=%s kwargs_keys=%s",
                getattr(fn, "__name__", str(fn)),
                args,
                list(kwargs.keys()),
            )
            raw = await asyncio.to_thread(_run_db, fn, *args, **kwargs)
            parsed = _parse_supabase_response(raw)
            parsed["diagnostics"] = {
                "called": getattr(fn, "__name__", str(fn)),
                "raw_snippet": str(raw)[:1000],
            }
            logger.debug(
                "_call_db result ok=%s data_preview=%s",
                parsed.get("ok"),
                str(parsed.get("raw"))[:200],
            )
            return parsed
        except Exception as exc:
            logger.exception("DB call failed: %s", exc)
            return {
                "ok": False,
                "error": str(exc),
                "diagnostics": {"fn": getattr(fn, "__name__", str(fn))},
            }

    # ------------------------------------------------------------------
    # Incoming messages (idempotency)
    # ------------------------------------------------------------------
    async def record_incoming_message(
        self,
        message_sid: str,
        user_id: Optional[int],
        from_phone: str,
        raw_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Idempotent record of incoming messages by message_sid."""
        logger.info(
            "record_incoming_message: sid=%s from=%s user_id=%s",
            message_sid,
            from_phone,
            user_id,
        )
        if self.client is None:
            logger.warning("record_incoming_message: no supabase client")
            return {"ok": False, "error": "no_supabase_client"}

        now = _now_iso()

        def _fn(mid, uid, frm, raw):
            tbl = self.client.table("incoming_messages")
            try:
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
                # If insert fails due unique constraint, return existing row
                return tbl.select("*").eq("message_sid", mid).maybe_single().execute()

        res = await self._call_db(_fn, message_sid, user_id, from_phone, raw_payload)
        logger.debug("record_incoming_message done: ok=%s", res.get("ok"))
        return res

    async def mark_incoming_processed(self, message_sid: str) -> Dict[str, Any]:
        """Mark incoming message as processed."""
        logger.info("mark_incoming_processed: sid=%s", message_sid)
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        now = _now_iso()

        def _fn(mid, processed_at):
            return (
                self.client.table("incoming_messages")
                .update({"processed": True, "processed_at": processed_at})
                .eq("message_sid", mid)
                .execute()
            )

        res = await self._call_db(_fn, message_sid, now)
        logger.debug("mark_incoming_processed done: ok=%s", res.get("ok"))
        return res

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    async def get_user_by_whatsapp_id(self, whatsapp_id: str) -> Dict[str, Any]:
        logger.info("get_user_by_whatsapp_id: %s", whatsapp_id)
        if self.client is None:
            logger.warning("get_user_by_whatsapp_id: no supabase client")
            return {"ok": False, "error": "no_supabase_client"}

        def _fn(wid):
            tbl = self.client.table("users")
            try:
                return tbl.select("*").eq("whatsapp_id", wid).maybe_single().execute()
            except Exception:
                return tbl.select("*").eq("whatsapp_id", wid).limit(1).execute()

        res = await self._call_db(_fn, whatsapp_id)
        if res.get("ok") and res.get("data"):
            data = res.get("data")
            if isinstance(data, list) and len(data) > 0:
                res["user"] = data[0]
            else:
                res["user"] = data
            logger.debug(
                "get_user_by_whatsapp_id: found user id=%s", res["user"].get("id")
            )
        else:
            res["user"] = None
            logger.debug("get_user_by_whatsapp_id: user not found")
        return res

    async def create_user(
        self, whatsapp_id: str, name: Optional[str] = None
    ) -> Dict[str, Any]:
        logger.info("create_user: whatsapp_id=%s name=%s", whatsapp_id, name)
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        user_data = {
            "whatsapp_id": whatsapp_id,
            "name": name or "Guest",
            "onboarding_step": 0,
            "created_at": _now_iso(),
            "last_active": _now_iso(),
        }

        def _fn(data):
            tbl = self.client.table("users")
            try:
                return tbl.upsert(data, on_conflict="whatsapp_id").execute()
            except TypeError:
                return tbl.upsert(data).execute()
            except Exception:
                return tbl.insert(data).execute()

        res = await self._call_db(_fn, user_data)
        if res.get("ok") and res.get("data"):
            data = res.get("data")
            res["user"] = data[0] if isinstance(data, list) else data
            logger.debug("create_user: created user id=%s", res["user"].get("id"))
        else:
            res["user"] = None
            logger.warning("create_user failed: %s", res.get("error"))
        return res

    async def upsert_user(
        self, whatsapp_id: str, user_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(
            "upsert_user: whatsapp_id=%s patch_keys=%s",
            whatsapp_id,
            list(user_data.keys()),
        )
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        user_data = {**user_data, "whatsapp_id": whatsapp_id, "last_active": _now_iso()}

        def _fn(data):
            tbl = self.client.table("users")
            try:
                return tbl.upsert(data, on_conflict="whatsapp_id").execute()
            except Exception:
                return tbl.upsert(data).execute()

        res = await self._call_db(_fn, user_data)
        if res.get("ok") and res.get("data"):
            data = res.get("data")
            res["user"] = data[0] if isinstance(data, list) else data
            logger.debug("upsert_user: done id=%s", res["user"].get("id"))
        else:
            res["user"] = None
            logger.warning("upsert_user failed: %s", res.get("error"))
        return res

    async def update_user_fields(
        self, user_id: int, patch: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(
            "update_user_fields: user_id=%s patch_keys=%s", user_id, list(patch.keys())
        )
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        patch = {**patch, "last_active": _now_iso()}

        def _fn(uid, data):
            return self.client.table("users").update(data).eq("id", uid).execute()

        res = await self._call_db(_fn, user_id, patch)
        if res.get("ok") and res.get("data"):
            res["result"] = res["data"]
            logger.debug("update_user_fields success for user_id=%s", user_id)
        else:
            logger.warning(
                "update_user_fields failed for user_id=%s error=%s",
                user_id,
                res.get("error"),
            )
        return res

    # ------------------------------------------------------------------
    # Sessions / Pantry / Meal Plans / Outgoing (keep existing behavior)
    # ------------------------------------------------------------------
    async def create_session(
        self, user_id: int, prompt: str, response_text: str
    ) -> Dict[str, Any]:
        """
        Create a lightweight session (audit) row in `sessions` table.
        """
        logger.info("create_session: user_id=%s prompt=%s", user_id, prompt)
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        row = {
            "user_id": user_id,
            "prompt": prompt,
            "response": response_text,
            "created_at": _now_iso(),
        }

        def _fn(data):
            return self.client.table("sessions").insert(data).execute()

        res = await self._call_db(_fn, row)
        if res.get("ok"):
            logger.debug("create_session: inserted for user_id=%s", user_id)
        else:
            logger.warning("create_session failed: %s", res.get("error"))
        return res

    def create_session_sync(self, user_id: int, prompt: str, response_text: str):
        """
        Sync wrapper around create_session.
        This is only for sync contexts (e.g., TwilioClient._persist_outgoing).
        """
        try:
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass  # no loop running

            if loop and loop.is_running():
                # Already inside an event loop (FastAPI) → run in a thread
                logger.debug(
                    "create_session_sync: running async create_session in thread executor"
                )
                return asyncio.run_coroutine_threadsafe(
                    self.create_session(user_id, prompt, response_text), loop
                ).result()
            else:
                # No loop → safe to run directly
                logger.debug(
                    "create_session_sync: running async create_session with asyncio.run()"
                )
                return asyncio.run(self.create_session(user_id, prompt, response_text))
        except Exception as exc:
            logger.exception("create_session_sync failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def upsert_user_pantry_items(
        self, user_id: int, items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        logger.info(
            "upsert_user_pantry_items: user_id=%s items=%s",
            user_id,
            len(items) if items else 0,
        )
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        if not items:
            return {"ok": True, "data": [], "inserted": []}

        normalized = []
        seen = set()
        for it in items:
            ing = _normalize_ingredient(it.get("ingredient") or "")
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

        def _fn_delete_and_insert(uid, ings, rows):
            tbl = self.client.table("user_pantry")
            try:
                if ings:
                    tbl.delete().eq("user_id", uid).in_("ingredient", ings).execute()
            except Exception:
                for ing in ings:
                    tbl.delete().eq("user_id", uid).eq("ingredient", ing).execute()
            if rows:
                return tbl.insert(rows).execute()
            return {"data": []}

        res = await self._call_db(
            _fn_delete_and_insert, user_id, ingredient_list, normalized
        )
        if res.get("ok") and res.get("data"):
            res["inserted"] = (
                res["data"] if isinstance(res["data"], list) else [res["data"]]
            )
            logger.debug("upsert_user_pantry_items: inserted=%s", len(res["inserted"]))
        else:
            res["inserted"] = []
            logger.warning("upsert_user_pantry_items: nothing inserted or error")
        return res

    async def create_meal_plan(
        self, user_id: int, plan_json: Dict[str, Any], pdf_url: Optional[str] = None
    ) -> Dict[str, Any]:
        logger.info("create_meal_plan: user_id=%s", user_id)
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        row = {
            "user_id": user_id,
            "plan_json": plan_json,
            "pdf_url": pdf_url,
            "created_at": _now_iso(),
        }

        def _fn(data):
            return self.client.table("meal_plans").insert(data).execute()

        res = await self._call_db(_fn, row)
        if res.get("ok"):
            logger.debug("create_meal_plan: created for user_id=%s", user_id)
        else:
            logger.warning("create_meal_plan failed: %s", res.get("error"))
        return res

    # Outgoing messages and other utilities would go here if needed (left unchanged)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Onboarding helpers (robust and logged)
    # ------------------------------------------------------------------
    async def update_user_onboarding_step(
        self, user_or_whatsapp: Any, step: Optional[int]
    ):
        """
        Update the user's onboarding_step.

        Accept either:
          - user_id (int) as first arg -> updates by id
          - whatsapp_id (str) as first arg -> updates by whatsapp_id

        Returns the update result dict from update_user_fields or direct DB update.
        """
        logger.info(
            "update_user_onboarding_step: identifier=%s step=%s", user_or_whatsapp, step
        )
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        # if numeric id provided -> use update_user_fields for consistency
        if isinstance(user_or_whatsapp, int):
            return await self.update_user_fields(
                user_or_whatsapp, {"onboarding_step": step}
            )

        # assume whatsapp_id string -> update by whatsapp_id
        whatsapp_id = str(user_or_whatsapp)

        def _fn(wid, step_val):
            tbl = self.client.table("users")
            return (
                tbl.update({"onboarding_step": step_val})
                .eq("whatsapp_id", wid)
                .execute()
            )

        res = await self._call_db(_fn, whatsapp_id, step)
        if res.get("ok"):
            logger.debug(
                "update_user_onboarding_step: updated whatsapp_id=%s", whatsapp_id
            )
        else:
            logger.warning(
                "update_user_onboarding_step failed whatsapp_id=%s error=%s",
                whatsapp_id,
                res.get("error"),
            )
        return res

    async def update_user_name_and_onboarding_step(
        self, user_id: int, name: str, step: int
    ):
        logger.info(
            "update_user_name_and_onboarding_step: user_id=%s name=%s step=%s",
            user_id,
            name,
            step,
        )
        return await self.update_user_fields(
            user_id, {"name": name, "onboarding_step": step}
        )

    async def update_user_diet_and_onboarding_step(
        self, user_id: int, diet: str, step: int
    ):
        logger.info(
            "update_user_diet_and_onboarding_step: user_id=%s diet=%s step=%s",
            user_id,
            diet,
            step,
        )
        return await self.update_user_fields(
            user_id, {"diet": diet, "onboarding_step": step}
        )

    async def update_user_cuisine_and_onboarding_step(
        self, user_id: int, cuisine: str, step: int
    ):
        logger.info(
            "update_user_cuisine_and_onboarding_step: user_id=%s cuisine=%s step=%s",
            user_id,
            cuisine,
            step,
        )
        return await self.update_user_fields(
            user_id, {"cuisine_pref": cuisine, "onboarding_step": step}
        )

    async def update_user_allergies_and_onboarding_step(
        self, user_id: int, allergies: list, step: int
    ):
        logger.info(
            "update_user_allergies_and_onboarding_step: user_id=%s allergies=%s step=%s",
            user_id,
            allergies,
            step,
        )
        return await self.update_user_fields(
            user_id, {"allergies": allergies, "onboarding_step": step}
        )

    async def update_user_household_and_complete_onboarding(
        self, user_id: int, household: str
    ):
        logger.info(
            "update_user_household_and_complete_onboarding: user_id=%s household=%s",
            user_id,
            household,
        )
        return await self.update_user_fields(
            user_id, {"household_size": household, "onboarding_step": None}
        )
