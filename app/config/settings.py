"""
Configuration settings for the meal planning bot.
"""
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Supabase Database
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    
    def model_post_init(self, __context):
        """Validate settings after initialization."""
        # Make Supabase optional for development/testing environments
        if not self.supabase_url or not self.supabase_service_role_key:
            print("⚠️ Warning: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY not set. Supabase features will be disabled.")
    
    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    
    # WhatsApp Cloud API (will be added when we get the keys)
    whatsapp_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    whatsapp_token: str = os.getenv("WHATSAPP_TOKEN", "")
    whatsapp_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "mambo_verify_token")
    
    # Google Cloud Vision
    google_application_credentials: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    
    # Twilio (for backup/verification)
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_phone_number: str = os.getenv("TWILIO_PHONE_NUMBER", "")
    
    class Config:
        env_file = ".env"

settings = Settings()