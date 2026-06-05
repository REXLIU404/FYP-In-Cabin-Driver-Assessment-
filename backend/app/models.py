"""SQLAlchemy ORM models for session-level persistence."""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from .db import Base


class SessionMeta(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    description = Column(String, default="")

    records = relationship(
        "InferenceRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InferenceRecord.window_id",
    )


class InferenceRecord(Base):
    __tablename__ = "inference_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    window_id = Column(Integer, index=True)
    timestamp = Column(String)

    # Branch outputs and fused result (RiskScore on the 0-100 scale)
    p_distraction = Column(Float)
    p_telemetry_anomaly = Column(Float)
    risk_score = Column(Float)
    risk_level = Column(String)
    dominant_evidence = Column(String)
    alert_severity = Column(String)
    system_health = Column(String)
    latency_ms = Column(Integer)
    flagged = Column(Boolean, default=False)

    # Full risk_update payload retained for export fidelity
    payload = Column(JSON)

    session = relationship("SessionMeta", back_populates="records")
