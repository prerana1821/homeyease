# app/db/client.py
"""
Supabase client accessor / diagnostics.

Keep this file strictly focused on returning the already-initialized global
Supabase client (created in app.config.supabase). Fail fast and provide
diagnostic helpers so API endpoints can include useful, non-sensitive info
about the client's state when returning status to callers.

Usage:
    from app.db.client import get_supabase_client, get_client_diagnostics

    client = get_supabase_client()
    # or
    diag = get_client_diagnostics()
"""
from functools import lru_cache
import logging
from typing import Any, Dict

from app.config.supabase import (
    supabase_client,
)  # global instance created in that module

logger = logging.getLogger(__name__)


class SupabaseClientNotInitialized(RuntimeError):
    """Raised when the supabase client is not available at runtime."""

    def __init__(self, msg: str):
        super().__init__(msg)


@lru_cache(maxsize=1)
def get_supabase_client() -> Any:
    """
    Return the initialized Supabase client.

    This function strictly returns the *already-created* client object that
    should have been instantiated when `app.config.supabase` ran during app
    startup/import. If the client is missing or malformed, raise a clear,
    actionable error rather than returning None.

    Raises:
        SupabaseClientNotInitialized: if the supabase client is not available
            or does not appear to be initialized correctly.
    """
    client = getattr(supabase_client, "client", None)

    if client is None:
        msg = (
            "Supabase client is not initialized. This usually means one of:\n"
            "  1) Environment variables SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (or similar) are missing/invalid,\n"
            "  2) The module app.config.supabase failed to create the client at import time,\n"
            "  3) Tests or runtime mutated the `supabase_client` object.\n\n"
            "Fix: Verify your environment, check app.config.supabase for errors, and ensure it is imported before calling DB helpers."
        )
        logger.error(msg)
        raise SupabaseClientNotInitialized(msg)

    # Basic sanity checks: ensure the object has expected attributes we will rely on.
    # We intentionally do not call any network operations here — keep this cheap.
    required_attrs = (
        "auth",
        "postgrest",
        "from_",
    )  # common attributes on supabase client wrappers
    missing = [a for a in required_attrs if not hasattr(client, a)]
    if missing:
        logger.warning(
            "Supabase client exists but is missing expected attribute(s): %s. "
            "This may indicate a custom wrapper or a different client library.",
            ", ".join(missing),
        )

    return client


def is_initialized() -> bool:
    """
    Lightweight check for whether the supabase client appears initialized.

    Returns:
        True if the client object exists (cheap), False otherwise.
    """
    try:
        _ = get_supabase_client()
        return True
    except SupabaseClientNotInitialized:
        return False
    except Exception:  # defensive: any unexpected error -> consider not initialized
        logger.exception(
            "Unexpected error while checking Supabase client initialization"
        )
        return False


def get_client_diagnostics() -> Dict[str, Any]:
    """
    Return a small, non-sensitive diagnostics dict about the supabase client.

    This is intended to be safe to include in API health responses or logs.
    DO NOT include secrets, tokens, or connection strings — only structural info.

    Example return:
    {
        "initialized": True,
        "has_auth": True,
        "has_postgrest": True,
        "wrapper_attrs": ["client", "health_check"],
    }

    Notes:
        - Keep this function local and cheap: it performs attribute inspection only.
        - If you want a network-level health check (ping DB), call your existing
          `supabase_client.health_check()` function instead (it likely lives in
          app.config.supabase).
    """
    diag: Dict[str, Any] = {
        "initialized": False,
        "has_auth": False,
        "has_postgrest": False,
        "wrapper_attrs": [],
    }
    try:
        # We don't call network; only introspect
        wrapper = supabase_client
        wrapper_attrs = [a for a in dir(wrapper) if not a.startswith("_")]
        diag["wrapper_attrs"] = wrapper_attrs

        client = getattr(wrapper, "client", None)
        diag["initialized"] = client is not None

        if client is not None:
            diag["has_auth"] = hasattr(client, "auth")
            diag["has_postgrest"] = hasattr(client, "postgrest")
            # also surface whether a common helper exists (used in this project)
            diag["has_health_check"] = hasattr(wrapper, "health_check")
        else:
            diag["has_health_check"] = hasattr(wrapper, "health_check")

    except Exception:
        logger.exception("Error while producing Supabase client diagnostics")
        diag["error"] = "exception while gathering diagnostics"

    return diag
