# app/services/user_service.py
from typing import Any, Dict, Optional
from datetime import datetime


class UserService:
    """
    Thin service wrapper around a DB client (eg. Supabase client or similar).
    * Expects a client with a .table(name) method that returns a query proxy
      with methods like .select(...).eq(...).insert(...).update(...).upsert(...).execute()
    * All public methods return {"ok": bool, "data": Any, "error": Optional[str]}
    """

    def __init__(self, db_client):
        self.db = db_client

    def _ok(self, data: Any = None):
        return {"ok": True, "data": data, "error": None}

    def _err(self, message: str):
        return {"ok": False, "data": None, "error": message}

    def _normalize_response(self, resp) -> Dict[str, Any]:
        """
        Accept a typical client response and extract `.data` or dict-like content.
        This is defensive: different clients return different shapes.
        """
        if resp is None:
            return {"ok": False, "data": None, "error": "empty response from db client"}
        # if response looks like supabase-py: has attributes `.data` and `.error`
        data = None
        error = None
        try:
            data = getattr(resp, "data", None)
            err_obj = getattr(resp, "error", None)
            if err_obj:
                error = str(err_obj)
        except Exception:
            # try dict-like
            try:
                data = resp.get("data")
                error = resp.get("error")
            except Exception:
                data = resp
        return {"ok": error is None, "data": data, "error": error}

    def get_user(
        self, user_id: Optional[int] = None, whatsapp_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieve a single user by id or whatsapp_id. At least one must be provided.
        """
        if not user_id and not whatsapp_id:
            return self._err("get_user requires either user_id or whatsapp_id")

        q = self.db.table("users").select("*")
        if user_id:
            q = q.eq("id", user_id)
        else:
            q = q.eq("whatsapp_id", whatsapp_id)

        q = q.limit(1)
        try:
            resp = q.execute()
        except Exception as e:
            return self._err(f"DB error during get_user: {e}")

        norm = self._normalize_response(resp)
        if not norm["ok"]:
            return self._err(f"get_user db error: {norm['error']}")
        rows = norm["data"] or []
        return self._ok(rows[0] if rows else None)

    def create_or_update_user(
        self, whatsapp_id: Optional[str] = None, user_id: Optional[int] = None, **fields
    ) -> Dict[str, Any]:
        """
        Create or update a user. Prefer upsert by whatsapp_id if provided, else by id.
        Returns the created/updated row.
        """
        if not whatsapp_id and not user_id:
            return self._err("create_or_update_user requires whatsapp_id or user_id")

        payload = {**fields}
        if whatsapp_id:
            payload["whatsapp_id"] = whatsapp_id
        if user_id:
            payload["id"] = user_id

        # Always add last_active timestamp if not supplied
        if "last_active" not in payload:
            payload["last_active"] = datetime.utcnow().isoformat()

        # Try a defensive upsert first, but *don't* chain .select() to the upsert call
        # (some clients/versions error on .upsert(...).select("*"))
        try:
            # Prefer on_conflict to be whatsapp_id if available else id
            on_conflict = "whatsapp_id" if whatsapp_id else "id"
            upsert_resp = (
                self.db.table("users")
                .upsert(payload, on_conflict=on_conflict)
                .execute()
            )
            upsert_norm = self._normalize_response(upsert_resp)
            if upsert_norm["ok"] and upsert_norm["data"]:
                # If returned data present, return it.
                # Some clients don't return the row on upsert; we'll SELECT below in that case.
                if upsert_norm["data"]:
                    # If API returned the inserted/updated row(s) directly, return the first row
                    rows = upsert_norm["data"]
                    return self._ok(rows[0] if isinstance(rows, list) else rows)
        except Exception:
            # swallow and fallback to safe path (see below)
            pass

        # Fallback: check if exists and then update or insert, then select the row
        try:
            # Does user already exist?
            exists_q = self.db.table("users").select("*")
            if whatsapp_id:
                exists_q = exists_q.eq("whatsapp_id", whatsapp_id)
            else:
                exists_q = exists_q.eq("id", user_id)
            exists_q = exists_q.limit(1)
            exists_resp = exists_q.execute()
            exists_norm = self._normalize_response(exists_resp)
            if not exists_norm["ok"]:
                return self._err(
                    f"create_or_update_user: error checking existing user: {exists_norm['error']}"
                )

            exists = exists_norm["data"] or []
            if exists:
                # update
                update_fields = {k: v for k, v in payload.items() if k not in ("id",)}
                update_q = self.db.table("users").update(update_fields)
                if whatsapp_id:
                    update_q = update_q.eq("whatsapp_id", whatsapp_id)
                else:
                    update_q = update_q.eq("id", user_id)
                update_resp = update_q.execute()
                update_norm = self._normalize_response(update_resp)
                # If update didn't return rows, fetch row explicitly
            else:
                # insert
                insert_resp = self.db.table("users").insert(payload).execute()
                insert_norm = self._normalize_response(insert_resp)
                if not insert_norm["ok"]:
                    return self._err(
                        f"create_or_update_user insert failed: {insert_norm['error']}"
                    )
            # Finally select the row to return what we have in DB
            final = self.get_user(user_id=user_id, whatsapp_id=whatsapp_id)
            return final
        except Exception as e:
            return self._err(f"create_or_update_user fallback error: {e}")

    def delete_user(
        self, user_id: Optional[int] = None, whatsapp_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Delete a user by id or whatsapp_id.
        """
        if not user_id and not whatsapp_id:
            return self._err("delete_user requires either user_id or whatsapp_id")

        q = self.db.table("users")
        if user_id:
            q = q.delete().eq("id", user_id)
        else:
            q = q.delete().eq("whatsapp_id", whatsapp_id)

        try:
            resp = q.execute()
        except Exception as e:
            return self._err(f"DB error during delete_user: {e}")

        norm = self._normalize_response(resp)
        if not norm["ok"]:
            return self._err(f"delete_user db error: {norm['error']}")
        return self._ok(norm["data"])
