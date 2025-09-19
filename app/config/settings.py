# app/config/settings.py
"""
Application configuration using pydantic-settings (pydantic v2 style).

This centralizes environment-driven configuration. Prefer reading values
from environment variables; do not rely on os.getenv inline defaults which
can silently hide missing configuration.
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AnyUrl, validator

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Application configuration loaded from environment.

    Relevant environment variables:
      - SUPABASE_URL
      - SUPABASE_SERVICE_ROLE_KEY
      - DATABASE_URL
      - OPENAI_API_KEY
      - GOOGLE_APPLICATION_CREDENTIALS
      - TWILIO_ACCOUNT_SID
      - TWILIO_AUTH_TOKEN
      - TWILIO_PHONE_NUMBER
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: Optional[str] = Field(default=None, env="SUPABASE_URL")
    supabase_service_role_key: Optional[str] = Field(
        default=None, env="SUPABASE_SERVICE_ROLE_KEY"
    )
    database_url: Optional[str] = Field(default=None, env="DATABASE_URL")

    # OpenAI
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")

    # Google Cloud Vision
    google_application_credentials: Optional[str] = Field(
        default=None, env="GOOGLE_APPLICATION_CREDENTIALS"
    )

    # Twilio
    twilio_account_sid: Optional[str] = Field(default=None, env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(default=None, env="TWILIO_AUTH_TOKEN")
    twilio_phone_number: Optional[str] = Field(default=None, env="TWILIO_PHONE_NUMBER")

    # --- validators / post-init checks ---
    @validator("supabase_url")
    def maybe_strip_supabase_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip()

    @validator("supabase_service_role_key")
    def maybe_strip_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip()

    def model_post_init(self, __context) -> None:  # pydantic v2 hooks
        """
        Light-weight validation/notice that runs after model is constructed.
        Uses logging (not print) so messages show up in server logs.
        """
        if not self.supabase_url or not self.supabase_service_role_key:
            logger.warning(
                "Supabase credentials are not configured. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to enable DB features."
            )
        # warn if OpenAI key missing (useful to surface early)
        if not self.openai_api_key:
            logger.info(
                "OPENAI_API_KEY not set. OpenAI-powered features will be disabled."
            )

        # Google credentials
        if not self.google_application_credentials:
            logger.info(
                "GOOGLE_APPLICATION_CREDENTIALS not set. Image OCR features will be disabled."
            )

        # Twilio note
        if not (
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_phone_number
        ):
            logger.info(
                "Twilio credentials missing or incomplete. Twilio fallback/verification may not work."
            )


# single exporter
settings = Settings()
