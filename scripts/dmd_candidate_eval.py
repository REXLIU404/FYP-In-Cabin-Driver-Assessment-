#!/usr/bin/env python3
"""DMD candidate evidence, item A: State Farm test and DMD test, stable vs DMD candidate.

Bound by ``docs/fyp2/dmd-candidate/protocol.json`` (committed before this run). The runner
refuses to start unless that protocol is committed, unmodified and older than the run.

What it does
------------
1. Reads the frozen 3657-image State Farm test list saved by run p4b_20261022
   (``shared_inputs/vision_sources.json``) and checks the protocol's record, driver and
   class counts. It never re-splits the dataset.
2. Runs BOTH models through the backend provider path (one child process per model, the
   candidate selected by ``DRA_ACTIVE_VISION``): original JPEG bytes -> TrainedProvider
   preprocess -> ONNX -> one float32 softmax. Metrics use those provider probabilities.
3. Runs BOTH models on the DMD test split (1354 frames, gC_13/gE_29) through
   ``scripts/dmd_infer_test.py``, the same code used for the 2026-10-29 DMD evidence.
4. Reports accuracy, macro-F1, per-class P/R/F1, log loss, the 10x10 confusion matrix and
   the binary safe-vs-rest diagnostic. The 0.7038 DMD threshold is reported as a
   historical column only; the operative threshold is 0.5.
5. Cross-checks the recomputed numbers against p4b (stable, State Farm), the 2026-10-29
   zero-shot archive (stable, DMD) and the 2026-10-29 adapted archive (candidate, DMD).

DESCRIPTIVE ONLY. No model is selected, no threshold or weight is chosen, and no result
here is a claim about real-world accuracy or safety.

Usage:
    .venv/bin/python scripts/dmd_candidate_eval.py --out docs/evidence/<date>/dmd-candidate/a-source-domain
    # internal worker:
    .venv/bin/python scripts/dmd_candidate_eval.py --worker spec.json out.json

Exit codes: 0 valid run; 1 invalid run (worker/identity/metric failure); 2 BLOCKED
(protocol gate, missing/mismatched frozen input, missing model).
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO / "scripts"
BACKEND_DIR = REPO / "backend"
sys.path.insert(0, str(SCRIPTS_DIR))

PROTOCOL = REPO / "docs" / "fyp2" / "dmd-candidate" / "protocol.json"
DEFAULT_OUT = REPO / "docs" / "evidence" / datetime.now().strftime("%Y-%m-%d") / "dmd-candidate" / "a-source-domain"
DEFAULT_STATE_FARM_SOURCES = Path(
    "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/"
    "shared_inputs/vision_sources.json")
DEFAULT_DMD_MANIFEST = Path("/Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/sampling_manifest.csv")
DEFAULT_DMD_FRAMES = DEFAULT_DMD_MANIFEST.parent / "frames"

STABLE_MODEL_ID = "stable_mobilenet_v3_large"
DMD_MODEL_ID = "dmd_adapted_mobilenet_v3_20261029"
STABLE_ONNX = REPO / "ml" / "outputs" / "vision" / "mobilenetv3_large_vision.onnx"
STABLE_SHA256 = "b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf"
DMD_ONNX = REPO / "ml" / "outputs" / "candidates" / DMD_MODEL_ID / "model.onnx"
DMD_SHA256 = "01f1d6a3a57936590d29f1a86856fd6e67c8c9fd382f48bd601f9c66ed2b4d55"

P4B_METRICS = REPO / "ml" / "outputs" / "runs" / "p4b_20261022" / "evaluation_metrics.json"
ARCHIVE_ZERO_SHOT = REPO / "docs" / "evidence" / "2026-10-29" / "dmd-adaptation" / "zero_shot_unexposed.json"
ARCHIVE_COMPARISON = REPO / "docs" / "evidence" / "2026-10-29" / "dmd-adaptation" / "comparison_test.json"
WORKER_TIMEOUT_S = 7200


# --------------------------------------------------------------------------- utilities
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def environment_versions() -> dict:
    versions = {"python": platform.python_version(), "platform": platform.platform()}
    for name in ("numpy", "onnxruntime", "PIL", "sklearn"):
        try:
            module = __import__(name)
        except Exception as exc:  # pragma: no cover - environment dependent
            versions[name] = f"unavailable ({type(exc).__name__}: {exc})"
        else:
            versions[name] = getattr(module, "__version__", "unknown")
    return versions


def git_state() -> dict:
    def run(*args):
        done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30)
        return done.stdout.strip() if done.returncode == 0 else None
    return {"commit": run("rev-parse", "HEAD"), "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(run("status", "--porcelain"))}


# ----------------------------------------------------------------------- protocol gate
def gate_verdict(*, dirty: bool, commit: str | None, commit_time: str | None,
                 blob_matches: bool, run_start: datetime) -> list[str]:
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


def _git(*args: str) -> str | None:
    done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30)
    return done.stdout.strip() if done.returncode == 0 else None


def protocol_gate(run_start: datetime, path: Path = PROTOCOL) -> dict:
    rel = str(path.relative_to(REPO))
    log = _git("log", "-1", "--format=%H %cI", "--", rel)
    commit, commit_time = (log.split(" ", 1) if log else (None, None))
    committed_blob = _git("rev-parse", f"HEAD:{rel}")
    working_blob = _git("hash-object", rel)
    dirty = bool(_git("status", "--porcelain", "--", rel))
    problems = gate_verdict(dirty=dirty, commit=commit, commit_time=commit_time,
                            blob_matches=committed_blob is not None and committed_blob == working_blob,
                            run_start=run_start)
    return {"path": rel, "sha256": sha256_file(path), "commit": commit, "commit_time": commit_time,
            "blob": committed_blob, "dirty": dirty,
            "status": "PASS" if not problems else "BLOCKED", "problems": problems}


# --------------------------------------------------------------- frozen input lists
def load_state_farm_sources(path: Path) -> list[dict]:
    """The frozen p4b input list. Raises ValueError on shape, split, duplicate or missing file."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, list) or not document:
        raise ValueError(f"{path}: expected a non-empty JSON list")
    rows, seen = [], set()
    for index, row in enumerate(document):
        for key in ("source_id", "class_id", "split", "image_path", "filename", "source_sha256"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError(f"{path}: record {index} lacks {key!r}")
        if row["split"] != "test":
            raise ValueError(f"{path}: record {row['source_id']} has split {row['split']!r}, expected 'test'")
        if row["source_id"] in seen:
            raise ValueError(f"{path}: duplicate source_id {row['source_id']!r}")
        if not Path(row["image_path"]).is_file():
            raise ValueError(f"{path}: missing image {row['image_path']}")
        seen.add(row["source_id"])
        rows.append(row)
    return rows


def verify_image_hashes(rows: list[dict]) -> list[dict]:
    """Every image must still hash to the frozen source_sha256. No image is skipped."""
    problems = []
    for row in rows:
        path = Path(row["image_path"])
        if not path.is_file():
            problems.append({"source_id": row["source_id"], "path": str(path), "problem": "missing"})
        elif sha256_file(path) != row["source_sha256"]:
            problems.append({"source_id": row["source_id"], "path": str(path), "problem": "sha256 mismatch"})
    return problems


def state_farm_problems(rows: list[dict], expected: dict) -> list[str]:
    problems = []
    if len(rows) != expected["expected_records"]:
        problems.append(f"State Farm: {len(rows)} records, expected {expected['expected_records']}")
    drivers = sorted({r.get("driver_id") for r in rows if r.get("driver_id")})
    if drivers != sorted(expected["expected_drivers"]):
        problems.append(f"State Farm drivers {drivers} != {sorted(expected['expected_drivers'])}")
    counts = {f"c{i}": sum(1 for r in rows if r["class_id"] == f"c{i}") for i in range(10)}
    if counts != expected["expected_class_counts"]:
        problems.append(f"State Farm class counts {counts} != {expected['expected_class_counts']}")
    if any(r["split"] != "test" for r in rows):
        problems.append("State Farm input contains a non-test split")
    return problems


def load_dmd_test_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if r.get("split") == "test"]
    for row in rows:
        for key in ("subject", "class_id", "file"):
            if not row.get(key):
                raise ValueError(f"{path}: a test row lacks {key!r}")
    return rows


