"""Dashboard Response Generator — session log export as JSON or CSV."""
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db

router = APIRouter(prefix="/api/sessions", tags=["export"])

_CSV_COLUMNS = [
    "session_id",
    "window_id",
    "timestamp",
    "P_distraction",
    "P_telemetry_anomaly",
    "RiskScore",
    "RiskLevel",
    "DominantEvidence",
    "AlertSeverity",
    "SystemHealth",
    "latency_ms",
    "flagged",
]


@router.get("/{session_id}/export")
def export_session(session_id: str, format: str = "json", db: Session = Depends(get_db)):
    if format not in ("json", "csv"):
        raise HTTPException(400, "format must be 'json' or 'csv'")
    if not db.get(models.SessionMeta, session_id):
        raise HTTPException(404, "session not found")
    recs = (
        db.query(models.InferenceRecord)
        .filter_by(session_id=session_id)
        .order_by(models.InferenceRecord.window_id)
        .all()
    )
    rows = [{**r.payload, "flagged": r.flagged} for r in recs]

    if format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{session_id}.csv"'
            },
        )

    return Response(
        content=json.dumps({"session_id": session_id, "records": rows}, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{session_id}.json"'},
    )
