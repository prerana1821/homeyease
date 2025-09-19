# app/config/supabase.py
"""
Supabase client singleton and lightweight health check.

This module intentionally:
  - Keeps initialization synchronous (the main uses run_in_executor to call health_check).
  - Performs early validation of configuration and returns a global SupabaseClient
    instance that exposes `.client`, `.health_check()`, and `.diagnostics()`.
  - Avoids logging secrets; diagnostics return structural info only.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from urllib.parse import urlparse

from supabase import create_client, Client  # supabase-py
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Simple strict supabase domain check (https + project ref + .supabase.co)
_SUPABASE_URL_RE = re.compile(r"^https://[A-Za-z0-9\-]+\.supabase\.co/?$")


class SupabaseClient:
    """
    Lightweight wrapper around the supabase-py `Client`.

    Use:
        from app.config.supabase import supabase_client
        client = supabase_client.client  # may be None if not configured
    """

    def __init__(self) -> None:
        self._client: Optional[Client] = None
        self._initialized: bool = False
        # Attempt initialization immediately on import; safe if env missing.
        self._initialize_client()

    def _validate_url(self, url: Optional[str]) -> bool:
        return bool(url and _SUPABASE_URL_RE.match(url))

    def _initialize_client(self) -> None:
        # Avoid re-initializing repeatedly in noisy dev loops
        if self._initialized and self._client is not None:
            return

        supabase_url = (settings.supabase_url or "").strip()
        supabase_key = settings.supabase_service_role_key or ""

        if not supabase_url or not supabase_key:
            logger.debug(
                "Supabase credentials not present at init: url=%r key_present=%s",
                supabase_url,
                bool(supabase_key),
            )
            self._client = None
            self._initialized = True
            return

        if not self._validate_url(supabase_url):
            logger.error(
                "Supabase URL format invalid: %r. Expected https://<project>.supabase.co",
                supabase_url,
            )
            self._client = None
            self._initialized = True
            return

        try:
            # create_client returns the supabase-py client object
            self._client = create_client(supabase_url, supabase_key)
            logger.info(
                "Initialized Supabase client for host=%s", urlparse(supabase_url).netloc
            )
            self._initialized = True
        except Exception as exc:
            logger.exception("Failed to initialize Supabase client: %s", exc)
            self._client = None
            self._initialized = True

    @property
    def client(self) -> Optional[Client]:
        """
        Return the underlying supabase client or None when not configured.

        Note: callers should not assume network connectivity; call `health_check()`
        to verify runtime connectivity.
        """
        # Attempt lazy re-init — useful if env variables are injected at runtime.
        if self._client is None and not self._initialized:
            self._initialize_client()
        return self._client

    def diagnostics(self) -> Dict[str, Any]:
        """
        Return non-sensitive diagnostics about the client configuration.
        Safe to include in logs or in API responses.
        """
        diag: Dict[str, Any] = {
            "configured": bool(
                settings.supabase_url and settings.supabase_service_role_key
            ),
            "client_present": self._client is not None,
            "host": None,
        }
        try:
            if settings.supabase_url:
                diag["host"] = urlparse(settings.supabase_url).netloc
        except Exception:
            diag["host"] = "parse-error"
        return diag

    def health_check(self, timeout_seconds: float = 3.0) -> bool:
        """
        Synchronous health check.

        Strategy:
          1. If no client configured -> False
          2. Execute a very small, cheap query against a known table (users) if it exists.
             The query uses `.execute()` and we handle various client return shapes safely.
          3. Any exception or non-success result -> False.

        Note: This method is intentionally synchronous so callers (startup, /health)
        can call it inside a threadpool executor if desired.
        """
        client = self.client
        if client is None:
            logger.debug("Supabase health_check: no client configured")
            return False

        try:
            # We expect the project to potentially have a 'users' table. If not, the call
            # may return an error object — treat that as unhealthy rather than crashing.
            res = client.table("users").select("id", count="exact").limit(1).execute()
            # The supabase-py response object can vary; check common attributes.
            # Prefer explicit failure checks:
            # - Some versions: res.error is set on error
            # - Some versions: res.status_code present
            if hasattr(res, "error") and res.error:
                logger.warning(
                    "Supabase health_check returned error object: %s",
                    getattr(res, "error"),
                )
                return False
            if (
                hasattr(res, "status_code")
                and isinstance(res.status_code, int)
                and res.status_code >= 400
            ):
                logger.warning("Supabase health_check HTTP status: %s", res.status_code)
                return False
            # If rows key exists, it's likely successful
            if hasattr(res, "data") and res.data is not None:
                return True
            # Fallback: if we see 'count' or other metadata, assume success
            return True
        except Exception as exc:
            logger.exception("Exception during Supabase health_check: %s", exc)
            return False


# Single module-level instance for easy import
supabase_client = SupabaseClient()
