"""Stream persisted session evidence without loading the full history into RAM."""
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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
            "assessment_available", "P_distraction_raw", "P_telemetry_raw"]


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
    records = (db.query(models.InferenceRecord).filter_by(session_id=session_id)
               .order_by(models.InferenceRecord.window_id).yield_per(100))

    def stream():
        if format == "json":
            yield '{"session_id":' + json.dumps(session_id) + ',"records":['
            first = True
            for rec in records:
                yield ("" if first else ",") + json.dumps({**rec.payload, "flagged": rec.flagged})
                first = False
            yield "]}"
        else:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            yield buf.getvalue()
            for rec in records:
                buf.seek(0)
                buf.truncate(0)
                payload = rec.payload or {}
                provenance = payload.get("provenance") or {}
                row = {**payload, "flagged": rec.flagged, **{k: provenance.get(k, "") for k in _COLUMNS if k in provenance},
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
