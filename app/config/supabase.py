"""
Supabase client configuration with singleton pattern.
"""
import os
from typing import Optional
from supabase import create_client, Client
from app.config.settings import settings

class SupabaseClient:
    """Singleton Supabase client for database operations."""
    
    _instance: Optional['SupabaseClient'] = None
    _client: Optional[Client] = None
    
    def __new__(cls) -> 'SupabaseClient':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize the Supabase client."""
        if not settings.supabase_url or not settings.supabase_service_role_key:
            print("⚠️ Supabase credentials not available. Client will not be initialized.")
            self._client = None
            return
        
        try:
            self._client = create_client(
                settings.supabase_url,
                settings.supabase_service_role_key
            )
        except Exception as e:
            print(f"❌ Failed to initialize Supabase client: {e}")
            self._client = None
    
    @property
    def client(self) -> Optional[Client]:
        """Get the Supabase client instance."""
        if self._client is None:
            self._initialize_client()
        return self._client
    
    async def health_check(self) -> bool:
        """Check if Supabase connection is healthy."""
        if self._client is None:
            return False
        
        try:
            # Simple query to test connection
            result = self._client.table('users').select('id').limit(1).execute()
            return True
        except Exception as e:
            print(f"Supabase health check failed: {e}")
            return False

# Global instance
supabase_client = SupabaseClient()