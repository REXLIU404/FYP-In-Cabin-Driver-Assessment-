"""Window logging, trained frame inference, and session-scoped temporal state."""
import hashlib
import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import cache, faults, inference, models
from ..db import get_db
from ..faults import FaultHTTPException, FaultSink, get_fault_sink
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
            raise FaultHTTPException(409, "request_id already used for different input",
                                     error_category=faults.CATEGORY_IDEMPOTENCY_CONFLICT,
                                     origin=faults.ORIGIN_SESSION)
        return _record_to_update(rec)
    return None


def _persist_window(db, sid, w, *, mode, provenance=None, request_id=None, digest=None, started=None):
    """Allocate, fuse and commit one window. Does NOT roll back when it raises: the
    caller owns the transaction boundary (``_save_window`` for replay, ``infer_frame``
    for live, which must roll back BEFORE it records the fault)."""
    # Atomic UPDATE obtains the SQLite writer lock before reading temporal state.
    # No count/max race, and deletion never causes identifier reuse.
    number = db.execute(update(models.SessionMeta).where(models.SessionMeta.id == sid)
                        .values(next_window_id=models.SessionMeta.next_window_id + 1)
                        .returning(models.SessionMeta.next_window_id)).scalar_one_or_none()
    if number is None:
        db.rollback()
        raise FaultHTTPException(404, "session not found", error_category=faults.CATEGORY_NOT_FOUND,
                                 origin=faults.ORIGIN_SESSION)
    sess = db.get(models.SessionMeta, sid)
    db.refresh(sess)
    if sess.operation_mode != mode:
        raise FaultHTTPException(409, "Input does not match session operation mode",
                                 error_category=faults.CATEGORY_MODE_CONFLICT, origin=faults.ORIGIN_SESSION)
    existing = _existing_request(db, sid, request_id, digest)
    if existing:
        db.rollback()
        return existing
    state = dict(sess.runtime_state or {})
    if provenance:
        for key in inference.EVIDENCE_WATERMARK_KEYS:
            stamp, previous = provenance.get(key), state.get(key)
            if stamp and previous and datetime.fromisoformat(stamp) < datetime.fromisoformat(previous):
                raise FaultHTTPException(409, "Out-of-order evidence timestamp",
                                         error_category=faults.CATEGORY_OUT_OF_ORDER_EVIDENCE,
                                         origin=faults.ORIGIN_SESSION)
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
        alert_severity=ru.AlertSeverity, system_health=ru.SystemHealth,
        assessment_available=ru.assessment_available, latency_ms=ru.latency_ms,
        flagged=False, payload=ru.model_dump(),
    )
    db.add(rec)
    sess.runtime_state = state
    try:
        db.commit()
    except IntegrityError:
        # A concurrent twin won uq_record_session_request between our check and our
        # commit. That is a duplicate delivery, not a server error: answer it the way
        # the pre-check would have (same input -> the stored record, different -> 409).
        # An IntegrityError that is NOT that race is re-raised unchanged.
        db.rollback()
        twin = _existing_request(db, sid, request_id, digest)
        if twin is None:
            raise
        return twin
    if request_id is not None:
        # A NEW record was committed: the session works again. (The replay and twin
        # returns above are deliberately not recoveries.)
        faults.mark_recovered(db, sid, request_id)
    cache.set_latest(sid, ru)
    return ru


def _save_window(db, sid, w, **kwargs):
    try:
        return _persist_window(db, sid, w, **kwargs)
    except Exception:
        db.rollback()
        raise


@router.post("/{session_id}/windows", response_model=RiskUpdate, status_code=201)
def add_window(session_id: str, w: WindowInput, db: Session = Depends(get_db)):
    return _save_window(db, session_id, w, mode="PREPARED_SESSION_RUNTIME")


def _run_models(payload: LiveInput):
    from ..providers.trained import get_provider, InvalidFrame, ModelRuntimeError, ModelUnavailable
    try:
        return get_provider().infer(payload)
    except InvalidFrame as exc:
        raise FaultHTTPException(422, str(exc), error_category=faults.CATEGORY_INPUT_VALIDATION,
                                 origin=faults.ORIGIN_REQUEST_VALIDATION) from exc
    except ModelUnavailable as exc:
        raise FaultHTTPException(503, str(exc), error_category=faults.CATEGORY_MODELS_UNAVAILABLE,
                                 origin=faults.ORIGIN_MODEL_LOAD) from exc
    except ModelRuntimeError as exc:
        # One branch failing fails the whole request: no single-branch fallback window.
        raise FaultHTTPException(500, str(exc), error_category=faults.CATEGORY_MODEL_RUNTIME,
                                 origin=exc.origin) from exc


def _infer(db, session_id: str, payload: LiveInput):
    started = time.perf_counter()
    sess = db.get(models.SessionMeta, session_id)
    if not sess:
        raise FaultHTTPException(404, "session not found", error_category=faults.CATEGORY_NOT_FOUND,
                                 origin=faults.ORIGIN_SESSION)
    if sess.operation_mode != "LIVE_MODEL_RUNTIME":
        raise FaultHTTPException(409, "Create a live model session first",
                                 error_category=faults.CATEGORY_MODE_CONFLICT, origin=faults.ORIGIN_SESSION)
    # The attempt index is a header and is NOT part of the hash: a retry must be
    # byte-identical to the request it repeats, or it would collide with itself (409).
    digest = hashlib.sha256(json.dumps(payload.model_dump(), sort_keys=True).encode()).hexdigest()
    existing = _existing_request(db, session_id, payload.request_id, digest)
    if existing:
        return existing
    # Finish the read transaction before doing model work and taking a writer lock.
    db.rollback()
    window, provenance = _run_models(payload)
    return _persist_window(db, session_id, window, mode="LIVE_MODEL_RUNTIME", provenance=provenance,
                           request_id=payload.request_id, digest=digest, started=started)


@router.post("/{session_id}/infer", response_model=RiskUpdate, status_code=201)
def infer_frame(session_id: str, payload: LiveInput, request: Request,
                db: Session = Depends(get_db), sink: FaultSink = Depends(get_fault_sink),
                attempt_index: int = Header(1, ge=1, alias="X-Attempt-Index")):
    # Seen by the global handlers, which must not record what this route already has.
    request.state.fault_context = {"session_id": session_id, "request_id": payload.request_id,
                                   "attempt_index": attempt_index}
    try:
        return _infer(db, session_id, payload)
    except Exception as exc:
        # Order matters. The failed transaction may still hold SQLite's only write
        # lock; the fault is written on a second connection, which would otherwise
        # wait out busy_timeout and then fail. Roll back first, then record.
        _rollback_quietly(db)
        info = faults.classify_exception(exc)
        faults.record_fault(db, session_id=session_id, request_id=payload.request_id,
                            attempt_index=attempt_index, origin=info.origin,
                            error_category=info.error_category, http_status=info.http_status,
                            retryable=info.retryable, detail=info.detail, sink=sink)
        request.state.fault_recorded = True
        raise  # the original exception, unchanged


def _rollback_quietly(db) -> None:
    try:
        db.rollback()
    except Exception:  # must not replace the exception being reported
        pass


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
    # Only the cached record itself goes stale; deleting an older window must not
    # cool a cache that still holds the (unchanged) latest one.
    cached = cache.get_latest(session_id)
    if cached is not None and cached.window_id == window_id:
        cache.clear(session_id)
