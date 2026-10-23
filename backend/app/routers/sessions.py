"""Session CRUD; configuration is immutable for the lifetime of one session."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import cache, models
from ..db import get_db
from ..inference import default_config
from ..schemas import SessionCreate, SessionOut

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _to_out(s, count):
    return SessionOut(id=s.id, created_at=s.created_at.isoformat(), total_windows=count, operation_mode=s.operation_mode)


@router.post("", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreate, db: Session = Depends(get_db)):
    sid = body.session_id or f"S{uuid.uuid4().hex}"
    if db.get(models.SessionMeta, sid):
        raise HTTPException(409, "session already exists")
    s = models.SessionMeta(id=sid, description=body.description, created_at=datetime.now(timezone.utc),
                          operation_mode=body.operation_mode,
                          runtime_config=(body.config if "config" in body.model_fields_set else default_config()).model_dump())
    db.add(s)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "session already exists") from exc
    db.refresh(s)
    return _to_out(s, 0)


@router.get("", response_model=list[SessionOut])
def list_sessions(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = (db.query(models.SessionMeta, func.count(models.InferenceRecord.id)).outerjoin(models.InferenceRecord)
            .group_by(models.SessionMeta.id).order_by(models.SessionMeta.created_at.desc()).offset(offset).limit(limit).all())
    return [_to_out(s, count) for s, count in rows]


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(models.SessionMeta, session_id)
    if not s:
        raise HTTPException(404, "session not found")
    count = db.query(func.count(models.InferenceRecord.id)).filter_by(session_id=session_id).scalar()
    return _to_out(s, count)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(models.SessionMeta, session_id)
    if not s:
        raise HTTPException(404, "session not found")
    db.delete(s)
    db.commit()
    cache.clear(session_id)
