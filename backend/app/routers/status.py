"""System Status Manager: backend-level health for one session.

Surfaces the latest fused health/severity, the active AI provider, and — honestly
— that no trained models are loaded yet (MockAIProvider echoes prepared
probabilities). This is a backend-only payload, not the shared RiskUpdate.
"""
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

# Flip to True only once real ONNX/XGBoost providers replace MockAIProvider.
_MODELS_LOADED = False


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

    return SystemStatusOut(
        session_id=session_id,
        exists=exists,
        total_windows=total,
        latest_window_id=latest.window_id if latest else None,
        latest_system_health=latest.system_health if latest else None,
        latest_alert_severity=latest.alert_severity if latest else None,
        ai_provider=mock_ai.name,
        models_loaded=_MODELS_LOADED,
        cache_warm=cache.get_latest(session_id) is not None,
        database_scheme=settings.database_url.split(":", 1)[0],
        server_time=datetime.now(timezone.utc).isoformat(),
    )
