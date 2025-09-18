"""
User service for database operations using Supabase.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.config.supabase import supabase_client

class UserService:
    def __init__(self):
        self.client = supabase_client.client
        if self.client is None:
            print("⚠️ Warning: Supabase client not available. Database operations will fail.")
    
    async def get_user_by_whatsapp_id(self, whatsapp_id: str) -> Optional[Dict[str, Any]]:
        """Get user by WhatsApp ID."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            response = self.client.table('users').select('*').eq('whatsapp_id', whatsapp_id).single().execute()
            return response.data if response.data else None
        except Exception as e:
            print(f"Error getting user by whatsapp_id: {e}")
            return None
    
    async def create_user(self, whatsapp_id: str, name: str = None) -> Optional[Dict[str, Any]]:
        """Create a new user using upsert to prevent duplicate key errors."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            user_data = {
                'whatsapp_id': whatsapp_id,
                'name': name if name is not None else 'Guest',
                'onboarding_step': 0,  # Start onboarding
                'created_at': datetime.utcnow().isoformat(),
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').upsert(
                user_data, 
                on_conflict='whatsapp_id'
            ).select().execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    async def update_user_onboarding_step(self, user_id: int, step: Optional[int]) -> Optional[Dict[str, Any]]:
        """Update user onboarding step."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'onboarding_step': step,
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select('*').execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating onboarding step: {e}")
            return None
    
    async def update_user_name(self, user_id: int, name: str) -> Optional[Dict[str, Any]]:
        """Update user name."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'name': name,
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select('*').execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user name: {e}")
            return None
    
    async def update_user_diet(self, user_id: int, diet: str) -> Optional[Dict[str, Any]]:
        """Update user diet preference."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'diet': diet,
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select('*').execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user diet: {e}")
            return None
    
    async def update_user_cuisine(self, user_id: int, cuisine: str) -> Optional[Dict[str, Any]]:
        """Update user cuisine preference."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'cuisine_pref': cuisine,
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select('*').execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user cuisine: {e}")
            return None
    
    async def update_user_allergies(self, user_id: int, allergies: List[str]) -> Optional[Dict[str, Any]]:
        """Update user allergies."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'allergies': allergies,
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select('*').execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user allergies: {e}")
            return None
    
    async def update_user_household(self, user_id: int, household_size: str) -> Optional[Dict[str, Any]]:
        """Update user household size."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'household_size': household_size,
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select('*').execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user household: {e}")
            return None
    
    async def upsert_user(self, whatsapp_id: str, user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Upsert user data using Supabase's efficient upsert operation."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            user_data['whatsapp_id'] = whatsapp_id
            user_data['last_active'] = datetime.utcnow().isoformat()
            
            response = self.client.table('users').upsert(
                user_data, 
                on_conflict='whatsapp_id'
            ).select().execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error upserting user: {e}")
            return None
    
    # Combined update methods for better performance (reduce round-trips)
    async def update_user_name_and_onboarding_step(self, user_id: int, name: str, step: Optional[int]) -> Optional[Dict[str, Any]]:
        """Update user name and onboarding step in a single operation."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'name': name,
                'onboarding_step': step,
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select().execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user name and onboarding step: {e}")
            return None
    
    async def update_user_diet_and_onboarding_step(self, user_id: int, diet: str, step: Optional[int]) -> Optional[Dict[str, Any]]:
        """Update user diet and onboarding step in a single operation."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'diet': diet,
                'onboarding_step': step,
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select().execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user diet and onboarding step: {e}")
            return None
    
    async def update_user_cuisine_and_onboarding_step(self, user_id: int, cuisine: str, step: Optional[int]) -> Optional[Dict[str, Any]]:
        """Update user cuisine and onboarding step in a single operation."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'cuisine_pref': cuisine,
                'onboarding_step': step,
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select().execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user cuisine and onboarding step: {e}")
            return None
    
    async def update_user_allergies_and_onboarding_step(self, user_id: int, allergies: List[str], step: Optional[int]) -> Optional[Dict[str, Any]]:
        """Update user allergies and onboarding step in a single operation."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'allergies': allergies,
                'onboarding_step': step,
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select().execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user allergies and onboarding step: {e}")
            return None
    
    async def update_user_household_and_complete_onboarding(self, user_id: int, household_size: str) -> Optional[Dict[str, Any]]:
        """Update user household and complete onboarding (set step to None) in a single operation."""
        if self.client is None:
            print("❌ Supabase client not available")
            return None
            
        try:
            update_data = {
                'household_size': household_size,
                'onboarding_step': None,  # Complete onboarding
                'last_active': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('users').update(update_data).eq('id', user_id).select().execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user household and completing onboarding: {e}")
            return None