def dmd_problems(rows: list[dict], expected: dict) -> list[str]:
    problems = []
    if len(rows) != expected["expected_records"]:
        problems.append(f"DMD: {len(rows)} test rows, expected {expected['expected_records']}")
    subjects = sorted({r["subject"] for r in rows})
    if subjects != sorted(expected["expected_subjects"]):
        problems.append(f"DMD subjects {subjects} != {sorted(expected['expected_subjects'])}")
    counts = {f"c{i}": sum(1 for r in rows if r["class_id"] == f"c{i}") for i in range(10)}
    if counts != expected["expected_class_counts"]:
        problems.append(f"DMD class counts {counts} != {expected['expected_class_counts']}")
    bad = sorted({r["class_id"] for r in rows if r["class_id"] not in counts})
    if bad:
        problems.append(f"DMD class ids outside c0..c9: {bad}")
    return problems


# ------------------------------------------------------------------------------ metrics
def softmax64(logits) -> list[float]:
    values = [float(x) for x in logits]
    peak = max(values)
    shifted = [math.exp(x - peak) for x in values]
    total = sum(shifted)
    return [x / total for x in shifted]


def binary_diagnostic(labels: list[int], probs: list[list[float]], threshold: float) -> dict:
    """P_distraction = 1 - P(c0) at one threshold; counts are over true safe vs non-safe."""
    tp = fp = fn = tn = 0
    for label, row in zip(labels, probs):
        decision = (1.0 - row[0]) >= threshold
        truth = label != 0
        tp += decision and truth
        fp += decision and not truth
        fn += (not decision) and truth
        tn += (not decision) and not truth
    positives = tp + fp
    c0 = fp + tn
    non_c0 = tp + fn
    return {
        "threshold": threshold,
        "counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "c0_support": c0,
        "non_c0_support": non_c0,
        "c0_false_positive_proxy": (fp / c0) if c0 else None,
        "distraction_recall": (tp / non_c0) if non_c0 else None,
        "precision": (tp / positives) if positives else 0.0,
        "binary_accuracy": (tp + tn) / len(labels) if labels else None,
    }


