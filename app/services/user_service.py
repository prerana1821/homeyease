# app/services/user_service.py
"""
User service for database operations using Supabase.

This version is defensive about supabase-python client shapes and returns
structured dicts to make diagnostics easier in higher layers.
"""
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import asyncio
import logging

from app.config.supabase import supabase_client

logger = logging.getLogger(__name__)


def _parse_supabase_response(resp: Any) -> Dict[str, Any]:
    """
    Normalize a supabase client response in a best-effort way.
    Returns: {'ok': bool, 'data': <possibly list or dict>, 'status_code': int|None, 'raw': resp}
    """
    if resp is None:
        return {"ok": False, "data": None, "status_code": None, "raw": resp}

    # Some client versions return an object with .data attribute
    if hasattr(resp, "data"):
        data = getattr(resp, "data")
        status_code = getattr(resp, "status_code", None)
        return {
            "ok": True if data else False,
            "data": data,
            "status_code": status_code,
            "raw": resp,
        }

    # Some versions return a dict-like result
    try:
        if isinstance(resp, dict):
            data = resp.get("data", resp.get("result", resp.get("records", None)))
            status_code = resp.get("status_code", resp.get("statusCode", None))
            ok = True if data else False
            return {"ok": ok, "data": data, "status_code": status_code, "raw": resp}
    except Exception:
        pass

    # Fallback: stringify
    return {"ok": False, "data": None, "status_code": None, "raw": resp}


def _run_db(fn: Callable, *args, **kwargs):
    """
    Run blocking DB function in a thread and return the raw result.
    Designed to be called with asyncio.to_thread or wrapped by callers.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        # bubble up - caller will wrap
        raise


class UserService:

    def __init__(self):
        # supabase_client.client may be None; keep it lazy
        self.client = supabase_client.client
        if self.client is None:
            logger.warning("Supabase client not available. DB operations will fail.")

    # Helper used across methods to call sync supabase functions in a background thread
    async def _call_db(self, fn: Callable, *args, **kwargs) -> Dict[str, Any]:
        """
        Run fn(*args, **kwargs) in a thread and parse the supabase response.
        Returns: normalized dict from _parse_supabase_response
        """
        if self.client is None:
            return {
                "ok": False,
                "error": "no_supabase_client",
                "diagnostics": {"client": None},
            }

        try:
            raw = await asyncio.to_thread(_run_db, fn, *args, **kwargs)
            parsed = _parse_supabase_response(raw)
            parsed["diagnostics"] = {
                "called": getattr(fn, "__name__", str(fn)),
                "raw_repr": str(raw)[:1000],
            }
            return parsed
        except Exception as exc:
            logger.exception("DB call failed: %s", exc)
            return {
                "ok": False,
                "error": str(exc),
                "diagnostics": {"fn": getattr(fn, "__name__", str(fn))},
            }

    # Basic fetch
    async def get_user_by_whatsapp_id(self, whatsapp_id: str) -> Dict[str, Any]:
        """Get user by WhatsApp ID. Returns structured dict for diagnostics."""
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        def _fn():
            tbl = self.client.table("users")
            # prefer single() if available, else filter+limit
            try:
                return tbl.select("*").eq("whatsapp_id", whatsapp_id).single().execute()
            except Exception:
                # fallback approach
                try:
                    return (
                        tbl.select("*")
                        .eq("whatsapp_id", whatsapp_id)
                        .limit(1)
                        .execute()
                    )
                except Exception as exc:
                    raise

        return await self._call_db(_fn)

    async def create_user(
        self, whatsapp_id: str, name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create or upsert a user. Returns diagnostics and created row if available."""
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        user_data = {
            "whatsapp_id": whatsapp_id,
            "name": name or "Guest",
            "onboarding_step": 0,
            "created_at": datetime.utcnow().isoformat(),
            "last_active": datetime.utcnow().isoformat(),
        }

        def _fn(data):
            tbl = self.client.table("users")
            # some supabase clients allow upsert(...).select().execute() while others don't.
            try:
                # Try the more modern form
                return tbl.upsert(data, on_conflict="whatsapp_id").execute()
            except Exception:
                # Some older clients returned a query builder that accepts 'upsert' and then `execute()` only.
                return tbl.upsert(data, on_conflict="whatsapp_id").execute()

        res = await self._call_db(_fn, user_data)
        # Normalize extracted single row result into res['result']
        if res.get("ok") and res.get("data"):
            # data may be a list or single dict
            data = res.get("data")
            if isinstance(data, list) and len(data) > 0:
                res["result"] = data[0]
            else:
                res["result"] = data
        return res

    async def update_user_onboarding_step(
        self, user_id: int, step: Optional[int]
    ) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        def _fn():
            return (
                self.client.table("users")
                .update(
                    {
                        "onboarding_step": step,
                        "last_active": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", user_id)
                .execute()
            )

        return await self._call_db(_fn)

    async def update_user_name_and_onboarding_step(
        self, user_id: int, name: str, step: Optional[int]
    ) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        def _fn():
            return (
                self.client.table("users")
                .update(
                    {
                        "name": name,
                        "onboarding_step": step,
                        "last_active": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", user_id)
                .execute()
            )

        return await self._call_db(_fn)

    async def update_user_diet_and_onboarding_step(
        self, user_id: int, diet: str, step: Optional[int]
    ) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        def _fn():
            return (
                self.client.table("users")
                .update(
                    {
                        "diet": diet,
                        "onboarding_step": step,
                        "last_active": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", user_id)
                .execute()
            )

        return await self._call_db(_fn)

    async def update_user_cuisine_and_onboarding_step(
        self, user_id: int, cuisine: str, step: Optional[int]
    ) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        def _fn():
            return (
                self.client.table("users")
                .update(
                    {
                        "cuisine_pref": cuisine,
                        "onboarding_step": step,
                        "last_active": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", user_id)
                .execute()
            )

        return await self._call_db(_fn)

    async def update_user_allergies_and_onboarding_step(
        self, user_id: int, allergies: List[str], step: Optional[int]
    ) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        def _fn():
            return (
                self.client.table("users")
                .update(
                    {
                        "allergies": allergies,
                        "onboarding_step": step,
                        "last_active": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", user_id)
                .execute()
            )

        return await self._call_db(_fn)

    async def update_user_household_and_complete_onboarding(
        self, user_id: int, household_size: str
    ) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}

        def _fn():
            return (
                self.client.table("users")
                .update(
                    {
                        "household_size": household_size,
                        "onboarding_step": None,
                        "last_active": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", user_id)
                .execute()
            )

        return await self._call_db(_fn)

    async def upsert_user(
        self, whatsapp_id: str, user_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generic upsert wrapper - merges whatsapp_id into the payload."""
        if self.client is None:
            return {"ok": False, "error": "no_supabase_client"}
        user_data["whatsapp_id"] = whatsapp_id
        user_data["last_active"] = datetime.utcnow().isoformat()

        def _fn(data):
            return (
                self.client.table("users")
                .upsert(data, on_conflict="whatsapp_id")
                .execute()
            )

        res = await self._call_db(_fn, user_data)
        if res.get("ok") and res.get("data"):
            data = res.get("data")
            res["result"] = data[0] if isinstance(data, list) and data else data
        return res
