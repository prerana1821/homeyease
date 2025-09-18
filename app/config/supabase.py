"""
Improved Supabase client singleton with URL validation and safer initialization.
"""
import logging
import re
from typing import Optional
from urllib.parse import urlparse
from supabase import create_client, Client
from app.config.settings import settings

logger = logging.getLogger(__name__)

SUPABASE_URL_RE = re.compile(r"^https://[A-Za-z0-9\-]+\.supabase\.co/?")


class SupabaseClient:
    _instance: Optional["SupabaseClient"] = None
    _client: Optional[Client] = None
    _initialized: bool = False

    def __new__(cls) -> "SupabaseClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Prevent double-init during repeated imports / startup hooks
        if self._initialized:
            return
        self._initialized = True
        self._client = None
        self._initialize_client()

    def _validate_url(self, url: str) -> bool:
        if not url:
            return False
        # Basic strict check for supabase project domain + https
        return bool(SUPABASE_URL_RE.match(url))

    def _initialize_client(self) -> None:
        supabase_url = (settings.supabase_url or "").strip()
        supabase_key = (settings.supabase_service_role_key or "").strip()

        if not supabase_url or not supabase_key:
            logger.warning(
                "Supabase credentials not available: url=%r key_present=%s",
                supabase_url, bool(supabase_key))
            self._client = None
            return

        if not self._validate_url(supabase_url):
            logger.error(
                "Invalid Supabase URL format: %r. Expect https://<ref>.supabase.co",
                supabase_url)
            self._client = None
            return

        try:
            self._client = create_client(supabase_url, supabase_key)
            logger.info("Supabase client initialized for %s",
                        urlparse(supabase_url).netloc)
        except Exception as exc:
            logger.exception("Failed to initialize Supabase client: %s", exc)
            self._client = None

    @property
    def client(self) -> Optional[Client]:
        # Lazy re-init if previously failed but credentials might now be present
        if self._client is None:
            self._initialize_client()
        return self._client

    def health_check(self, timeout_seconds: float = 3.0) -> bool:
        """
        Lightweight health check:
        - If no client: False
        - Try a small select with a short timeout (supabase client calls are synchronous here).
        Note: keep this sync to avoid changing calling code; if you need async, wrap in executor.
        """
        if self._client is None:
            logger.debug("health_check: no supabase client present")
            return False
        try:
            # Simple request to test connectivity. Keep limit small.
            res = self._client.table('users').select(
                'id', count='exact').limit(1).execute()
            # Many supabase client versions put status_code or error in result; check for success
            if hasattr(res, "status_code") and res.status_code >= 400:
                logger.warning("Supabase health check returned status %s",
                               res.status_code)
                return False
            return True
        except Exception as exc:
            logger.exception("Supabase health_check failed: %s", exc)
            return False


# single global instance
supabase_client = SupabaseClient()
