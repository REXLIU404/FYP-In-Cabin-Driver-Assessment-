"""Typed runtime configuration (pydantic-settings).

Mirrors the frontend AppConfig defaults so the backend fusion produces the same
scores as the TypeScript prototype. Values can be overridden via environment
variables or a .env file.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DRA_")

    database_url: str = "sqlite:///./driver_risk.db"

    # Fusion weights (transparent design parameters; w_v + w_t = 1)
    weight_vision: float = 0.5
    weight_telemetry: float = 0.5

    # Risk-level thresholds on the 0-100 RiskScore scale
    threshold_low: float = 30.0
    threshold_high: float = 60.0

    # Temporal / freshness parameters
    ema_alpha: float = 0.35
    freshness_tolerance_s: float = 3.0


settings = Settings()
