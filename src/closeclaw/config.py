"""Configuration management using pydantic-settings.

Priority (high → low): init kwargs > env vars > .env > config.yaml > defaults
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# Set by get_settings() before constructing the singleton.
_config_file: str | Path | None = None


class AgentSettings(BaseModel):
    """Agent-related settings, typically from config.yaml."""

    agent_file: str = ""
    workspace: str = ""

    @model_validator(mode="after")
    def _expand_paths(self) -> AgentSettings:
        if self.agent_file:
            self.agent_file = str(Path(self.agent_file).expanduser())
        if self.workspace:
            self.workspace = str(Path(self.workspace).expanduser())
        return self


class Settings(BaseSettings):
    """Application settings, loaded from env / .env / config.yaml."""

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

    # --- Agent ---
    agent: AgentSettings = AgentSettings()

    @property
    def allowed_user_ids(self) -> list[int]:
        """Parse ``telegram_allowed_users`` into a list of ints."""
        raw = self.telegram_allowed_users.strip()
        if not raw:
            return []
        return [int(x.strip()) for x in raw.split(",")]

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(
                settings_cls, yaml_file=_config_file or "config.yaml"
            ),
            file_secret_settings,
        )


# Singleton-ish helper – import and call once at startup.
_settings: Settings | None = None


def get_settings(*, config_file: str | Path | None = None) -> Settings:
    global _settings, _config_file
    if _settings is None:
        _config_file = config_file
        _settings = Settings()
    return _settings
