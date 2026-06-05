"""Inference Orchestrator + Window Builder + Result Logging.

POST a window -> MockAIProvider -> late fusion -> risk_update -> persist + cache.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import cache, inference, models
from ..db import get_db
from ..schemas import RiskUpdate, WindowInput

router = APIRouter(prefix="/api/sessions", tags=["windows"])


def _record_to_update(rec: models.InferenceRecord) -> RiskUpdate:
    # Reconstruct from the stored payload, overriding flagged with live value.
    return RiskUpdate(**{**rec.payload, "flagged": rec.flagged})


@router.post("/{session_id}/windows", response_model=RiskUpdate, status_code=201)
def add_window(session_id: str, w: WindowInput, db: Session = Depends(get_db)):
    if not db.get(models.SessionMeta, session_id):
        raise HTTPException(404, "session not found")

    # Use max(window_id)+1 (not count+1) so ids stay unique even after a
    # window has been deleted from the middle of the session.
    last_id = (
        db.query(func.max(models.InferenceRecord.window_id))
        .filter_by(session_id=session_id)
        .scalar()
    )
    window_id = (last_id or 0) + 1

    ru = inference.run_inference(session_id, window_id, w)

    rec = models.InferenceRecord(
        session_id=session_id,
        window_id=window_id,
        timestamp=ru.timestamp,
        p_distraction=ru.P_distraction,
        p_telemetry_anomaly=ru.P_telemetry_anomaly,
        risk_score=ru.RiskScore,
        risk_level=ru.RiskLevel,
        dominant_evidence=ru.DominantEvidence,
        alert_severity=ru.AlertSeverity,
        system_health=ru.SystemHealth,
        latency_ms=ru.latency_ms,
        flagged=False,
        payload=ru.model_dump(),
    )
    db.add(rec)
    db.commit()
    cache.set_latest(session_id, ru)
    return ru


@router.get("/{session_id}/windows", response_model=list[RiskUpdate])
def list_windows(session_id: str, db: Session = Depends(get_db)):
    if not db.get(models.SessionMeta, session_id):
        raise HTTPException(404, "session not found")
    recs = (
        db.query(models.InferenceRecord)
        .filter_by(session_id=session_id)
        .order_by(models.InferenceRecord.window_id)
        .all()
    )
    return [_record_to_update(r) for r in recs]


@router.patch("/{session_id}/windows/{window_id}/flag", response_model=RiskUpdate)
def flag_window(
    session_id: str, window_id: int, flagged: bool = True, db: Session = Depends(get_db)
):
    rec = (
        db.query(models.InferenceRecord)
        .filter_by(session_id=session_id, window_id=window_id)
        .first()
    )
    if not rec:
        raise HTTPException(404, "window not found")
    rec.flagged = flagged
    rec.payload = {**rec.payload, "flagged": flagged}
    db.commit()
    return _record_to_update(rec)


@router.delete("/{session_id}/windows/{window_id}", status_code=204)
def delete_window(session_id: str, window_id: int, db: Session = Depends(get_db)):
    rec = (
        db.query(models.InferenceRecord)
        .filter_by(session_id=session_id, window_id=window_id)
        .first()
    )
    if not rec:
        raise HTTPException(404, "window not found")
    db.delete(rec)
    db.commit()
