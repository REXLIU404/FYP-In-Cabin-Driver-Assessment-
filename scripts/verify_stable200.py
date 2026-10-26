#!/usr/bin/env python3
"""Task 1.4 (DS-1): stable200 provider verification runner.

Re-computes the frozen stable200 membership hashes, drives fresh provider forwards for the
three Task 10A vision models (one child process per model), and compares them against the
references of the APPROVED tolerance declaration.

Approved tolerance (recorded per FUD-01 in docs/fyp2/task10a/approval_record.json, user
approval "都批准", tolerance `effective=true`): every reference set of every model must
satisfy BOTH ``max_abs_prob_delta <= 1e-4`` and ``argmax_agreement == 1.0``. The stable200
per-class mode rule is judged separately: for every class c_i the set of tied argmax modes
over its 20 images must be exactly [i]; a tied mode fails. A failed check is reported as
``pass: false`` with the worst sample's source_id, per-class deltas and top1-top2 margins -
the tolerance is never silently relaxed (docs/fyp2/task10a/tolerance_predeclaration.md,
sections 2-5).

References (paths, structure and expected SHA256 all from that document):

* ``stable_mobilenet_v3_large`` (env unset -> stable provider path): 100 P4A sources vs
  ``<p4a-root>/parity_MN-STABLE.json`` ``result.validation_predictions`` ORT logits
  (one float64 stable softmax of the cached logits = the reference probabilities); the
  200-image stable200 numeric comparison is ``null`` with reason ``NO_STABLE200_REFERENCE``;
  the per-class mode rule still runs on all 200 images.
* ``resnet18_search004_seed42`` / ``mobilenet_v3_large_search006_seed42`` (env
  DRA_ACTIVE_VISION=<model_id>): 200 images vs the package's
  ``validation/stable200_saved_predictions.csv`` ``probability_c*`` columns (PyTorch
  outputs, read directly, never re-softmaxed) plus 100 sources vs
  ``parity_RN-HPO42.json`` / ``parity_MN-HPO42.json``, and the same per-class mode rule.

Pairing is always by source_id, never by row number. The frozen membership hash is
``sha256("\\n".join(sorted(filename)).encode("utf-8"))`` (no trailing newline), the algorithm
re-computed on 2026-10-26 in docs/fyp2/task10a/preflight_report.md.

Each model runs in its own child process (cwd=backend, PYTHONPATH=backend) that builds the
real ``TrainedProvider`` and, per image, base64-encodes the ORIGINAL JPEG bytes (no
re-encode) -> ``preprocess`` -> ``vision.run`` -> one float32 softmax, exactly the
provider's inference arithmetic. Inputs rejected by preprocess are recorded, never skipped.

Exit codes: 0 every check passed; 1 at least one model failed; 2 usage error, membership
hash mismatch, or a BLOCKED pre-run state (a required image or reference is missing, or a
reference's SHA256 differs from the approved value - the exact path is written out).

Usage:
    python3 scripts/verify_stable200.py --out docs/evidence/<date>/stable200
    # internal worker mode (the parent spawns one child per model):
    python3 scripts/verify_stable200.py --worker spec.json out.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- frozen facts
REPO = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO / "scripts"
BACKEND_DIR = REPO / "backend"
CANDIDATES_ROOT = REPO / "ml" / "outputs" / "candidates"
TOLERANCE_DOC = "docs/fyp2/task10a/tolerance_predeclaration.md"
APPROVAL_RECORD = "docs/fyp2/task10a/approval_record.json"

DEFAULT_DATA_ROOT = Path(
    "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/state-farm-distracted-driver-detection/imgs/train")
DEFAULT_P4A_ROOT = Path("/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021")

# Frozen in docs/fyp2/task10a/preflight_report.md (re-computed there on 2026-10-26).
EXPECTED_MEMBERSHIP_SHA256 = "601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9"
EXPECTED_SOURCE_IDS_SHA256 = "2697d288e384f340cb51f002ce39fca024827c6969de9dc9f2db9682246c5d75"

# FUD-01 / APPROVED: both conditions must hold per reference set (tolerance doc section 3).
PROB_DELTA_TOLERANCE = 1e-4
ARGMAX_AGREEMENT_TOLERANCE = 1.0
NO_STABLE200_REFERENCE = "NO_STABLE200_REFERENCE"

STABLE_MODEL_ID = "stable_mobilenet_v3_large"
RN_MODEL_ID = "resnet18_search004_seed42"
MN_CANDIDATE_MODEL_ID = "mobilenet_v3_large_search006_seed42"

# Model id -> (active_vision env value or None for the stable path, parity file name,
# expected parity sha256, expected ONNX sha256). CSV expectations per the tolerance doc.
MODEL_SPECS = [
    {"model_id": STABLE_MODEL_ID, "active_vision": None,
     "parity_file": "parity_MN-STABLE.json",
     "parity_sha256": "bcecf7d0afcafa48213c0a4f9b85eb6f56ea05e5f463e24881cdf914888af0f8",
     "onnx_sha256": "b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf",
     "csv_sha256": None},
    {"model_id": RN_MODEL_ID, "active_vision": RN_MODEL_ID,
     "parity_file": "parity_RN-HPO42.json",
     "parity_sha256": "3885dbf8b87120382f0663f1aaad84d715f2c59cbb49f63006740e002c8c8cf9",
     "onnx_sha256": "5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3",
     "csv_sha256": "c7d233c813a01d54ff286a836e5c6cab069558b52a9ee547953052fc92a0787d"},
    {"model_id": MN_CANDIDATE_MODEL_ID, "active_vision": MN_CANDIDATE_MODEL_ID,
     "parity_file": "parity_MN-HPO42.json",
     "parity_sha256": "a8544656b264a5e0698418999c05bf2fe8e869af1b03e24041d2bbf6548fd73b",
     "onnx_sha256": "9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828",
     "csv_sha256": "47fd6f678247c81f6b0384a6453c7467c5b3dd39208647a9847f33807dba74b6"},
]
WORKER_TIMEOUT_S = 3600


# --------------------------------------------------------------------------- pure functions
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def membership_sha256(rows) -> str:
    """The frozen rule: sha256 of the sorted filenames joined by "\\n", no trailing newline."""
    return sha256_bytes("\n".join(sorted(r["filename"] for r in rows)).encode("utf-8"))


def source_ids_sha256(rows) -> str:
    return sha256_bytes("\n".join(sorted(r["source_id"] for r in rows)).encode("utf-8"))


def stable_softmax64(logits) -> list[float]:
    """One numerically stable float64 softmax (the reference transform for cached ORT logits)."""
    values = [float(x) for x in logits]
    peak = max(values)
    shifted = [math.exp(x - peak) for x in values]
    total = sum(shifted)
    return [x / total for x in shifted]


def argmax(values) -> int:
    """The lowest index on a tie (the frozen tie rule of the tolerance document)."""
    best = max(values)
    return next(i for i, v in enumerate(values) if v == best)


def top1_top2_margin(probs) -> float:
    top = argmax(probs)
    return probs[top] - max(p for i, p in enumerate(probs) if i != top)


def validate_probs(probs) -> list[str]:
    """Sanity of one 10-class probability vector (tolerance doc section 3: finite, [0,1],
    plausible sum, c0..c9 order). Returns the list of problems (empty = fine)."""
    problems = []
    if len(probs) != 10:
        problems.append(f"expected 10 classes, got {len(probs)}")
    if not all(math.isfinite(p) for p in probs):
        problems.append("non-finite probability")
    if any(p < 0 or p > 1 for p in probs):
        problems.append("probability outside [0,1]")
    total = sum(probs)
    if not 0.999 <= total <= 1.001:
        problems.append(f"sum {total} outside [0.999, 1.001]")
    return problems


def pair_by_source_id(fresh, reference):
    """Match by source_id, never by row order. Returns ``(pairs, missing_fresh,
    missing_reference)`` where pairs is sorted by source_id and the missing lists are sorted
    ids present on one side only."""
    fresh_ids, reference_ids = set(fresh), set(reference)
    missing_fresh = sorted(reference_ids - fresh_ids)
    missing_reference = sorted(fresh_ids - reference_ids)
    pairs = [(sid, fresh[sid], reference[sid]) for sid in sorted(fresh_ids & reference_ids)]
    return pairs, missing_fresh, missing_reference


def project_fresh(fresh: dict, reference: dict) -> dict:
    """Only the reference set's source_ids take part in ITS comparison: one worker forwards
    200 stable200 images plus 100 parity sources, so the raw fresh dict holds up to 300 ids
    and must be projected onto each reference set before pairing."""
    return {sid: fresh[sid] for sid in reference if sid in fresh}


def compare_set(fresh, reference) -> dict:
    """One reference set vs the fresh forwards, per the APPROVED FUD-01 conditions:
    ``max_abs_prob_delta <= 1e-4`` AND ``argmax_agreement == 1.0`` (both required), judged
    per source_id. ``worst`` carries the largest-delta sample: source_id, per-class deltas,
    both argmaxes and top1-top2 margins."""
    pairs, missing_fresh, missing_reference = pair_by_source_id(fresh, reference)
    worst = None
    max_delta = 0.0
    mismatches = []
    for source_id, fresh_probs, reference_probs in pairs:
        deltas = [abs(float(a) - float(b)) for a, b in zip(fresh_probs, reference_probs)]
        delta = max(deltas)
        if delta > max_delta:
            max_delta = delta
            worst = {"source_id": source_id, "max_delta": delta, "per_class_deltas": deltas,
                     "fresh_probs": [float(x) for x in fresh_probs],
                     "reference_probs": [float(x) for x in reference_probs],
                     "fresh_argmax": argmax(fresh_probs), "reference_argmax": argmax(reference_probs),
                     "top1_top2_margin_fresh": top1_top2_margin(fresh_probs),
                     "top1_top2_margin_reference": top1_top2_margin(reference_probs)}
        if argmax(fresh_probs) != argmax(reference_probs):
            mismatches.append(source_id)
    n = len(pairs)
    agreement = (n - len(mismatches)) / n if n else None
    pass_numeric = bool(n and not missing_fresh and not missing_reference
                        and max_delta <= PROB_DELTA_TOLERANCE
                        and agreement == ARGMAX_AGREEMENT_TOLERANCE)
    return {"n_compared": n, "missing_fresh": missing_fresh, "missing_reference": missing_reference,
            "max_abs_prob_delta": max_delta if n else None, "argmax_agreement": agreement,
            "argmax_mismatches": mismatches, "pass_numeric": pass_numeric, "worst": worst}


def mode_winners(values) -> list[int]:
    """Every tied mode of a sequence of observed values, ascending. A tie is reported as a
    tie, never resolved in favour of the correct class."""
    if not values:
        return []
    counts: dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    best = max(counts.values())
    return sorted(v for v, count in counts.items() if count == best)


def evaluate_class_rule(samples) -> dict:
    """The stable200 per-class mode rule (tolerance doc section 5): for each class c_i,
    ``winners == [i]``; a tied mode fails that class, and all ten classes must pass for
    ``all_unique_modes_equal_label``. ``samples`` are ``{"class_id": "c0".."c9", "argmax": int}``."""
    by_class = {f"c{i}": [] for i in range(10)}
    for sample in samples:
        by_class[sample["class_id"]].append(sample["argmax"])
    per_class: dict[str, dict] = {}
    all_pass = True
    for i in range(10):
        argmaxes = by_class[f"c{i}"]
        winners = mode_winners(argmaxes)
        passed = winners == [i]
        per_class[f"c{i}"] = {"n": len(argmaxes), "counts": [argmaxes.count(k) for k in range(10)],
                              "winners": winners, "pass": passed}
        all_pass = all_pass and passed
    return {"per_class": per_class, "all_unique_modes_equal_label": all_pass}


def parse_annotations(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parity_reference(path):
    """``{source_id: probability vector}`` from a P4A parity JSON: the cached ORT logits of
    ``result.validation_predictions`` softmaxed ONCE in float64; plus metadata."""
    document = json.loads(Path(path).read_text())
    entries = document["result"]["validation_predictions"]
    refs = {entry["source_id"]: stable_softmax64(entry["logits"]) for entry in entries}
    return refs, {"n": len(refs), "path": str(path), "sha256": sha256_file(path),
                  "kind": "p4a_ort_logits"}


def csv_reference(path):
    """``{source_id: probability vector}`` from a package's stable200_saved_predictions.csv:
    the ``probability_c*`` columns read directly (PyTorch outputs, never re-softmaxed)."""
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    refs = {row["source_id"]: [float(row[f"probability_c{i}"]) for i in range(10)] for row in rows}
    return refs, {"n": len(refs), "path": str(path), "sha256": sha256_file(path),
                  "kind": "pytorch_csv_probabilities"}


def forward_sample(provider, raw: bytes, source_id: str) -> dict:
    """One image through the EXACT provider path: base64 of the original JPEG bytes (no
    re-encode) -> ``TrainedProvider.preprocess`` -> ``vision.run`` -> one float32 softmax,
    the same arithmetic as the provider's ``infer()``."""
    import base64

    import numpy as np

    encoded = base64.b64encode(raw).decode("ascii")
    tensor = provider.preprocess(encoded)
    logits = np.asarray(provider.vision.run(None, {provider.input_name: tensor})[0][0], dtype=np.float32)
    exp = np.exp(logits - np.max(logits))
    probs = (exp / exp.sum()).astype(np.float64)
    return {"source_id": source_id, "probs": [float(p) for p in probs],
            "argmax": argmax([float(p) for p in probs]), "sha256": sha256_bytes(raw)}


