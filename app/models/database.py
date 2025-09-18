"""
Database connection using Supabase.
Keep this wrapper simple and strict: return the (already-created) global client
and raise an explicit error if it's unavailable.
"""
from typing import Any
from app.config.supabase import supabase_client  # global instance created in that module


def get_supabase_client() -> Any:
    """Return the initialized Supabase client or raise a clear error."""
    client = supabase_client.client
    if client is None:
        # Fail fast — better than surprising NoneType errors downstream
        raise RuntimeError(
            "Supabase client is not initialized. "
            "Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, and ensure the supabase module was imported at startup."
        )
    return client
