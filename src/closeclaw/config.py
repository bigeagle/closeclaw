"""Configuration management using pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from .env / environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Kimi / Moonshot API ---
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    kimi_model: str = "kimi-k2.5"

    # --- Telegram ---
    telegram_bot_token: str = ""
    # Stored as comma-separated string to avoid pydantic-settings JSON-parse
    # issues with empty env values.
    telegram_allowed_users: str = ""

    @property
    def allowed_user_ids(self) -> list[int]:
        """Parse ``telegram_allowed_users`` into a list of ints."""
        raw = self.telegram_allowed_users.strip()
        if not raw:
            return []
        return [int(x.strip()) for x in raw.split(",")]


# Singleton-ish helper – import and call once at startup.
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
