"""Window logging, trained frame inference, and session-scoped temporal state."""
import hashlib
import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import update
from sqlalchemy.orm import Session

from .. import cache, inference, models
from ..db import get_db
from ..schemas import LiveInput, RiskUpdate, RuntimeConfig, WindowInput

router = APIRouter(prefix="/api/sessions", tags=["windows"])


def _record_to_update(rec):
    return RiskUpdate(**{**rec.payload, "flagged": rec.flagged})


def _existing_request(db, sid, request_id, digest):
    if request_id is None:
        return None
    rec = db.query(models.InferenceRecord).filter_by(session_id=sid, request_id=request_id).first()
    if rec:
        if rec.request_hash != digest:
            raise HTTPException(409, "request_id already used for different input")
        return _record_to_update(rec)
    return None


def _save_window(db, sid, w, *, mode, provenance=None, request_id=None, digest=None, started=None):
    # Atomic UPDATE obtains the SQLite writer lock before reading temporal state.
    # No count/max race, and deletion never causes identifier reuse.
    number = db.execute(update(models.SessionMeta).where(models.SessionMeta.id == sid)
                        .values(next_window_id=models.SessionMeta.next_window_id + 1)
                        .returning(models.SessionMeta.next_window_id)).scalar_one_or_none()
    if number is None:
        db.rollback()
        raise HTTPException(404, "session not found")
    try:
        sess = db.get(models.SessionMeta, sid)
        db.refresh(sess)
        if sess.operation_mode != mode:
            raise HTTPException(409, "Input does not match session operation mode")
        existing = _existing_request(db, sid, request_id, digest)
        if existing:
            db.rollback()
            return existing
        state = dict(sess.runtime_state or {})
        if provenance:
            for key in ("captured_at", "telemetry_timestamp"):
                stamp, previous = provenance.get(key), state.get(key)
                if stamp and previous and datetime.fromisoformat(stamp) < datetime.fromisoformat(previous):
                    raise HTTPException(409, "Out-of-order evidence timestamp")
                if stamp:
                    state[key] = stamp
        config = RuntimeConfig(**sess.runtime_config) if sess.runtime_config else inference.default_config()
        ru = inference.run_inference(sid, number, w, state=state, config=config,
                                     provenance=provenance, operation_mode=mode)
        if started is not None:
            ru.latency_ms = round((time.perf_counter() - started) * 1000)
        rec = models.InferenceRecord(
            session_id=sid, window_id=number, request_id=request_id, request_hash=digest,
            timestamp=ru.timestamp, p_distraction=ru.P_distraction, p_telemetry_anomaly=ru.P_telemetry_anomaly,
            risk_score=ru.RiskScore, risk_level=ru.RiskLevel, dominant_evidence=ru.DominantEvidence,
            alert_severity=ru.AlertSeverity, system_health=ru.SystemHealth, latency_ms=ru.latency_ms,
            flagged=False, payload=ru.model_dump(),
        )
        db.add(rec)
        sess.runtime_state = state
        db.commit()
    except Exception:
        db.rollback()
        raise
    cache.set_latest(sid, ru)
    return ru


@router.post("/{session_id}/windows", response_model=RiskUpdate, status_code=201)
def add_window(session_id: str, w: WindowInput, db: Session = Depends(get_db)):
    return _save_window(db, session_id, w, mode="PREPARED_SESSION_RUNTIME")


@router.post("/{session_id}/infer", response_model=RiskUpdate, status_code=201)
def infer_frame(session_id: str, payload: LiveInput, db: Session = Depends(get_db)):
    from ..providers.trained import get_provider, InvalidFrame, ModelUnavailable
    started = time.perf_counter()
    sess = db.get(models.SessionMeta, session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    if sess.operation_mode != "LIVE_MODEL_RUNTIME":
        raise HTTPException(409, "Create a live model session first")
    digest = hashlib.sha256(json.dumps(payload.model_dump(), sort_keys=True).encode()).hexdigest()
    existing = _existing_request(db, session_id, payload.request_id, digest)
    if existing:
        return existing
    # Finish the read transaction before doing model work and taking a writer lock.
    db.rollback()
    try:
        window, provenance = get_provider().infer(payload)
    except InvalidFrame as exc:
        raise HTTPException(422, str(exc)) from exc
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return _save_window(db, session_id, window, mode="LIVE_MODEL_RUNTIME", provenance=provenance,
                        request_id=payload.request_id, digest=digest, started=started)


@router.get("/{session_id}/windows", response_model=list[RiskUpdate])
def list_windows(session_id: str, after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=1000), db: Session = Depends(get_db)):
    if not db.get(models.SessionMeta, session_id):
        raise HTTPException(404, "session not found")
    recs = db.query(models.InferenceRecord).filter(models.InferenceRecord.session_id == session_id,
            models.InferenceRecord.window_id > after).order_by(models.InferenceRecord.window_id).limit(limit).all()
    return [_record_to_update(r) for r in recs]


@router.patch("/{session_id}/windows/{window_id}/flag", response_model=RiskUpdate)
def flag_window(session_id: str, window_id: int, flagged: bool = True, db: Session = Depends(get_db)):
    rec = db.query(models.InferenceRecord).filter_by(session_id=session_id, window_id=window_id).first()
    if not rec:
        raise HTTPException(404, "window not found")
    rec.flagged = flagged
    rec.payload = {**rec.payload, "flagged": flagged}
    db.commit()
    cached = cache.get_latest(session_id)
    if cached is not None and cached.window_id == window_id:
        cache.set_latest(session_id, _record_to_update(rec))
    return _record_to_update(rec)


@router.delete("/{session_id}/windows/{window_id}", status_code=204)
def delete_window(session_id: str, window_id: int, db: Session = Depends(get_db)):
    rec = db.query(models.InferenceRecord).filter_by(session_id=session_id, window_id=window_id).first()
    if not rec:
        raise HTTPException(404, "window not found")
    db.delete(rec)
    db.commit()
    cache.clear(session_id)
