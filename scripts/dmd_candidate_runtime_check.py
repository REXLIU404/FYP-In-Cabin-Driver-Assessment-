#!/usr/bin/env python3
"""DMD candidate evidence, item B: runtime compatibility and provider parity.

Bound by ``docs/fyp2/dmd-candidate/protocol.json``. Three checks:

1. ``scripts/validate_runtime_manifest.py`` validates the candidate package (manifest schema,
   class order, sha256 of model.onnx, containment).
2. ``DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029`` is loaded through the real
   ``TrainedProvider`` in a child process; its reported model id, sha256 and classes are
   checked against the protocol.
3. Provider parity: from the frozen State Farm test list, 20 images per class (200 in all,
   sorted by class then filename). The provider's preprocessed tensor goes through the
   provider's ONNX session and a second, independently loaded ONNX session on the same
   file. Pass = max_abs_prob_delta <= 1e-4 AND argmax_agreement == 1.0, the approved
   FUD-01 conditions. The independent-preprocess tensor comparison is recorded as
   information, not as a pass condition.

The tolerance is never relaxed after a result. The candidate package is read only; its
``evaluation_metrics.json`` is not modified.

Usage:
    .venv/bin/python scripts/dmd_candidate_runtime_check.py --out docs/evidence/<date>/dmd-candidate/b-runtime-compat
    # internal worker:
    .venv/bin/python scripts/dmd_candidate_runtime_check.py --worker spec.json out.json

Exit codes: 0 valid and passing; 1 a check failed; 2 BLOCKED (protocol gate, missing input,
missing model/package, validator failure).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
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

from dmd_candidate_eval import (  # noqa: E402
    DEFAULT_STATE_FARM_SOURCES,
    environment_versions,
    git_state,
    load_state_farm_sources,
    protocol_gate,
    sha256_file,
)

PROTOCOL = REPO / "docs" / "fyp2" / "dmd-candidate" / "protocol.json"
DEFAULT_OUT = REPO / "docs" / "evidence" / datetime.now().strftime("%Y-%m-%d") / "dmd-candidate" / "b-runtime-compat"
PACKAGE = REPO / "ml" / "outputs" / "candidates" / "dmd_adapted_mobilenet_v3_20261029"
MANIFEST = PACKAGE / "runtime_manifest.json"
MODEL = PACKAGE / "model.onnx"
VALIDATOR = SCRIPTS_DIR / "validate_runtime_manifest.py"
DMD_MODEL_ID = "dmd_adapted_mobilenet_v3_20261029"
DMD_SHA256 = "01f1d6a3a57936590d29f1a86856fd6e67c8c9fd382f48bd601f9c66ed2b4d55"
TOLERANCE = 1e-4
ARGMAX_AGREEMENT_REQUIRED = 1.0
WORKER_TIMEOUT_S = 3600


def argmax(values) -> int:
    best = max(values)
    return next(i for i, v in enumerate(values) if v == best)


def top1_top2_margin(probs) -> float:
    top = argmax(probs)
    return probs[top] - max(p for i, p in enumerate(probs) if i != top)


def select_parity_sample(sources: list[dict], per_class: int = 20) -> list[dict]:
    """First ``per_class`` filenames of every class after sorting, in class order."""
    sample = []
    for class_id in [f"c{i}" for i in range(10)]:
        rows = sorted((s for s in sources if s["class_id"] == class_id), key=lambda s: s["filename"])
        if len(rows) < per_class:
            raise ValueError(f"class {class_id} has {len(rows)} images, need {per_class}")
        sample.extend(rows[:per_class])
    return sample


def compare_distributions(fresh: dict[str, list[float]], reference: dict[str, list[float]]) -> dict:
    """FUD-01: max_abs_prob_delta <= 1e-4 AND argmax agreement == 1.0, paired by source_id."""
    fresh_ids, reference_ids = set(fresh), set(reference)
    missing_fresh = sorted(reference_ids - fresh_ids)
    missing_reference = sorted(fresh_ids - reference_ids)
    pairs = [(sid, fresh[sid], reference[sid]) for sid in sorted(fresh_ids & reference_ids)]
    max_delta, worst, mismatches = 0.0, None, []
    for sid, fresh_probs, reference_probs in pairs:
        deltas = [abs(float(a) - float(b)) for a, b in zip(fresh_probs, reference_probs)]
        delta = max(deltas)
        if delta > max_delta:
            max_delta = delta
            worst = {"source_id": sid, "max_delta": delta, "per_class_deltas": deltas,
                     "fresh_probs": [float(x) for x in fresh_probs],
                     "reference_probs": [float(x) for x in reference_probs],
                     "fresh_argmax": argmax(fresh_probs), "reference_argmax": argmax(reference_probs),
                     "top1_top2_margin_fresh": top1_top2_margin(fresh_probs),
                     "top1_top2_margin_reference": top1_top2_margin(reference_probs)}
        if argmax(fresh_probs) != argmax(reference_probs):
            mismatches.append(sid)
    n = len(pairs)
    agreement = (n - len(mismatches)) / n if n else None
    passed = bool(n and not missing_fresh and not missing_reference
                  and max_delta <= TOLERANCE and agreement == ARGMAX_AGREEMENT_REQUIRED)
    return {"n_compared": n, "missing_fresh": missing_fresh, "missing_reference": missing_reference,
            "max_abs_prob_delta": max_delta if n else None, "argmax_agreement": agreement,
            "argmax_mismatches": mismatches, "pass_numeric": passed, "worst": worst}


def independent_preprocess(path: Path):
    from dmd_infer_test import preprocess

    return preprocess(Path(path))


def _softmax(logits):
    import numpy as np

    row = np.asarray(logits, dtype=np.float32)
    exp = np.exp(row - np.max(row))
    return (exp / exp.sum()).astype("float64").tolist()


def validate_manifest(package_dir: Path = PACKAGE, manifest_path: Path = MANIFEST,
                      validator: Path = VALIDATOR) -> dict:
    command = [sys.executable, str(validator), str(manifest_path), "--package-dir", str(package_dir)]
    done = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=120)
    return {"command": [Path(c).name if i == 0 else c for i, c in enumerate(command)],
            "exit_code": done.returncode, "stdout": done.stdout.strip(),
            "stderr": done.stderr.strip()}


def _model_info(session) -> dict:
    inp = session.get_inputs()[0]
    out = session.get_outputs()[0]
    return {"input_name": inp.name, "input_type": inp.type, "input_shape": list(inp.shape),
            "output_name": out.name, "output_shape": list(out.shape)}


def _parity(provider, direct_session, sources: list[dict]) -> dict:
    import numpy as np

    provider_probs, direct_probs, independent_probs = {}, {}, {}
    tensor_deltas, samples, rejected = [], [], []
    direct_input = direct_session.get_inputs()[0].name
    for item in sources:
        try:
            raw = Path(item["image_path"]).read_bytes()
            tensor = provider.preprocess(base64.b64encode(raw).decode("ascii"))
            provider_logits = provider.vision.run(None, {provider.input_name: tensor})[0][0]
            direct_logits = direct_session.run(None, {direct_input: tensor})[0][0]
            independent_tensor = independent_preprocess(Path(item["image_path"]))
            tensor_delta = float(np.max(np.abs(tensor - independent_tensor)))
            independent_logits = direct_session.run(None, {direct_input: independent_tensor})[0][0]
            p_probs, d_probs, i_probs = _softmax(provider_logits), _softmax(direct_logits), _softmax(independent_logits)
            provider_probs[item["source_id"]] = p_probs
            direct_probs[item["source_id"]] = d_probs
            independent_probs[item["source_id"]] = i_probs
            tensor_deltas.append({"source_id": item["source_id"], "max_abs_tensor_delta": tensor_delta})
            samples.append({"source_id": item["source_id"], "class_id": item["class_id"],
                            "provider_probs": p_probs, "direct_probs": d_probs,
                            "independent_probs": i_probs,
                            "provider_argmax": argmax(p_probs), "direct_argmax": argmax(d_probs),
                            "independent_argmax": argmax(i_probs),
                            "max_abs_tensor_delta": tensor_delta})
        except Exception as exc:
            rejected.append({"source_id": item["source_id"], "path": item["image_path"],
                             "error": f"{type(exc).__name__}: {exc}"})
    comparison = compare_distributions(provider_probs, direct_probs)
    independent_comparison = compare_distributions(provider_probs, independent_probs)
    worst_tensor = max(tensor_deltas, key=lambda r: r["max_abs_tensor_delta"], default=None)
    return {"provider_vs_direct": comparison,
            "provider_vs_independent_preprocess": independent_comparison,
            "preprocess_tensor": {"max_abs_tensor_delta": worst_tensor,
                                  "n": len(tensor_deltas),
                                  "note": "information only, not part of the FUD-01 pass rule"},
            "rejected": rejected, "samples": samples}


def provider_parity_in_process(sources: list[dict]) -> dict:
    """Build the real provider with the candidate selected, then run the parity check."""
    import onnxruntime as ort

    from app.config import settings

    previous = settings.active_vision
    settings.active_vision = DMD_MODEL_ID
    try:
        from app.providers.trained import TrainedProvider

        provider = TrainedProvider()
    finally:
        settings.active_vision = previous
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    direct = ort.InferenceSession(str(MODEL), opts, providers=["CPUExecutionProvider"])
    vision = provider.info.get("vision", {})
    result = _parity(provider, direct, sources)
    return {"identity": {"model_id": vision.get("model_id"), "sha256": vision.get("sha256"),
                         "source": vision.get("source"), "classes": vision.get("classes")},
            "provider": provider.info.get("provider"),
            "direct_session": _model_info(direct),
            **result}


def _spawn_worker(sources: list[dict], out_dir: Path) -> tuple[dict, dict | None]:
    spec_path = out_dir / "worker_spec.json"
    out_path = out_dir / "worker_out.json"
    spec_path.write_text(json.dumps({"model_id": DMD_MODEL_ID, "package": str(PACKAGE),
                                     "model": str(MODEL), "sources": sources}, indent=2))
    env = {k: v for k, v in os.environ.items() if not k.startswith("DRA_")}
    env.update(PYTHONPATH=str(BACKEND_DIR), PYTHONDONTWRITEBYTECODE="1",
               DRA_ACTIVE_VISION=DMD_MODEL_ID)
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(spec_path), str(out_path)]
    began = time.time()
    done = subprocess.run(command, cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
                          timeout=WORKER_TIMEOUT_S)
    record = {"command": [Path(command[0]).name, *command[1:]], "exit_code": done.returncode,
              "duration_s": round(time.time() - began, 1),
              "stderr_tail": done.stderr.strip().splitlines()[-20:]}
    output = json.loads(out_path.read_text()) if out_path.is_file() else None
    return record, output


def run_worker(spec_path: Path, out_path: Path) -> int:
    spec = json.loads(spec_path.read_text())
    result = {"model_id": spec["model_id"], "started": datetime.now(timezone.utc).isoformat(),
              "environment": environment_versions()}
    try:
        import onnxruntime as ort
        from app.providers.trained import TrainedProvider

        provider = TrainedProvider()
        vision = provider.info.get("vision", {})
        result["provider"] = {"name": provider.info.get("provider"), "vision": vision,
                              "telemetry_sha256": (provider.info.get("telemetry") or {}).get("sha256")}
        expected_sha = sha256_file(Path(spec["model"]))
        if vision.get("model_id") != spec["model_id"]:
            result["error"] = f"provider loaded {vision.get('model_id')!r}, expected {spec['model_id']!r}"
        elif vision.get("sha256") != expected_sha or expected_sha != DMD_SHA256:
            result["error"] = (f"model sha256 mismatch: provider {vision.get('sha256')!r}, "
                               f"file {expected_sha}, declared {DMD_SHA256}")
        if "error" in result:
            out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
            return 1
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        direct = ort.InferenceSession(str(spec["model"]), opts, providers=["CPUExecutionProvider"])
        result["direct_session"] = _model_info(direct)
        result.update(_parity(provider, direct, spec["sources"]))
        result["finished"] = datetime.now(timezone.utc).isoformat()
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["provider_vs_direct"]["pass_numeric"] and not result["rejected"] else 1
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
        result["finished"] = datetime.now(timezone.utc).isoformat()
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
        return 1


def run(args) -> int:
    run_start = datetime.now(timezone.utc)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    gate = protocol_gate(run_start)
    header = {"run_start_utc": run_start.isoformat(), "protocol_gate": gate,
              "script_sha256": sha256_file(Path(__file__)),
              "git": git_state(), "environment": environment_versions()}
    if gate["status"] != "PASS":
        (out_dir / "results.json").write_text(json.dumps({**header, "status": "BLOCKED",
                                                          "problems": gate["problems"]}, indent=2))
        print("BLOCKED:", *gate["problems"], sep="\n  ", file=sys.stderr)
        return 2
    blockers = []
    for path in (PACKAGE, MANIFEST, MODEL, VALIDATOR):
        if not path.exists():
            blockers.append(f"missing {path}")
    if blockers:
        (out_dir / "results.json").write_text(json.dumps({**header, "status": "BLOCKED",
                                                          "problems": blockers}, indent=2))
        print("BLOCKED:", *blockers, sep="\n  ", file=sys.stderr)
        return 2

    validation = validate_manifest()
    (out_dir / "manifest_validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    if validation["exit_code"] != 0:
        (out_dir / "results.json").write_text(json.dumps(
            {**header, "status": "BLOCKED", "manifest_validation": validation,
             "problems": ["runtime manifest validation failed"]}, indent=2))
        print("BLOCKED: runtime manifest validation failed", file=sys.stderr)
        return 2

    sources = load_state_farm_sources(Path(args.state_farm_sources))
    sample = select_parity_sample(sources, per_class=args.per_class)
    header["sample"] = {"source_list": str(Path(args.state_farm_sources)),
                        "source_list_sha256": sha256_file(args.state_farm_sources),
                        "rule": f"first {args.per_class} filenames per class after sorting, class order c0..c9",
                        "n": len(sample),
                        "source_ids_sha256": __import__("hashlib").sha256(
                            "\n".join(sorted(s["source_id"] for s in sample)).encode()).hexdigest()}

    worker_record, output = _spawn_worker(sample, out_dir)
    problems = []
    if output is None or output.get("error"):
        problems.append(f"worker failed: {(output or {}).get('error') or 'no output'}")
    if worker_record["exit_code"] != 0:
        problems.append(f"worker exit code {worker_record['exit_code']}")
    if output and output.get("rejected"):
        problems.append(f"{len(output['rejected'])} input(s) rejected")
    if output:
        vision = (output.get("provider") or {}).get("vision") or {}
        identity_ok = (vision.get("model_id") == DMD_MODEL_ID
                       and vision.get("sha256") == DMD_SHA256
                       and (vision.get("classes") or [None])[0] == "safe_driving")
        if not identity_ok:
            problems.append(f"provider identity mismatch: {vision.get('model_id')!r} / {vision.get('sha256')!r}")
        (out_dir / "provider_identity.json").write_text(json.dumps({
            "provider": output.get("provider"), "identity_ok": identity_ok,
            "expected": {"model_id": DMD_MODEL_ID, "sha256": DMD_SHA256, "c0": "safe_driving"}},
            indent=2) + "\n")
        (out_dir / "provider_parity.json").write_text(json.dumps({
            "model_id": DMD_MODEL_ID,
            "sample": header["sample"],
            "tolerance": {"max_abs_prob_delta": TOLERANCE,
                          "argmax_agreement": ARGMAX_AGREEMENT_REQUIRED,
                          "source": "docs/fyp2/task10a/tolerance_predeclaration.md (FUD-01, APPROVED 2026-10-26)"},
            "direct_session": output.get("direct_session"),
            "provider_vs_direct": output.get("provider_vs_direct"),
            "provider_vs_independent_preprocess": output.get("provider_vs_independent_preprocess"),
            "preprocess_tensor": output.get("preprocess_tensor"),
            "rejected": output.get("rejected")}, indent=2) + "\n")
        if not output["provider_vs_direct"]["pass_numeric"]:
            problems.append("provider-vs-direct parity failed")

    status = "PASS" if not problems else "FAIL"
    result = {**header, "status": status, "problems": problems,
              "manifest_validation": validation, "worker": worker_record,
              "provider_identity_ok": bool(output and (output.get("provider") or {}).get("vision", {}).get("model_id") == DMD_MODEL_ID),
              "provider_vs_direct": (output or {}).get("provider_vs_direct"),
              "provider_vs_independent_preprocess": (output or {}).get("provider_vs_independent_preprocess"),
              "preprocess_tensor": (output or {}).get("preprocess_tensor"),
              "direct_session": (output or {}).get("direct_session")}
    (out_dir / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"B {status}: {out_dir}")
    if problems:
        print("PROBLEMS:", *problems, sep="\n  ", file=sys.stderr)
    return 0 if status == "PASS" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--state-farm-sources", type=Path, default=DEFAULT_STATE_FARM_SOURCES)
    parser.add_argument("--per-class", type=int, default=20)
    parser.add_argument("--worker", nargs=2, metavar=("SPEC", "OUT"), default=None,
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return run_worker(Path(args.worker[0]), Path(args.worker[1]))
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
