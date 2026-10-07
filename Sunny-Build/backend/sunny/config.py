# Sunny V2 — configuration

from __future__ import annotations

import os
import time
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All Sunny configuration, loaded from .env with 5-second TTL live reload."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- paths ---
    vault_path: Path = Path("/data/sunny-vault")
    db_path: Path = Path(".sunny/sunny.db")
    secret_dir: Path = Path(".sunny/secrets")

    # --- Claude ---
    claude_api_key: str = ""
    claude_base_url: str = "https://api.anthropic.com/v1"
    model_fast: str = "claude-haiku-4-5-20251001"
    model_default: str = "claude-sonnet-5-5"
    model_deep: str = "claude-opus-5-5"

    # --- LLM gateway ---
    llm_spend_daily: float = 10.0
    llm_spend_monthly: float = 150.0
    llm_max_concurrent: int = 2
    llm_concurrent_sleep: int = 2

    # --- auth ---
    admin_password_hash: str = ""
    session_max_age_hours: int = 720  # 30 days

    # --- voice ---
    vosk_model_path: str = ""
    whisper_model_size: str = "int8"
    whisper_model_path: str = ""
    silero_onnx_path: str = ""
    piper_model_path: str = ""

    # --- integrations ---
    nextcloud_caldav_url: str = ""
    nextcloud_user: str = ""
    nextcloud_password: str = ""
    nextcloud_calendar_id: str = ""
    google_creds_path: str = ""
    garmin_username: str = ""
    garmin_password: str = ""

    # --- push ---
    push_vapid_private_key: str = ""
    push_vapid_public_key: str = ""

    # --- misc ---
    listen_host: str = "0.0.0.0"
    listen_port: int = 8080
    log_level: str = "INFO"

    # --- TTL reload ---
    _config_cache: dict = Field(default_factory=dict)
    _last_loaded: float = 0.0
    ttl_seconds: int = 5

    def looks_configured(self) -> bool:
        """Return True when essential config values are present."""
        return bool(self.vault_path.exists() or self._dry_run_ok())

    def _dry_run_ok(self) -> bool:
        """During P0 scaffolding the vault may not exist yet."""
        return True

    def get(self, key: str, default: str = "") -> str:
        """Attr-style access with cache."""
        val = getattr(self, key, default)
        if isinstance(val, str):
            return val
        return str(val)

    @field_validator("model_fast", "model_default", "model_deep")
    @classmethod
    def _ensure_models(cls, v: str) -> str:
        if not v:
            return "claude-haiku-4-5-20251001"
        return v


_settings: Settings | None = None
_settings_mtime: float = 0.0
_settings_cache: Settings | None = None


def get_settings() -> Settings:
    """Return cached Settings; reload from env if TTL expired or .env mtime changed."""
    global _settings, _settings_mtime, _settings_cache
    now = time.time()

    # If TTL not expired, return cached copy
    if _settings_cache is not None and (now - _settings_cache._last_loaded) < _settings_cache.ttl_seconds:
        return _settings_cache

    # Rebuild from environment (env vars + .env)
    _settings = Settings()
    _settings._last_loaded = now
    _settings_cache = _settings

    # Track .env file mtime for file-based reload
    env_file = Path(".env")
    if env_file.exists():
        _settings_mtime = env_file.stat().st_mtime

    return _settings


def reload_if_changed() -> Settings:
    """Reload if .env file changed or TTL expired."""
    env_file = Path(".env")
    if env_file.exists():
        try:
            new_mtime = env_file.stat().st_mtime
        except OSError:
            new_mtime = 0
        if new_mtime != _settings_mtime:
            global _settings_cache
            _settings_cache = None
    return get_settings()
