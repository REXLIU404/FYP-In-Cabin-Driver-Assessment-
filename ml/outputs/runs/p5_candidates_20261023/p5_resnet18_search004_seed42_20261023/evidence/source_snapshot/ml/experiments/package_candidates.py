"""P5 copy-only candidate delivery. No training, inference, export or deployment.

The package directory is the contract. Zip files are deterministic delivery copies.
Original paths in provenance are historical identifiers, never runtime dependencies.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PIN = "2745348"
HEAD = "335da4e3de203836c045452f84cc291bcd352a26"
P4A = ROOT / "ml/outputs/runs/p4a_20261021"
P4B = ROOT / "ml/outputs/runs/p4b_20261022"
METADATA = Path("/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/eda_outputs/processed/vision/vision_metadata_with_split.csv")
SMOKE_SHA = "601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9"
SMOKE_SOURCE_SHA = "2697d288e384f340cb51f002ce39fca024827c6969de9dc9f2db9682246c5d75"
CLASSES = [f"c{i}" for i in range(10)]
CLASS_TO_IDX = {name: i for i, name in enumerate(CLASSES)}
SPECS = {
    "RN-HPO42": {"architecture": "resnet18", "trial": "search_004", "export": "resnet18_search004_seed42",
        "run_id": "p5_resnet18_search004_seed42_20261023", "role": "VALIDATION_PREFERRED",
        "onnx_sha256": "5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3"},
    "MN-HPO42": {"architecture": "mobilenet_v3_large", "trial": "search_006", "export": "mobilenet_v3_large_search006_seed42",
        "run_id": "p5_mobilenet_v3_large_search006_seed42_20261023", "role": "RETAINED_COMPARATOR",
        "onnx_sha256": "9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828"},
}
REQUIRED = frozenset({"model.onnx", "runtime_manifest.json", "evaluation_metrics.json", "model_card.md",
    "class_metadata.json", "predictions_test_clean.csv", "validation/predictions_validation.csv",
    "validation/validation_metrics.json", "validation/class_report.json", "validation/stable200_annotations.csv",
    "validation/stable200_saved_predictions.csv", "validation/saved_prediction_diagnostic.json",
    "validation/p4a100_parity.json", "validation/p4a100_annotations.json", "evidence/source_config.json",
    "evidence/selection_log.json", "evidence/source_export_benchmark_manifest.json", "evidence/p4b_completion.json",
    "evidence/provenance.json", "evidence/source_hashes.json"})


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False); stream.write("\n")


def write_csv(path, rows):
    if not rows:
        raise ValueError("Empty prediction/annotation table")
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def load_pinned_contract(directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    blobs = {}
    for source in ("backend/app/runtime_manifest.py", "backend/app/runtime_manifest.schema.json", "scripts/validate_runtime_manifest.py",
                   "docs/fyp2/handoff/task-10a-runtime-manifest.md"):
        content = subprocess.check_output(["git", "show", f"{PIN}:{source}"], cwd=ROOT)
        blob = subprocess.check_output(["git", "rev-parse", f"{PIN}:{source}"], cwd=ROOT, text=True).strip()
        name = Path(source).name
        target = directory / name
        if target.exists() and target.read_bytes() != content:
            raise ValueError("Pinned contract snapshot changed")
        if not target.exists(): target.write_bytes(content)
        blobs[source] = {"git_blob_sha1": blob, "sha256": hashlib.sha256(content).hexdigest()}
    spec = importlib.util.spec_from_file_location("p5_pinned_runtime_manifest", directory / "runtime_manifest.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module, {"system_contract_commit": PIN, "blobs": blobs}


def check_onnx_graph(path):
    """Inspect the graph without an ORT session or any forward pass."""
    import onnx
    model = onnx.load(str(path), load_external_data=False)
    if any(t.data_location == onnx.TensorProto.EXTERNAL or t.external_data for t in model.graph.initializer):
        raise ValueError("External ONNX tensor data prohibited")
    onnx.checker.check_model(model)
    if len(model.graph.input) != 1 or len(model.graph.output) != 1:
        raise ValueError("Exactly one input/output required")
    def shape(value):
        return [dim.dim_param if dim.dim_param else dim.dim_value for dim in value.type.tensor_type.shape.dim]
    inp, out = model.graph.input[0], model.graph.output[0]
    a, b = shape(inp), shape(out)
    if inp.name != "input" or out.name != "logits" or inp.type.tensor_type.elem_type != 1 or out.type.tensor_type.elem_type != 1:
        raise ValueError("Expected input/logits float32")
    if len(a) != 4 or not isinstance(a[0], str) or not a[0] or a[1:] != [3, 224, 224]:
        raise ValueError("Dynamic NCHW input required")
    if len(b) != 2 or b[0] != a[0] or b[1] != 10:
        raise ValueError("Dynamic batch ten-class logits required")
    if any(node.op_type in {"Softmax", "LogSoftmax"} for node in model.graph.node):
        raise ValueError("Graph must emit raw logits without softmax")
    return {"status": "PASS", "input_name": inp.name, "input_shape": a, "output_name": out.name,
            "output_shape": b, "dtype": "float32", "softmax_nodes": 0, "external_tensors": 0, "forward_passes": 0}


def validate_candidate(package_dir, contract):
    root = Path(package_dir)
    if root.is_symlink(): raise ValueError("Package symlink prohibited")
    files = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink(): raise ValueError(f"Symlink prohibited: {relative}")
        if path.is_file():
            if path.suffix.lower() in {".pt", ".pth", ".joblib", ".pkl", ".pickle"} or any(
                token in relative.lower() for token in ("random_forest", "logistic_regression")):
                raise ValueError(f"Forbidden model/comparator artifact: {relative}")
            files[relative] = path
    missing = REQUIRED - files.keys()
    if missing: raise ValueError(f"Missing required evidence: {sorted(missing)}")
    index = read_json(root / "artifact_manifest.json")["files"]
    for name in index:
        if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name:
            raise ValueError("Inventory path escapes package")
    if set(index) != set(files) - {"artifact_manifest.json"}:
        raise ValueError("File inventory incomplete or unexpected")
    for name, info in index.items():
        if files[name].stat().st_size != info["bytes"] or digest(files[name]) != info["sha256"]:
            raise ValueError(f"Evidence integrity/hash mismatch: {name}")
    manifest = read_json(root / "runtime_manifest.json")
    errors = contract.validate_package(manifest, root)
    if errors: raise ValueError("; ".join(errors))
    if manifest["classes"] != CLASSES or manifest["class_to_idx"] != CLASS_TO_IDX or manifest["safe_class"] != "c0":
        raise ValueError("Frozen c0-c9 class contract mismatch")
    graph = check_onnx_graph(root / manifest["model"]["path"])
    return {"status": "PASS", "package": root.name, "schema_hash_path": "PASS", "inventory_files": len(index),
            "graph": graph, "provider_load_forward": "NOT_RUN", "official_stable200_behavior": "NOT_RUN",
            "system_integration": "BLOCKED_NOT_IMPLEMENTED"}


def read_cached_predictions(database, identity, checkpoint_sha256, condition, expected_count):
    """Read completed P4 rows, checking the original metadata+NPY payload SHA."""
    database = Path(database)
    if database.is_symlink(): raise ValueError("Cache symlink refused")
    conn = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        meta = json.loads(conn.execute("SELECT value FROM meta WHERE key='manifest'").fetchone()[0])
        if meta.get("schema") != 2 or meta["identities"].get(identity) != checkpoint_sha256:
            raise ValueError("Cache frozen identity mismatch")
        rows = []
        for source_id, input_sha, label, status, payload, payload_sha in conn.execute(
            "SELECT source_id,input_sha,label,status,payload,payload_sha FROM predictions WHERE identity=? AND condition=? ORDER BY source_id", (identity, condition)):
            if status != "COMPLETED": raise ValueError("Incomplete cached prediction")
            metadata = {"identity": identity, "checkpoint_sha256": checkpoint_sha256, "source_id": source_id,
                        "condition": condition, "input_sha256": input_sha, "label": int(label)}
            if hashlib.sha256(canonical(metadata) + payload).hexdigest() != payload_sha:
                raise ValueError("Cache row/payload SHA tamper")
            output = np.load(io.BytesIO(payload), allow_pickle=False)
            classes = 10 if identity in SPECS else 3
            if output.shape != (classes,) or not np.isfinite(output).all(): raise ValueError("Invalid cached output")
            vision = identity in SPECS
            if vision:
                if output.dtype != np.float32: raise ValueError("Vision raw logits must remain float32")
                shifted = output.astype(np.float64) - float(output.max()); probability = np.exp(shifted); probability /= probability.sum()
            else:
                probability = output.astype(np.float64)
                if np.min(probability) < 0 or np.max(probability) > 1 or abs(probability.sum() - 1) > 1e-6:
                    raise ValueError("Invalid telemetry probabilities")
                probability /= probability.sum()
            record = {"source_id": source_id, "true_label_index": int(label), "predicted_label_index": int(np.argmax(output)),
                      "input_sha256": input_sha, "cache_row_sha256": payload_sha, "condition": condition}
            if vision: record.update({f"logit_c{i}": float(v) for i, v in enumerate(output)})
            record.update({f"probability_{'c' if vision else 'class_'}{i}": float(v) for i, v in enumerate(probability)})
            rows.append(record)
        if len(rows) != expected_count: raise ValueError(f"Cache count {len(rows)} != {expected_count}")
        if len({r['source_id'] for r in rows}) != len(rows): raise ValueError("Duplicate cached source ID")
        return rows
    finally:
        conn.close()


def stable_smoke(metadata_rows, validation_predictions, per_class=20):
    annotations = []
    for class_id in CLASSES:
        rows = sorted((r for r in metadata_rows if r['split'] == 'val' and r['class_id'] == class_id), key=lambda r: r['filename'])[:per_class]
        if len(rows) != per_class: raise ValueError("Incomplete validation smoke class")
        annotations += [{"source_id": f"vision-v1:{class_id}/{r['filename']}", "filename": r['filename'], "class_id": class_id,
                         "true_label_index": CLASS_TO_IDX[class_id], "training_label": r['class_name'], "driver_id": r['driver_id'], "split": "val"} for r in rows]
    predictions = {r['source_id']: r for r in validation_predictions}
    if len(predictions) != len(validation_predictions): raise ValueError("Duplicate validation predictions")
    selected = []
    for row in annotations:
        pred = predictions.get(row['source_id'])
        if pred is None or int(pred['true_label_index']) != row['true_label_index']:
            raise ValueError("Missing/misaligned saved validation prediction")
        selected.append(pred)
    modes = {}
    for i, class_id in enumerate(CLASSES):
        counts = Counter(int(p['predicted_label_index']) for a, p in zip(annotations, selected) if a['class_id'] == class_id)
        winners = sorted(k for k, v in counts.items() if v == max(counts.values()))
        modes[class_id] = {"count": sum(counts.values()), "predicted_counts": dict(counts), "modes": winners,
                           "unique_mode_equals_label": winners == [i]}
    return annotations, selected, {"scope": "SAVED_VALIDATION_PREDICTION_DIAGNOSTIC", "n": len(annotations),
        "filename_sha256": hashlib.sha256("\n".join(sorted(r['filename'] for r in annotations)).encode()).hexdigest(),
        "source_ids_sha256": hashlib.sha256("\n".join(sorted(r['source_id'] for r in annotations)).encode()).hexdigest(),
        "per_class": modes, "all_unique_modes_equal_label": all(v['unique_mode_equals_label'] for v in modes.values()),
        "provider_load_forward": "NOT_RUN", "official_behavior_check": "NOT_RUN", "new_inference": False,
        "limitation": "Saved PyTorch validation predictions are diagnostic only; no stable200 ONNX/provider behavior claim."}


def deterministic_zip(directory, output):
    root = Path(directory)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_symlink(): raise ValueError("Archive symlink prohibited")
            if path.is_file():
                entry = zipfile.ZipInfo(f"{root.name}/{path.relative_to(root).as_posix()}", date_time=(2026, 10, 23, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED; entry.external_attr = 0o100644 << 16
                archive.writestr(entry, path.read_bytes(), compresslevel=6)


def seal_package(directory):
    files = {p.relative_to(directory).as_posix(): {"sha256": digest(p), "bytes": p.stat().st_size}
             for p in sorted(directory.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"}
    write_json(directory / "artifact_manifest.json", {"schema": 1, "files": files,
               "scope": "Self-contained candidate delivery; all file references here are relative to this directory."})


def preservation_snapshot():
    from ml.experiments.p4_core import FROZEN_IDENTITIES
    from ml.experiments.p4_preflight import PROTECTED
    expected = dict(PROTECTED)
    for model in FROZEN_IDENTITIES.values(): expected[model['path']] = model['sha256']
    expected[str(METADATA)] = "b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4"
    expected["/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/eda_outputs/processed/telemetry/telemetry_test.csv"] = "3bc3d47680a87359e1470fd8ffaf5ff330dc4419b37cc645e5736d51a91c96de"
    for spec in SPECS.values(): expected[str(P4A / 'runtime_benchmark' / spec['export'] / 'model.onnx')] = spec['onnx_sha256']
    actual = {name: digest(ROOT / name) for name in expected}
    if actual != expected: raise ValueError("Protected/frozen identity SHA mismatch")
    names = ["ml/outputs/runs/p3_vision_20261018/selection_log.json", "ml/outputs/runs/p3_vision_20261018/search_state.json",
             "ml/outputs/runs/p3_telemetry_20261018/selection_log.json", "ml/configs/p4_protocol.json",
             "ml/experiments/p4_core.py", "ml/experiments/p4_data.py", "ml/experiments/p4_preflight.py", "ml/experiments/run_p4.py",
             "ml/experiments/e1_generators.py", "ml/experiments/run_e1_preparation.py", "ml/configs/e1_preparation.json"]
    # Existing P4 source evidence is immutable; include every small evidence file and the cache DB/WAL.
    for directory in (P4A, P4B):
        for path in directory.rglob("*"):
            if path.is_file() and not path.is_symlink() and path.suffix != '.npy' and not path.name.endswith('-shm'):
                names.append(str(path))
    actual.update({name: digest(ROOT / name) for name in names})
    git = {key: subprocess.check_output(args, cwd=ROOT, text=True).strip() for key, args in {
        "branch": ["git", "branch", "--show-current"], "head": ["git", "rev-parse", "HEAD"],
        "status": ["git", "status", "--short"], "staged": ["git", "diff", "--cached", "--name-only"]}.items()}
    if git['branch'] != 'fyp2/ml-training' or git['head'] != HEAD or git['staged']:
        raise ValueError("Unexpected Git branch/head/staged files")
    return {"hashes": actual, "git": git}


def build_delivery(output):
    """Copy the two frozen graphs, reuse predictions, and seal exact source evidence."""
    from ml.experiments.p4_core import FROZEN_IDENTITIES
    output = Path(output).resolve()
    if output.parent != (ROOT / "ml/outputs/runs").resolve() or output.name != "p5_candidates_20261023":
        raise ValueError("P5 output must be its isolated approved run directory")
    output.mkdir(exist_ok=True); verification = output / "verification"; verification.mkdir(exist_ok=True)
    if (verification / 'startup_snapshot.json').exists(): raise ValueError("Delivery already started; use verify-only, never overwrite")
    before = preservation_snapshot(); write_json(verification / 'startup_snapshot.json', before)
    contract, pinned = load_pinned_contract(verification / 'pinned_contract')
    write_json(verification / 'contract_pin.json', pinned)
    completion = read_json(P4B / 'completion.json')
    if completion['status'] != 'MACHINE_EVALUATION_COMPLETED' or completion['formal_prediction_count'] != 388449:
        raise ValueError("P4-B completion mismatch")
    cache_meta = read_json(P4B / 'cache/binding.json')
    if cache_meta['binding'] != completion['binding']: raise ValueError("P4 cache/completion binding mismatch")
    metrics = read_json(P4B / 'evaluation_metrics.json')
    attestation = read_json(P4A / 'core/preflight_attestation.json')
    for name, sha in attestation['files'].items():
        if digest(P4A / name) != sha: raise ValueError(f"P4-A attested evidence changed: {name}")
    if attestation['onnx_sha256'] != {k: s['onnx_sha256'] for k, s in SPECS.items()}:
        # Older attestation can additionally contain the stable ONNX.
        if any(attestation['onnx_sha256'].get(k) != s['onnx_sha256'] for k, s in SPECS.items()):
            raise ValueError("P4-A ONNX attestation mismatch")
    sources = read_json(P4B / 'shared_inputs/vision_sources.json')
    source_by_id = {r['source_id']: r for r in sources}
    if len(source_by_id) != 3657: raise ValueError("P4 source annotation count")
    with METADATA.open() as stream: validation_metadata = [r for r in csv.DictReader(stream) if r['split'] == 'val']
    source_log = []
    def copy(source, target):
        source, target = Path(source), Path(target)
        if source.is_symlink() or not source.is_file(): raise ValueError(f"Regular source file required: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists(): raise ValueError(f"Refusing overwrite: {target}")
        shutil.copyfile(source, target)
        if digest(source) != digest(target): raise ValueError("Copy hash mismatch")
        row = {"source": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
               "destination": str(target.relative_to(output)), "sha256": digest(source), "bytes": source.stat().st_size}
        source_log.append(row); return row
    checks = []
    for identity, spec in SPECS.items():
        package = output / spec['run_id']; package.mkdir()
        start = len(source_log)
        source_dir = ROOT / 'ml/outputs/runs/p3_vision_20261018/search' / spec['architecture'] / spec['trial'] / 'attempt_01'
        export_dir = P4A / 'runtime_benchmark' / spec['export']
        # Safe metadata inspection only; no forward, optimizer, deserialization of pickle/joblib.
        import torch
        checkpoint = torch.load(ROOT / FROZEN_IDENTITIES[identity]['path'], map_location='cpu', weights_only=True)
        if checkpoint.get('class_to_idx') != CLASS_TO_IDX or checkpoint.get('seed') != 42:
            raise ValueError("Checkpoint real class mapping/seed mismatch")
        del checkpoint
        copy(export_dir / 'model.onnx', package / 'model.onnx')
        for name, dest in {'config.json':'evidence/source_config.json', 'selection_log.json':'evidence/trial_selection_log.json',
                           'artifact_manifest.json':'evidence/source_training_artifact_manifest.json',
                           'predictions_validation.csv':'validation/predictions_validation.csv',
                           'validation_metrics.json':'validation/validation_metrics.json', 'class_report.json':'validation/class_report.json'}.items():
            copy(source_dir / name, package / dest)
        copy(ROOT / 'ml/outputs/runs/p3_vision_20261018/selection_log.json', package / 'evidence/selection_log.json')
        copy(export_dir / 'benchmark_manifest.json', package / 'evidence/source_export_benchmark_manifest.json')
        copy(export_dir / 'export_attempt.json', package / 'evidence/source_export_attempt.json')
        copy(P4A / f'export_{identity}.json', package / 'evidence/source_export_result.json')
        copy(P4A / f'parity_{identity}.json', package / 'validation/p4a100_parity.json')
        copy(P4A / 'validation/validation_manifest.json', package / 'validation/p4a100_annotations.json')
        copy(P4A / 'core/preflight_attestation.json', package / 'evidence/p4a_preflight_attestation.json')
        copy(P4A / 'environment_snapshot.json', package / 'evidence/p4a_environment.json')
        for name in ('completion.json', 'provenance_before.json', 'provenance_after.json', 'protocol.json', 'source_manifest.json'):
            copy(P4B / name, package / 'evidence' / ('p4b_' + name))
        copy(P4B / 'verification/independent_cached_audit.json', package / 'evidence/p4b_cached_audit.json')
        copy(P4B / 'verification/closure_integrity.json', package / 'evidence/p4b_closure_integrity.json')
        for filename in ('ml/vision/train_hpo.py', 'ml/experiments/comparator_common.py', 'ml/configs/p4_protocol.json',
                         'ml/experiments/p4_core.py', 'ml/experiments/run_p4.py', 'ml/experiments/p4_preflight.py',
                         'ml/experiments/package_candidates.py', 'ml/tests/test_candidate_package.py'):
            copy(ROOT / filename, package / 'evidence/source_snapshot' / filename)
        clean = read_cached_predictions(P4B / 'cache/predictions.sqlite3', identity, FROZEN_IDENTITIES[identity]['sha256'], 'clean', 3657)
        for row in clean:
            source = source_by_id.get(row['source_id'])
            if source is None or int(source['class_id'][1:]) != row['true_label_index']:
                raise ValueError("Clean cached source/annotation mismatch")
            row.update(driver_id=source['driver_id'], filename=source['filename'], class_id=source['class_id'], training_label=source['class_name'])
        write_csv(package / 'predictions_test_clean.csv', clean)
        with (source_dir / 'predictions_validation.csv').open() as stream: saved_validation = list(csv.DictReader(stream))
        if len(saved_validation) != 2868: raise ValueError("Full validation prediction count mismatch")
        annotations, saved, diagnostic = stable_smoke(validation_metadata, saved_validation)
        if diagnostic['filename_sha256'] != SMOKE_SHA or diagnostic['source_ids_sha256'] != SMOKE_SOURCE_SHA:
            raise ValueError("Official stable200 membership SHA mismatch")
        write_csv(package / 'validation/stable200_annotations.csv', annotations)
        write_csv(package / 'validation/stable200_saved_predictions.csv', saved)
        write_json(package / 'validation/saved_prediction_diagnostic.json', diagnostic)
        parity = read_json(P4A / f'parity_{identity}.json')
        if parity['status'] != 'COMPLETED' or parity['result']['status'] != 'PASS' or not parity['result']['argmax_equal'] or len(parity['result']['validation_predictions']) != 100:
            raise ValueError("Original P4-A100 parity evidence invalid")
        if parity['result']['tensor_sha256'] != attestation['validation_tensor_sha256']:
            raise ValueError("Original P4-A100 tensor binding mismatch")
        labels = {row['class_id']: row['class_name'] for row in validation_metadata}
        if labels['c0'] != 'normal_driving': raise ValueError("Training c0 label mismatch")
        write_json(package / 'class_metadata.json', {'classes': CLASSES, 'class_to_idx': CLASS_TO_IDX,
            'training_labels': labels, 'runtime_aliases': {'c0': 'safe_driving'}, 'safe_class': 'c0',
            'meaning': 'Runtime alias does not rename the original training label normal_driving.'})
        write_json(package / 'runtime_manifest.json', {'manifest_version':1, 'kind':'vision_classifier', 'run_id':package.name,
            'architecture':spec['architecture'], 'model':{'path':'model.onnx','format':'onnx','sha256':spec['onnx_sha256']},
            'input':{'shape':[1,3,224,224],'dtype':'float32','layout':'NCHW','color':'RGB'},
            'preprocess':'rgb_resize_224_bilinear_no_crop_div255_imagenet', 'output':{'kind':'logits','shape':[1,10]},
            'classes':CLASSES, 'class_to_idx':CLASS_TO_IDX, 'safe_class':'c0',
            'contract_smoke_set':{'split':'val','selection':'Each class sorted by filename, first 20; same stable200 membership.',
                'n':200,'sample_ids_sha256':SMOKE_SHA,'rule':'per_class_mode_equals_label'},
            'provenance':{'source_run_id':'p3_vision_20261018','source_trial_id':spec['trial'], 'source_commit':HEAD,
                'checkpoint_sha256':FROZEN_IDENTITIES[identity]['sha256'], 'graph_batch':'dynamic N',
                'input_name':'input','output_name':'logits','seed':42,'training_c0_label':'normal_driving','runtime_c0_alias':'safe_driving'}})
        write_json(package / 'evaluation_metrics.json', {'identity':identity,'role':spec['role'], 'source_run_id':'p4b_20261022',
            'validation':read_json(source_dir / 'validation_metrics.json'), 'clean_test_and_stress':metrics['models'][identity],
            'runtime':metrics['runtime'][identity], 'limitations':metrics['limitations'],
            'prediction_semantics':{'test':'Original FP32 cached raw logits plus derived float64 softmax probabilities; c0-c9 order.',
                'validation':'Original saved P3 PyTorch logits/probabilities, full2868; not new inference.'},
            'provider_load_forward':'NOT_RUN','official_stable200_behavior':'NOT_RUN','system_integration':'BLOCKED_NOT_IMPLEMENTED',
            'new_training':False,'new_exports':False,'new_inference':False,'qc':'REMOVED_FROM_SCOPE'})
        write_json(package / 'evidence/provenance.json', {'candidate_package':True,'deployment_eligible':False,
            'identity':identity,'packaging_action':'COPY_EXISTING_P4A_ONNX_NO_REEXPORT','system_contract':pinned,
            'source_checkpoint':FROZEN_IDENTITIES[identity], 'original_export_flags_preserved':{'candidate_package':False,'deployment_eligible':False},
            'historical_paths':'Informational source identifiers; no runtime access outside this package is required.',
            'package_loading_dependencies':['model.onnx','runtime_manifest.json'], 'p4_binding':completion['binding'],
            'p4a100_parity':'REUSED_AND_HASH_VERIFIED; 100 val IDs,211 repeated appearances, distinct from stable200.',
            'stable200':'SAVED_VALIDATION_PREDICTION_DIAGNOSTIC only; official provider behavior NOT_RUN.',
            'git_at_packaging':before['git'],'reproducibility':'Dirty source snapshot/hash traceability; no independent retraining or full numerical rerun.'})
        (package / 'model_card.md').write_text(f'''# {spec['architecture']} candidate — {identity}\n\nRole: {spec['role']} frozen by validation; seed42, {spec['trial']}.\n\nThis directory copies the original P4A FP32 ONNX unchanged. Original benchmark/export records retain candidate_package=false and deployment_eligible=false; those records describe the earlier export. This P5 delivery is a candidate package, not deployment approval.\n\nInput: RGB, direct PIL bilinear224×224, no crop, divide255, ImageNet mean [0.485,0.456,0.406] / std [0.229,0.224,0.225], NCHW float32. Graph input/output names input/logits, dynamic batch N; manifest describes one request [1,3,224,224]→[1,10]. No graph softmax.\n\nclass_to_idx is the actual c0:0 through c9:9. Training c0 label is normal_driving; runtime safe_driving is an alias. Raw outputs are logits.\n\nEvidence: full2868 saved validation predictions,3657 clean cached test predictions with source/driver IDs, clean per-class metrics, stress stability, six-round CPU ORT runtime, frozen validation selection and source hashes. P4A100 parity is original reused evidence; stable200 is only a saved-prediction diagnostic. No new forward/held-out inference, export, benchmark or training occurred.\n\nManifest/schema/hash/static graph checks can pass. Current provider does not consume this manifest; provider_load_forward=NOT_RUN, official stable200 behavior=NOT_RUN, system_integration=BLOCKED_NOT_IMPLEMENTED. Future Task10A integration is outside this delivery.\n\nLimitations: four test drivers; historical test exposure; source-domain results do not establish frontal-camera, live capture-to-render, edge, vehicle-grade or safety performance. Stress label validity is unverified and manual QC is REMOVED_FROM_SCOPE. See evaluation_metrics.json for exact existing numbers and full limitations.\n\nReproduction: inspect artifact_manifest.json and evidence/source_hashes.json; validate using the pinned runtime_manifest.py/schema at commit2745348 and inspect graph statically. Source snapshots/config/environment are evidence, not active dependencies. P3 training, P4A export/parity and P4B numerical execution are historical, not rerun by P5. Dirty source snapshots support traceability, not a clean-commit or bitwise guarantee.\n''')
        write_json(package / 'evidence/source_hashes.json', {'copied_sources':source_log[start:], 'checkpoint_sha256':FROZEN_IDENTITIES[identity]['sha256'],
            'onnx_sha256':spec['onnx_sha256'], 'metadata_sha256':digest(METADATA), 'p4_cache_database_sha256':digest(P4B / 'cache/predictions.sqlite3'),
            'p4_cache_wal_sha256':digest(P4B / 'cache/predictions.sqlite3-wal'), 'prediction_rows_verified':3657,
            'validation_rows':2868,'stable200_rows':200,'parity_distinct_val_ids':100,'new_inference':False})
        seal_package(package); checks.append(validate_candidate(package, contract))
        deterministic_zip(package, output / f'{package.name}.zip')
    telemetry = output / 'telemetry_research_evidence'; telemetry.mkdir()
    source = ROOT / 'ml/outputs/runs/p3_telemetry_20261018/xgboost/xgboost_02'; start = len(source_log)
    for name in ('config.json','selection_log.json','validation_metrics.json','class_report.json','train_statistics.json','predictions_validation.csv'):
        copy(source / name, telemetry / name)
    copy(ROOT / 'ml/outputs/runs/p3_telemetry_20261018/selection_log.json', telemetry / 'frozen_selection_log.json')
    xgb = FROZEN_IDENTITIES['XGB-HPO42']
    rows = read_cached_predictions(P4B / 'cache/predictions.sqlite3','XGB-HPO42',xgb['sha256'],'D0',4500)
    write_csv(telemetry / 'predictions_test_clean.csv', rows)
    write_json(telemetry / 'evaluation_metrics.json', {'identity':'XGB-HPO42','class_order':['Safe','Aggressive','Distracted'],
        'source_run_id':'p4b_20261022','clean_test_and_stress':metrics['models']['XGB-HPO42'],'limitations':metrics['limitations'],
        'candidate_package':False,'runtime_candidate':'BLOCKED_NO_IMPORTER_OR_SCHEMA','checkpoint_copied':False,
        'new_export':False,'new_inference':False,'prediction_semantics':'Cached original probabilities; float64 normalized for table, no logits.'})
    write_json(telemetry / 'source_hashes.json', {'copied_sources':source_log[start:], 'checkpoint_path':xgb['path'], 'checkpoint_sha256':digest(ROOT/xgb['path']),
        'p4_cache_database_sha256':digest(P4B/'cache/predictions.sqlite3'),'p4_completion_sha256':digest(P4B/'completion.json'),
        'scope':'Research evidence only; no joblib load/copy, no runtime manifest, no RF/LR candidate.'})
    seal_package(telemetry)
    after = preservation_snapshot()
    if after['hashes'] != before['hashes']: raise ValueError("Preexisting protected/source evidence changed")
    write_json(verification / 'preservation_after.json', {'status':'PASS','before':before['hashes'],'after':after['hashes'],'git':after['git']})
    write_json(verification / 'source_copy_log.json', source_log)
    result = {'status':'PASS','scope':'P5_COPY_ONLY_PACKAGING','packages':checks,'archives':[{'file':p.name,'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(output.glob('*.zip'))],
        'telemetry':'RESEARCH_EVIDENCE_ONLY_NO_RUNTIME_CANDIDATE', 'protected_files_unchanged':len(before['hashes']),
        'model_forwards':0,'new_heldout_inference':0,'new_exports':0,'new_training':0,'new_benchmarks':0,
        'system_integration':'BLOCKED_NOT_IMPLEMENTED','provider_load_forward':'NOT_RUN'}
    write_json(verification / 'final_package_check.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build','verify'])
    parser.add_argument('--run-dir', type=Path, default=ROOT/'ml/outputs/runs/p5_candidates_20261023')
    args = parser.parse_args()
    if args.action == 'build': result = build_delivery(args.run_dir)
    else:
        contract, _ = load_pinned_contract(args.run_dir/'verification/pinned_contract')
        result = [validate_candidate(args.run_dir/spec['run_id'], contract) for spec in SPECS.values()]
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
