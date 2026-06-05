"""Latest risk_update for dashboard polling (served from the Output Cache,
falling back to the most recent persisted record)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import cache, models
from ..db import get_db
from ..schemas import RiskUpdate

router = APIRouter(prefix="/api/sessions", tags=["risk"])


@router.get("/{session_id}/risk/latest", response_model=RiskUpdate)
def latest_risk(session_id: str, db: Session = Depends(get_db)):
    cached = cache.get_latest(session_id)
    if cached is not None:
        return cached
    rec = (
        db.query(models.InferenceRecord)
        .filter_by(session_id=session_id)
        .order_by(models.InferenceRecord.window_id.desc())
        .first()
    )
    if not rec:
        raise HTTPException(404, "no risk update available for this session")
    return RiskUpdate(**{**rec.payload, "flagged": rec.flagged})
