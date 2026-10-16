"""Window logging, trained frame inference, and session-scoped temporal state."""
import base64
import binascii
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import cache, faults, inference, models, timing
from ..db import get_db
from ..faults import FaultHTTPException, FaultSink, get_fault_sink
from ..schemas import LiveInput, RiskUpdate, RuntimeConfig, WindowInput

router = APIRouter(prefix="/api/sessions", tags=["windows"])

# The detail texts the client classifies a 409 on (retryPolicy.ts / test_retry_contract.py).
OUT_OF_ORDER_DETAIL = "Out-of-order evidence timestamp"
OBSERVATION_CONFLICT_DETAIL = "Observation identity already registered with different content or acquisition time"


@dataclass(frozen=True)
class Evidence:
    """What one live request says about its own observations, taken from the REQUEST (never
    from the provider's provenance): the identity metadata, the acquisition times and the
    content hashes. A branch the request did not carry has its hash set to None."""

    captured_at: Optional[str] = None
    image_hash: Optional[str] = None
    vision_frame: Optional[tuple] = None  # (epoch, index)
    telemetry_timestamp: Optional[str] = None
    telemetry_hash: Optional[str] = None
    telemetry_seq: Optional[int] = None


def image_digest(encoded: str) -> str:
    """sha256 of the image BYTES. A ``data:`` URL prefix is not part of the image. Text that is
    not valid base64 (a test double; the real provider rejects it with a 422 before this runs)
    is hashed as text, so the digest is total."""
    body = encoded.split(",", 1)[1] if encoded.startswith("data:") and "," in encoded else encoded
    try:
        raw = base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError):
        raw = body.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def telemetry_digest(features) -> str:
    """sha256 of the eight feature values, in canonical (sorted-key) JSON."""
    return hashlib.sha256(json.dumps(features.model_dump(), sort_keys=True).encode()).hexdigest()


def evidence_of(payload: LiveInput) -> Evidence:
    frame = payload.vision_frame
    return Evidence(
        captured_at=payload.captured_at if payload.image_base64 is not None else None,
        image_hash=image_digest(payload.image_base64) if payload.image_base64 is not None else None,
        vision_frame=(frame.epoch, frame.index) if frame is not None else None,
        telemetry_timestamp=payload.telemetry_timestamp if payload.telemetry_features is not None else None,
        telemetry_hash=telemetry_digest(payload.telemetry_features) if payload.telemetry_features is not None else None,
        telemetry_seq=payload.telemetry_seq)


def request_digest(payload: LiveInput) -> str:
    """The request hash that makes a re-sent request an idempotent replay. R10 fields that are
    None are left out of ``canonical_body``, so the same HTTP body hashes as it did before them."""
    return hashlib.sha256(json.dumps(payload.canonical_body(), sort_keys=True).encode()).hexdigest()


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


