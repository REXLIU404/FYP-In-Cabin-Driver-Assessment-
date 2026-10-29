#!/usr/bin/env python3
"""Task 10A Phase 2 (DS-2): paired Stage-2 comparison runner for the vision identities.

Replays the frozen stable200 sequence (200 images, 10 classes x 20, in the approved block
order) through the REAL ``/infer`` pipeline once per compared vision identity, in one fresh
OS subprocess each, with a synthetic injected clock and a fresh temporary SQLite per child.
Everything downstream (fusion, R10 EMA, R10 alert FSM, persistence) is the unchanged
product code of this commit.

Binding authority (read-only, never modified by this runner):

* ``docs/fyp2/task10a/comparison_protocol.json`` - the user-approved protocol (FUD-02..05,
  approval record ``docs/fyp2/task10a/approval_record.json`` binds its SHA256). The runner
  requires ``status == APPROVED``, a recorded user approval, the SHA256 recorded in the
  approval record, and ``protocol_mtime_ns < run_start_epoch_ns`` BEFORE it imports any
  ``app.*`` module; it re-hashes the file after the run and the value must be unchanged.
* ``docs/fyp2/task10a/tolerance_predeclaration.md`` - FUD-01 tolerance; it applies to the
  Stage-1 provider checks (see ``scripts/verify_stable200.py``). This Stage-2 run is
  descriptive: no winner, no threshold, no active-model change (decision rule
  ``DESCRIPTIVE_ONLY``, replacement authority stays with the user at Stage 5).

Per child (declared protocol mechanics):

* synthetic time base t_i = t0 + i*100 ms (t0 = 2026-10-25T00:00:00Z), injected by patching
  ``app.inference.datetime`` and ``app.providers.trained.datetime``; no real sleeps;
* observation identity: vision frame (epoch=1, index=i+1), telemetry_seq=i+1, request ids
  ``task10a_w0001..w0200``, captured_at = telemetry_timestamp = t_i, client_clock;
* one fixed raw telemetry row (protocol ``telemetry_pairing.features``) repeated as NEW
  synthetic samples; telemetry_source ``prepared_replay``;
* image transport: base64 of the exact original JPEG bytes (verified byte-for-byte against
  the protocol ``ordered_samples`` sha256 before sending; no re-encode);
* fixed runtime configuration from the protocol; session mode LIVE_MODEL_RUNTIME; no
  ``port 8000`` listener (``fastapi.testclient.TestClient``); the fault sink is redirected
  inside the child's temporary directory; ``DRA_DATABASE_URL`` points at a fresh temporary
  SQLite, never at ``driver_risk.db*``.

Validity (protocol ``validity_and_failure_policy``): exactly 200 persisted windows per model,
all fresh with age 0 and ``assessment_available=true``, every observation NEW, every window's
``vision_model_id``/``vision_model_sha256`` matching the protocol identity and the stable
telemetry hash matching. Any missing input, hash mismatch, HTTP error or identity mismatch
fails validity - no prepared-probability or stable fallback is ever used. If every raw
probability and every downstream result is identical across identities, the run is withheld
and flagged for investigation (``identical_results``) instead of interpreted.

Output: ``docs/evidence/<run-date>/comparison/comparison_results.json`` plus one worker JSON
per model; the merged file records commands, exit codes, environment, implemented head,
dirty state, protocol path/SHA/mtime, run timestamps, output mtime, the recomputed input
hashes, per-model sequences and descriptive paired summaries.

Exit codes: 0 the prescribed scenario was replayed for every model and no alarm fired;
1 a model failed validity or the identical-results alarm fired; 2 usage error or a BLOCKED
precheck (protocol gate, input verification, missing package/reference - exact path written).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO / "scripts"
BACKEND_DIR = REPO / "backend"
CANDIDATES_ROOT = REPO / "ml" / "outputs" / "candidates"
DEFAULT_PROTOCOL = REPO / "docs/fyp2/task10a/comparison_protocol.json"
DEFAULT_APPROVAL_RECORD = REPO / "docs/fyp2/task10a/approval_record.json"
WORKER_TIMEOUT_S = 3600

EXPECTED_PROTOCOL_STATUS = "APPROVED"
STABLE_MODEL_ID = "stable_mobilenet_v3_large"


# ------------------------------------------------------------------------------ primitives
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def load_json(path) -> dict:
    return json.loads(Path(path).read_text())


def iso_at(t0_iso: str, offset_ms: int) -> str:
    """t_i = t0 + i*interval as integer milliseconds, ISO8601 UTC."""
    t0 = datetime.fromisoformat(t0_iso.replace("Z", "+00:00"))
    return (t0 + timedelta(milliseconds=int(offset_ms))).isoformat()


# ---------------------------------------------------------------------------- protocol gate
def protocol_gate(protocol_path, approval_record_path, run_start_epoch_ns: int) -> dict:
    """The frozen-protocol precheck, run BEFORE any app import: approved status, recorded
    user approval, the SHA256 the approval record binds, and mtime strictly before the run."""
    problems: list[str] = []
    protocol_path, approval_record_path = Path(protocol_path), Path(approval_record_path)
    checks = {"protocol_status": False, "approval_status": False, "sha_match": False,
              "mtime_before_run": False}
    gate = {"status": "BLOCKED", "problems": problems, "checks": checks,
            "protocol_path": str(protocol_path), "approval_record": str(approval_record_path)}

    if not protocol_path.is_file():
        problems.append(f"protocol file is missing: {protocol_path}")
        return gate
    if not approval_record_path.is_file():
        problems.append(f"approval record is missing: {approval_record_path}")
        return gate
    protocol = load_json(protocol_path)
    approval = load_json(approval_record_path)
    gate["protocol_sha256"] = sha256_file(protocol_path)
    gate["protocol_mtime_ns"] = protocol_path.stat().st_mtime_ns

    approval_section = protocol.get("approval") or {}
    checks["protocol_status"] = protocol.get("status") == EXPECTED_PROTOCOL_STATUS
    if not checks["protocol_status"]:
        problems.append(f"protocol status is {protocol.get('status')!r}, "
                        f"expected {EXPECTED_PROTOCOL_STATUS!r}")
    checks["approval_status"] = (
        approval.get("status") == "APPROVED"
        and approval_section.get("status") == "APPROVED"
        and approval_section.get("approved_by") == "user")
    if not checks["approval_status"]:
        problems.append("no recorded explicit user approval of this protocol "
                        f"({approval_record_path})")
    expected_sha = ((approval.get("approved_protocol") or {}).get("sha256") or "").lower()
    gate["expected_sha256"] = expected_sha or None
    checks["sha_match"] = bool(expected_sha) and gate["protocol_sha256"] == expected_sha
    if not checks["sha_match"]:
        problems.append(f"protocol sha256 {gate['protocol_sha256']} does not match the "
                        f"approved {expected_sha or '(none recorded)'}")
    checks["mtime_before_run"] = gate["protocol_mtime_ns"] < int(run_start_epoch_ns)
    if not checks["mtime_before_run"]:
        problems.append(f"protocol mtime {gate['protocol_mtime_ns']} is not before the run "
                        f"start {run_start_epoch_ns}")
    gate["status"] = "PASS" if not problems else "BLOCKED"
    return gate


# ------------------------------------------------------------------------------ input plan
def build_steps(protocol: dict) -> list[dict]:
    """The 200 ordered replay steps: identity, request id, synthetic time and the exact
    original-JPEG path + sha256, straight from the protocol's frozen ordered_samples."""
    time_basis = protocol["time_basis"]
    data_root = Path(protocol["input_set"]["data_root"])
    steps = []
    for index, sample in enumerate(protocol["input_set"]["ordered_samples"]):
        if sample.get("sequence_index") != index:
            raise ValueError(f"ordered_samples[{index}] has sequence_index "
                             f"{sample.get('sequence_index')!r}; the protocol order is frozen")
        steps.append({
            "sequence_index": index,
            "source_id": sample["source_id"],
            "class_id": sample["class_id"],
            "filename": sample["filename"],
            "path": str(data_root / sample["class_id"] / sample["filename"]),
            "sha256": sample["sha256"],
            "t_iso": iso_at(time_basis["t0"], index * int(time_basis["interval_ms"])),
            "request_id": f"task10a_w{index + 1:04d}",
            "vision_frame": {"epoch": 1, "index": index + 1},
            "telemetry_seq": index + 1,
        })
    return steps