def summarise(labels: list[int], probs: list[list[float]], thresholds: dict[str, float]) -> dict:
    """10-class metrics plus the safe-vs-rest diagnostic at every declared threshold."""
    from sklearn.metrics import log_loss as sklearn_log_loss

    from dmd_evaluate import multiclass_metrics

    multiclass = multiclass_metrics(labels, probs, num_classes=10)
    multiclass["log_loss"] = float(sklearn_log_loss(labels, probs, labels=list(range(10))))
    multiclass["n"] = len(labels)
    return {"multiclass": multiclass,
            "binary": {name: binary_diagnostic(labels, probs, threshold)
                       for name, threshold in thresholds.items()}}


def binary_full(labels: list[int], probs: list[list[float]], threshold: float) -> dict:
    """The DMD archive's binary view (rocAUC/prAUC/Brier/ECE) plus the count fields."""
    from dmd_evaluate import binary_metrics

    distraction = [1.0 - row[0] for row in probs]
    y = [0 if label == 0 else 1 for label in labels]
    result = binary_metrics(y, distraction, threshold)
    result.update(binary_diagnostic(labels, probs, threshold))
    return result


def cross_check(actual: dict, expected: dict, tolerance: float = 1e-9) -> list[dict]:
    """Field-by-field comparison; a difference beyond ``tolerance`` is returned, not hidden."""
    mismatches = []
    for metric, expected_value in expected.items():
        if metric not in actual:
            mismatches.append({"metric": metric, "actual": None, "expected": expected_value,
                               "delta": None, "reason": "missing"})
            continue
        delta = abs(float(actual[metric]) - float(expected_value))
        if delta > tolerance:
            mismatches.append({"metric": metric, "actual": actual[metric],
                               "expected": expected_value, "delta": delta})
    return mismatches


