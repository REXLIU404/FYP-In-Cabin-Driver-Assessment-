"""Typed runtime configuration (pydantic-settings).

Mirrors the frontend AppConfig defaults so the backend fusion produces the same
scores as the TypeScript prototype. Values can be overridden via environment
variables or a .env file.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from pydantic import model_validator


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
    model_root: Path = Path(__file__).resolve().parents[2] / "ml" / "outputs"
    inference_threads: int = 2
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    @model_validator(mode="after")
    def check_runtime(self):
        from .schemas import RuntimeConfig
        RuntimeConfig(**{key: getattr(self, key) for key in RuntimeConfig.model_fields})
        if self.inference_threads < 1:
            raise ValueError("inference_threads must be positive")
        return self


settings = Settings()