def base_plan(protocol: dict, steps: list[dict]) -> dict:
    """The model-independent part of a child's plan (including the approved fixed telemetry
    identity the child verifies against /api/models)."""
    pairing = protocol["telemetry_pairing"]
    return {"protocol_sha256": protocol.get("protocol_sha256"),
            "t0": protocol["time_basis"]["t0"],
            "interval_ms": int(protocol["time_basis"]["interval_ms"]),
            "telemetry_source": pairing.get("telemetry_source", "prepared_replay"),
            "features": pairing["features"],
            "expected_telemetry_sha256": protocol["fixed_configuration"]["telemetry"]["sha256"],
            "config": protocol["fixed_configuration"]["runtime_config"],
            "steps": steps, "n": len(steps)}


def build_payload(step: dict, raw: bytes, features: dict) -> dict:
    """One LiveInput body: original bytes base64-encoded (never re-encoded), synthetic
    observation identity and the fixed telemetry row as a NEW synthetic sample."""
    import base64

    return {
        "request_id": step["request_id"],
        "image_base64": base64.b64encode(raw).decode("ascii"),
        "captured_at": step["t_iso"],
        "captured_at_source": "client_clock",
        "telemetry_features": features,
        "telemetry_timestamp": step["t_iso"],
        "telemetry_source": "prepared_replay",
        "telemetry_seq": step["telemetry_seq"],
        "vision_frame": step["vision_frame"],
    }


# --------------------------------------------------------------------- input verification
def compute_input_hashes(rows) -> dict:
    """The two frozen membership hashes: sha256 of the sorted filenames / source_ids joined
    by "\\n" with no trailing newline."""
    return {"membership_sha256": sha256_bytes("\n".join(sorted(r["filename"] for r in rows)).encode("utf-8")),
            "source_ids_sha256": sha256_bytes("\n".join(sorted(r["source_id"] for r in rows)).encode("utf-8"))}


def compute_image_manifest(entries) -> dict:
    """Per-file sha256 of the ORIGINAL JPEG bytes plus the frozen aggregate: for the sorted
    source_ids, ``source_id + '\\t' + sha256`` joined by "\\n" (no trailing newline).
    A missing/unreadable file keeps a problem with its exact path - never a silent skip."""
    images, problems = [], []
    for entry in sorted(entries, key=lambda e: e["source_id"]):
        path = Path(entry["path"])
        try:
            raw = path.read_bytes()
        except OSError:
            problems.append(f"missing input image: {path}")
            continue
        images.append({"source_id": entry["source_id"], "path": str(path),
                       "bytes": len(raw), "sha256": sha256_bytes(raw)})
    aggregate = None
    if not problems:
        aggregate = sha256_bytes("\n".join(f"{img['source_id']}\t{img['sha256']}"
                                           for img in images).encode("utf-8"))
    return {"sha256": aggregate, "images": images, "problems": problems}