def archive_zero_shot_metrics(archive: dict) -> dict:
    """The 2026-10-29 zero-shot archive stores probabilities/labels, not a metrics summary."""
    from dmd_evaluate import multiclass_metrics

    metrics = multiclass_metrics(archive["labels"], archive["probabilities"])
    return {"accuracy": metrics["accuracy"], "macro_f1": metrics["macro_f1"]}


# ----------------------------------------------------------------------- worker (provider)
def _state_farm_spec(model_id: str, rows: list[dict]) -> dict:
    return {"model_id": model_id,
            "sources": [{"source_id": r["source_id"], "class_id": r["class_id"],
                         "image_path": r["image_path"], "source_sha256": r["source_sha256"]}
                        for r in rows]}


def run_state_farm_worker(model_id: str, rows: list[dict], out_dir: Path) -> tuple[dict, dict | None]:
    spec_path = out_dir / f"worker_spec_state_farm_{model_id}.json"
    out_path = out_dir / f"raw_state_farm_{model_id}.json"
    spec_path.write_text(json.dumps(_state_farm_spec(model_id, rows), indent=2))
    env = {k: v for k, v in os.environ.items() if not k.startswith("DRA_")}
    env.update(PYTHONPATH=str(BACKEND_DIR), PYTHONDONTWRITEBYTECODE="1")
    if model_id != STABLE_MODEL_ID:
        env["DRA_ACTIVE_VISION"] = model_id
    command = [sys.executable, str(Path(__file__).resolve()),
               "--worker", str(spec_path), str(out_path)]
    began = time.time()
    done = subprocess.run(command, cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
                          timeout=WORKER_TIMEOUT_S)
    record = {"command": [Path(command[0]).name, *[Path(c).name if i == 1 else c
                                                    for i, c in enumerate(command[1:], 1)]],
              "exit_code": done.returncode, "duration_s": round(time.time() - began, 1),
              "stderr_tail": done.stderr.strip().splitlines()[-20:]}
    output = None
    if out_path.is_file():
        try:
            output = json.loads(out_path.read_text())
        except ValueError:
            record["stderr_tail"].append(f"{out_path} is not valid JSON")
    return record, output


def run_worker(spec_path: Path, out_path: Path) -> int:
    """Child process: build the real TrainedProvider, check its identity, forward every image."""
    spec = json.loads(spec_path.read_text())
    model_id = spec["model_id"]
    result = {"model_id": model_id, "started": datetime.now(timezone.utc).isoformat(),
              "environment": environment_versions()}
    try:
        from app.providers.trained import TrainedProvider

        provider = TrainedProvider()
        vision = provider.info.get("vision", {})
        result["provider"] = {"name": provider.info.get("provider"), "vision": vision}
        if vision.get("model_id") != model_id:
            result["error"] = (f"provider loaded {vision.get('model_id')!r}, expected {model_id!r}: "
                               "DRA_ACTIVE_VISION did not take effect")
        elif vision.get("sha256") not in (STABLE_SHA256, DMD_SHA256):
            result["error"] = f"provider reported unexpected sha256 {vision.get('sha256')!r}"
        if "error" in result:
            out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
            return 1
        samples, rejected = [], []
        for item in spec["sources"]:
            try:
                raw = Path(item["image_path"]).read_bytes()
                if sha256_bytes(raw) != item["source_sha256"]:
                    raise ValueError("image bytes do not match the frozen source_sha256")
                tensor = provider.preprocess(base64.b64encode(raw).decode("ascii"))
                logits = provider.vision.run(None, {provider.input_name: tensor})[0][0]
                logits = [float(x) for x in logits]
                provider_probs = softmax64(logits)
                samples.append({"source_id": item["source_id"], "class_id": item["class_id"],
                                "argmax": max(range(10), key=lambda i: provider_probs[i]),
                                "provider_probs": provider_probs,
                                "float64_probs": softmax64(logits),
                                "logits": logits})
            except Exception as exc:
                rejected.append({"source_id": item["source_id"], "path": item["image_path"],
                                 "error": f"{type(exc).__name__}: {exc}"})
        result.update(samples=samples, rejected=rejected,
                      finished=datetime.now(timezone.utc).isoformat())
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
        return 0 if not rejected else 1
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
        result["finished"] = datetime.now(timezone.utc).isoformat()
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
        return 1


