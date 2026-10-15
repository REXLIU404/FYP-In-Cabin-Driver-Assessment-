"""Stream persisted session evidence without loading the full history into RAM."""
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import String, type_coerce
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db

router = APIRouter(prefix="/api/sessions", tags=["export"])
_COLUMNS = ["session_id", "window_id", "timestamp", "operation_mode", "P_distraction",
            "P_telemetry_anomaly", "RiskScore", "RiskLevel", "DominantEvidence", "AlertSeverity",
            "SystemHealth", "latency_ms", "flagged", "vision_source", "telemetry_source",
            "vision_model_sha256", "telemetry_model_sha256", "request_id", "provenance",
            "modality_freshness", "visual_top_classes", "telemetry_behavior_classes",
            "telemetry_feature_contributions", "telemetry_features", "explanation",
            # Appended (never inserted) so positional consumers of the older columns keep working.
            # The raw pair is the honest model output; P_distraction / P_telemetry_anomaly are
            # replaced by 0.0 for a missing branch. NEVER put assessment_available in provenance:
            # the row builder below lets any provenance key named in _COLUMNS shadow the top level.
            "assessment_available", "P_distraction_raw", "P_telemetry_raw",
            # Appended for rows whose stored payload cannot be read (see _decode_payload).
            # Empty on every readable row; "true" + a reason on an unreadable one.
            "payload_unreadable", "payload_unreadable_reason"]
_RISK_FIELDS = ("RiskScore", "RiskLevel", "DominantEvidence", "AlertSeverity")
_JSON_KINDS = {list: "array", str: "string", bool: "boolean", int: "number", float: "number", type(None): "null"}


def _decode_payload(raw):
    """``(payload, None)`` for a readable row, ``(None, reason)`` otherwise.

    The payload column is JSON text that predates this code in places: a row can hold
    SQL NULL, text that is not JSON, or JSON that is not an object (a list, a string...).
    Any of them used to blow up INSIDE the response generator, after the 200 and the first
    bytes had gone out, so the client was left holding half a JSON document or CSV file.
    The caller reads the column as raw text (``type_coerce``) so that even malformed text
    arrives here instead of failing in the ORM, and turns a ``reason`` into a marked row."""
    if raw is None:
        return None, "payload is NULL"
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return None, "payload is not valid JSON: the stored bytes are not UTF-8"
    elif not isinstance(raw, str):
        raw = str(raw)  # SQLite is dynamically typed: a number stored in a JSON column
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError) as exc:  # JSONDecodeError is a ValueError
        return None, f"payload is not valid JSON: {exc}"
    if isinstance(value, dict):
        return value, None
    return None, f"payload is a JSON {_JSON_KINDS.get(type(value), type(value).__name__)}, not an object"


def _unreadable_record(session_id, window_id, flagged, reason):
    """The most an unreadable row can honestly say: which row it is and that it is
    unreadable. The four risk fields are null, never recomputed or taken from the typed
    columns next to the payload: those are not guaranteed to describe this blob."""
    return {"session_id": session_id, "window_id": window_id, "flagged": flagged,
            **{name: None for name in _RISK_FIELDS},
            "payload_unreadable": True, "payload_unreadable_reason": reason}


def _csv_cell(value):
    """Explicit CSV encoding (the unavailable representation is a cross-stack contract,
    matched by the frontend export): None -> empty cell, bool -> lowercase true/false."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


@router.get("/{session_id}/export")
def export_session(session_id: str, format: str = "json", db: Session = Depends(get_db)):
    if format not in ("json", "csv"):
        raise HTTPException(400, "format must be 'json' or 'csv'")
    if not db.get(models.SessionMeta, session_id):
        raise HTTPException(404, "session not found")
    # Columns, not entities, and the payload as raw text: a row whose payload the JSON type
    # could not decode must reach _decode_payload, not fail while the ORM loads it.
    records = (db.query(models.InferenceRecord.window_id, models.InferenceRecord.flagged,
                        type_coerce(models.InferenceRecord.payload, String).label("payload"))
               .filter(models.InferenceRecord.session_id == session_id)
               .order_by(models.InferenceRecord.window_id).yield_per(100))

    def stream():
        if format == "json":
            yield '{"session_id":' + json.dumps(session_id) + ',"records":['
            first = True
            for window_id, flagged, raw in records:
                payload, reason = _decode_payload(raw)
                record = (_unreadable_record(session_id, window_id, flagged, reason) if payload is None
                          else {**payload, "flagged": flagged})
                yield ("" if first else ",") + json.dumps(record)
                first = False
            yield "]}"
        else:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            yield buf.getvalue()
            for window_id, flagged, raw in records:
                buf.seek(0)
                buf.truncate(0)
                payload, reason = _decode_payload(raw)
                if payload is None:
                    row = _unreadable_record(session_id, window_id, flagged, reason)
                else:
                    provenance = payload.get("provenance") or {}
                    row = {**payload, "flagged": flagged, **{k: provenance.get(k, "") for k in _COLUMNS if k in provenance},
                           "provenance": json.dumps(provenance)}
                    for key in ("modality_freshness", "visual_top_classes", "telemetry_behavior_classes",
                                "telemetry_feature_contributions", "telemetry_features"):
                        row[key] = json.dumps(row.get(key))
                row = {k: ("'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v) for k, v in row.items()}
                row = {k: _csv_cell(v) for k, v in row.items()}
                writer.writerow(row)
                yield buf.getvalue()

    return StreamingResponse(stream(), media_type="application/json" if format == "json" else "text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{session_id}.{format}"'})
