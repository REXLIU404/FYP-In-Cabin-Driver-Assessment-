"""Read-only access to the generated constructed scenario bundles (Task 4).

``GET /api/scenarios`` lists every bundle directory under ``settings.scenario_root`` with an
integrity verdict (schema, every listed frame present and matching its sha256);
``/api/scenarios/{id}/manifest`` serves the manifest and
``/api/scenarios/{id}/frames/{file}`` serves ONE frame - only files the manifest lists, so
nothing else under the root (a stray manifest copy, a scenario JSON) is ever reachable.

The root is re-read on every request, so tests (and a later runtime) can repoint it at will.
"""
import hashlib
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from ..config import settings

SCHEMA = "constructed-scenario/1"

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(scenario_id: str):
    """The parsed manifest of ``scenario_id``, or None when it is absent/unreadable."""
    path = settings.scenario_root / scenario_id / "manifest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _integrity(scenario_id: str) -> dict:
    """The list entry of one bundle: provenance fields plus an integrity verdict.

    The verdict checks the manifest schema, that every listed frame exists and that its
    bytes still match the recorded sha256; the error names the FIRST failure found.
    """
    entry = {"id": scenario_id, "segments": 0, "duration_ms": 0,
             "generated_at": None, "status": "invalid", "error": None}
    manifest = _load_manifest(scenario_id)
    if manifest is None:
        entry["error"] = "manifest.json is missing or not readable JSON"
        return entry
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        entry["error"] = "the manifest schema is not constructed-scenario/1"
        return entry
    entry["segments"] = len(manifest.get("segments", []))
    entry["duration_ms"] = manifest.get("duration_ms", 0)
    entry["generated_at"] = manifest.get("generated_at")
    for frame in manifest.get("frames", []):
        file = frame.get("file")
        if not file:
            entry["error"] = "a frame entry has no file"
            return entry
        path = settings.scenario_root / scenario_id / "frames" / file
        if not path.is_file():
            entry["error"] = f"frame {file} is missing"
            return entry
        if frame.get("sha256") != _sha256(path):
            entry["error"] = f"frame {file} does not match its sha256"
            return entry
    entry["status"] = "ok"
    return entry


@router.get("")
def list_scenarios() -> list[dict]:
    root = settings.scenario_root
    if not root.is_dir():
        return []
    entries = sorted((child for child in root.iterdir() if child.is_dir()),
                     key=lambda child: child.name)
    return [_integrity(child.name) for child in entries]


@router.get("/{scenario_id}/manifest")
def get_manifest(scenario_id: str) -> JSONResponse:
    manifest = _load_manifest(scenario_id)
    if manifest is None:
        raise HTTPException(404, "scenario not found")
    return JSONResponse(manifest)


@router.get("/{scenario_id}/frames/{file}")
def get_frame(scenario_id: str, file: str) -> Response:
    manifest = _load_manifest(scenario_id)
    if manifest is None:
        raise HTTPException(404, "scenario not found")
    # Whitelist: only files the manifest lists are served, so nothing else under the
    # root (manifest copies, scenario JSONs, traversal targets) is ever reachable.
    listed = {frame.get("file") for frame in manifest.get("frames", [])}
    if file not in listed:
        raise HTTPException(404, "frame not found")
    path = settings.scenario_root / scenario_id / "frames" / file
    if not path.is_file():
        raise HTTPException(404, "frame not found")
    return Response(path.read_bytes(), media_type="image/jpeg")
