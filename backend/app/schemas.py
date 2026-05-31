"""Pydantic v2 schemas — mirror the CURRENT TypeScript RiskUpdate contract.

IMPORTANT (kept in sync with ai/src/types.ts, NOT the older guidebook example):
- RiskScore is on a 0-100 scale (not 0-1).
- DominantEvidence uses the full strings, e.g. "Combined evidence".
- P_telemetry_anomaly is a retained legacy field name = telemetry non-safe
  behaviour probability (1 - P(Safe)), NOT unsupervised anomaly detection.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

RiskLevel = Literal["Low", "Medium", "High"]
AlertSeverity = Literal["NORMAL", "CAUTION", "HIGH_ALERT"]
SystemHealth = Literal["FULL", "DEGRADED", "UNAVAILABLE"]
FreshnessStatus = Literal["fresh", "stale", "missing"]
OperationMode = Literal["PREPARED_SESSION_RUNTIME"]
DominantEvidence = Literal[
    "Vision-dominant",
    "Telemetry-dominant",
    "Combined evidence",
    "Partial evidence",
    "Low observed risk",
]


class VisualClassProbability(BaseModel):
    label: str
    probability: float


class TelemetryBehaviorProbability(BaseModel):
    label: Literal["Safe", "Aggressive", "Distracted"]
    probability: float


class TelemetryFeatureContribution(BaseModel):
    feature: str
    contribution: float


class TelemetryFeatures(BaseModel):
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
    latency_ms: int = 0


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


class SessionCreate(BaseModel):
    session_id: Optional[str] = None
    description: str = ""


class SessionOut(BaseModel):
    id: str
    created_at: str
    total_windows: int
