"""Persisted session status plus model readiness in the serving worker."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import cache, models
from ..config import settings
from ..db import get_db
from ..providers.mock_ai import mock_ai
from ..schemas import SystemStatusOut

router = APIRouter(prefix="/api/sessions", tags=["system-status"])

@router.get("/{session_id}/system-status", response_model=SystemStatusOut)
def system_status(session_id: str, db: Session = Depends(get_db)):
    sess = db.get(models.SessionMeta, session_id)
    exists = sess is not None

    latest = None
    total = 0
    if exists:
        total = (
            db.query(func.count(models.InferenceRecord.id))
            .filter_by(session_id=session_id)
            .scalar()
            or 0
        )
        latest = (
            db.query(models.InferenceRecord)
            .filter_by(session_id=session_id)
            .order_by(models.InferenceRecord.window_id.desc())
            .first()
        )

    live = bool(sess and sess.operation_mode == "LIVE_MODEL_RUNTIME")
    model_info = {}
    if live:
        from ..providers.trained import loaded_model_info
        model_info = loaded_model_info()
    return SystemStatusOut(
        session_id=session_id,
        exists=exists,
        total_windows=total,
        latest_window_id=latest.window_id if latest else None,
        latest_assessment_available=bool(latest.assessment_available) if latest else None,
        latest_risk_score=latest.risk_score if latest else None,
        latest_system_health=latest.system_health if latest else None,
        latest_alert_severity=latest.alert_severity if latest else None,
        # A hand-written legacy row may have no payload (or no provenance) at all.
        ai_provider=(((latest.payload or {}).get("provenance") or {}).get("provider", mock_ai.name) if latest else ("MobileNetV3ONNX+XGBoost" if sess and sess.operation_mode == "LIVE_MODEL_RUNTIME" else mock_ai.name)),
        models_loaded=bool(model_info),
        cache_warm=cache.get_latest(session_id) is not None,
        database_scheme=settings.database_url.split(":", 1)[0],
        server_time=datetime.now(timezone.utc).isoformat(),
        model_info=model_info,
    )