def _instant(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _out_of_order() -> FaultHTTPException:
    return FaultHTTPException(409, OUT_OF_ORDER_DETAIL, error_category=faults.CATEGORY_OUT_OF_ORDER_EVIDENCE,
                              origin=faults.ORIGIN_SESSION)


def _observation_conflict() -> FaultHTTPException:
    return FaultHTTPException(409, OBSERVATION_CONFLICT_DETAIL,
                              error_category=faults.CATEGORY_OBSERVATION_CONFLICT, origin=faults.ORIGIN_SESSION)


def _advance_watermark(state: dict, key: str, stamp: str) -> None:
    """The watermark only ever moves forward: a NEW observation with an explicit identity may
    carry an older stamp (a client clock that stepped back) and must not lower it."""
    previous = state.get(key)
    if not previous or _instant(stamp) > _instant(previous):
        state[key] = stamp


def _classify_telemetry(state: dict, ev: Evidence) -> Optional[inference.Observation]:
    """NEW / REPEAT / refusal for the telemetry branch, against what the session has accepted.
    Runs under the writer lock and registers a NEW observation into ``state`` (the caller's copy,
    committed with the window or not at all).

    With a ``telemetry_seq``: bigger -> NEW; equal with the same features AND the same acquisition
    time -> REPEAT; equal with anything different -> 409 observation_conflict; smaller -> 409
    out-of-order. Without one (the weaker fallback): a later time -> NEW; the same time with the
    same feature hash -> REPEAT, with another hash -> NEW; an earlier time -> 409 out-of-order.
    A REPEAT answers with the REGISTERED acquisition time and refreshes nothing."""
    if ev.telemetry_hash is None:
        return None
    stamp, seq = ev.telemetry_timestamp, ev.telemetry_seq
    last_seq = state.get("obs_t_seq")
    registered_ts, registered_hash = state.get("obs_t_ts"), state.get("obs_t_hash")
    same_content = (registered_hash == ev.telemetry_hash and registered_ts is not None
                    and _instant(registered_ts) == _instant(stamp))
    watermark_key = inference.EVIDENCE_WATERMARK_KEYS[1]
    if seq is not None:
        if last_seq is not None and seq < last_seq:
            raise _out_of_order()
        if last_seq is not None and seq == last_seq:
            if same_content:
                return inference.Observation("repeat", registered_ts, "explicit", seq)
            raise _observation_conflict()
        identity = "explicit"
    else:
        watermark = state.get(watermark_key)
        if watermark and _instant(stamp) < _instant(watermark):
            raise _out_of_order()
        if same_content:
            return inference.Observation("repeat", registered_ts, "fallback")
        identity = "fallback"
    state.update(obs_t_seq=seq, obs_t_ts=stamp, obs_t_hash=ev.telemetry_hash)
    _advance_watermark(state, watermark_key, stamp)
    return inference.Observation("new", stamp, identity, seq)


def _classify_vision(state: dict, ev: Evidence) -> Optional[inference.Observation]:
    """NEW / REPEAT / refusal for the vision branch.

    With a ``vision_frame`` (epoch, index): lexicographically bigger -> NEW; equal with the same
    image bytes AND the same acquisition time -> REPEAT; equal with other bytes or another time ->
    409 observation_conflict; smaller (an older epoch included) -> 409 out-of-order. The image
    hash is an AUDIT here: a NEW frame whose bytes equal the previous accepted frame's is still
    NEW, flagged ``hash_repeat_audit``. Without one (the weaker fallback): the same bytes as the
    previous accepted frame -> REPEAT, with the REGISTERED acquisition time; otherwise NEW, and
    subject to the ``captured_at`` watermark. A REPEAT never refreshes the acquisition time."""
    if ev.image_hash is None:
        return None
    stamp, frame = ev.captured_at, ev.vision_frame
    registered_ts, registered_hash = state.get("obs_v_ts"), state.get("obs_v_hash")
    watermark_key = inference.EVIDENCE_WATERMARK_KEYS[0]
    audit = False
    if frame is not None:
        last = (state.get("obs_v_epoch"), state.get("obs_v_index"))
        if last[0] is not None:
            if frame < last:
                raise _out_of_order()
            if frame == last:
                if (registered_hash == ev.image_hash and registered_ts is not None
                        and _instant(registered_ts) == _instant(stamp)):
                    return inference.Observation("repeat", registered_ts, "explicit", f"{frame[0]}:{frame[1]}")
                raise _observation_conflict()
        audit = registered_hash is not None and registered_hash == ev.image_hash
        identity, ref = "explicit", f"{frame[0]}:{frame[1]}"
    else:
        if registered_hash is not None and registered_hash == ev.image_hash and registered_ts is not None:
            return inference.Observation("repeat", registered_ts, "fallback")
        watermark = state.get(watermark_key)
        if watermark and _instant(stamp) < _instant(watermark):
            raise _out_of_order()
        identity, ref = "fallback", None
    state.update(obs_v_epoch=frame[0] if frame else None, obs_v_index=frame[1] if frame else None,
                 obs_v_ts=stamp, obs_v_hash=ev.image_hash)
    _advance_watermark(state, watermark_key, stamp)
    return inference.Observation("new", stamp, identity, ref, audit)


def _persist_window(db, sid, w, *, mode, provenance=None, request_id=None, digest=None, started=None,
                    evidence=None):
    """Allocate, fuse and commit one window. Does NOT roll back when it raises: the
    caller owns the transaction boundary (``_save_window`` for replay, ``infer_frame``
    for live, which must roll back BEFORE it records the fault).

    For a live window ``evidence`` is classified here, under the writer lock the allocation
    took and in the same transaction as the window record: the registry, the watermarks, the
    FSM memory and the window counter all commit together or not at all."""
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
    observations = None
    if mode == inference.LIVE_MODE:
        evidence = evidence or Evidence()
        observations = inference.Observations(vision=_classify_vision(state, evidence),
                                              telemetry=_classify_telemetry(state, evidence))
    config = RuntimeConfig(**sess.runtime_config) if sess.runtime_config else inference.default_config()
    with timing.measure("fusion"):
        ru = inference.run_inference(sid, number, w, state=state, config=config, provenance=provenance,
                                     operation_mode=mode, observations=observations)
    if started is not None:
        # latency_ms stops HERE, before the record is added and committed: it excludes the
        # commit and the cache write. Server-Timing's ``commit`` / ``total`` cover those.
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
        with timing.measure("commit"):  # db.commit() and nothing else
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
    digest = request_digest(payload)
    existing = _existing_request(db, session_id, payload.request_id, digest)
    if existing:
        return existing
    # Finish the read transaction before doing model work and taking a writer lock.
    db.rollback()
    window, provenance = _run_models(payload)
    timing.record_provider_timings(provenance.get("timing_ms"))
    provenance = {**provenance, "captured_at_source": payload.captured_at_source}
    return _persist_window(db, session_id, window, mode=inference.LIVE_MODE, provenance=provenance,
                           request_id=payload.request_id, digest=digest, started=started,
                           evidence=evidence_of(payload))


@router.post("/{session_id}/infer", response_model=RiskUpdate, status_code=201)
def infer_frame(session_id: str, payload: LiveInput, request: Request, response: Response,
                db: Session = Depends(get_db), sink: FaultSink = Depends(get_fault_sink),
                attempt_index: int = Header(1, ge=1, le=1000, alias="X-Attempt-Index")):
    # le=1000 equals faults.MAX_ATTEMPT_INDEX. Above it FastAPI answers 422 before this
    # body runs, and the global handler records the fault with attempt_index NULL.
    # Seen by the global handlers, which must not record what this route already has.
    request.state.fault_context = {"session_id": session_id, "request_id": payload.request_id,
                                   "attempt_index": attempt_index}
    handler_started = time.perf_counter()
    timer = timing.SegmentTimer()
    try:
        with timing.activate(timer):
            result = _infer(db, session_id, payload)
        # Success only: a failed request has no Server-Timing (its outcome is a fault row).
        timer.ms["total"] = (time.perf_counter() - handler_started) * 1000
        response.headers["Server-Timing"] = timer.header()
        return result
    except Exception as exc:
        # Order matters. The failed transaction may still hold SQLite's only write
        # lock; the fault is written on a second connection, which would otherwise
        # wait out busy_timeout and then fail. Roll back first, then record.
        _rollback_quietly(db)
        info = faults.classify_exception(exc)  # never raises: it falls back to "unknown"
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