def image_path_for_source(source_id: str, data_root: Path) -> Path:
    """A P4A source_id is "vision-v1:<class>/<file>"; the JPEG lives at
    ``<data-root>/<class>/<file>`` (preflight_report.md)."""
    relative = source_id.removeprefix("vision-v1:")
    if not relative or relative == source_id or Path(relative).parent.name not in {f"c{i}" for i in range(10)}:
        raise ValueError(f"unexpected source_id format: {source_id!r}")
    return data_root / relative


def environment_versions() -> dict:
    import platform

    versions = {"python": platform.python_version(), "platform": platform.platform()}
    for module_name in ("numpy", "onnxruntime", "PIL", "xgboost"):
        try:
            module = __import__(module_name)
        except Exception as exc:  # pragma: no cover - depends on the environment
            versions[module_name] = f"unavailable ({type(exc).__name__}: {exc})"
        else:
            versions[module_name] = getattr(module, "__version__", "unknown")
    return versions


# --------------------------------------------------------------------------------- worker
def run_worker(spec_path: Path, out_path: Path) -> int:
    """Child-process half of the runner: load the real TrainedProvider for ONE model and
    forward every listed image. Rejected inputs are recorded, never skipped."""
    spec = json.loads(spec_path.read_text())
    model_id = spec["model_id"]
    result = {"model_id": model_id, "started": datetime.now().isoformat(),
              "environment": environment_versions(), "images_requested": len(spec["images"])}
    try:
        from app.providers.trained import TrainedProvider

        provider = TrainedProvider()
        vision_info = provider.info.get("vision", {})
        result["provider"] = {"name": provider.info.get("provider"), "vision": vision_info}
        loaded = vision_info.get("model_id")
        if loaded != model_id:
            result["error"] = (f"provider loaded '{loaded}' but the worker spec asked for "
                               f"'{model_id}': the DRA_ACTIVE_VISION switch did not take effect")
            result["finished"] = datetime.now().isoformat()
            out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
            return 1
        samples: dict[str, dict] = {}
        rejected: dict[str, dict] = {}
        for item in spec["images"]:
            sid = item["source_id"]
            try:
                raw = Path(item["path"]).read_bytes()
                samples[sid] = forward_sample(provider, raw, sid)
            except Exception as exc:
                rejected[sid] = {"error": f"{type(exc).__name__}: {exc}", "path": item["path"]}
        result["samples"] = samples
        result["rejected"] = rejected
        result["finished"] = datetime.now().isoformat()
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["finished"] = datetime.now().isoformat()
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
        return 1


