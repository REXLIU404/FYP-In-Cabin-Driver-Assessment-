"""P4-A validation-only export/parity and bounded CPU throughput workers.

Run workers under the P4 supervisor: export/parity each <=120s, combined
prepare/export/parity <=600s; generation/throughput combined <=600s.
No held-out observation reader, training entrypoint, or deployment packaging.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))
RUN = ROOT / 'ml/outputs/runs/p4a_20261021'
DATA = Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-')
METADATA_SHA = 'b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4'
CLASSES = [f'c{i}' for i in range(10)]
MEAN = np.array([.485, .456, .406], dtype=np.float32)[:, None, None]
STD = np.array([.229, .224, .225], dtype=np.float32)[:, None, None]
IDENTITIES = {
    'MN-HPO42': {'arch': 'mobilenet_v3_large', 'directory': 'mobilenet_v3_large_search006_seed42',
        'checkpoint': 'ml/outputs/runs/p3_vision_20261018/search/mobilenet_v3_large/search_006/attempt_01/checkpoint.pt',
        'sha256': 'bc96e7a230de6391820b1e04e7480087841680ae6cc1b6e73cba42b25eb67295'},
    'RN-HPO42': {'arch': 'resnet18', 'directory': 'resnet18_search004_seed42',
        'checkpoint': 'ml/outputs/runs/p3_vision_20261018/search/resnet18/search_004/attempt_01/checkpoint.pt',
        'sha256': '008d831c98ea5e4b6c5c821787b3dc9a1dcbc6ca47a74dd1d8f7110eb4ac7d20'},
    'MN-STABLE': {'arch': 'mobilenet_v3_large', 'checkpoint': 'ml/outputs/vision/mobilenetv3_large_vision.pt',
        'sha256': '196ca7b151d84e0c4a8eac87128da9dd8f22c894984a991ef611536bb523e7c7',
        'onnx': 'ml/outputs/vision/mobilenetv3_large_vision.onnx',
        'onnx_sha256': 'b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf'},
}
PROTECTED = {
    IDENTITIES['MN-STABLE']['checkpoint']: IDENTITIES['MN-STABLE']['sha256'],
    IDENTITIES['MN-STABLE']['onnx']: IDENTITIES['MN-STABLE']['onnx_sha256'],
    'ml/outputs/telemetry/xgb_telemetry.json': '9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07',
    'docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md': '0731ebfbe8c49ef08452a23688a6fce26a13f9c3497d53ec898da91d9866daf0',
}


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def reject_symlink(path):
    if any(p.is_symlink() for p in [Path(path), *Path(path).parents]):
        raise ValueError('Symlink path prohibited')


def protected_snapshot():
    actual = {name: sha256(ROOT / name) for name in PROTECTED}
    if actual != PROTECTED:
        raise ValueError('Protected file hash mismatch')
    return actual


def select_validation(rows):
    rows = [dict(row) for row in rows if row['split'] == 'val']
    ids = [f"vision-v1:{row['class_id']}/{row['filename']}" for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate validation source ID')
    selected = []
    for label in CLASSES:
        candidates = [r for r in rows if r['class_id'] == label]
        if len(candidates) < 10:
            raise ValueError(f'Insufficient validation class {label}')
        candidates.sort(key=lambda r: hashlib.sha256(f"42|runtime-val|vision-v1:{r['class_id']}/{r['filename']}".encode()).hexdigest())
        selected.extend(candidates[:10])
    return selected


def preprocess(image):
    rgb = image.convert('RGB').resize((224, 224), Image.Resampling.BILINEAR)
    values = np.asarray(rgb, dtype=np.float32).transpose(2, 0, 1) / np.float32(255)
    return np.ascontiguousarray((values - MEAN) / STD, dtype=np.float32)


def logits(values, count):
    values = np.asarray(values)
    if values.dtype != np.float32 or values.shape != (count, 10) or not np.isfinite(values).all():
        raise ValueError('Malformed FP32 finite logits')
    return values


def softmax(values):
    values = values.astype(np.float64)
    values = np.exp(values - values.max(axis=1, keepdims=True))
    return values / values.sum(axis=1, keepdims=True)


def check_parity(bank, reference, runtime):
    if len(bank) != 100:
        raise ValueError('Parity requires exactly validation100')
    plan = [bank[i:i + 1] for i in range(100)]
    plan += [bank[i:i + 32] for i in range(0, 100, 32)] + [bank[:2], bank[:9]]
    maximum_abs = maximum_relative = maximum_probability = 0.0
    records, single_predictions = [], []
    for index, batch in enumerate(plan):
        expected = logits(reference(batch), len(batch))
        actual = logits(runtime(batch), len(batch))
        error = np.abs(actual.astype(np.float64) - expected.astype(np.float64))
        if np.any(error > 1e-4 + 1e-4 * np.abs(expected)) or not np.array_equal(actual.argmax(1), expected.argmax(1)):
            raise ValueError(f'ONNX parity failure in batch {index}, N={len(batch)}')
        absolute = float(error.max())
        relative = float((error / np.maximum(np.abs(expected), np.finfo(np.float32).tiny)).max())
        probability = float(np.abs(softmax(actual) - softmax(expected)).max())
        maximum_abs = max(maximum_abs, absolute)
        maximum_relative = max(maximum_relative, relative)
        maximum_probability = max(maximum_probability, probability)
        records.append({'batch': index, 'N': len(batch), 'max_absolute_error': absolute,
                        'max_relative_error': relative, 'max_probability_error': probability})
        if index < 100:
            single_predictions.append(actual)
    return {'status': 'PASS', 'atol': 1e-4, 'rtol': 1e-4, 'argmax_equal': True,
            'samples_compared': 211, 'max_absolute_error': maximum_abs,
            'max_relative_error': maximum_relative, 'max_probability_error': maximum_probability,
            'batches': records}, np.concatenate(single_predictions)


def reserve_export(run, identity):
    if identity == 'MN-STABLE':
        raise ValueError('Cannot export stable reference')
    spec = IDENTITIES[identity]
    directory = Path(run) / 'runtime_benchmark' / spec['directory']
    reject_symlink(directory)
    directory.mkdir(parents=True, exist_ok=False)
    # An attempt is consumed even if torch/export/checker later fails. Never retry.
    write_json(directory / 'export_attempt.json', {'identity': identity, 'maximum_attempts': 1})
    return directory / 'model.onnx'


def validate_graph(model):
    import onnx
    graph = model.graph
    if any(t.data_location == onnx.TensorProto.EXTERNAL or t.external_data for t in graph.initializer):
        raise ValueError("ONNX external weights prohibited")
    onnx.checker.check_model(model)
    def shape(value, name, tail):
        tensor = value.type.tensor_type
        dims = tensor.shape.dim
        if value.name != name or tensor.elem_type != onnx.TensorProto.FLOAT or len(dims) != len(tail) + 1:
            raise ValueError('ONNX FP32 I/O contract')
        if not dims[0].dim_param or any(d.dim_value != size for d, size in zip(dims[1:], tail)):
            raise ValueError('ONNX dynamic N/shape contract')
    if len(graph.input) != 1 or len(graph.output) != 1:
        raise ValueError('ONNX requires one input and logits output')
    shape(graph.input[0], 'input', [3, 224, 224])
    shape(graph.output[0], 'logits', [10])
    if any(t.data_location == onnx.TensorProto.EXTERNAL or t.external_data for t in graph.initializer):
        raise ValueError('ONNX external weights prohibited')
    # Reject all Softmax nodes, including an output wrapped in Identity/Cast.
    if any(node.op_type in {'Softmax', 'LogSoftmax'} for node in graph.node):
        raise ValueError('ONNX output must be raw logits, no Softmax/LogSoftmax')


def measure_throughput(bank, runtime):
    if len(bank) != 100:
        raise ValueError('Throughput requires validation100')
    rounds, timings = [], []
    for round_id in range(3):
        inputs = [bank[i:i + 32] for i in range(0, 100, 32)]
        raw = []
        started = time.perf_counter_ns()
        for batch in inputs:
            tick = time.perf_counter_ns()
            output = runtime(batch)
            raw.append(time.perf_counter_ns() - tick)
            logits(output, len(batch))
        elapsed = time.perf_counter_ns() - started
        rounds.append({'round': round_id, 'warmup': round_id == 0, 'images': 100,
                       'batch_sizes': [32, 32, 32, 4], 'batch_nanoseconds': raw,
                       'loop_nanoseconds': elapsed, 'images_per_second': 100e9 / elapsed})
        if round_id:
            timings.extend(raw)
    measured_ns = sum(r['loop_nanoseconds'] for r in rounds[1:])
    return {'scope': 'BOUNDED_VAL_ONLY_THROUGHPUT_PREFLIGHT', 'batch_size': 32,
            'warmup_images': 100, 'measured_images': 200, 'rounds': rounds,
            'batch_nanoseconds': timings, 'p50_batch_ms': float(np.percentile(timings, 50, method='linear') / 1e6),
            'p95_batch_ms': float(np.percentile(timings, 95, method='linear') / 1e6),
            'images_per_second': 200e9 / measured_ns, 'seconds_per_100': measured_ns / 2e9,
            'formal_runtime_benchmark_completed': False}


def project_budget(throughput, generation_seconds_per_1900):
    if set(throughput) != set(IDENTITIES) or generation_seconds_per_1900 <= 0:
        raise ValueError('Projection requires all three vision identities and measured generator timing')
    by_model = {}
    for name, item in throughput.items():
        rate = item['seconds_per_100']
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError('Invalid throughput rate')
        by_model[name] = {'clean_seconds': rate * 36.57 * 1.25,
                          'stress_seconds': rate * 36.57 * 18 * 1.25}
        by_model[name]['fits_model_caps'] = by_model[name]['clean_seconds'] <= 400 and by_model[name]['stress_seconds'] <= 2400
    clean = sum(x['clean_seconds'] for x in by_model.values())
    stress = sum(x['stress_seconds'] for x in by_model.values())
    generation = generation_seconds_per_1900 / 1900 * 69483 * 1.25
    total = generation + clean + stress + 600 + 1200 + 1800 + 1200
    return {'vision_input_count': 69483, 'vision_prediction_count': 208449, 'margin': 1.25,
            'by_model': by_model, 'vision_clean_seconds': clean, 'vision_stress_seconds': stress,
            'generation_seconds': generation, 'total_with_other_stage_caps_seconds': total,
            'stage_caps_seconds': {'preflight': 600, 'preparation': 1200, 'vision_clean': 1200,
                                  'vision_stress': 7200, 'telemetry': 1200, 'runtime': 1800, 'aggregation': 1200},
            'per_model_caps_seconds': {'vision_clean': 400, 'vision_stress': 2400},
            'proposed_total_cap_seconds': 14400,
            'fits_proposed_caps': total <= 14400 and generation <= 1200 and clean <= 1200 and stress <= 7200 and all(x['fits_model_caps'] for x in by_model.values()),
            'uncertainty': 'Extrapolation from 100 validation sources, excludes formal cache/QC write costs; not a measured full-run duration.',
            'formal_runtime_benchmark_completed': False}


def check_resources(path, *, available_ram=None, free_disk=None):
    import psutil
    available_ram = psutil.virtual_memory().available if available_ram is None else available_ram
    free_disk = psutil.disk_usage(path).free if free_disk is None else free_disk
    if available_ram < 8 * 1024**3:
        raise RuntimeError('BLOCKED: available RAM below 8 GiB')
    if free_disk < 20 * 1024**3:
        raise RuntimeError('BLOCKED: free disk below 20 GiB')
    return {'available_ram_bytes': available_ram, 'free_disk_bytes': free_disk}


class ValidationAccess:
    """An OS audit-hook plus explicit whitelist; metadata membership only, no test reads."""
    def __init__(self, paths):
        self.allowed = {str(Path(p).resolve()) for p in paths}
        self.accessed = []

    def checked_image(self, path):
        path = Path(path)
        reject_symlink(path)
        if str(path.resolve()) not in self.allowed:
            raise PermissionError('Observation outside frozen validation whitelist')
        self.accessed.append(str(path.resolve()))
        return path

    def audit(self, event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(args[0]))
        if path.name == 'telemetry_test.csv':
            raise PermissionError('Held-out telemetry is forbidden in P4-A')
        if path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'} and str(path.resolve()) not in self.allowed:
            raise PermissionError('Image outside frozen validation whitelist')


def frozen_validation():
    metadata = DATA / 'eda_outputs/processed/vision/vision_metadata_with_split.csv'
    if sha256(metadata) != METADATA_SHA:
        raise ValueError('Frozen metadata hash mismatch')
    with metadata.open(newline='') as stream:
        rows = [dict(row, source_row=i) for i, row in enumerate(csv.DictReader(stream))]
    groups = {split: {row['driver_id'] for row in rows if row['split'] == split} for split in ['train', 'val', 'test']}
    if any(groups[a] & groups[b] for a, b in [('train', 'val'), ('train', 'test'), ('val', 'test')]):
        raise ValueError('Frozen split drivers overlap')
    if {split: sum(row['split'] == split for row in rows) for split in groups} != {'train': 15899, 'val': 2868, 'test': 3657}:
        raise ValueError('Frozen split membership count changed')
    selected = select_validation(rows)
    guard = ValidationAccess([row['image_path'] for row in selected])
    sys.addaudithook(guard.audit)
    return selected, guard


def prepare(run):
    selected, guard = frozen_validation()
    directory = run / 'validation'
    directory.mkdir(exist_ok=False)
    bank, records, raw = [], [], []
    for row in selected:
        path = guard.checked_image(row['image_path'])
        image_sha = sha256(path)
        tick = time.perf_counter_ns()
        with Image.open(path) as image:
            tensor = preprocess(image)
        raw.append(time.perf_counter_ns() - tick)
        source_id = f"vision-v1:{row['class_id']}/{row['filename']}"
        bank.append(tensor)
        records.append({**row, 'source_id': source_id, 'image_sha256': image_sha,
                        'tensor_sha256': hashlib.sha256(tensor.tobytes()).hexdigest()})
    bank = np.ascontiguousarray(bank, dtype=np.float32)
    np.save(directory / 'validation_bank.npy', bank, allow_pickle=False)
    manifest = {'split': 'val', 'seed': 42, 'selection': '10 per class ordered by SHA256(42|runtime-val|source_id)',
        'class_to_idx': {c: i for i, c in enumerate(CLASSES)}, 'count': 100,
        'metadata_sha256': METADATA_SHA, 'records': records,
        'ordered_source_id_sha256': hashlib.sha256('\n'.join(r['source_id'] for r in records).encode()).hexdigest(),
        'bank_file_sha256': sha256(directory / 'validation_bank.npy'),
        'tensor_sha256': hashlib.sha256(bank.tobytes()).hexdigest(),
        'preprocess_nanoseconds': raw, 'preprocess_seconds_per_100': sum(raw) / 1e9,
        'accessed_validation_paths': guard.accessed, 'test_images_opened': 0, 'test_telemetry_rows_read': 0}
    write_json(directory / 'validation_manifest.json', manifest)
    return {'count': 100, 'tensor_sha256': manifest['tensor_sha256'], 'preprocess_seconds_per_100': sum(raw) / 1e9}


def load_bank(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'validation_manifest.json').read_text())
    path = directory / 'validation_bank.npy'
    reject_symlink(path)
    if sha256(path) != manifest['bank_file_sha256']:
        raise ValueError('Validation bank file hash changed')
    bank = np.load(path, allow_pickle=False)
    if bank.shape != (100, 3, 224, 224) or bank.dtype != np.float32 or not bank.flags.c_contiguous or not np.isfinite(bank).all():
        raise ValueError('Invalid validation bank')
    if hashlib.sha256(bank.tobytes()).hexdigest() != manifest['tensor_sha256']:
        raise ValueError('Validation bank tensor hash changed')
    bank.flags.writeable = False
    return bank


def validate_checkpoint(saved, identity, names):
    spec = IDENTITIES[identity]
    if saved.get('arch') != spec['arch'] or saved.get('classes') != CLASSES:
        raise ValueError('Checkpoint architecture/classes mismatch')
    if identity != 'MN-STABLE' and (saved.get('seed') != 42 or saved.get('class_to_idx') != {c: i for i, c in enumerate(CLASSES)}):
        raise ValueError('Checkpoint seed/class_to_idx mismatch')
    if saved.get('idx_to_name') != names or names.get('c0') != 'normal_driving':
        raise ValueError('Checkpoint original label names mismatch')
    key = 'fc.weight' if spec['arch'] == 'resnet18' else 'classifier.3.weight'
    if saved['state_dict'][key].shape[0] != 10:
        raise ValueError('Checkpoint classifier head mismatch')


def torch_model(identity, run):
    import torch
    from torchvision import models
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    spec = IDENTITIES[identity]
    path = ROOT / spec['checkpoint']
    if sha256(path) != spec['sha256']:
        raise ValueError('Frozen checkpoint SHA mismatch')
    saved = torch.load(path, map_location='cpu', weights_only=True)
    records = json.loads((run / 'validation/validation_manifest.json').read_text())['records']
    names = {r['class_id']: r['class_name'] for r in records}
    validate_checkpoint(saved, identity, names)
    if spec['arch'] == 'resnet18':
        model = models.resnet18(weights=None)
        model.fc = torch.nn.Linear(model.fc.in_features, 10)
    else:
        model = models.mobilenet_v3_large(weights=None)
        model.classifier[-1] = torch.nn.Linear(model.classifier[-1].in_features, 10)
    model.load_state_dict(saved['state_dict'], strict=True)
    model.cpu().eval()
    return model


def onnx_path(identity, run):
    spec = IDENTITIES[identity]
    if identity == 'MN-STABLE':
        path = ROOT / spec['onnx']
        expected = spec['onnx_sha256']
    else:
        path = run / 'runtime_benchmark' / spec['directory'] / 'model.onnx'
        manifest = json.loads((path.parent / 'benchmark_manifest.json').read_text())
        if manifest['identity'] != identity or manifest['source_checkpoint_sha256'] != spec['sha256']:
            raise ValueError('Benchmark ONNX provenance mismatch')
        expected = manifest['onnx_sha256']
    reject_symlink(path)
    if sha256(path) != expected:
        raise ValueError('Benchmark ONNX hash mismatch')
    return path


def ort_session(path):
    import onnx
    import onnxruntime as ort
    validate_graph(onnx.load(path, load_external_data=False))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.add_session_config_entry('session.intra_op.allow_spinning', '0')
    options.add_session_config_entry('session.inter_op.allow_spinning', '0')
    session = ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
    if session.get_providers() != ['CPUExecutionProvider']:
        raise ValueError('Unexpected execution provider')
    return session


def export_model(run, identity):
    import torch
    import onnx
    target = reserve_export(run, identity)
    model = torch_model(identity, run)
    example = load_bank(run / 'validation')[:1].copy()
    tick = time.perf_counter_ns()
    with torch.inference_mode():
        torch.onnx.export(model, torch.from_numpy(example), str(target), export_params=True,
            opset_version=17, input_names=['input'], output_names=['logits'],
            dynamic_axes={'input': {0: 'N'}, 'logits': {0: 'N'}}, keep_initializers_as_inputs=False,
            dynamo=False, external_data=False)
    elapsed = time.perf_counter_ns() - tick
    validate_graph(onnx.load(target, load_external_data=False))
    if set(p.name for p in target.parent.iterdir()) != {'model.onnx', 'export_attempt.json'}:
        raise ValueError('Unexpected export sidecar')
    manifest = {'identity': identity, 'candidate_package': False, 'deployment_eligible': False,
        'source_checkpoint_path': str(ROOT / IDENTITIES[identity]['checkpoint']),
        'source_checkpoint_sha256': IDENTITIES[identity]['sha256'], 'onnx_path': str(target.resolve()),
        'onnx_sha256': sha256(target), 'onnx_bytes': target.stat().st_size,
        'input': {'name': 'input', 'dtype': 'float32', 'shape': ['N', 3, 224, 224]},
        'output': {'name': 'logits', 'dtype': 'float32', 'shape': ['N', 10], 'semantics': 'raw_logits'},
        'class_to_idx': {c: i for i, c in enumerate(CLASSES)}, 'export_nanoseconds': elapsed,
        'export': {'dynamo': False, 'opset': 17, 'external_data': False, 'export_params': True,
                   'keep_initializers_as_inputs': False}, 'scope': 'benchmark/evaluation-only'}
    write_json(target.parent / 'benchmark_manifest.json', manifest)
    return manifest


def parity_model(run, identity):
    import torch
    bank = load_bank(run / 'validation')
    model = torch_model(identity, run)
    session = ort_session(onnx_path(identity, run))
    def reference(batch):
        with torch.inference_mode():
            return model(torch.from_numpy(batch.copy())).numpy()
    report, predictions = check_parity(bank, reference, lambda x: session.run(['logits'], {'input': x})[0])
    records = json.loads((run / 'validation/validation_manifest.json').read_text())['records']
    report['validation_predictions'] = [dict(source_id=r['source_id'], class_id=r['class_id'], driver_id=r['driver_id'],
        predicted_class=CLASSES[int(logit.argmax())], logits=logit.tolist()) for r, logit in zip(records, predictions)]
    report['identity'] = identity
    report['tensor_sha256'] = hashlib.sha256(bank.tobytes()).hexdigest()
    if hashlib.sha256(load_bank(run / 'validation').tobytes()).hexdigest() != report['tensor_sha256']:
        raise ValueError('Shared bank changed during parity')
    return report


def throughput_model(run, identity):
    import psutil
    from threadpoolctl import threadpool_info
    parity = json.loads((run / f'parity_{identity}.json').read_text())
    if parity['result']['status'] != 'PASS':
        raise ValueError('Parity gate not passed')
    bank = load_bank(run / 'validation')
    baseline = psutil.Process().memory_info().rss
    tick = time.perf_counter_ns()
    session = ort_session(onnx_path(identity, run))
    load_ns = time.perf_counter_ns() - tick
    report = measure_throughput(bank, lambda x: session.run(['logits'], {'input': x})[0])
    report.update(identity=identity, session_load_nanoseconds=load_ns, rss_baseline_bytes=baseline,
                  rss_after_load_bytes=psutil.Process().memory_info().rss, threadpools=threadpool_info(),
                  tensor_sha256=hashlib.sha256(bank.tobytes()).hexdigest())
    load_bank(run / 'validation')  # Byte check after all worker calls.
    return report


def generation(run):
    from ml.experiments import e1_generators as e1
    selected, guard = frozen_validation()
    manifest = json.loads((run / 'validation/validation_manifest.json').read_text())
    if [r['source_row'] for r in manifest['records']] != [r['source_row'] for r in selected]:
        raise ValueError('Generator validation population mismatch')
    decode_times, generator_times, normalize_times = [], [], []
    total_started = time.perf_counter_ns()
    count = 0
    for row, frozen in zip(selected, manifest['records']):
        path = guard.checked_image(row['image_path'])
        if sha256(path) != frozen['image_sha256']:
            raise ValueError('Validation source image changed')
        tick = time.perf_counter_ns()
        with Image.open(path) as original:
            original = original.convert('RGB')
        decode_times.append(time.perf_counter_ns() - tick)
        variants = iter(e1.vision_variants(original, frozen['source_id'], row['driver_id'], source_split='val'))
        for _ in range(19):
            tick = time.perf_counter_ns()
            image, record = next(variants)
            generator_times.append(time.perf_counter_ns() - tick)
            tick = time.perf_counter_ns()
            tensor = preprocess(image)
            if not np.isfinite(tensor).all():
                raise ValueError('Generated non-finite validation tensor')
            normalize_times.append(time.perf_counter_ns() - tick)
            count += 1
    if count != 1900:
        raise ValueError('Validation generator count mismatch')
    return {'sources': 100, 'variants': count, 'source_split': 'val',
        'decode_nanoseconds': decode_times, 'generator_nanoseconds': generator_times,
        'normalize_nanoseconds': normalize_times, 'seconds_per_1900': (time.perf_counter_ns() - total_started) / 1e9,
        'normalization_seconds': sum(normalize_times) / 1e9, 'generation_seconds': sum(generator_times) / 1e9,
        'test_images_opened': 0, 'test_telemetry_rows_read': 0}


def git_snapshot():
    return {name: subprocess.check_output(command, cwd=ROOT, text=True).strip() for name, command in {
        'root': ['git', 'rev-parse', '--show-toplevel'], 'branch': ['git', 'branch', '--show-current'],
        'head': ['git', 'rev-parse', 'HEAD'], 'dirty': ['git', 'status', '--short'],
        'staged': ['git', 'diff', '--cached', '--name-only']}.items()}



def run_preflight(run, *, supervisor_factory=None):
    """One-shot supervisor owns every real worker and both cumulative stage caps."""
    if supervisor_factory is None:
        from ml.experiments.p4_core import BudgetSupervisor
        supervisor_factory = BudgetSupervisor
    run = Path(run)
    write_json(run / 'preflight_invocation.json', {
        'scope': 'P4-A validation/synthetic only', 'maximum_exports': 2,
        'stage_caps': {'preflight': 600, 'timing': 600}, 'total_seconds': 1200,
        'source_sha256': sha256(Path(__file__)), 'started_unix_seconds': time.time(),
        'formal_runtime_benchmark_completed': False})
    supervisor = None
    status, error = 'COMPLETED', None
    records = []
    try:
        supervisor = supervisor_factory(run / 'budget', output_root=run, total_seconds=1200,
            stage_caps={'preflight': 600, 'timing': 600})
        plan = [('prepare', None, 'preflight')]
        plan.extend(('export', identity, 'preflight') for identity in ['MN-HPO42', 'RN-HPO42'])
        plan.extend(('parity', identity, 'preflight') for identity in IDENTITIES)
        plan.extend(('throughput', identity, 'timing') for identity in IDENTITIES)
        plan.extend([('generation', None, 'timing'), ('projection', None, 'timing')])
        for action, identity, stage in plan:
            command = ['/usr/bin/env', 'P4_BUDGET_WORKER=1', sys.executable, '-B', str(Path(__file__).resolve()),
                       action, '--run-dir', str(run)]
            if identity:
                command.extend(['--identity', identity])
            cap = 600 if action == 'generation' else 120
            records.append(supervisor.run(command, stage=stage,
                model=f'{action}:{identity or "shared"}', model_cap_seconds=cap,
                worker_cap_seconds=cap, rss_cap_bytes=8 * 1024**3, cwd=ROOT))
    except BaseException as caught:
        status, error = 'FAILED_OR_BLOCKED', f'{type(caught).__name__}: {caught}'
        raise
    finally:
        write_json(run / 'preflight_summary.json', {'status': status, 'error': error,
            'completed_workers': len(records), 'stage_caps': {'preflight': 600, 'timing': 600},
            'budget_state': str(run / 'budget/budget_state.json'), 'records': records,
            'formal_runtime_benchmark_completed': False, 'test_images_opened': 0,
            'test_telemetry_rows_read': 0})
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run-preflight', 'prepare', 'export', 'parity', 'throughput', 'generation', 'projection'])
    parser.add_argument('--identity', choices=list(IDENTITIES))
    parser.add_argument('--run-dir', type=Path, default=RUN)
    args = parser.parse_args(argv)
    if args.run_dir.resolve() != RUN.resolve():
        raise ValueError('Only approved p4a_20261021 evidence directory permitted')
    run = args.run_dir.resolve()
    reject_symlink(run)
    if not run.is_dir():
        raise ValueError('Root supervisor must initialize run directory')
    if args.action in {'export', 'parity', 'throughput'} and args.identity is None:
        parser.error('--identity required for model action')
    if args.action == 'run-preflight':
        check_resources(run)
        run_preflight(run)
        return 0
    if os.environ.get('P4_BUDGET_WORKER') != '1':
        raise ValueError('Worker requires run-preflight budget supervision')
    resources = check_resources(run)
    before = protected_snapshot()
    git = git_snapshot()
    if git['branch'] != 'fyp2/ml-training' or git['staged']:
        raise ValueError('Wrong branch or staged work')
    selected, guard = frozen_validation()
    result_path = run / (f'{args.action}_{args.identity}.json' if args.identity else f'{args.action}.json')
    with result_path.open('x') as stream:
        started = time.perf_counter_ns()
        result = None
        error = None
        try:
            if args.action == 'prepare': result = prepare(run)
            elif args.action == 'export': result = export_model(run, args.identity)
            elif args.action == 'parity': result = parity_model(run, args.identity)
            elif args.action == 'throughput': result = throughput_model(run, args.identity)
            elif args.action == 'generation': result = generation(run)
            else:
                throughputs = {name: json.loads((run / f'throughput_{name}.json').read_text())['result'] for name in IDENTITIES}
                timing = json.loads((run / 'generation.json').read_text())['result']['seconds_per_1900']
                result = project_budget(throughputs, timing)
        except BaseException as caught:
            error = f'{type(caught).__name__}: {caught}'
            raise
        finally:
            after = protected_snapshot()
            from threadpoolctl import threadpool_info
            json.dump({'status': 'FAILED' if error else 'COMPLETED', 'error': error, 'result': result,
                'action': args.action, 'identity': args.identity, 'resources': resources,
                'elapsed_nanoseconds': time.perf_counter_ns() - started,
                'protected_before': before, 'protected_after': after, 'git_before': git, 'git_after': git_snapshot(),
                'source_sha256': sha256(Path(__file__)), 'threadpools': threadpool_info(),
                'ru_maxrss_native': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'ru_maxrss_units': 'bytes on macOS; whole worker lifetime high-water mark',
                'sampled_rss': 'Parent BudgetSupervisor 20ms process-tree samples',
                'test_images_opened': 0, 'test_telemetry_rows_read': 0}, stream, indent=2, allow_nan=False)
            stream.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
