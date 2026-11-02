#!/usr/bin/env python3
"""E2 and E5 (light) fusion evaluation, bound by ``docs/fyp2/e2e5/protocol.json``.

Usage (from the repo root, with the backend venv):

    .venv/bin/python scripts/fusion_eval.py e2 [--out DIR]
    .venv/bin/python scripts/fusion_eval.py e5 [--out DIR]

E2 sends 60 constructed (image, telemetry row) pairs, in 6 label strata, through the REAL
``/infer`` once per fusion-weight setting of report Table 9. That is 300 one-window
sessions, so no EMA history is involved. E5 (light) replays the ``viva_compact``
constructed scenario three times through the same ``/infer``, with EMA and the
AlertSeverity FSM:

- as declared;
- with vision held safe;
- with telemetry held Safe.

Both are DESCRIPTIVE ONLY: no weight is chosen and nothing here measures real-world
risk-prediction accuracy. The operational reference is the protocol's source-label policy,
declared and committed before any run (D06).

Mechanics shared with ``scripts/compare_vision_models.py``:

- one worker subprocess that strips every inherited ``DRA_*`` variable;
- a temporary SQLite (never ``backend/driver_risk.db*``) and ``fastapi.testclient.TestClient``
  (no port 8000 listener);
- an injected server clock, and a fault sink inside the work directory.

Images are read from the data root and are never copied into the evidence; only their file
names and sha256 are recorded.

Exit codes:

- 0: valid run;
- 1: a window or identity check failed;
- 2: BLOCKED (protocol gate, data root, or usage).
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO / "scripts"
BACKEND_DIR = REPO / "backend"
sys.path.insert(0, str(SCRIPTS_DIR))

from build_dataset_replay import (  # noqa: E402
    TELEMETRY_FEATURES,
    build_bundle,
    read_telemetry_rows,
    read_vision_metadata,
)
from compare_vision_models import (  # noqa: E402
    STABLE_MODEL_ID,
    environment_versions,
    git_state,
    linear_quantile,
    make_clock,
    sha256_bytes,
    sha256_file,
)
from freeze_manifest import DataRootError, resolve_data_root  # noqa: E402

PROTOCOL = REPO / "docs" / "fyp2" / "e2e5" / "protocol.json"
T0 = "2026-11-02T00:00:00+00:00"
WORKER_TIMEOUT_S = 3600
SEVERITY_ORDER = {"NORMAL": 0, "CAUTION": 1, "HIGH_ALERT": 2}


def iso_at(offset_ms: int, t0: str = T0) -> str:
    return (datetime.fromisoformat(t0) + timedelta(milliseconds=int(offset_ms))).isoformat()


# ---------------------------------------------------------------------- protocol gate
def expected_vision_model(protocol: dict) -> str:
    """The machine-readable vision model of a protocol; absent means the stable model."""
    return (protocol.get("fixed_runtime") or {}).get("vision_model_id", STABLE_MODEL_ID)


def worker_environment(base_env: dict, vision_model_id: str, backend_dir: Path,
                       work_dir: Path) -> dict:
    """The child environment: no inherited DRA_*; the candidate id when one is declared."""
    env = {k: v for k, v in base_env.items() if not k.startswith("DRA_")}
    env.update(PYTHONPATH=str(backend_dir), PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(work_dir),
               DRA_DATABASE_URL=f"sqlite:///{work_dir / 'eval.sqlite'}")
    if vision_model_id != STABLE_MODEL_ID:
        env["DRA_ACTIVE_VISION"] = vision_model_id
    return env


def _git(*args: str) -> str | None:
    done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30)
    return done.stdout.strip() if done.returncode == 0 else None


def gate_verdict(*, dirty: bool, commit: str | None, commit_time: str | None,
                 blob_matches: bool, run_start: datetime) -> list[str]:
    """The problems that block a run: the protocol must be committed, unmodified, and its
    commit must be older than the run (it was declared before any result existed)."""
    problems = []
    if commit is None or commit_time is None:
        problems.append("protocol.json is not committed")
    else:
        if datetime.fromisoformat(commit_time) >= run_start:
            problems.append(f"protocol commit time {commit_time} is not before the run start "
                            f"{run_start.isoformat()}")
        if not blob_matches:
            problems.append("protocol.json differs from its committed blob")
    if dirty:
        problems.append("protocol.json has uncommitted changes")
    return problems


def protocol_gate(run_start: datetime, path: Path = PROTOCOL) -> dict:
    path = Path(path)
    if not path.is_absolute():
        path = REPO / path
    rel = str(path.relative_to(REPO))
    log = _git("log", "-1", "--format=%H %cI", "--", rel)
    commit, commit_time = (log.split(" ", 1) if log else (None, None))
    committed_blob = _git("rev-parse", f"HEAD:{rel}")
    working_blob = _git("hash-object", rel)
    dirty = bool(_git("status", "--porcelain", "--", rel))
    problems = gate_verdict(dirty=dirty, commit=commit, commit_time=commit_time,
                            blob_matches=committed_blob is not None and committed_blob == working_blob,
                            run_start=run_start)
    return {"path": rel, "sha256": sha256_file(path), "commit": commit,
            "commit_time": commit_time, "blob": committed_blob, "dirty": dirty,
            "status": "PASS" if not problems else "BLOCKED", "problems": problems}


# ------------------------------------------------------------- reference and oracles
def reference(vision_class: str, telemetry_label: str, policy: dict) -> tuple[str, list[str]]:
    """The protocol's operational reference, from SOURCE labels only."""
    non_safe = int(vision_class != "c0") + int(telemetry_label != "Safe")
    key = ("no_branch_non_safe", "exactly_one_branch_non_safe", "both_branches_non_safe")[non_safe]
    return policy["names"][key], list(policy["levels"][key])