# --------------------------------------------------------------------------------- parent
def candidates_package(model_id: str) -> Path:
    index = json.loads((CANDIDATES_ROOT / "index.json").read_text())
    entry = index.get(model_id)
    if not isinstance(entry, dict) or not isinstance(entry.get("package"), str):
        raise ValueError(f"vision candidate '{model_id}' is not in {CANDIDATES_ROOT / 'index.json'}")
    return CANDIDATES_ROOT / entry["package"]


def reference_meta(refs: dict, expected_sha256: str) -> dict:
    return {"path": refs["path"], "sha256": refs["sha256"], "expected_sha256": expected_sha256,
            "sha256_match": refs["sha256"] == expected_sha256, "kind": refs["kind"], "n": refs["n"]}


def attach_worst_image_hash(comparison: dict, samples: dict) -> None:
    """The tolerance document (section 4) asks for the worst sample's image hash next to its
    source_id, per-class deltas and top1-top2 margins."""
    worst = comparison.get("worst")
    if worst and worst["source_id"] in samples:
        worst["fresh_image_sha256"] = samples[worst["source_id"]].get("sha256")


def spawn_worker(model_id: str, images: list[dict], active_vision: str | None,
                 spec_path: Path, out_path: Path):
    spec_path.write_text(json.dumps({"model_id": model_id, "images": images}, indent=2))
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(BACKEND_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if active_vision is None:
        # The stable model: DRA_ACTIVE_VISION is NOT set (its absence is what selects the
        # stable provider path). The worker verifies the loaded model_id either way.
        env.pop("DRA_ACTIVE_VISION", None)
    else:
        env["DRA_ACTIVE_VISION"] = active_vision
    command = [sys.executable, str(SCRIPTS_DIR / "verify_stable200.py"),
               "--worker", str(spec_path), str(out_path)]
    started = datetime.now()
    try:
        done = subprocess.run(command, cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
                              timeout=WORKER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"command": command, "exit_code": None, "stderr_tail": f"worker timed out "
                f"after {WORKER_TIMEOUT_S} s", "duration_s": None}, None
    duration = (datetime.now() - started).total_seconds()
    worker_record = {"command": command, "exit_code": done.returncode,
                     "stderr_tail": done.stderr.strip().splitlines()[-20:], "duration_s": round(duration, 2)}
    worker_json = None
    if out_path.exists():
        try:
            worker_json = json.loads(out_path.read_text())
        except ValueError:
            worker_record["stderr_tail"].append(f"worker output {out_path} is not valid JSON")
    return worker_record, worker_json


def build_model_entry(spec: dict, rows: list[dict], parity_refs: dict, parity_meta: dict,
                      csv_refs: dict | None, csv_meta: dict | None, worker_record: dict,
                      worker_json: dict | None, preprocess_identity) -> dict:
    model_id = spec["model_id"]
    entry: dict = {"model_id": model_id, "worker": worker_record}
    problems: list[str] = []
    if worker_json is None or worker_json.get("error"):
        entry["status"] = "FAIL"
        entry["worker_error"] = (worker_json or {}).get("error", "no worker result JSON")
        entry["stable200_pytorch_comparison"] = csv_meta if csv_refs is not None else None
        if csv_refs is None:
            entry["stable200_pytorch_comparison_reason"] = NO_STABLE200_REFERENCE
        return entry
    entry["environment"] = worker_json.get("environment", {})
    entry["provider"] = worker_json.get("provider", {})
    entry["preprocess_rejected"] = worker_json.get("rejected", {})
    if worker_json.get("rejected"):
        problems.append(f"{len(worker_json['rejected'])} input(s) rejected by preprocess")
    if worker_record["exit_code"] != 0:
        problems.append(f"worker exit code {worker_record['exit_code']}")

    actual_onnx = (worker_json.get("provider", {}).get("vision") or {}).get("sha256")
    onnx_match = actual_onnx == spec["onnx_sha256"]
    entry["model"] = {"onnx_sha256_actual": actual_onnx, "onnx_sha256_expected": spec["onnx_sha256"],
                      "onnx_sha256_match": onnx_match, "preprocess_identity": preprocess_identity}
    if not onnx_match:
        problems.append(f"ONNX sha256 mismatch: loaded {actual_onnx}, "
                        f"approved {spec['onnx_sha256']}")

    samples = worker_json.get("samples", {})
    fresh_probs = {sid: sample["probs"] for sid, sample in samples.items()}
    sanity_problems = {sid: validate_probs(probs) for sid, probs in fresh_probs.items()
                       if validate_probs(probs)}
    entry["probability_sanity_problems"] = sanity_problems
    if sanity_problems:
        problems.append(f"{len(sanity_problems)} fresh vector(s) failed probability sanity")

    parity_comparison = compare_set(project_fresh(fresh_probs, parity_refs), parity_refs)
    attach_worst_image_hash(parity_comparison, samples)
    entry["parity100_reference_comparison"] = {"reference": parity_meta,
                                               "comparison": parity_comparison}
    if not parity_comparison["pass_numeric"]:
        problems.append("parity100 numeric check failed")

    behavior_samples = []
    missing_behavior_ids = []
    for row in rows:
        sample = samples.get(row["source_id"])
        if sample is None:
            missing_behavior_ids.append(row["source_id"])
            continue
        behavior_samples.append({"class_id": row["class_id"], "argmax": sample["argmax"]})
    behavior = evaluate_class_rule(behavior_samples)
    behavior["n_behavior"] = len(behavior_samples)
    behavior["n_missing"] = len(missing_behavior_ids)
    behavior["missing_source_ids"] = missing_behavior_ids
    entry["stable200_behavior"] = behavior
    if not behavior["all_unique_modes_equal_label"] or missing_behavior_ids:
        problems.append("stable200 per-class mode rule failed")

    if csv_refs is not None:
        csv_comparison = compare_set(project_fresh(fresh_probs, csv_refs), csv_refs)
        attach_worst_image_hash(csv_comparison, samples)
        entry["stable200_pytorch_comparison"] = {"reference": csv_meta, "comparison": csv_comparison}
        if not csv_comparison["pass_numeric"]:
            problems.append("stable200 pytorch numeric check failed")
    else:
        entry["stable200_pytorch_comparison"] = None
        entry["stable200_pytorch_comparison_reason"] = NO_STABLE200_REFERENCE

    entry["status"] = "PASS" if not problems else "FAIL"
    entry["problems"] = problems
    return entry


def run(args) -> int:
    started = datetime.now()
    data_root = Path(args.data_root)
    p4a_root = Path(args.p4a_root)
    # Absolute: the worker child processes run with cwd=backend and receive these paths
    # on their command line, so a relative --out would silently resolve elsewhere.
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    blockers: list[dict] = []

    # --- candidates index and the frozen stable200 membership ----------------------------
    index_path = CANDIDATES_ROOT / "index.json"
    if not index_path.is_file():
        blockers.append({"kind": "candidates_index_missing", "path": str(index_path)})
    packages = {}
    for spec in MODEL_SPECS:
        if spec["active_vision"] is None:
            continue
        try:
            packages[spec["model_id"]] = candidates_package(spec["model_id"])
        except (ValueError, OSError) as exc:
            blockers.append({"kind": "candidate_package_missing", "model_id": spec["model_id"],
                             "error": str(exc)})

    rows, membership = [], {}
    try:
        annotations_path = packages[RN_MODEL_ID] / "validation/stable200_annotations.csv"
        rows = parse_annotations(annotations_path)
        member = membership_sha256(rows)
        source_member = source_ids_sha256(rows)
        membership = {"annotations": str(annotations_path), "n": len(rows),
                      "membership_sha256": member, "membership_sha256_expected": EXPECTED_MEMBERSHIP_SHA256,
                      "membership_sha256_match": member == EXPECTED_MEMBERSHIP_SHA256,
                      "source_ids_sha256": source_member,
                      "source_ids_sha256_expected": EXPECTED_SOURCE_IDS_SHA256,
                      "source_ids_sha256_match": source_member == EXPECTED_SOURCE_IDS_SHA256}
        if member != EXPECTED_MEMBERSHIP_SHA256 or source_member != EXPECTED_SOURCE_IDS_SHA256:
            print(f"MEMBERSHIP MISMATCH: {annotations_path}\n"
                  f"  membership_sha256: {member} (expected {EXPECTED_MEMBERSHIP_SHA256})\n"
                  f"  source_ids_sha256: {source_member} (expected {EXPECTED_SOURCE_IDS_SHA256})",
                  file=sys.stderr)
            return 2
        # The two candidates declare the SAME 200 members; verify the second package agrees.
        mn_annotations = packages[MN_CANDIDATE_MODEL_ID] / "validation/stable200_annotations.csv"
        mn_member = membership_sha256(parse_annotations(mn_annotations))
        membership["mn_package_membership_sha256"] = mn_member
        membership["mn_package_membership_sha256_match"] = mn_member == EXPECTED_MEMBERSHIP_SHA256
        if mn_member != EXPECTED_MEMBERSHIP_SHA256:
            blockers.append({"kind": "membership_disagreement_between_candidate_packages",
                             "path": str(mn_annotations), "sha256": mn_member,
                             "expected": EXPECTED_MEMBERSHIP_SHA256})
    except (KeyError, ValueError, OSError) as exc:
        print(f"stable200 annotations unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    # --- approval provenance --------------------------------------------------------------
    approval_path = REPO / APPROVAL_RECORD
    tolerance_path = REPO / TOLERANCE_DOC
    approval = {}
    if approval_path.is_file() and tolerance_path.is_file():
        approval = json.loads(approval_path.read_text())
        tolerance = {"document": TOLERANCE_DOC, "document_sha256": sha256_file(tolerance_path),
                     "approval_record": APPROVAL_RECORD, "approval_record_sha256": sha256_file(approval_path),
                     "approved_tolerance": approval.get("approved_tolerance"),
                     "approval_status": approval.get("status"),
                     "max_abs_prob_delta": PROB_DELTA_TOLERANCE,
                     "argmax_agreement": ARGMAX_AGREEMENT_TOLERANCE}
    else:
        tolerance = {"document": TOLERANCE_DOC, "approval_record": APPROVAL_RECORD,
                     "max_abs_prob_delta": PROB_DELTA_TOLERANCE, "argmax_agreement": ARGMAX_AGREEMENT_TOLERANCE}
        blockers.append({"kind": "approval_record_missing",
                         "path": str(approval_path if not approval_path.is_file() else tolerance_path)})

    # --- references and images ------------------------------------------------------------
    parity_refs_by_model: dict[str, tuple[dict, dict]] = {}
    csv_refs_by_model: dict[str, tuple[dict, dict]] = {}
    images_by_model: dict[str, list[dict]] = {}
    for spec in MODEL_SPECS:
        model_id = spec["model_id"]
        parity_path = p4a_root / spec["parity_file"]
        if not parity_path.is_file():
            blockers.append({"kind": "parity_reference_missing", "path": str(parity_path), "model_id": model_id})
            continue
        refs, meta = parity_reference(parity_path)
        meta = reference_meta(meta, spec["parity_sha256"])
        if not meta["sha256_match"]:
            blockers.append({"kind": "parity_reference_hash_mismatch", **meta, "model_id": model_id})
        parity_refs_by_model[model_id] = (refs, meta)

        images: dict[str, dict] = {}
        for row in rows:
            path = data_root / row["class_id"] / row["filename"]
            images[row["source_id"]] = {"source_id": row["source_id"], "class_id": row["class_id"],
                                        "path": str(path)}
        for source_id in sorted(refs):
            try:
                path = image_path_for_source(source_id, data_root)
            except ValueError as exc:
                blockers.append({"kind": "bad_source_id", "error": str(exc), "model_id": model_id})
                continue
            images.setdefault(source_id, {"source_id": source_id, "path": str(path)})
        for sid, item in images.items():
            if not Path(item["path"]).is_file():
                blockers.append({"kind": "image_missing", "path": item["path"], "source_id": sid,
                                 "model_id": model_id})
        images_by_model[model_id] = list(images.values())

        if spec["csv_sha256"] is not None:
            csv_path = packages[model_id] / "validation/stable200_saved_predictions.csv"
            if not csv_path.is_file():
                blockers.append({"kind": "csv_reference_missing", "path": str(csv_path), "model_id": model_id})
                continue
            csv_refs, csv_meta = csv_reference(csv_path)
            csv_meta = reference_meta(csv_meta, spec["csv_sha256"])
            if not csv_meta["sha256_match"]:
                blockers.append({"kind": "csv_reference_hash_mismatch", **csv_meta, "model_id": model_id})
            csv_refs_by_model[model_id] = (csv_refs, csv_meta)

    official = {"record_type": "stable200_verification_run", "run": {
        "command": [sys.executable, *sys.argv], "started": started.isoformat(),
        "script_sha256": sha256_file(Path(__file__))},
        "membership": membership, "tolerance": tolerance, "blockers": blockers,
        "models": {}, "environment": {"python": sys.version.split()[0]}}

    if blockers:
        official["overall_status"] = "BLOCKED"
        official["run"]["finished"] = datetime.now().isoformat()
        official["run"]["exit_code"] = 2
        write_outputs(out_dir, official, {})
        return 2

    # --- one child process per model -------------------------------------------------------
    entries: dict[str, dict] = {}
    all_pass = True
    for spec in MODEL_SPECS:
        model_id = spec["model_id"]
        spec_path = out_dir / f"worker_spec_{model_id}.json"
        worker_out = out_dir / f"worker_out_{model_id}.json"
        worker_record, worker_json = spawn_worker(model_id, images_by_model[model_id],
                                                  spec["active_vision"], spec_path, worker_out)
        preprocess_identity = None
        if spec["active_vision"] is not None:
            try:
                manifest = json.loads((packages[model_id] / "runtime_manifest.json").read_text())
                preprocess_identity = manifest.get("preprocess")
            except (OSError, ValueError):
                preprocess_identity = None
        entry = build_model_entry(spec, rows,
                                  *parity_refs_by_model[model_id],
                                  *(csv_refs_by_model.get(model_id) or (None, None)),
                                  worker_record, worker_json, preprocess_identity)
        entries[model_id] = entry
        all_pass = all_pass and entry["status"] == "PASS"

    official["models"] = entries
    official["overall_status"] = "PASS" if all_pass else "FAIL"
    official["run"]["finished"] = datetime.now().isoformat()
    official["run"]["exit_code"] = 0 if all_pass else 1
    write_outputs(out_dir, official, entries)
    return 0 if all_pass else 1


def write_outputs(out_dir: Path, official: dict, entries: dict[str, dict]) -> None:
    """One JSON per model plus the merged official_stable200_behavior.json."""
    for model_id, entry in entries.items():
        (out_dir / f"{model_id}.json").write_text(json.dumps(entry, indent=2, sort_keys=True))
    (out_dir / "official_stable200_behavior.json").write_text(
        json.dumps(official, indent=2, sort_keys=True))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="stable200 provider verification runner (Task 1.4 / DS-1)")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT,
                        help=f"images live at <data-root>/<class_id>/<filename> (default: {DEFAULT_DATA_ROOT})")
    parser.add_argument("--p4a-root", type=Path, default=DEFAULT_P4A_ROOT,
                        help=f"read-only P4A run directory with the parity JSONs (default: {DEFAULT_P4A_ROOT})")
    parser.add_argument("--out", type=Path, default=None,
                        help="evidence directory (default: docs/evidence/<today>/stable200)")
    parser.add_argument("--worker", nargs=2, metavar=("SPEC", "OUT"), default=None,
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return run_worker(Path(args.worker[0]), Path(args.worker[1]))
    out = args.out or REPO / "docs" / "evidence" / datetime.now().strftime("%Y-%m-%d") / "stable200"
    return run(argparse.Namespace(data_root=args.data_root, p4a_root=args.p4a_root, out=out))


if __name__ == "__main__":
    sys.exit(main())