def compute_features_hash(features: dict) -> str:
    """sha256 of the eight features as Python floats in canonical (sorted-key, compact) JSON."""
    canonical = json.dumps({k: float(v) for k, v in features.items()}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(canonical.encode("utf-8"))


def _hash_check(problems: list, name: str, actual, expected, path) -> bool:
    ok = actual == expected
    if not ok:
        problems.append(f"{name} mismatch at {path}: actual {actual!r}, expected {expected!r}")
    return ok


def verify_protocol_inputs(protocol, *, data_root, annotations_paths, metadata_path,
                           telemetry_csv_path) -> dict:
    """Recompute every frozen input hash BEFORE any model runs (protocol hash_verification):
    annotations bytes, membership, source ids, every original JPEG sha256, the image manifest
    aggregate, metadata bytes and the fixed telemetry CSV. Mismatch = BLOCKED, exact path."""
    problems: list[str] = []
    input_set = protocol["input_set"]
    samples = input_set["ordered_samples"]
    rows = [{"filename": s["filename"], "source_id": s["source_id"], "class_id": s["class_id"]}
            for s in samples]
    hashes = compute_input_hashes(rows)

    n = input_set.get("n")
    if n is not None and len(samples) != n:
        problems.append(f"input_set has {len(samples)} ordered samples, protocol declares n={n}")
    per_class = input_set.get("per_class")
    classes = [f"c{i}" for i in range(10)]
    if per_class and len(samples) == per_class * len(classes):
        counts = {c: sum(1 for s in samples if s["class_id"] == c) for c in classes}
        wrong = {c: v for c, v in counts.items() if v != per_class}
        if wrong:
            problems.append(f"per-class counts wrong: {wrong}, expected {per_class} each")

    _hash_check(problems, "membership_sha256", hashes["membership_sha256"],
                input_set.get("membership_sha256"), "input_set.ordered_samples")
    _hash_check(problems, "source_ids_sha256", hashes["source_ids_sha256"],
                input_set.get("source_ids_sha256"), "input_set.ordered_samples")

    entries = [{"source_id": s["source_id"],
                "path": Path(data_root) / s["class_id"] / s["filename"]} for s in samples]
    manifest = compute_image_manifest(entries)
    problems.extend(manifest["problems"])
    declared_by_source = {s["source_id"]: s["sha256"] for s in samples}
    for image in manifest["images"]:
        if image["sha256"] != declared_by_source.get(image["source_id"]):
            problems.append(f"image byte hash mismatch: {image['path']} (actual {image['sha256']}, "
                            f"declared {declared_by_source.get(image['source_id'])})")
    _hash_check(problems, "image_bytes_manifest_sha256", manifest["sha256"],
                input_set.get("image_bytes_manifest_sha256"), "input_set.ordered_samples")

    annotations_expected = input_set.get("annotations_sha256")
    for annotations_path in annotations_paths:
        actual = sha256_file(annotations_path) if Path(annotations_path).is_file() else None
        _hash_check(problems, f"annotations_sha256 ({Path(annotations_path).name})", actual,
                    annotations_expected, annotations_path)

    metadata_actual = sha256_file(metadata_path) if Path(metadata_path).is_file() else None
    _hash_check(problems, "metadata_sha256", metadata_actual, input_set.get("metadata_sha256"),
                metadata_path)

    pairing = protocol["telemetry_pairing"]
    telemetry_actual = (sha256_file(telemetry_csv_path)
                        if Path(telemetry_csv_path).is_file() else None)
    _hash_check(problems, "telemetry_source_file_sha256", telemetry_actual,
                pairing.get("source_file_sha256"), telemetry_csv_path)
    features_actual = compute_features_hash(pairing["features"])
    _hash_check(problems, "telemetry_features_sha256", features_actual,
                pairing.get("features_sha256"), "telemetry_pairing.features")

    return {"ok": not problems, "problems": problems,
            "recomputed": {"membership_sha256": hashes["membership_sha256"],
                           "source_ids_sha256": hashes["source_ids_sha256"],
                           "image_bytes_manifest_sha256": manifest["sha256"],
                           "annotations_sha256": {str(p): sha256_file(p)
                                                  for p in annotations_paths if Path(p).is_file()},
                           "metadata_sha256": metadata_actual,
                           "telemetry_source_file_sha256": telemetry_actual,
                           "telemetry_features_sha256": features_actual,
                           "n_images_verified": len(manifest["images"])}}


# --------------------------------------------------------------------------- extraction
def argmax(values) -> int:
    """Lowest index on a tie (the same tie rule as the Stage-1 checks)."""
    best = max(values)
    return next(i for i, v in enumerate(values) if v == best)


def probability_vector(classes) -> tuple[dict, list[str]]:
    """Map the runtime ``visual_top_classes`` order onto the canonical c0..c9 keys. The first
    entry must be the runtime alias ``safe_driving`` (c0); never rely on display sorting."""
    problems: list[str] = []
    if len(classes) != 10:
        problems.append(f"expected 10 class probabilities, got {len(classes)}")
    if not classes or classes[0].get("label") != "safe_driving":
        problems.append(f"c0 label is not the runtime alias 'safe_driving': "
                        f"{classes[0].get('label') if classes else None!r}")
    probs = {}
    for i, entry in enumerate(classes):
        try:
            value = float(entry["probability"])
        except (KeyError, TypeError, ValueError):
            problems.append(f"probability c{i} is not a number")
            continue
        probs[f"c{i}"] = value
    if len(probs) == 10:
        if any(p < 0.0 or p > 1.0 for p in probs.values()):
            problems.append("probability outside [0,1]")
        total = sum(probs.values())
        if not 0.999 <= total <= 1.001:
            problems.append(f"probabilities sum to {total}, outside [0.999, 1.001]")
    return probs, problems


def extract_window(response: dict, step: dict) -> dict:
    """One per-window record for the merged results (protocol result_contract fields)."""
    probs, problems = probability_vector(response.get("visual_top_classes") or [])
    provenance = response.get("provenance") or {}
    if response.get("assessment_available") is not True:
        problems.append(f"assessment_available is {response.get('assessment_available')!r} "
                        f"(SystemHealth={response.get('SystemHealth')!r})")
    return {
        "sequence_index": step["sequence_index"],
        "window_id": response.get("window_id"),
        "source_id": step["source_id"],
        "class_id": step["class_id"],
        "request_id": step["request_id"],
        "synthetic_timestamp": step["t_iso"],
        "response_timestamp": response.get("timestamp"),
        "vision_frame": step["vision_frame"],
        "telemetry_seq": step["telemetry_seq"],
        "RiskScore": response.get("RiskScore"),
        "RiskLevel": response.get("RiskLevel"),
        "DominantEvidence": response.get("DominantEvidence"),
        "AlertSeverity": response.get("AlertSeverity"),
        "assessment_available": response.get("assessment_available"),
        "SystemHealth": response.get("SystemHealth"),
        "P_distraction": response.get("P_distraction"),
        "P_distraction_raw": provenance.get("P_distraction_raw"),
        "P_telemetry_anomaly": response.get("P_telemetry_anomaly"),
        "probabilities": probs,
        "argmax": argmax(list(probs.values())) if len(probs) == 10 else None,
        "modality_freshness": response.get("modality_freshness"),
        "provenance": provenance,
        "problems": problems,
    }


def window_checks(response: dict, step: dict, plan: dict) -> dict:
    """The per-window validity verdicts of the prescribed scenario."""
    provenance = response.get("provenance") or {}
    freshness = response.get("modality_freshness") or {}
    return {
        "fresh": freshness.get("vision") == "fresh" and freshness.get("telemetry") == "fresh",
        "age_zero": provenance.get("vision_age_s") == 0 and provenance.get("telemetry_age_s") == 0,
        "available": response.get("assessment_available") is True,
        "observations_new": (provenance.get("vision_obs") == "new"
                             and provenance.get("telemetry_obs") == "new"),
        "identity": (provenance.get("vision_model_id") == plan["model_id"]
                     and provenance.get("vision_model_sha256") == plan["expected_model_sha256"]),
        "timestamp": response.get("timestamp") == step["t_iso"],
    }


# ------------------------------------------------------------------------------ statistics
def linear_quantile(values, q: float):
    """The linear-interpolation quantile (NumPy ``method="linear"`` definition)."""
    ordered = sorted(float(v) for v in values if v is not None)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * float(q)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize(values) -> dict:
    available = [float(v) for v in values if v is not None]
    if not available:
        return {"n": 0, "min": None, "max": None, "mean": None, "p25": None,
                "median": None, "p75": None, "p95": None}
    return {"n": len(available), "min": min(available), "max": max(available),
            "mean": sum(available) / len(available),
            "p25": linear_quantile(available, 0.25), "median": linear_quantile(available, 0.5),
            "p75": linear_quantile(available, 0.75), "p95": linear_quantile(available, 0.95)}


# ------------------------------------------------------------------------------- sequences
def category_counts(sequence) -> dict:
    counts: dict[str, int] = {}
    for value in sequence:
        key = "null" if value is None else str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def class_boundaries(steps) -> dict:
    """The first window of every class block (the constructed scenario's only boundaries)."""
    indices = [0] + [i for i in range(1, len(steps))
                     if steps[i]["class_id"] != steps[i - 1]["class_id"]]
    return {"sequence_indices": indices, "window_ids": [i + 1 for i in indices]}


def transitions(sequence, steps) -> dict:
    """Initial state separately, then every change with window, source_id, t_i and whether
    it sits on a class boundary of the constructed sequence."""
    changes = []
    for i in range(1, len(sequence)):
        if sequence[i] != sequence[i - 1]:
            changes.append({
                "window_id": steps[i]["sequence_index"] + 1,
                "source_id": steps[i]["source_id"],
                "t_iso": steps[i]["t_iso"],
                "from": sequence[i - 1], "to": sequence[i],
                "class_boundary": steps[i]["class_id"] != steps[i - 1]["class_id"],
            })
    return {"initial": sequence[0] if sequence else None, "transitions": changes}


def aligned_differences(sequence_a, sequence_b) -> list[dict]:
    length = min(len(sequence_a), len(sequence_b))
    return [{"window_id": i + 1, "a": sequence_a[i], "b": sequence_b[i]}
            for i in range(length) if sequence_a[i] != sequence_b[i]]


def per_window_prob_deltas(windows_a, windows_b) -> dict:
    """Aligned per-window probability deltas between two model runs (paired by window id,
    never by row position alone) plus the argmax agreement count."""
    if [w["window_id"] for w in windows_a] != [w["window_id"] for w in windows_b]:
        raise ValueError("model runs are not aligned by window_id")
    per_window, disagreements = [], []
    for window_a, window_b in zip(windows_a, windows_b):
        deltas = [abs(float(window_a["probabilities"][f"c{i}"])
                      - float(window_b["probabilities"][f"c{i}"])) for i in range(10)]
        per_window.append({"window_id": window_a["window_id"], "source_id": window_a["source_id"],
                           "max_abs_prob_delta": max(deltas),
                           "argmax_a": window_a["argmax"], "argmax_b": window_b["argmax"]})
        if window_a["argmax"] != window_b["argmax"]:
            disagreements.append(window_a["source_id"])
    n = len(per_window)
    return {"n_compared": n,
            "max_abs_prob_delta": max((w["max_abs_prob_delta"] for w in per_window), default=None),
            "mean_abs_prob_delta": (sum(w["max_abs_prob_delta"] for w in per_window) / n) if n else None,
            "argmax_agreement": ((n - len(disagreements)) / n) if n else None,
            "argmax_disagreement_source_ids": disagreements,
            "per_window": per_window}


def risk_score_deltas(windows_a, windows_b) -> list[dict]:
    """Paired RiskScore differences (b minus a) for the same window - descriptive only."""
    return [{"window_id": a["window_id"],
             "a": a["RiskScore"], "b": b["RiskScore"],
             "delta": (None if a["RiskScore"] is None or b["RiskScore"] is None
                       else b["RiskScore"] - a["RiskScore"])}
            for a, b in zip(windows_a, windows_b)]


def identical_results(windows_by_model: dict) -> bool:
    """The broken-runner alarm (protocol validity policy): identical EVERYTHING across all
    identities. Coarse equality of RiskLevel/argmax alone is possible and not an alarm."""
    fields = ("RiskScore", "RiskLevel", "DominantEvidence", "AlertSeverity", "P_distraction")
    ids = list(windows_by_model)
    if len(ids) < 2:
        return False
    base = windows_by_model[ids[0]]
    for other in ids[1:]:
        candidate = windows_by_model[other]
        if len(base) != len(candidate):
            return False
        for window_a, window_b in zip(base, candidate):
            if window_a["probabilities"] != window_b["probabilities"]:
                return False
            if any(window_a.get(name) != window_b.get(name) for name in fields):
                return False
    return True


def class_argmax_counts(windows) -> dict:
    """Per constructed class, the argmax distribution over its 20 windows."""
    counts: dict[str, dict] = {}
    for window in windows:
        bucket = counts.setdefault(window["class_id"], {})
        key = str(window["argmax"])
        bucket[key] = bucket.get(key, 0) + 1
    return counts


# --------------------------------------------------------------------------------- worker
def make_clock(current: datetime):
    """A datetime subclass whose now() the runner advances before each synchronous POST."""

    class Clock(datetime):
        _current = current

        @classmethod
        def now(cls, tz=None):
            return cls._current.astimezone(tz) if tz is not None else cls._current

        @classmethod
        def set_iso(cls, text: str):
            cls._current = datetime.fromisoformat(text)

    return Clock


def environment_versions() -> dict:
    import platform

    versions = {"python": platform.python_version(), "platform": platform.platform()}
    for module_name in ("numpy", "onnxruntime", "PIL", "xgboost"):
        try:
            module = __import__(module_name)
        except Exception as exc:  # pragma: no cover - environment dependent
            versions[module_name] = f"unavailable ({type(exc).__name__}: {exc})"
        else:
            versions[module_name] = getattr(module, "__version__", "unknown")
    return versions


def execute_plan(plan: dict) -> dict:
    """One child's whole run: real app, real provider, patched clock, temp SQLite."""
    started = datetime.now(timezone.utc)
    work_dir = Path(plan["work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    checks = {"identity_ok": False, "all_fresh": True, "all_age_zero": True,
              "all_available": True, "all_observations_new": True,
              "all_timestamps_match": True, "persisted_count": 0, "timestamps_match": False,
              "monotonic_windows": False, "database_isolated": False}
    windows: list[dict] = []
    identity: dict = {}

    from fastapi.testclient import TestClient

    import app.inference as inference_mod
    import app.providers.trained as trained_mod
    from app import cache, faults
    from app.config import settings
    from app.main import app

    db_file = plan["db_url"].removeprefix("sqlite:///")
    checks["database_isolated"] = (
        settings.database_url == plan["db_url"]
        and Path(db_file).resolve().is_relative_to(work_dir.resolve()))
    if not checks["database_isolated"]:
        problems.append(f"DRA_DATABASE_URL is {settings.database_url!r}, expected the child's "
                        f"temporary SQLite under {work_dir}")

    clock = make_clock(datetime.fromisoformat(plan["t0"]))
    previous = {"sink": faults.DEFAULT_SINK_PATH, "inference": inference_mod.datetime,
                "trained": trained_mod.datetime}
    faults.DEFAULT_SINK_PATH = work_dir / "fault_events.log"
    inference_mod.datetime = clock
    trained_mod.datetime = clock
    try:
        with TestClient(app) as client:
            models_response = client.get("/api/models")
            if models_response.status_code != 200:
                problems.append(f"GET /api/models -> {models_response.status_code}: "
                                f"{models_response.text[:300]}")
            else:
                identity["models_endpoint"] = models_response.json()
                vision = identity["models_endpoint"].get("vision") or {}
                telemetry = identity["models_endpoint"].get("telemetry") or {}
                identity["vision_model_id"] = vision.get("model_id")
                identity["vision_model_sha256"] = vision.get("sha256")
                identity["telemetry_model_sha256"] = telemetry.get("sha256")
                checks["identity_ok"] = (
                    identity["vision_model_id"] == plan["model_id"]
                    and identity["vision_model_sha256"] == plan["expected_model_sha256"]
                    and identity["telemetry_model_sha256"] == plan["expected_telemetry_sha256"])
                if not checks["identity_ok"]:
                    problems.append(
                        f"model identity mismatch: loaded {identity['vision_model_id']!r}/"
                        f"{(identity['vision_model_sha256'] or '')[:12]}… and telemetry "
                        f"{(identity['telemetry_model_sha256'] or '')[:12]}…, expected "
                        f"{plan['model_id']!r}/{plan['expected_model_sha256'][:12]}… and "
                        f"{plan['expected_telemetry_sha256'][:12]}…")
            if not problems:
                created = client.post("/api/sessions", json={
                    "session_id": plan["session_id"],
                    "description": "Task 10A Stage-2 constructed comparison (fixed synthetic input)",
                    "operation_mode": "LIVE_MODEL_RUNTIME",
                    "config": plan["config"]})
                if created.status_code != 201:
                    problems.append(f"POST /api/sessions -> {created.status_code}: "
                                    f"{created.text[:300]}")
                else:
                    for step in plan["steps"]:
                        if problems:
                            break
                        raw = Path(step["path"]).read_bytes()
                        if sha256_bytes(raw) != step["sha256"]:
                            problems.append(f"image byte hash changed mid-run: {step['path']}")
                            break
                        clock.set_iso(step["t_iso"])
                        response = client.post(f"/api/sessions/{plan['session_id']}/infer",
                                               json=build_payload(step, raw, plan["features"]))
                        if response.status_code != 201:
                            problems.append(f"POST /infer {step['request_id']} -> "
                                            f"{response.status_code}: {response.text[:300]}")
                            break
                        body = response.json()
                        verdict = window_checks(body, step, plan)
                        for name, ok in verdict.items():
                            if not ok:
                                problems.append(f"window {step['request_id']}: {name} check failed")
                        windows.append(extract_window(body, step))
                        problems.extend(f"window {step['request_id']}: {p}"
                                        for p in windows[-1]["problems"])
                        for key, name in (("fresh", "all_fresh"), ("age_zero", "all_age_zero"),
                                          ("available", "all_available"),
                                          ("observations_new", "all_observations_new"),
                                          ("timestamp", "all_timestamps_match")):
                            checks[name] = checks[name] and verdict[key]
                    stored = client.get(f"/api/sessions/{plan['session_id']}/windows",
                                        params={"after": 0, "limit": 1000})
                    persisted = stored.json() if stored.status_code == 200 else []
                    checks["persisted_count"] = len(persisted)
                    stored_ids = [row.get("window_id") for row in persisted]
                    checks["monotonic_windows"] = stored_ids == list(range(1, len(plan["steps"]) + 1))
                    checks["timestamps_match"] = (
                        len(persisted) == len(plan["steps"])
                        and [row.get("timestamp") for row in persisted]
                        == [s["t_iso"] for s in plan["steps"]])
                    identity["persisted_window_ids"] = stored_ids
                    if checks["persisted_count"] != len(plan["steps"]):
                        problems.append(f"expected {len(plan['steps'])} persisted windows, "
                                        f"found {checks['persisted_count']}")
                    if not checks["timestamps_match"]:
                        problems.append("persisted canonical timestamps are not the injected t_i")
    except Exception as exc:  # a crashed child still reports what it has
        problems.append(f"child raised {type(exc).__name__}: {exc}")
        identity["traceback"] = traceback.format_exc()
    finally:
        inference_mod.datetime = previous["inference"]
        trained_mod.datetime = previous["trained"]
        faults.DEFAULT_SINK_PATH = previous["sink"]
        try:
            cache.clear(plan["session_id"])
        except Exception:
            pass

    finished = datetime.now(timezone.utc)
    return {
        "model_id": plan["model_id"],
        "status": "PASS" if not problems else "FAIL",
        "session_id": plan["session_id"],
        "database_path": plan["db_url"],
        "subprocess_pid": os.getpid(),
        "identity": identity,
        "window_count": len(windows),
        "window_ids": [w["window_id"] for w in windows],
        "windows": windows,
        "validity": {"checks": checks, "problems": problems},
        "environment": environment_versions(),
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
    }


def run_child(spec_path, out_path) -> int:
    plan = load_json(spec_path)
    try:
        result = execute_plan(plan)
    except Exception as exc:
        result = {"model_id": plan.get("model_id"), "status": "FAIL",
                  "validity": {"checks": {}, "problems": [f"{type(exc).__name__}: {exc}"],
                               "traceback": traceback.format_exc()}}
    Path(out_path).write_text(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


# --------------------------------------------------------------------------------- parent
def candidates_package(model_id: str) -> Path:
    index = load_json(CANDIDATES_ROOT / "index.json")
    entry = index.get(model_id)
    if not isinstance(entry, dict) or not isinstance(entry.get("package"), str):
        raise ValueError(f"vision candidate '{model_id}' is not in "
                         f"{CANDIDATES_ROOT / 'index.json'}")
    return CANDIDATES_ROOT / entry["package"]


def model_specs(protocol: dict) -> list[dict]:
    specs = []
    for identity in protocol["compared_identities"]:
        model_id = identity["model_id"]
        spec = {"model_id": model_id, "env_value": identity["env_value"],
                "expected_model_sha256": identity["sha256"], "manifest_sha256": None}
        if model_id != STABLE_MODEL_ID:
            manifest = candidates_package(model_id) / "runtime_manifest.json"
            if not manifest.is_file():
                raise ValueError(f"candidate runtime manifest is missing: {manifest}")
            spec["manifest_sha256"] = sha256_file(manifest)
        specs.append(spec)
    return specs


def spawn_worker(spec: dict, plan: dict, out_dir: Path):
    model_id = spec["model_id"]
    work_dir = Path(tempfile.mkdtemp(prefix=f"task10a-cmp-{model_id}-"))
    plan = dict(plan)
    plan.update({"model_id": model_id, "expected_model_sha256": spec["expected_model_sha256"],
                 "session_id": f"task10a-cmp-{model_id}", "work_dir": str(work_dir),
                 "db_url": f"sqlite:///{work_dir / 'comparison.sqlite'}"})
    spec_path = out_dir / f"worker_spec_{model_id}.json"
    out_path = out_dir / f"worker_out_{model_id}.json"
    spec_path.write_text(json.dumps(plan, indent=2))
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(BACKEND_DIR) + (os.pathsep + existing if existing else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["DRA_ACTIVE_VISION"] = spec["env_value"]
    env["DRA_DATABASE_URL"] = plan["db_url"]
    env["TMPDIR"] = str(work_dir)
    command = [sys.executable, str(SCRIPTS_DIR / "compare_vision_models.py"),
               "--worker", str(spec_path), str(out_path)]
    began = time.time()
    try:
        done = subprocess.run(command, cwd=BACKEND_DIR, env=env, capture_output=True,
                              text=True, timeout=WORKER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"command": command, "exit_code": None, "duration_s": None,
                "stderr_tail": f"worker timed out after {WORKER_TIMEOUT_S} s"}, None, plan
    record = {"command": command, "exit_code": done.returncode,
              "duration_s": round(time.time() - began, 2),
              "stderr_tail": done.stderr.strip().splitlines()[-20:]}
    result = load_json(out_path) if out_path.is_file() else None
    if result is None:
        record["stderr_tail"].append(f"worker output {out_path} is missing or invalid JSON")
    return record, result, plan


def git_state(repo: Path = REPO) -> dict:
    def run(*args):
        done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                              timeout=30)
        return done.stdout.strip() if done.returncode == 0 else None

    head = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    dirty = status.splitlines() if status else []
    return {"implemented_head": head, "dirty_state": dirty}


def model_summaries(windows: list[dict], steps: list[dict]) -> dict:
    levels = [w["RiskLevel"] for w in windows]
    dominant = [w["DominantEvidence"] for w in windows]
    alerts = [w["AlertSeverity"] for w in windows]
    return {
        "risk_score": summarize([w["RiskScore"] for w in windows]),
        "risk_score_sequence": [w["RiskScore"] for w in windows],
        "risk_level": {"sequence": levels, "counts": category_counts(levels),
                       "transitions": transitions(levels, steps)},
        "dominant_evidence": {"sequence": dominant, "counts": category_counts(dominant)},
        "alert_fsm": {"sequence": alerts, "counts": category_counts(alerts),
                      "initial": transitions(alerts, steps)["initial"],
                      "transitions": transitions(alerts, steps)["transitions"]},
        "vision_non_safe": {
            "raw": summarize([w["P_distraction_raw"] for w in windows]),
            "ema": summarize([w["P_distraction"] for w in windows])},
        "telemetry_non_safe": summarize([w["P_telemetry_anomaly"] for w in windows]),
        "class_argmax_counts": class_argmax_counts(windows),
        "class_argmax_sequences": {c: [w["argmax"] for w in windows if w["class_id"] == c]
                                   for c in (f"c{i}" for i in range(10))},
        "class_boundaries": class_boundaries(steps),
    }


def paired_summary(reference: list[dict], other: list[dict], steps: list[dict]) -> dict:
    return {
        "probabilities": per_window_prob_deltas(reference, other),
        "risk_score": {"per_window": risk_score_deltas(reference, other),
                       "summary": summarize([d["delta"] for d in
                                             risk_score_deltas(reference, other)])},
        "risk_level_differences": aligned_differences([w["RiskLevel"] for w in reference],
                                                      [w["RiskLevel"] for w in other]),
        "dominant_evidence_differences": aligned_differences(
            [w["DominantEvidence"] for w in reference],
            [w["DominantEvidence"] for w in other]),
        "alert_differences": aligned_differences([w["AlertSeverity"] for w in reference],
                                                 [w["AlertSeverity"] for w in other]),
    }


def run(args) -> int:
    run_start_utc = datetime.now(timezone.utc)
    run_start_epoch_ns = time.time_ns()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    gate = protocol_gate(args.protocol, args.approval_record, run_start_epoch_ns)
    protocol = load_json(args.protocol) if gate["status"] == "PASS" else None
    official = {
        "record_type": "TASK10A_STAGE2_COMPARISON",
        "run_start_utc": run_start_utc.isoformat(),
        "run_start_epoch_ns": run_start_epoch_ns,
        "approved_protocol_path": str(Path(args.protocol).resolve()),
        "approval_reference": str(Path(args.approval_record).resolve()),
        "protocol_sha256": gate.get("protocol_sha256"),
        "protocol_mtime_ns": gate.get("protocol_mtime_ns"),
        "protocol_gate": gate,
        "commands": {}, "exit_codes": {}, "models": {}, "paired_summaries": {},
        "environment": environment_versions(), **git_state(),
        "validity": {"status": "BLOCKED", "problems": list(gate["problems"])},
        "failures_and_limitations": [
            "Constructed evaluation scenario (protocol D06): class blocks of the fixed "
            "stable200 order; transitions at block boundaries reflect this order and the "
            "EMA carry, not real dwell time; a single Low block cannot show 10 s recovery.",
            "One fixed telemetry row repeated as NEW synthetic samples: the telemetry branch "
            "is identical across models and windows; a single row cannot establish general "
            "multimodal benefit.",
            "Descriptive only: no winner, no single score, no significance claim; higher "
            "Macro-F1 or lower RiskScore does not prove safer driving; the active model is "
            "unchanged.",
            "Inputs are dataset images transported as original JPEG bytes; provenance "
            "vision_source remains the server's camera_frame value and every result is "
            "labelled a constructed dataset input, not a camera capture.",
        ],
    }
    if gate["status"] != "PASS":
        official["run_end_utc"] = datetime.now(timezone.utc).isoformat()
        official["run_end_epoch_ns"] = time.time_ns()
        finalize(out_dir, official, exit_code=2)
        print("BLOCKED: " + "; ".join(gate["problems"]), file=sys.stderr)
        return 2

    steps = build_steps(protocol)
    base = base_plan(protocol, steps)
    base["protocol_path"] = str(Path(args.protocol).resolve())
    base["protocol_sha256"] = gate["protocol_sha256"]

    packages = {}
    for identity in protocol["compared_identities"]:
        if identity["model_id"] != STABLE_MODEL_ID:
            try:
                packages[identity["model_id"]] = candidates_package(identity["model_id"])
            except (ValueError, OSError) as exc:
                official["validity"]["problems"].append(str(exc))

    annotations_paths = [packages[model_id] / "validation/stable200_annotations.csv"
                         for model_id in packages]
    input_verification = verify_protocol_inputs(
        protocol, data_root=protocol["input_set"]["data_root"],
        annotations_paths=annotations_paths,
        metadata_path=protocol["input_set"]["metadata_path"],
        telemetry_csv_path=protocol["telemetry_pairing"]["source_file"])
    official["input_verification"] = input_verification
    official["recomputed_membership_sha256"] = input_verification["recomputed"]["membership_sha256"]
    official["recomputed_source_ids_sha256"] = input_verification["recomputed"]["source_ids_sha256"]
    official["recomputed_image_bytes_manifest_sha256"] = \
        input_verification["recomputed"]["image_bytes_manifest_sha256"]
    if not input_verification["ok"]:
        official["validity"]["problems"].extend(input_verification["problems"])
        official["run_end_utc"] = datetime.now(timezone.utc).isoformat()
        official["run_end_epoch_ns"] = time.time_ns()
        finalize(out_dir, official, exit_code=2)
        print("BLOCKED: " + "; ".join(input_verification["problems"]), file=sys.stderr)
        return 2

    try:
        specs = model_specs(protocol)
    except (ValueError, OSError) as exc:
        official["validity"]["problems"].append(str(exc))
        official["run_end_utc"] = datetime.now(timezone.utc).isoformat()
        official["run_end_epoch_ns"] = time.time_ns()
        finalize(out_dir, official, exit_code=2)
        return 2

    all_pass = True
    for spec in specs:
        worker_record, worker_result, plan = spawn_worker(spec, base, out_dir)
        if worker_result is None:
            worker_result = {"model_id": spec["model_id"], "status": "FAIL",
                             "validity": {"checks": {}, "problems": ["no worker result"]}}
        official["commands"][spec["model_id"]] = worker_record["command"]
        official["exit_codes"][spec["model_id"]] = worker_record["exit_code"]
        status = worker_result.get("status")
        all_pass = all_pass and status == "PASS" and worker_record["exit_code"] == 0
        official["models"][spec["model_id"]] = {
            "model_id": spec["model_id"],
            "env_value": spec["env_value"],
            "model_sha256": (worker_result.get("identity") or {}).get("vision_model_sha256"),
            "expected_model_sha256": spec["expected_model_sha256"],
            "telemetry_model_sha256":
                (worker_result.get("identity") or {}).get("telemetry_model_sha256"),
            "manifest_sha256": spec["manifest_sha256"],
            "database_path": worker_result.get("database_path"),
            "subprocess_pid": worker_result.get("subprocess_pid"),
            "session_id": worker_result.get("session_id"),
            "status": status,
            "worker": worker_record,
            "environment": worker_result.get("environment"),
            "validity": worker_result.get("validity"),
            "window_ids": worker_result.get("window_ids"),
            "windows": worker_result.get("windows", []),
            "started_utc": worker_result.get("started_utc"),
            "finished_utc": worker_result.get("finished_utc"),
        }
        if spec["model_id"] == STABLE_MODEL_ID:
            official["models"][spec["model_id"]]["manifest_sha256_reason"] = \
                "stable provider has no candidate runtime manifest"

    windows_by_model = {model_id: entry["windows"]
                        for model_id, entry in official["models"].items() if entry["windows"]}
    if len(windows_by_model) == len(specs) and all(
            len(windows) == len(steps) for windows in windows_by_model.values()):
        official["identical_results"] = identical_results(windows_by_model)
        if official["identical_results"]:
            official["validity"]["problems"].append(
                "identical_results: every raw probability and downstream result is identical "
                "across all identities - withhold interpretation and investigate provider "
                "loading/selection")
            all_pass = False
        for spec in specs:
            model_id = spec["model_id"]
            official["models"][model_id]["summaries"] = model_summaries(
                windows_by_model[model_id], steps)
        reference_id = specs[0]["model_id"]
        for spec in specs[1:]:
            other_id = spec["model_id"]
            official["paired_summaries"][f"{other_id}_minus_{reference_id}"] = paired_summary(
                windows_by_model[reference_id], windows_by_model[other_id], steps)
    else:
        official["identical_results"] = None
        official["validity"]["problems"].append(
            "not every model produced a full window sequence; summaries withheld")

    for model_id, entry in official["models"].items():
        for problem in (entry.get("validity") or {}).get("problems", []):
            official["validity"]["problems"].append(f"{model_id}: {problem}")
    official["validity"]["status"] = "PASS" if all_pass and not official["validity"]["problems"] else "FAIL"
    official["run_end_utc"] = datetime.now(timezone.utc).isoformat()
    official["run_end_epoch_ns"] = time.time_ns()
    exit_code = 0 if official["validity"]["status"] == "PASS" else 1
    finalize(out_dir, official, exit_code=exit_code)
    return exit_code


def finalize(out_dir: Path, official: dict, *, exit_code: int) -> None:
    """Write comparison_results.json; record the output mtime observed during finalization
    (a later rewrite of the same file only moves the file's own mtime further forward)."""
    official["exit_code"] = exit_code
    out_path = out_dir / "comparison_results.json"
    official["output_mtime_ns"] = None
    out_path.write_text(json.dumps(official, indent=2, sort_keys=True))
    official["output_mtime_ns"] = out_path.stat().st_mtime_ns
    out_path.write_text(json.dumps(official, indent=2, sort_keys=True))
    if out_path.stat().st_mtime_ns <= official["run_start_epoch_ns"]:
        raise RuntimeError("output mtime is not after the run start")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage-2 paired vision comparison runner (Task 10A / DS-2)")
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL,
                        help=f"approved protocol (read-only; default: {DEFAULT_PROTOCOL})")
    parser.add_argument("--approval-record", type=Path, default=DEFAULT_APPROVAL_RECORD,
                        help=f"approval record binding the protocol sha256 (default: "
                             f"{DEFAULT_APPROVAL_RECORD})")
    parser.add_argument("--out", type=Path, default=None,
                        help="evidence directory (default: docs/evidence/<today>/comparison)")
    parser.add_argument("--worker", nargs=2, metavar=("SPEC", "OUT"), default=None,
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return run_child(Path(args.worker[0]), Path(args.worker[1]))
    out = args.out or REPO / "docs" / "evidence" / datetime.now().strftime("%Y-%m-%d") / "comparison"
    return run(argparse.Namespace(protocol=args.protocol, approval_record=args.approval_record,
                                  out=out))


if __name__ == "__main__":
    sys.exit(main())
