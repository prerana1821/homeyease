"""
Database connection using Supabase.
"""
# This file is kept for compatibility but all database operations
# are now handled through the Supabase client in app/config/supabase.py

# Import the Supabase client
from app.config.supabase import SupabaseClient

def get_supabase_client():
    """Get Supabase client instance."""
    return SupabaseClient().client