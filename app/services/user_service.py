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
        return {
            "ok": ok,
            "data": data,
            "status_code": status_code,
            "raw": resp
        }
    try:
        if isinstance(resp, dict):
            data = resp.get("data",
                            resp.get("result", resp.get("records", None)))
            status_code = resp.get(
                "status_code", resp.get("statusCode", resp.get("status",
                                                               None)))
            ok = True if data is not None else False
            return {
                "ok": ok,
                "data": data,
                "status_code": status_code,
                "raw": resp
            }
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
            logger.warning(
                "Supabase client not available. DB operations will fail.")

    async def _call_db(self, fn: Callable, *args, **kwargs) -> Dict[str, Any]:
        if self.client is None:
            return {
                "ok": False,
                "error": "no_supabase_client",
                "diagnostics": {}
            }
        try:
            raw = await asyncio.to_thread(_run_db, fn, *args, **kwargs)
            parsed = _parse_supabase_response(raw)
            parsed["diagnostics"] = {
                "called": getattr(fn, "__name__", str(fn)),
                "raw_snippet": str(raw)[:1000],
            }
            return parsed
        except Exception as exc:
            logger.exception("DB call failed: %s", exc)
            return {
                "ok": False,
                "error": str(exc),
                "diagnostics": {
                    "fn": getattr(fn, "__name__", str(fn))
                },
            }

    async def record_incoming_message(
        self,
        message_sid: str,
        user_id: Optional[int],
        from_phone: str,
        raw_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Idempotent record of incoming messages by message_sid."""
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        now = _now_iso()

        def _fn(mid, uid, frm, raw):
            tbl = self.client.table("incoming_messages")
            try:
                return tbl.insert({
                    "message_sid": mid,
                    "user_id": uid,
                    "from_phone": frm,
                    "raw_payload": raw,
                    "processed": False,
                    "created_at": now,
                }).execute()
            except Exception:
                return tbl.select("*").eq("message_sid",
                                          mid).maybe_single().execute()

        return await self._call_db(_fn, message_sid, user_id, from_phone,
                                   raw_payload)

    async def mark_incoming_processed(self,
                                      message_sid: str) -> Dict[str, Any]:
        """Mark incoming message as processed."""
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        now = _now_iso()

        def _fn(mid, processed_at):
            return (self.client.table("incoming_messages").update({
                "processed":
                True,
                "processed_at":
                processed_at
            }).eq("message_sid", mid).execute())

        return await self._call_db(_fn, message_sid, now)

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    async def get_user_by_whatsapp_id(self,
                                      whatsapp_id: str) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        def _fn(wid):
            tbl = self.client.table("users")
            try:
                return tbl.select("*").eq("whatsapp_id",
                                          wid).maybe_single().execute()
            except Exception:
                return tbl.select("*").eq("whatsapp_id",
                                          wid).limit(1).execute()

        res = await self._call_db(_fn, whatsapp_id)
        if res.get("ok") and res.get("data"):
            data = res.get("data")
            if isinstance(data, list) and len(data) > 0:
                res["user"] = data[0]
            else:
                res["user"] = data
        else:
            res["user"] = None
        return res

    async def create_user(self,
                          whatsapp_id: str,
                          name: Optional[str] = None) -> Dict[str, Any]:
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
        else:
            res["user"] = None
        return res

    async def upsert_user(self, whatsapp_id: str,
                          user_data: Dict[str, Any]) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        user_data = {
            **user_data, "whatsapp_id": whatsapp_id,
            "last_active": _now_iso()
        }

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
        else:
            res["user"] = None
        return res

    async def update_user_fields(self, user_id: int,
                                 patch: Dict[str, Any]) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        patch = {**patch, "last_active": _now_iso()}

        def _fn(uid, data):
            return self.client.table("users").update(data).eq("id",
                                                              uid).execute()

        res = await self._call_db(_fn, user_id, patch)
        if res.get("ok") and res.get("data"):
            res["result"] = res["data"]
        return res

    # ------------------------------------------------------------------
    # Sessions / Pantry / Meal Plans / Messages
    # (unchanged; omitted here for brevity, keep your existing code)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Onboarding helpers
    # ------------------------------------------------------------------
    async def update_user_onboarding_step(self, user_id: int, step: int):
        return await self.update_user_fields(user_id,
                                             {"onboarding_step": step})

    async def update_user_name_and_onboarding_step(self, user_id: int,
                                                   name: str, step: int):
        return await self.update_user_fields(user_id, {
            "name": name,
            "onboarding_step": step
        })

    async def update_user_diet_and_onboarding_step(self, user_id: int,
                                                   diet: str, step: int):
        return await self.update_user_fields(user_id, {
            "diet": diet,
            "onboarding_step": step
        })

    async def update_user_cuisine_and_onboarding_step(self, user_id: int,
                                                      cuisine: str, step: int):
        return await self.update_user_fields(user_id, {
            "cuisine_pref": cuisine,
            "onboarding_step": step
        })

    async def update_user_allergies_and_onboarding_step(
            self, user_id: int, allergies: list, step: int):
        return await self.update_user_fields(user_id, {
            "allergies": allergies,
            "onboarding_step": step
        })

    async def update_user_household_and_complete_onboarding(
            self, user_id: int, household: str):
        return await self.update_user_fields(user_id, {
            "household_size": household,
            "onboarding_step": None
        })
