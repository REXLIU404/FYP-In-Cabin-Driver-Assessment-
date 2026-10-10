"""Pydantic v2 schemas — mirror the CURRENT TypeScript RiskUpdate contract.

IMPORTANT (kept in sync with ai/src/types.ts, NOT the older guidebook example):
- RiskScore is on a 0-100 scale (not 0-1).
- DominantEvidence uses the full strings, e.g. "Combined evidence".
- P_telemetry_anomaly is a retained legacy field name = telemetry non-safe
  behaviour probability (1 - P(Safe)), NOT unsupervised anomaly detection.
"""
from typing import Literal, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

RiskLevel = Literal["Low", "Medium", "High"]
AlertSeverity = Literal["NORMAL", "CAUTION", "HIGH_ALERT"]
SystemHealth = Literal["FULL", "DEGRADED", "UNAVAILABLE"]
FreshnessStatus = Literal["fresh", "stale", "missing"]
OperationMode = Literal["PREPARED_SESSION_RUNTIME", "LIVE_MODEL_RUNTIME"]
DominantEvidence = Literal[
    "Vision-dominant",
    "Telemetry-dominant",
    "Combined evidence",
    "Partial evidence",
    "Low observed risk",
]


class VisualClassProbability(BaseModel):
    label: str
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)


class TelemetryBehaviorProbability(BaseModel):
    label: Literal["Safe", "Aggressive", "Distracted"]
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)


class TelemetryFeatureContribution(BaseModel):
    feature: str
    contribution: float


class TelemetryFeatures(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    speed_kmph: float
    accel_x: float
    accel_y: float
    brake_pressure: float
    steering_angle: float
    throttle: float
    lane_deviation: float
    headway_distance: float


class ModalityFreshness(BaseModel):
    vision: FreshnessStatus
    telemetry: FreshnessStatus


class WindowInput(BaseModel):
    """What the client POSTs per Δt. Probabilities originate from the prepared
    session (or, in FYP2, from real MobileNetV3 + XGBoost inference)."""

    P_distraction: float = Field(ge=0.0, le=1.0)
    P_telemetry_anomaly: float = Field(ge=0.0, le=1.0)
    vision_status: FreshnessStatus = "fresh"
    telemetry_status: FreshnessStatus = "fresh"
    timestamp: Optional[str] = None
    visual_top_classes: list[VisualClassProbability] = []
    telemetry_behavior_classes: list[TelemetryBehaviorProbability] = []
    telemetry_feature_contributions: list[TelemetryFeatureContribution] = []
    telemetry_features: Optional[TelemetryFeatures] = None
    latency_ms: int = Field(default=0, ge=0)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value):
        return normalize_timestamp(value) if value is not None else None


def normalize_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    if (parsed - datetime.now(timezone.utc)).total_seconds() > 5:
        raise ValueError("timestamp is in the future; check device clock")
    return parsed.astimezone(timezone.utc).isoformat()


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    weight_vision: float = Field(default=0.5, ge=0, le=1)
    weight_telemetry: float = Field(default=0.5, ge=0, le=1)
    ema_alpha: float = Field(default=0.35, gt=0, le=1)
    threshold_low: float = Field(default=30, ge=0, le=100)
    threshold_high: float = Field(default=60, ge=0, le=100)
    freshness_tolerance_s: float = Field(default=3, gt=0, le=30)

    @model_validator(mode="after")
    def coherent(self):
        if abs(self.weight_vision + self.weight_telemetry - 1) > 1e-6:
            raise ValueError("fusion weights must sum to 1")
        if self.threshold_low >= self.threshold_high:
            raise ValueError("low threshold must be below high threshold")
        return self


class LiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    image_base64: Optional[str] = Field(default=None, max_length=2_800_000)
    captured_at: Optional[str] = None
    telemetry_features: Optional[TelemetryFeatures] = None
    telemetry_timestamp: Optional[str] = None
    telemetry_source: Literal["prepared_replay", "sensor", "missing"] = "missing"

    @field_validator("captured_at", "telemetry_timestamp")
    @classmethod
    def valid_time(cls, value):
        return normalize_timestamp(value) if value is not None else None

    @model_validator(mode="after")
    def consistent_inputs(self):
        if self.image_base64 is not None and self.captured_at is None:
            raise ValueError("image requires captured_at")
        if self.telemetry_features is not None:
            if self.telemetry_timestamp is None or self.telemetry_source == "missing":
                raise ValueError("telemetry requires timestamp and source")
        elif self.telemetry_source != "missing":
            raise ValueError("telemetry source requires feature values")
        return self


class RiskUpdate(BaseModel):
    session_id: str
    window_id: int
    timestamp: str
    P_distraction: float
    P_telemetry_anomaly: float
    RiskScore: float  # 0-100
    RiskLevel: RiskLevel
    DominantEvidence: DominantEvidence
    AlertSeverity: AlertSeverity
    SystemHealth: SystemHealth
    operation_mode: OperationMode = "PREPARED_SESSION_RUNTIME"
    modality_freshness: ModalityFreshness
    latency_ms: int
    visual_top_classes: list[VisualClassProbability] = []
    telemetry_behavior_classes: list[TelemetryBehaviorProbability] = []
    telemetry_feature_contributions: list[TelemetryFeatureContribution] = []
    telemetry_features: Optional[TelemetryFeatures] = None
    explanation: str = ""
    flagged: bool = False
    provenance: dict = Field(default_factory=dict)


class SessionCreate(BaseModel):
    session_id: Optional[str] = Field(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    description: str = ""
    operation_mode: OperationMode = "PREPARED_SESSION_RUNTIME"
    config: RuntimeConfig = Field(default_factory=RuntimeConfig)


class SessionOut(BaseModel):
    id: str
    created_at: str
    total_windows: int
    operation_mode: OperationMode = "PREPARED_SESSION_RUNTIME"


class SystemStatusOut(BaseModel):
    """Latest persisted evidence and current worker readiness for this session.
    Latest health is historical; it is not a claim of current stream freshness."""

    session_id: str
    exists: bool
    total_windows: int
    latest_window_id: Optional[int] = None
    latest_system_health: Optional[SystemHealth] = None
    latest_alert_severity: Optional[AlertSeverity] = None
    ai_provider: str
    models_loaded: bool
    cache_warm: bool
    database_scheme: str
    server_time: str
    model_info: dict = Field(default_factory=dict)
