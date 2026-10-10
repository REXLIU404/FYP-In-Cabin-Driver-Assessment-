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
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


class SessionMeta(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    description = Column(String, default="")
    next_window_id = Column(Integer, nullable=False, default=0, server_default="0")
    operation_mode = Column(String, nullable=False, default="PREPARED_SESSION_RUNTIME", server_default="PREPARED_SESSION_RUNTIME")
    runtime_state = Column(JSON, nullable=False, default=dict, server_default="{}")
    runtime_config = Column(JSON, nullable=False, default=dict, server_default="{}")

    records = relationship(
        "InferenceRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InferenceRecord.window_id",
    )


class InferenceRecord(Base):
    __tablename__ = "inference_records"
    __table_args__ = (UniqueConstraint("session_id", "window_id"), UniqueConstraint("session_id", "request_id"))

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    window_id = Column(Integer, index=True)
    request_id = Column(String, nullable=True)
    request_hash = Column(String, nullable=True)
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