# --------------------------------------------------------------------------- DMD inference
def run_dmd_model(model_id: str, onnx_path: Path, rows: list[dict], frames_root: Path) -> dict:
    from dmd_infer_test import infer, softmax

    files = [r["file"] for r in rows]
    logits = infer(onnx_path, frames_root, files)
    probs = [softmax(row) for row in logits]
    return {"model_id": model_id, "onnx_path": str(onnx_path), "onnx_sha256": sha256_file(onnx_path),
            "files": files, "labels": [int(r["class_id"][1:]) for r in rows],
            "logits": logits, "probabilities": probs,
            "distraction": [1.0 - p[0] for p in probs]}


# ------------------------------------------------------------------------------ writer
def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def per_class_rows(model: str, summary: dict) -> list[dict]:
    return [{"model": model, **{"class": c}, **summary["multiclass"]["per_class"][c]}
            for c in [f"c{i}" for i in range(10)]]


def write_confusion(path: Path, matrix: list[list[int]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["true\\pred", *[f"c{i}" for i in range(10)]])
        for i, row in enumerate(matrix):
            writer.writerow([f"c{i}", *row])


# --------------------------------------------------------------------------------- main
def _load_inputs(args, protocol: dict) -> tuple[list[dict], list[dict], list[str]]:
    problems = []
    a = protocol["a_source_domain"]
    sources = load_state_farm_sources(Path(args.state_farm_sources))
    problems += state_farm_problems(sources, a["state_farm_test"])
    dmd_rows = load_dmd_test_rows(Path(args.dmd_manifest))
    problems += dmd_problems(dmd_rows, a["dmd_body_test"])
    return sources, dmd_rows, problems


def _check_models() -> tuple[dict, list[str]]:
    problems = []
    identities = {}
    for model_id, path, expected in ((STABLE_MODEL_ID, STABLE_ONNX, STABLE_SHA256),
                                     (DMD_MODEL_ID, DMD_ONNX, DMD_SHA256)):
        if not path.is_file():
            problems.append(f"model file missing: {path}")
            continue
        actual = sha256_file(path)
        identities[model_id] = {"onnx_path": str(path), "sha256": actual, "expected_sha256": expected}
        if actual != expected:
            problems.append(f"{model_id}: sha256 {actual} != declared {expected}")
    return identities, problems


def run(args) -> int:
    run_start = datetime.now(timezone.utc)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    gate = protocol_gate(run_start)
    header = {"run_start_utc": run_start.isoformat(), "protocol_gate": gate,
              "script_sha256": sha256_file(Path(__file__)),
              "git": git_state(), "environment": environment_versions()}
    if gate["status"] != "PASS":
        dump(out_dir / "results.json", {**header, "status": "BLOCKED", "problems": gate["problems"]})
        print("BLOCKED:", *gate["problems"], sep="\n  ", file=sys.stderr)
        return 2

    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    model_identities, model_problems = _check_models()
    if model_problems:
        dump(out_dir / "results.json", {**header, "status": "BLOCKED", "problems": model_problems})
        print("BLOCKED:", *model_problems, sep="\n  ", file=sys.stderr)
        return 2
    sources, dmd_rows, input_problems = _load_inputs(args, protocol)
    if input_problems:
        dump(out_dir / "results.json", {**header, "status": "BLOCKED", "problems": input_problems})
        print("BLOCKED:", *input_problems, sep="\n  ", file=sys.stderr)
        return 2
    hash_problems = verify_image_hashes(sources)
    if hash_problems:
        dump(out_dir / "results.json", {**header, "status": "BLOCKED", "problems": hash_problems})
        print("BLOCKED: frozen State Farm images changed", file=sys.stderr)
        return 2

    dmd_frames = Path(args.dmd_frames)
    missing_frames = [r["file"] for r in dmd_rows if not (dmd_frames / r["file"]).is_file()]
    if missing_frames:
        dump(out_dir / "results.json", {**header, "status": "BLOCKED",
                                        "problems": {"missing_dmd_frames": missing_frames[:20],
                                                     "count": len(missing_frames)}})
        print(f"BLOCKED: {len(missing_frames)} DMD frames missing under {dmd_frames}", file=sys.stderr)
        return 2

    thresholds = {"0.5": 0.5,
                  str(protocol["a_source_domain"]["dmd_body_test"]["non_operative_threshold"]):
                      protocol["a_source_domain"]["dmd_body_test"]["non_operative_threshold"]}

    state_farm_dir, dmd_dir = out_dir / "state_farm", out_dir / "dmd_test"
    state_farm_dir.mkdir(exist_ok=True)
    dmd_dir.mkdir(exist_ok=True)

    problems, warnings = [], []
    state_farm = {"workers": {}, "metrics": {}, "cross_checks": {}}
    state_farm["input"] = {
        "path": str(Path(args.state_farm_sources)), "sha256": sha256_file(args.state_farm_sources),
        "records": len(sources), "drivers": sorted({r["driver_id"] for r in sources}),
        "class_counts": {f"c{i}": sum(1 for r in sources if r["class_id"] == f"c{i}") for i in range(10)},
    }
    raw = {}
    for model_id in (STABLE_MODEL_ID, DMD_MODEL_ID):
        record, output = run_state_farm_worker(model_id, sources, out_dir)
        state_farm["workers"][model_id] = record
        if output is None or output.get("error") or output.get("rejected"):
            problems.append(f"State Farm worker failed for {model_id}: "
                            f"{(output or {}).get('error') or 'see worker record'}")
            continue
        raw[model_id] = output
        dump(state_farm_dir / f"predictions_{model_id}.json", {
            "model_id": model_id, "onnx_sha256": model_identities[model_id]["sha256"],
            "provider": output.get("provider"),
            "samples": [{"source_id": s["source_id"], "class_id": s["class_id"],
                         "argmax": s["argmax"], "provider_probs": s["provider_probs"],
                         "float64_probs": s["float64_probs"], "logits": s["logits"]}
                        for s in output["samples"]]})
        labels = [int(s["class_id"][1:]) for s in output["samples"]]
        provider_probs = [s["provider_probs"] for s in output["samples"]]
        float64_probs = [s["float64_probs"] for s in output["samples"]]
        state_farm["metrics"][model_id] = {"provider_path": summarise(labels, provider_probs, {"0.5": 0.5}),
                                           "float64_softmax": summarise(labels, float64_probs, {"0.5": 0.5})}

    if STABLE_MODEL_ID in state_farm["metrics"]:
        p4b = json.loads(P4B_METRICS.read_text())["models"]["MN-STABLE"]["clean"]
        expected = {"accuracy": p4b["accuracy"], "macro_f1": p4b["macro_f1"], "log_loss": p4b["log_loss"]}
        recomputed = state_farm["metrics"][STABLE_MODEL_ID]["float64_softmax"]["multiclass"]
        mismatches = cross_check(recomputed, expected)
        confusion_match = state_farm["metrics"][STABLE_MODEL_ID]["float64_softmax"]["multiclass"]["confusion_matrix"] == p4b["confusion"]
        state_farm["cross_checks"]["p4b"] = {"expected": expected, "mismatches": mismatches,
                                            "confusion_matrix_match": confusion_match,
                                            "ok": not mismatches and confusion_match}

    per_class, binary_rows = [], []
    for model_id, metrics in state_farm["metrics"].items():
        per_class += per_class_rows(model_id, metrics["provider_path"])
        summary = metrics["provider_path"]
        write_confusion(state_farm_dir / f"confusion_{model_id}.csv",
                        summary["multiclass"]["confusion_matrix"])
        binary_rows.append({"dataset": "state_farm_test", "model": model_id,
                            **summary["binary"]["0.5"]})
    write_csv(state_farm_dir / "per_class.csv", per_class,
              ["model", "class", "precision", "recall", "f1", "support"])
    write_csv(state_farm_dir / "binary_diagnostics.csv", binary_rows,
              ["dataset", "model", "threshold", "c0_support", "non_c0_support",
               "c0_false_positive_proxy", "distraction_recall", "precision", "binary_accuracy",
               "counts"])
    if not state_farm["cross_checks"].get("p4b", {}).get("ok", False):
        warnings.append("State Farm stable recomputation does not match p4b exactly; see cross_checks.p4b")

    # ------------------------------------------------------------------ DMD test split
    dmd = {"input": {"manifest": str(Path(args.dmd_manifest)),
                     "manifest_sha256": sha256_file(args.dmd_manifest),
                     "frames_root": str(dmd_frames), "records": len(dmd_rows),
                     "subjects": sorted({r["subject"] for r in dmd_rows}),
                     "class_counts": {f"c{i}": sum(1 for r in dmd_rows if r["class_id"] == f"c{i}")
                                      for i in range(10)}},
           "metrics": {}, "cross_checks": {}}
    labels = [int(r["class_id"][1:]) for r in dmd_rows]
    dmd_raw = {}
    for model_id, onnx_path in ((STABLE_MODEL_ID, STABLE_ONNX), (DMD_MODEL_ID, DMD_ONNX)):
        try:
            result = run_dmd_model(model_id, onnx_path, dmd_rows, dmd_frames)
        except Exception as exc:
            problems.append(f"DMD inference failed for {model_id}: {type(exc).__name__}: {exc}")
            continue
        dmd_raw[model_id] = result
        dump(dmd_dir / f"predictions_{model_id}.json", result)
        summary = summarise(labels, result["probabilities"], thresholds)
        summary["binary_full"] = {name: binary_full(labels, result["probabilities"], threshold)
                                  for name, threshold in thresholds.items()}
        dmd["metrics"][model_id] = summary

    if STABLE_MODEL_ID in dmd_raw:
        archive = json.loads(ARCHIVE_ZERO_SHOT.read_text())
        archived_metrics = archive_zero_shot_metrics(archive)
        expected = {"accuracy": archived_metrics["accuracy"], "macro_f1": archived_metrics["macro_f1"]}
        recomputed = dmd["metrics"][STABLE_MODEL_ID]["multiclass"]
        mismatches = cross_check(recomputed, expected, tolerance=5e-5)
        max_prob_delta = max(abs(a - b) for row_a, row_b in
                             zip(dmd_raw[STABLE_MODEL_ID]["probabilities"], archive["probabilities"])
                             for a, b in zip(row_a, row_b))
        identity_match = (dmd_raw[STABLE_MODEL_ID]["files"] == archive["files"]
                          and dmd_raw[STABLE_MODEL_ID]["labels"] == archive["labels"])
        if not identity_match:
            mismatches.append({"metric": "file_or_label_identity", "actual": "differs",
                               "expected": "the archived files/labels", "delta": None})
        dmd["cross_checks"]["zero_shot_archive"] = {
            "expected": expected, "mismatches": mismatches, "max_abs_probability_delta": max_prob_delta,
            "file_and_label_identity_match": identity_match,
            "ok": not mismatches and max_prob_delta <= 1e-9}
        if not dmd["cross_checks"]["zero_shot_archive"]["ok"]:
            warnings.append("DMD stable zero-shot recomputation does not match the 2026-10-29 archive exactly")

    if DMD_MODEL_ID in dmd_raw:
        archive = json.loads(ARCHIVE_COMPARISON.read_text())
        expected = {"accuracy": archive["multiclass"]["adapted"]["acc"],
                    "macro_f1": archive["multiclass"]["adapted"]["macro_f1"]}
        recomputed = dmd["metrics"][DMD_MODEL_ID]["multiclass"]
        mismatches = cross_check(recomputed, expected, tolerance=5e-5)
        per_class_deltas = {}
        for c, archived in archive["adapted_per_class"].items():
            ours = recomputed["per_class"][c]
            deltas = {k: abs(ours[k] - archived[k]) for k in ("precision", "recall", "f1")}
            if max(deltas.values()) > 1e-4:
                per_class_deltas[c] = deltas
        binary_05 = dmd["metrics"][DMD_MODEL_ID]["binary_full"]["0.5"]
        archived_binary = archive["binary"]["adapted@0.5"]
        binary_deltas = {k: abs(binary_05[k] - archived_binary[k])
                         for k in ("recall", "fpr", "precision", "balanced_accuracy", "roc_auc", "pr_auc",
                                   "brier", "ece")}
        dmd["cross_checks"]["adapted_archive"] = {
            "expected": expected, "mismatches": mismatches,
            "per_class_deltas_beyond_1e_4": per_class_deltas,
            "binary_0_5_deltas": binary_deltas,
            "ok": not mismatches and not per_class_deltas and max(binary_deltas.values()) <= 1e-4}
        if not dmd["cross_checks"]["adapted_archive"]["ok"]:
            warnings.append("DMD candidate recomputation does not match the 2026-10-29 adapted archive exactly")

    per_class, binary_rows = [], []
    for model_id, summary in dmd["metrics"].items():
        per_class += per_class_rows(model_id, summary)
        write_confusion(dmd_dir / f"confusion_{model_id}.csv", summary["multiclass"]["confusion_matrix"])
        for name, metrics in summary["binary_full"].items():
            binary_rows.append({"dataset": "dmd_body_test", "model": model_id,
                                "operative": name == "0.5", **metrics})
    write_csv(dmd_dir / "per_class.csv", per_class,
              ["model", "class", "precision", "recall", "f1", "support"])
    write_csv(dmd_dir / "binary_diagnostics.csv", binary_rows,
              ["dataset", "model", "operative", "threshold", "recall", "fpr", "precision",
               "balanced_accuracy", "roc_auc", "pr_auc", "brier", "ece", "c0_support",
               "non_c0_support", "c0_false_positive_proxy", "distraction_recall",
               "binary_accuracy", "counts"])

    c_models = [m for m in (STABLE_MODEL_ID, DMD_MODEL_ID) if m in state_farm["metrics"] and m in dmd["metrics"]]
    if len(c_models) != 2:
        problems.append("one or both models are missing a dataset result")

    status = "PASS" if not problems and not warnings else ("PASS_WITH_WARNINGS" if not problems else "FAIL")
    result = {**header, "status": status, "problems": problems, "warnings": warnings,
              "models": model_identities,
              "state_farm": state_farm, "dmd_test": dmd}
    dump(out_dir / "results.json", result)
    print(f"A {status}: {out_dir}")
    if warnings:
        print("WARNINGS:", *warnings, sep="\n  ", file=sys.stderr)
    return 0 if status != "FAIL" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--state-farm-sources", type=Path, default=DEFAULT_STATE_FARM_SOURCES)
    parser.add_argument("--dmd-manifest", type=Path, default=DEFAULT_DMD_MANIFEST)
    parser.add_argument("--dmd-frames", type=Path, default=DEFAULT_DMD_FRAMES)
    parser.add_argument("--worker", nargs=2, metavar=("SPEC", "OUT"), default=None,
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return run_worker(Path(args.worker[0]), Path(args.worker[1]))
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
