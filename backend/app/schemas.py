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
# "stale" is HISTORICAL. Ruling A (D13): the runtime never produces it - evidence older than
# freshness_tolerance_s is expired and recorded as "missing" (provenance: {modality}_expired,
# {modality}_age_s). The literal stays because a stored record written before the ruling carries
# it and must still validate on every read path, and because a sender may still DECLARE a branch
# stale on WindowInput, which the pipeline then treats as expired.
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
    """The canonical per-window record. Availability contract (mirrors
    ai/src/types.ts):

        assessment_available == (RiskScore is not None)
                             == (SystemHealth != "UNAVAILABLE")

    and, when False, RiskScore / RiskLevel / DominantEvidence / AlertSeverity
    are all None together - a window with no usable evidence is never reported as
    a fabricated 0 / "Low" / "NORMAL". When True, all four are present.

    Do NOT give the four nullable fields a default in the class body
    (``RiskLevel: Optional[RiskLevel] = None``): the assignment rebinds the
    class-scope name ``RiskLevel`` - the module-level ``Literal`` alias - and
    pydantic then demands ``None`` for every value. They are required-but-nullable.
    """

    session_id: str
    window_id: int
    timestamp: str
    assessment_available: bool  # before any number, so it is read first
    P_distraction: float
    P_telemetry_anomaly: float
    RiskScore: Optional[float]  # 0-100; None when unavailable
    RiskLevel: Optional[RiskLevel]
    DominantEvidence: Optional[DominantEvidence]
    AlertSeverity: Optional[AlertSeverity]
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

    @model_validator(mode="before")
    @classmethod
    def derive_and_normalise_legacy(cls, data):
        """Defence 1 - rows and producers that predate ``assessment_available``.

        Every read path (windows.py, risk.py, status.py) rebuilds this model from
        the stored JSON blob, so a pre-existing row must still validate. When the
        key is absent the flag is derived from the two signals that used to carry
        it, and any window that is unavailable by either signal is rewritten to
        the canonical unavailable form:

        * legacy rows stored a fabricated ``0 / "Low" / "NORMAL"`` next to
          ``SystemHealth == "UNAVAILABLE"``;
        * a producer can emit ``RiskScore is None`` while still labelling the
          window DEGRADED/NORMAL (e.g. a zero fusion weight on the only fresh
          branch) - the score being None is what makes it unavailable.

        When the key IS present nothing is rewritten: the strict check below
        decides, so a producer that contradicts its own flag fails loudly."""
        if (isinstance(data, dict) and "assessment_available" not in data
                and "RiskScore" in data and "SystemHealth" in data):
            available = data["RiskScore"] is not None and data["SystemHealth"] != "UNAVAILABLE"
            data = {**data, "assessment_available": available}
            if not available:
                data.update(RiskScore=None, RiskLevel=None, DominantEvidence=None,
                            AlertSeverity=None, SystemHealth="UNAVAILABLE")
        return data

    @model_validator(mode="after")
    def availability_invariant(self):
        """Defence 2 - enforce the contract on every instance."""
        values = (self.RiskScore, self.RiskLevel, self.DominantEvidence, self.AlertSeverity)
        if self.assessment_available:
            if any(v is None for v in values):
                raise ValueError("an available assessment must carry RiskScore, RiskLevel, "
                                 "DominantEvidence and AlertSeverity")
            if self.SystemHealth == "UNAVAILABLE":
                raise ValueError("assessment_available is true but SystemHealth is UNAVAILABLE")
        else:
            if any(v is not None for v in values):
                raise ValueError("an unavailable assessment must have RiskScore, RiskLevel, "
                                 "DominantEvidence and AlertSeverity all null")
            if self.SystemHealth != "UNAVAILABLE":
                raise ValueError("assessment_available is false but SystemHealth is not UNAVAILABLE")
        return self


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


class FaultEventOut(BaseModel):
    """One failed ``/infer`` attempt. ``session_id`` is not a foreign key: the row
    outlives the session it failed in (and may name a session that never existed)."""

    id: int
    session_id: Optional[str]
    request_id: Optional[str]
    attempt_index: Optional[int]  # as told by the client (X-Attempt-Index); None = unparseable
    origin: str
    error_category: str
    http_status: Optional[int]
    retryable: bool
    detail: str
    recovery_status: Literal["open", "recovered", "exhausted"]
    recovered_by_request_id: Optional[str]
    occurred_at: str
    recovered_at: Optional[str]


class SystemStatusOut(BaseModel):
    """Latest persisted evidence and current worker readiness for this session.
    Latest health is historical; it is not a claim of current stream freshness."""

    session_id: str
    exists: bool
    total_windows: int
    latest_window_id: Optional[int] = None
    # None = "no record yet"; False = "a record exists but carries no assessment".
    latest_assessment_available: Optional[bool] = None
    latest_risk_score: Optional[float] = None
    latest_system_health: Optional[SystemHealth] = None
    latest_alert_severity: Optional[AlertSeverity] = None
    open_fault_events: int  # faults of this session not yet followed by a new committed record
    ai_provider: str
    models_loaded: bool
    cache_warm: bool
    database_scheme: str
    server_time: str
    model_info: dict = Field(default_factory=dict)