def _exact(value: float) -> Fraction:
    # The decimal the double prints as: the same value the product rounds (its repr).
    return Fraction(Decimal(repr(float(value))))


def exact_score(pd: float, pt: float, w_v: float, w_t: float) -> Fraction:
    """Independent recomputation of the fused 0-100 score, both branches fresh, in exact
    rational arithmetic; it never calls the product fusion code."""
    clamp = lambda x: min(Fraction(1), max(Fraction(0), x))  # noqa: E731
    wv, wt = _exact(w_v), _exact(w_t)
    return (wv * clamp(_exact(pd)) + wt * clamp(_exact(pt))) / (wv + wt) * 100


def round_half_up_1dp(value: Fraction) -> float:
    return float((Decimal(value.numerator) / Decimal(value.denominator))
                 .quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def is_decimal_tie(value: Fraction) -> bool:
    """The exact score sits on a .x5 tie. Only there may the product, which rounds the
    double's repr (fusion.round_half_up), land one tenth below the exact half-up value."""
    tenths = value * 10
    return tenths - (tenths.numerator // tenths.denominator) == Fraction(1, 2)


def level_of(score: float, low: float, high: float) -> str:
    return "Low" if score < low else ("Medium" if score < high else "High")


def dominant_of(pd: float, pt: float, score: float, low: float, gap: float = 0.15) -> str:
    """The documented decision tree for a FULL-health window (raw strength, R14)."""
    if score < low:
        return "Low observed risk"
    if abs(pd - pt) < gap:
        return "Combined evidence"
    return "Vision-dominant" if pd > pt else "Telemetry-dominant"


def r14_disagrees(dominant: str | None, pd: float, pt: float, w_v: float, w_t: float) -> bool:
    """The raw-strength label names one branch while the other carries the larger weighted
    contribution (the documented R14 limitation)."""
    if dominant == "Vision-dominant":
        return w_t * pt > w_v * pd
    if dominant == "Telemetry-dominant":
        return w_v * pd > w_t * pt
    return False


# ---------------------------------------------------------------------------- E2 plan
def e2_pairs(vision_rows: list[dict], telemetry_rows: list[dict], e2: dict, policy: dict) -> list[dict]:
    """The 60 constructed pairs, exactly as the protocol's sampling rule states."""
    test = [r for r in vision_rows if r["split"] == "test"]
    pools = {kind: sorted((r for r in test if r["class_id"] in classes), key=lambda r: r["filename"])
             for kind, classes in e2["vision_pools"].items()}
    by_label = {label: [(n, row) for n, row in enumerate(telemetry_rows)
                        if row["behavior_label"] == label]
                for label in ("Safe", "Aggressive", "Distracted")}
    k = e2["pairs_per_stratum"]
    strata = e2["strata"]
    rng = random.Random(e2["seed"])
    drawn_vision = {kind: rng.sample(pools[kind], k * sum(s["vision"] == kind for s in strata))
                    for kind in ("safe", "distracted")}
    drawn_tel = {label: rng.sample(by_label[label], k * sum(s["telemetry"] == label for s in strata))
                 for label in ("Safe", "Aggressive", "Distracted")}
    used_v = {kind: 0 for kind in drawn_vision}
    used_t = {label: 0 for label in drawn_tel}
    pairs = []
    for stratum in strata:
        for i in range(k):
            image = drawn_vision[stratum["vision"]][used_v[stratum["vision"]]]
            row_n, row = drawn_tel[stratum["telemetry"]][used_t[stratum["telemetry"]]]
            used_v[stratum["vision"]] += 1
            used_t[stratum["telemetry"]] += 1
            ref_name, ref_levels = reference(image["class_id"], row["behavior_label"], policy)
            pairs.append({
                "pair_id": f"{stratum['id']}-{i + 1:02d}",
                "stratum": stratum["id"],
                "vision": {"filename": image["filename"], "class_id": image["class_id"],
                           "driver_id": image["driver_id"], "image_path": image["image_path"]},
                "telemetry": {"row": row_n, "label": row["behavior_label"],
                              "features": {f: float(row[f]) for f in TELEMETRY_FEATURES}},
                "reference": ref_name, "reference_levels": ref_levels,
            })
    return pairs


def runtime_config(protocol: dict, w_v: float, w_t: float) -> dict:
    fixed = protocol["fixed_runtime"]
    return {"weight_vision": w_v, "weight_telemetry": w_t, "ema_alpha": fixed["ema_alpha"],
            "threshold_low": fixed["threshold_low"], "threshold_high": fixed["threshold_high"],
            "freshness_tolerance_s": fixed["freshness_tolerance_s"]}


def e2_sessions(pairs: list[dict], protocol: dict) -> list[dict]:
    sessions = []
    for p_index, pair in enumerate(pairs):
        for w_index, weight in enumerate(protocol["e2"]["weights"]):
            t = iso_at((p_index * len(protocol["e2"]["weights"]) + w_index) * 1000)
            sessions.append({
                "session_id": f"e2-{pair['pair_id']}-w{w_index}",
                "mode": "LIVE_MODEL_RUNTIME",
                "config": runtime_config(protocol, weight["w_v"], weight["w_t"]),
                "meta": {"pair_id": pair["pair_id"], "weight_index": w_index},
                "steps": [{
                    "request_id": f"e2_{pair['pair_id']}_w{w_index}".replace("-", "_"),
                    "server_time": t,
                    "image_path": pair["vision"]["image_path"],
                    "image_sha256": pair["vision"].get("sha256"),
                    "captured_at": t, "captured_at_source": "client_clock",
                    "vision_frame": {"epoch": 1, "index": 1},
                    "telemetry_features": pair["telemetry"]["features"],
                    "telemetry_timestamp": t, "telemetry_seq": 1,
                }],
            })
    return sessions


# ---------------------------------------------------------------------------- E5 plan
def e5_variant_scenarios(base: dict, variants: list[dict]) -> dict[str, dict]:
    """The three scenarios: the declared one, and one with each branch held safe."""
    out = {}
    for variant in variants:
        scenario = json.loads(json.dumps(base))
        if variant["id"] == "VISION_HELD_SAFE":
            scenario["scenario_id"] = f"{base['scenario_id']}_vision_held"
            for segment in scenario["segments"]:
                segment["vision_class"] = "c0"
        elif variant["id"] == "TELEMETRY_HELD_SAFE":
            scenario["scenario_id"] = f"{base['scenario_id']}_telemetry_held"
            for segment in scenario["segments"]:
                segment["telemetry_label"] = "Safe"
        elif variant["id"] != "FUSED":
            raise ValueError(f"unknown E5 variant {variant['id']!r}")
        out[variant["id"]] = scenario
    return out


def e5_steps(manifest: dict, frames_dir: Path, interval_ms: int, policy: dict,
             variant_id: str) -> list[dict]:
    """The playback of ai/src/scenarioTimeline.ts at the product's default 10 windows/s:
    frame n = floor(pos/frame_period), row k = floor(pos/telemetry_period), telemetry_seq
    from 0, +1 each time k grows; acquisition times on the playback clock."""
    fp, tp = manifest["frame_period_ms"], manifest["telemetry_period_ms"]
    steps, seq, last_k = [], 0, 0
    for i in range(manifest["duration_ms"] // interval_ms):
        pos = i * interval_ms
        n, k = pos // fp, pos // tp
        if k > last_k:
            seq, last_k = seq + 1, k
        frame, row = manifest["frames"][n], manifest["telemetry"][k]
        if frame["segment_index"] != row["segment_index"]:
            raise ValueError(f"frame {n} and row {k} fall in different segments at {pos} ms")
        ref_name, ref_levels = reference(frame["class_id"], row["label"], policy)
        steps.append({
            "request_id": f"e5_{variant_id.lower()}_{i:04d}",
            "server_time": iso_at(pos),
            "image_path": str(frames_dir / frame["file"]), "image_sha256": frame["sha256"],
            "captured_at": iso_at(n * fp), "captured_at_source": "replay_clock",
            "vision_frame": {"epoch": 1, "index": n},
            "telemetry_features": row["features"], "telemetry_timestamp": iso_at(k * tp),
            "telemetry_seq": seq,
            "replay": {"scenario_id": manifest["scenario_id"], "segment_index": frame["segment_index"],
                       "frame_file": frame["file"], "vision_label": frame["vision_label"],
                       "telemetry_row": row["row"], "telemetry_label": row["label"]},
            "meta": {"pos_ms": pos, "segment_index": frame["segment_index"], "frame_n": n,
                     "row_k": k, "class_id": frame["class_id"], "telemetry_label": row["label"],
                     "reference": ref_name, "reference_levels": ref_levels},
        })
    return steps


def unchanged_segment_identity(manifests: dict[str, dict]) -> dict:
    """A segment whose labels a variant did not change must get the same frames and rows."""
    base = manifests["FUSED"]
    report = {}
    for variant, manifest in manifests.items():
        if variant == "FUSED":
            continue
        rows = []
        for seg_b, seg_v in zip(base["segments"], manifest["segments"]):
            idx = seg_b["index"]
            same_labels = (seg_b["vision_class"], seg_b["telemetry_label"]) == \
                          (seg_v["vision_class"], seg_v["telemetry_label"])
            frames_b = [f["sha256"] for f in base["frames"] if f["segment_index"] == idx]
            frames_v = [f["sha256"] for f in manifest["frames"] if f["segment_index"] == idx]
            tel_b = [(t["row"], t["label"]) for t in base["telemetry"] if t["segment_index"] == idx]
            tel_v = [(t["row"], t["label"]) for t in manifest["telemetry"] if t["segment_index"] == idx]
            rows.append({"segment_index": idx, "labels_unchanged": same_labels,
                         "vision_identical": frames_b == frames_v,
                         "telemetry_identical": tel_b == tel_v})
        report[variant] = rows
    return report


# --------------------------------------------------------------------------- worker
def _payload(step: dict) -> tuple[dict, str]:
    raw = Path(step["image_path"]).read_bytes()
    if step.get("image_sha256") and sha256_bytes(raw) != step["image_sha256"]:
        raise ValueError(f"image bytes changed: {step['image_path']}")
    body = {
        "request_id": step["request_id"],
        "image_base64": base64.b64encode(raw).decode("ascii"),
        "captured_at": step["captured_at"], "captured_at_source": step["captured_at_source"],
        "vision_frame": step["vision_frame"],
        "telemetry_features": step["telemetry_features"],
        "telemetry_timestamp": step["telemetry_timestamp"],
        "telemetry_source": "prepared_replay", "telemetry_seq": step["telemetry_seq"],
    }
    if step.get("replay"):
        body["replay"] = step["replay"]
    return body, sha256_bytes(raw)


def _window(body: dict) -> dict:
    prov = body.get("provenance") or {}
    fresh = body.get("modality_freshness") or {}
    return {
        "window_id": body.get("window_id"), "timestamp": body.get("timestamp"),
        "RiskScore": body.get("RiskScore"), "RiskLevel": body.get("RiskLevel"),
        "DominantEvidence": body.get("DominantEvidence"),
        "AlertSeverity": body.get("AlertSeverity"), "SystemHealth": body.get("SystemHealth"),
        "assessment_available": body.get("assessment_available"),
        "P_distraction": body.get("P_distraction"),
        "P_telemetry_anomaly": body.get("P_telemetry_anomaly"),
        "P_distraction_raw": prov.get("P_distraction_raw"),
        "P_telemetry_raw": prov.get("P_telemetry_raw"),
        "vision_obs": prov.get("vision_obs"), "telemetry_obs": prov.get("telemetry_obs"),
        "vision_freshness": fresh.get("vision"), "telemetry_freshness": fresh.get("telemetry"),
        "vision_model_id": prov.get("vision_model_id"),
        "vision_model_sha256": prov.get("vision_model_sha256"),
        "telemetry_model_sha256": prov.get("telemetry_model_sha256"),
    }


def execute(plan: dict) -> dict:
    """The worker: real app, real providers, injected clock, temporary SQLite."""
    work_dir = Path(plan["work_dir"])
    problems: list[str] = []
    identity: dict = {}
    sessions_out = []
    expected_vision = plan.get("vision_model_id", STABLE_MODEL_ID)
    expected_vision_sha = plan.get("vision_model_sha256")

    from fastapi.testclient import TestClient

    import app.inference as inference_mod
    import app.providers.trained as trained_mod
    from app import cache, faults
    from app.config import settings
    from app.main import app

    db_file = Path(settings.database_url.removeprefix("sqlite:///"))
    if not db_file.resolve().is_relative_to(work_dir.resolve()):
        return {"status": "FAIL", "problems": [f"database {settings.database_url} is not under {work_dir}"]}
    clock = make_clock(datetime.fromisoformat(T0))
    previous = (faults.DEFAULT_SINK_PATH, inference_mod.datetime, trained_mod.datetime)
    faults.DEFAULT_SINK_PATH = work_dir / "fault_events.log"
    inference_mod.datetime = trained_mod.datetime = clock
    try:
        with TestClient(app) as client:
            models = client.get("/api/models").json()
            identity = {"vision_model_id": (models.get("vision") or {}).get("model_id"),
                        "vision_model_sha256": (models.get("vision") or {}).get("sha256"),
                        "telemetry_model_sha256": (models.get("telemetry") or {}).get("sha256"),
                        "models_endpoint": models}
            if identity["vision_model_id"] != expected_vision:
                problems.append(f"active vision model is {identity['vision_model_id']!r}, "
                                f"the protocol requires {expected_vision!r}")
            if expected_vision_sha and identity["vision_model_sha256"] != expected_vision_sha:
                problems.append(f"vision model sha256 is {identity['vision_model_sha256']!r}, "
                                f"the protocol requires {expected_vision_sha!r}")
            for session in plan["sessions"] if not problems else []:
                created = client.post("/api/sessions", json={
                    "session_id": session["session_id"], "operation_mode": session["mode"],
                    "description": "E2/E5 fusion evaluation (constructed, docs/fyp2/e2e5)",
                    "config": session["config"]})
                if created.status_code != 201:
                    problems.append(f"POST /api/sessions {session['session_id']} -> "
                                    f"{created.status_code}: {created.text[:300]}")
                    break
                windows = []
                for step in session["steps"]:
                    clock.set_iso(step["server_time"])
                    body, image_sha = _payload(step)
                    response = client.post(f"/api/sessions/{session['session_id']}/infer", json=body)
                    if response.status_code != 201:
                        problems.append(f"POST /infer {step['request_id']} -> "
                                        f"{response.status_code}: {response.text[:300]}")
                        break
                    window = _window(response.json())
                    window.update(request_id=step["request_id"], image_sha256=image_sha,
                                  meta=step.get("meta", {}))
                    used = (window["vision_model_id"], window["vision_model_sha256"],
                            window["telemetry_model_sha256"])
                    expected = (expected_vision, identity["vision_model_sha256"],
                                identity["telemetry_model_sha256"])
                    if used != expected:
                        problems.append(f"{step['request_id']}: window used models {used}, "
                                        f"GET /api/models reported {expected}")
                    windows.append(window)
                sessions_out.append({"session_id": session["session_id"],
                                     "meta": session.get("meta", {}), "windows": windows})
                cache.clear(session["session_id"])
                if problems:
                    break
    except Exception as exc:
        problems.append(f"worker raised {type(exc).__name__}: {exc}")
        identity["traceback"] = traceback.format_exc()
    finally:
        faults.DEFAULT_SINK_PATH, inference_mod.datetime, trained_mod.datetime = previous
    return {"status": "PASS" if not problems else "FAIL", "problems": problems,
            "identity": identity, "sessions": sessions_out, "environment": environment_versions()}


def run_worker(plan: dict, out_dir: Path) -> tuple[dict, dict]:
    work_dir = Path(plan["work_dir"])
    spec, result = work_dir / "worker_spec.json", work_dir / "worker_out.json"
    spec.write_text(json.dumps(plan))
    env = worker_environment(os.environ, plan.get("vision_model_id", STABLE_MODEL_ID),
                             BACKEND_DIR, work_dir)
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(spec), str(result)]
    began = time.time()
    done = subprocess.run(command, cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
                          timeout=WORKER_TIMEOUT_S)
    record = {"command": [Path(c).name if i < 2 else c for i, c in enumerate(command)],
              "exit_code": done.returncode, "duration_s": round(time.time() - began, 1),
              "stderr_tail": done.stderr.strip().splitlines()[-15:]}
    output = json.loads(result.read_text()) if result.is_file() else \
        {"status": "FAIL", "problems": ["worker wrote no output"], "sessions": []}
    return record, output


# ------------------------------------------------------------------------- statistics
def quantiles(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    r = lambda x: round(x, 3)  # noqa: E731
    return {"n": len(values), "min": r(min(values)), "q1": r(linear_quantile(values, 0.25)),
            "median": r(linear_quantile(values, 0.5)), "q3": r(linear_quantile(values, 0.75)),
            "max": r(max(values)), "mean": r(sum(values) / len(values))}


def counts(values, keys) -> dict:
    return {key: sum(v == key for v in values) for key in keys}


LEVELS = ("Low", "Medium", "High")
DOMINANTS = ("Low observed risk", "Combined evidence", "Vision-dominant", "Telemetry-dominant",
             "Partial evidence")


def e2_rows(pairs: list[dict], sessions: list[dict], protocol: dict) -> list[dict]:
    """One row per (pair, weight) with every per-window check the protocol names."""
    weights = protocol["e2"]["weights"]
    low, high = protocol["fixed_runtime"]["threshold_low"], protocol["fixed_runtime"]["threshold_high"]
    by_pair = {p["pair_id"]: p for p in pairs}
    rows = []
    for session in sessions:
        pair = by_pair[session["meta"]["pair_id"]]
        weight = weights[session["meta"]["weight_index"]]
        w = session["windows"][0]
        pd, pt, score = w["P_distraction"], w["P_telemetry_anomaly"], w["RiskScore"]
        exact = exact_score(pd, pt, weight["w_v"], weight["w_t"])
        exact_f = float(exact)
        v_non_safe, t_non_safe = pair["vision"]["class_id"] != "c0", pair["telemetry"]["label"] != "Safe"
        rows.append({
            "pair_id": pair["pair_id"], "stratum": pair["stratum"],
            "weight_index": session["meta"]["weight_index"], "w_v": weight["w_v"], "w_t": weight["w_t"],
            "vision_file": pair["vision"]["filename"], "vision_class": pair["vision"]["class_id"],
            "driver_id": pair["vision"]["driver_id"], "telemetry_row": pair["telemetry"]["row"],
            "telemetry_label": pair["telemetry"]["label"],
            "P_distraction": pd, "P_telemetry": pt,
            "P_distraction_raw": w["P_distraction_raw"], "P_telemetry_raw": w["P_telemetry_raw"],
            "RiskScore": score, "RiskLevel": w["RiskLevel"], "DominantEvidence": w["DominantEvidence"],
            "SystemHealth": w["SystemHealth"], "AlertSeverity": w["AlertSeverity"],
            "fresh_both": w["vision_freshness"] == "fresh" and w["telemetry_freshness"] == "fresh",
            "observations_new": w["vision_obs"] == "new" and w["telemetry_obs"] == "new",
            "reference": pair["reference"], "agrees": w["RiskLevel"] in pair["reference_levels"],
            "exact_score": round(exact_f, 6),
            "formula_error": round(score - exact_f, 6) if score is not None else None,
            "rounded_match": score == round_half_up_1dp(exact),
            "exact_tie": is_decimal_tie(exact),
            "level_oracle_match": score is not None and w["RiskLevel"] == level_of(score, low, high),
            "dominant_oracle_match": score is not None and w["DominantEvidence"] == dominant_of(pd, pt, score, low),
            "r14_disagrees": r14_disagrees(w["DominantEvidence"], pd, pt, weight["w_v"], weight["w_t"]),
            "attenuation_case": (max(pd, pt) >= 0.8 and min(pd, pt) < 0.2 and w["RiskLevel"] != "High"),
            "vision_model_disagrees": (pd >= 0.5) != v_non_safe,
            "telemetry_model_disagrees": (pt >= 0.5) != t_non_safe,
        })
    return rows


def threshold_ties(rows: list[dict], protocol: dict) -> dict:
    """NOT PRE-DECLARED (added after the 2026-11-02 review): how many windows take their
    level from the product's 1-dp rounding at a threshold. Table 9's 0.3 and 0.6 times a
    near-saturated branch land on 30 and 60, so the rounded and unrounded levels can differ.
    Reported next to the declared numbers, never in place of them."""
    weights = protocol["e2"]["weights"]
    low, high = protocol["fixed_runtime"]["threshold_low"], protocol["fixed_runtime"]["threshold_high"]
    base_index = protocol["e2"]["baseline_weight_index"]
    ref_levels = {"REF_LOW": ["Low"], "REF_ELEVATED": ["Medium", "High"], "REF_HIGH": ["High"]}
    unrounded = {(r["pair_id"], r["weight_index"]): level_of(r["exact_score"], low, high) for r in rows}
    out = {}
    for j, weight in enumerate(weights):
        cell = [r for r in rows if r["weight_index"] == j]
        decided = [r for r in cell if unrounded[(r["pair_id"], j)] != r["RiskLevel"]]
        out[weight["name"]] = {
            "within_0_1_of_a_threshold": sum(min(abs(r["exact_score"] - low), abs(r["exact_score"] - high)) <= 0.1
                                             for r in cell),
            "level_decided_by_rounding": len(decided),
            "pairs_decided_by_rounding": sorted(r["pair_id"] for r in decided),
            "agrees_unrounded": sum(unrounded[(r["pair_id"], j)] in ref_levels[r["reference"]] for r in cell),
            "changed_vs_baseline_unrounded": None if j == base_index else sum(
                unrounded[(r["pair_id"], j)] != unrounded[(r["pair_id"], base_index)] for r in cell),
        }
    return out


def e2_summary(rows: list[dict], protocol: dict) -> dict:
    weights = protocol["e2"]["weights"]
    strata = [s["id"] for s in protocol["e2"]["strata"]]
    base_index = protocol["e2"]["baseline_weight_index"]
    cell = lambda s, j: [r for r in rows if r["stratum"] == s and r["weight_index"] == j]  # noqa: E731
    probs = {}
    for r in rows:
        probs.setdefault(r["pair_id"], set()).add((r["P_distraction"], r["P_telemetry"]))
    baseline = {r["pair_id"]: r for r in rows if r["weight_index"] == base_index}
    rank = {lvl: i for i, lvl in enumerate(LEVELS)}
    changes = {}
    for j, weight in enumerate(weights):
        if j == base_index:
            continue
        moved = [r for r in rows if r["weight_index"] == j
                 and r["RiskLevel"] != baseline[r["pair_id"]]["RiskLevel"]]
        changes[weight["name"]] = {
            "pairs": len(baseline), "changed": len(moved),
            "up": sum(rank[r["RiskLevel"]] > rank[baseline[r["pair_id"]]["RiskLevel"]] for r in moved),
            "down": sum(rank[r["RiskLevel"]] < rank[baseline[r["pair_id"]]["RiskLevel"]] for r in moved),
            "by_stratum": {s: sum(r["stratum"] == s for r in moved) for s in strata},
            "pairs_changed": sorted(r["pair_id"] for r in moved)}
    pair_level = [r for r in rows if r["weight_index"] == base_index]
    consistent = {r["pair_id"] for r in pair_level
                  if not r["vision_model_disagrees"] and not r["telemetry_model_disagrees"]}
    return {
        "checks": {
            "windows": len(rows),
            "max_abs_formula_error": max(abs(r["formula_error"]) for r in rows),
            "formula_error_within_half_step": all(abs(r["formula_error"]) <= 0.05 + 1e-9 for r in rows),
            "rounded_mismatches": sum(not r["rounded_match"] for r in rows),
            "rounded_mismatches_off_tie": sum(not r["rounded_match"] and not r["exact_tie"] for r in rows),
            "level_oracle_mismatches": sum(not r["level_oracle_match"] for r in rows),
            "dominant_oracle_mismatches": sum(not r["dominant_oracle_match"] for r in rows),
            "probabilities_identical_across_weights": all(len(v) == 1 for v in probs.values()),
            "all_fresh": all(r["fresh_both"] for r in rows),
            "all_observations_new": all(r["observations_new"] for r in rows),
            "all_health_full": all(r["SystemHealth"] == "FULL" for r in rows),
        },
        "inputs": {
            "pairs": len(baseline),
            "unique_images": len({r["vision_file"] for r in pair_level}),
            "unique_telemetry_rows": len({r["telemetry_row"] for r in pair_level}),
            "drivers": counts([r["driver_id"] for r in pair_level], sorted({r["driver_id"] for r in pair_level})),
            "vision_classes": counts([r["vision_class"] for r in pair_level],
                                     sorted({r["vision_class"] for r in pair_level})),
        },
        "cells": {s: {w["name"]: {
            "score": quantiles([r["RiskScore"] for r in cell(s, j)]),
            "levels": counts([r["RiskLevel"] for r in cell(s, j)], LEVELS),
            "agrees": sum(r["agrees"] for r in cell(s, j)),
            "dominant": counts([r["DominantEvidence"] for r in cell(s, j)], DOMINANTS),
            "r14_disagrees": sum(r["r14_disagrees"] for r in cell(s, j)),
            "attenuation_cases": sum(r["attenuation_case"] for r in cell(s, j)),
        } for j, w in enumerate(weights)} for s in strata},
        "by_weight": {w["name"]: {
            "agrees": sum(r["agrees"] for r in rows if r["weight_index"] == j),
            "agrees_model_consistent_pairs": sum(r["agrees"] for r in rows
                                                 if r["weight_index"] == j and r["pair_id"] in consistent),
            "levels": counts([r["RiskLevel"] for r in rows if r["weight_index"] == j], LEVELS),
            "r14_disagrees": sum(r["r14_disagrees"] for r in rows if r["weight_index"] == j),
            "attenuation_cases": sum(r["attenuation_case"] for r in rows if r["weight_index"] == j),
        } for j, w in enumerate(weights)},
        "level_change_vs_baseline": changes,
        "branch_model_disagreement": {s: {
            "vision": sum(r["vision_model_disagrees"] for r in pair_level if r["stratum"] == s),
            "telemetry": sum(r["telemetry_model_disagrees"] for r in pair_level if r["stratum"] == s),
        } for s in strata},
        "model_consistent_pairs": len(consistent),
        "attenuation_examples_baseline": [
            {k: r[k] for k in ("pair_id", "stratum", "P_distraction", "P_telemetry", "RiskScore",
                               "RiskLevel", "DominantEvidence", "reference")}
            for r in pair_level if r["attenuation_case"]],
        "post_hoc_not_predeclared": {"threshold_ties": threshold_ties(rows, protocol)},
        "r14_examples": [
            {k: r[k] for k in ("pair_id", "w_v", "w_t", "P_distraction", "P_telemetry", "RiskScore",
                               "DominantEvidence")}
            for r in rows if r["r14_disagrees"]],
    }


def lag_ms(windows: list[dict], start_ms: int, levels: list[str]) -> int | None:
    for w in windows:
        if w["RiskLevel"] in levels:
            return w["meta"]["pos_ms"] - start_ms
    return None


def e5_summary(by_variant: dict[str, list[dict]], manifests: dict[str, dict]) -> dict:
    base = manifests["FUSED"]
    out = {"segments": []}
    for segment in base["segments"]:
        idx = segment["index"]
        entry = {"index": idx, "title": segment["title"], "start_ms": segment["start_ms"],
                 "duration_ms": segment["duration_ms"], "variants": {}}
        for variant, windows in by_variant.items():
            seg = [w for w in windows if w["meta"]["segment_index"] == idx]
            vseg = manifests[variant]["segments"][idx]
            ref_levels = seg[0]["meta"]["reference_levels"]
            severities = [w["AlertSeverity"] for w in seg if w["AlertSeverity"]]
            high_alert = next((w["meta"]["pos_ms"] - segment["start_ms"] for w in seg
                               if w["AlertSeverity"] == "HIGH_ALERT"), None)
            normal_again = next((w["meta"]["pos_ms"] - segment["start_ms"] for w in seg
                                 if w["AlertSeverity"] == "NORMAL"), None)
            entry["variants"][variant] = {
                "labels": {"vision_class": vseg["vision_class"], "telemetry_label": vseg["telemetry_label"]},
                "reference": seg[0]["meta"]["reference"],
                "windows": len(seg),
                "score": quantiles([w["RiskScore"] for w in seg]),
                "score_last": seg[-1]["RiskScore"],
                "levels": counts([w["RiskLevel"] for w in seg], LEVELS),
                "agrees": sum(w["RiskLevel"] in ref_levels for w in seg),
                "lag_ms_to_reference": lag_ms(seg, segment["start_ms"], ref_levels),
                "dominant": counts([w["DominantEvidence"] for w in seg], DOMINANTS),
                "alert_max": max(severities, key=SEVERITY_ORDER.get) if severities else None,
                "first_high_alert_ms": high_alert,
                "alert_first": seg[0]["AlertSeverity"], "alert_last": seg[-1]["AlertSeverity"],
                "first_normal_ms": normal_again,
                "P_distraction_mean": round(sum(w["P_distraction"] for w in seg) / len(seg), 4),
                "P_telemetry_mean": round(sum(w["P_telemetry_anomaly"] for w in seg) / len(seg), 4),
            }
        fused = [w for w in by_variant["FUSED"] if w["meta"]["segment_index"] == idx]
        for variant, name in (("VISION_HELD_SAFE", "from_vision"), ("TELEMETRY_HELD_SAFE", "from_telemetry")):
            other = [w for w in by_variant[variant] if w["meta"]["segment_index"] == idx]
            deltas = [round(a["RiskScore"] - b["RiskScore"], 1) for a, b in zip(fused, other)]
            entry[f"contribution_{name}"] = quantiles(deltas)
        out["segments"].append(entry)
    return out


# ---------------------------------------------------------------------------- outputs
def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _start(kind: str, out: Path | None, protocol_path: Path = PROTOCOL) -> tuple[datetime, dict, dict, Path, Path]:
    run_start = datetime.now(timezone.utc)
    protocol_path = Path(protocol_path)
    if not protocol_path.is_absolute():
        protocol_path = REPO / protocol_path
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    gate = protocol_gate(run_start, protocol_path)
    try:
        data_root, _ = resolve_data_root()
    except DataRootError as exc:
        data_root, gate["problems"] = None, gate["problems"] + [str(exc)]
    if data_root is None:
        gate["problems"].append("no data root with eda_outputs/processed was found")
    gate["status"] = "PASS" if not gate["problems"] else "BLOCKED"
    name = {"e2": "e2-weight-sensitivity", "e5": "e5-light-counterfactual"}[kind]
    out_dir = out or REPO / "docs" / "evidence" / run_start.astimezone().strftime("%Y-%m-%d") / name
    out_dir.mkdir(parents=True, exist_ok=True)
    return run_start, protocol, gate, out_dir, data_root


def _header(run_start: datetime, gate: dict, data_root: Path | None) -> dict:
    return {"run_start_utc": run_start.isoformat(), "protocol_gate": gate,
            "data_root": str(data_root) if data_root else None, "git": git_state()}


def run_e2(out: Path | None, protocol_path: Path = PROTOCOL) -> int:
    run_start, protocol, gate, out_dir, data_root = _start("e2", out, protocol_path)
    header = _header(run_start, gate, data_root)
    if gate["status"] != "PASS":
        dump(out_dir / "results.json", {**header, "status": "BLOCKED"})
        print("BLOCKED:", *gate["problems"], sep="\n  ", file=sys.stderr)
        return 2
    processed = data_root / "eda_outputs" / "processed"
    vision_csv = processed / "vision" / "vision_metadata_with_split.csv"
    telemetry_csv = processed / "telemetry" / "telemetry_test.csv"
    pairs = e2_pairs(read_vision_metadata(vision_csv), read_telemetry_rows(telemetry_csv),
                     protocol["e2"], protocol["operational_reference_policy"])
    for pair in pairs:
        pair["vision"]["sha256"] = sha256_file(pair["vision"]["image_path"])
    work_dir = Path(tempfile.mkdtemp(prefix="e2-fusion-eval-"))
    record, output = run_worker({"work_dir": str(work_dir), "sessions": e2_sessions(pairs, protocol),
                                 "vision_model_id": expected_vision_model(protocol),
                                 "vision_model_sha256": (protocol.get("fixed_runtime") or {}).get("vision_model_sha256")},
                                out_dir)
    status = output["status"]
    result = {**header, "inputs": {"vision_csv_sha256": sha256_file(vision_csv),
                                   "telemetry_csv_sha256": sha256_file(telemetry_csv)},
              "worker": record, "identity": output.get("identity"), "environment": output.get("environment"),
              "problems": output["problems"]}
    if status == "PASS":
        rows = e2_rows(pairs, output["sessions"], protocol)
        summary = e2_summary(rows, protocol)
        checks = summary["checks"]
        failed = [k for k in ("formula_error_within_half_step", "probabilities_identical_across_weights",
                              "all_fresh", "all_observations_new", "all_health_full") if not checks[k]]
        failed += [k for k in ("level_oracle_mismatches", "dominant_oracle_mismatches",
                               "rounded_mismatches_off_tie") if checks[k]]
        if checks["windows"] != len(pairs) * len(protocol["e2"]["weights"]):
            failed.append("window count")
        status = "PASS" if not failed else "FAIL"
        result.update(problems=result["problems"] + [f"check failed: {f}" for f in failed], summary=summary)
        dump(out_dir / "pairs.json", [p | {"vision": {k: v for k, v in p["vision"].items()
                                                      if k != "image_path"}} for p in pairs])
        write_csv(out_dir / "e2_rows.csv", rows, list(rows[0].keys()))
        from fusion_eval_figures import e2_figures
        result["figures"] = e2_figures(rows, protocol, out_dir)
    result["status"] = status
    result["output_written_utc"] = datetime.now(timezone.utc).isoformat()
    dump(out_dir / "results.json", result)
    print(f"E2 {status}: {out_dir}")
    return 0 if status == "PASS" else 1


def run_e5(out: Path | None, protocol_path: Path = PROTOCOL) -> int:
    run_start, protocol, gate, out_dir, data_root = _start("e5", out, protocol_path)
    header = _header(run_start, gate, data_root)
    if gate["status"] != "PASS":
        dump(out_dir / "results.json", {**header, "status": "BLOCKED"})
        print("BLOCKED:", *gate["problems"], sep="\n  ", file=sys.stderr)
        return 2
    e5 = protocol["e5_light"]
    policy = protocol["operational_reference_policy"]
    base_file = REPO / e5["base_scenario"].split(" ")[0]
    base = json.loads(base_file.read_text(encoding="utf-8"))
    work_dir = Path(tempfile.mkdtemp(prefix="e5-fusion-eval-"))
    scenarios = e5_variant_scenarios(base, e5["variants"])
    manifests, sessions = {}, []
    for variant, scenario in scenarios.items():
        scenario_file = base_file if variant == "FUSED" else work_dir / f"{scenario['scenario_id']}.json"
        if variant != "FUSED":
            scenario_file.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
        manifest_path = build_bundle(scenario, scenario_file=scenario_file,
                                     out_root=work_dir / "bundles", data_root=data_root)
        manifests[variant] = json.loads(manifest_path.read_text(encoding="utf-8"))
        steps = e5_steps(manifests[variant], manifest_path.parent / "frames",
                         e5["timeline"]["window_interval_ms"], policy, variant)
        sessions.append({"session_id": f"e5-{variant.lower().replace('_', '-')}",
                         "mode": "CONSTRUCTED_SCENARIO_RUNTIME",
                         "config": runtime_config(protocol, 0.5, 0.5),
                         "meta": {"variant": variant}, "steps": steps})
    identity_check = unchanged_segment_identity(manifests)
    record, output = run_worker({"work_dir": str(work_dir), "sessions": sessions,
                                 "vision_model_id": expected_vision_model(protocol),
                                 "vision_model_sha256": (protocol.get("fixed_runtime") or {}).get("vision_model_sha256")},
                                out_dir)
    status = output["status"]
    result = {**header, "scenarios": {v: {"scenario_id": m["scenario_id"],
                                          "scenario_sha256": m["scenario_sha256"],
                                          "segments": m["segments"]} for v, m in manifests.items()},
              "unchanged_segment_identity": identity_check, "worker": record,
              "identity": output.get("identity"), "environment": output.get("environment"),
              "problems": output["problems"]}
    if status == "PASS":
        by_variant = {s["meta"]["variant"]: s["windows"] for s in output["sessions"]}
        expected = manifests["FUSED"]["duration_ms"] // e5["timeline"]["window_interval_ms"]
        failed = [f"{v}: {len(w)} windows, expected {expected}" for v, w in by_variant.items()
                  if len(w) != expected]
        failed += [f"{v} segment {row['segment_index']}: unchanged labels but different inputs"
                   for v, segments in identity_check.items() for row in segments
                   if row["labels_unchanged"] and not (row["vision_identical"] and row["telemetry_identical"])]
        failed += [f"{v}: a window is not assessable" for v, w in by_variant.items()
                   if not all(x["assessment_available"] for x in w)]
        result["summary"] = e5_summary(by_variant, manifests)
        windows = [{"variant": v, **{k: x[k] for k in ("request_id", "RiskScore", "RiskLevel",
                                                        "DominantEvidence", "AlertSeverity", "SystemHealth",
                                                        "P_distraction", "P_telemetry_anomaly",
                                                        "P_distraction_raw", "P_telemetry_raw",
                                                        "vision_obs", "telemetry_obs",
                                                        "vision_freshness", "telemetry_freshness")},
                    **x["meta"], "reference_levels": "|".join(x["meta"]["reference_levels"])}
                   for v, w in by_variant.items() for x in w]
        write_csv(out_dir / "e5_windows.csv", windows, list(windows[0].keys()))
        from fusion_eval_figures import e5_figure
        result["figures"] = e5_figure(by_variant, manifests["FUSED"], protocol, out_dir)
        status = "PASS" if not failed else "FAIL"
        result["problems"] += failed
    result["status"] = status
    result["output_written_utc"] = datetime.now(timezone.utc).isoformat()
    dump(out_dir / "results.json", result)
    print(f"E5 {status}: {out_dir}")
    return 0 if status == "PASS" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("kind", nargs="?", choices=("e2", "e5"))
    parser.add_argument("--out", type=Path, default=None, help="evidence directory (default: dated)")
    parser.add_argument("--protocol", type=Path, default=PROTOCOL,
                        help="committed protocol JSON (default: docs/fyp2/e2e5/protocol.json)")
    parser.add_argument("--worker", nargs=2, metavar=("SPEC", "OUT"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        spec, out = map(Path, args.worker)
        out.write_text(json.dumps(execute(json.loads(spec.read_text()))))
        return 0
    if args.kind is None:
        parser.error("choose e2 or e5")
    return run_e2(args.out, args.protocol) if args.kind == "e2" else run_e5(args.out, args.protocol)


if __name__ == "__main__":
    sys.exit(main())
