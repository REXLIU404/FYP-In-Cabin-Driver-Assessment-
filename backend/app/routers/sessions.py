"""Session Controller: create / list / read / delete sessions."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import cache, models
from ..db import get_db
from ..schemas import SessionCreate, SessionOut

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _to_out(s: models.SessionMeta) -> SessionOut:
    return SessionOut(
        id=s.id,
        created_at=s.created_at.isoformat() if s.created_at else "",
        total_windows=len(s.records),
    )


@router.post("", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreate, db: Session = Depends(get_db)):
    sid = body.session_id or f"S{uuid.uuid4().hex[:8]}"
    if db.get(models.SessionMeta, sid):
        raise HTTPException(409, "session already exists")
    s = models.SessionMeta(
        id=sid, description=body.description, created_at=datetime.now(timezone.utc)
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _to_out(s)


@router.get("", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db)):
    return [_to_out(s) for s in db.query(models.SessionMeta).all()]


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(models.SessionMeta, session_id)
    if not s:
        raise HTTPException(404, "session not found")
    return _to_out(s)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(models.SessionMeta, session_id)
    if not s:
        raise HTTPException(404, "session not found")
    db.delete(s)  # cascade removes inference records
    db.commit()
    cache.clear(session_id)
