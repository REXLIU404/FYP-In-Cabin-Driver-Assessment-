"""Inference Orchestrator + Window Builder + Result Logging.

POST a window -> MockAIProvider -> late fusion -> risk_update -> persist + cache.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import cache, fusion, models
from ..config import settings
from ..db import get_db
from ..providers.mock_ai import mock_ai
from ..schemas import ModalityFreshness, RiskUpdate, WindowInput

router = APIRouter(prefix="/api/sessions", tags=["windows"])


def _record_to_update(rec: models.InferenceRecord) -> RiskUpdate:
    # Reconstruct from the stored payload, overriding flagged with live value.
    return RiskUpdate(**{**rec.payload, "flagged": rec.flagged})


@router.post("/{session_id}/windows", response_model=RiskUpdate, status_code=201)
def add_window(session_id: str, w: WindowInput, db: Session = Depends(get_db)):
    if not db.get(models.SessionMeta, session_id):
        raise HTTPException(404, "session not found")

    out = mock_ai.infer(w)
    score = fusion.compute_risk_score(
        out["P_distraction"],
        out["P_telemetry_anomaly"],
        settings.weight_vision,
        settings.weight_telemetry,
        out["vision_status"],
        out["telemetry_status"],
    )
    level = fusion.map_risk_level(score)
    health = fusion.map_system_health(out["vision_status"], out["telemetry_status"])
    dominant = fusion.determine_dominant_evidence(
        out["P_distraction"], out["P_telemetry_anomaly"], score, health
    )
    alert = fusion.map_alert_severity(level)

    window_id = (
        db.query(models.InferenceRecord)
        .filter_by(session_id=session_id)
        .count()
        + 1
    )
    ts = w.timestamp or datetime.now(timezone.utc).isoformat()

    ru = RiskUpdate(
        session_id=session_id,
        window_id=window_id,
        timestamp=ts,
        P_distraction=out["P_distraction"],
        P_telemetry_anomaly=out["P_telemetry_anomaly"],
        RiskScore=score,
        RiskLevel=level,
        DominantEvidence=dominant,
        AlertSeverity=alert,
        SystemHealth=health,
        modality_freshness=ModalityFreshness(
            vision=out["vision_status"], telemetry=out["telemetry_status"]
        ),
        latency_ms=out["latency_ms"],
        visual_top_classes=out["visual_top_classes"],
        telemetry_behavior_classes=out["telemetry_behavior_classes"],
        telemetry_feature_contributions=out["telemetry_feature_contributions"],
        telemetry_features=out["telemetry_features"],
        explanation=fusion.build_explanation(dominant, level),
    )

    rec = models.InferenceRecord(
        session_id=session_id,
        window_id=window_id,
        timestamp=ts,
        p_distraction=ru.P_distraction,
        p_telemetry_anomaly=ru.P_telemetry_anomaly,
        risk_score=score,
        risk_level=level,
        dominant_evidence=dominant,
        alert_severity=alert,
        system_health=health,
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
