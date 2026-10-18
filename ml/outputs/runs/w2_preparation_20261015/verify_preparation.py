"""Week 2 preparation evidence only: no classifier fit, prediction or export.

Run from the repository root with ./.venv/bin/python -B <this file>.
Writes preparation_evidence.json beside this file only after all checks pass.
Source datasets, deployed artifacts and existing reports remain read-only.
"""
import ast
import base64
import binascii
import hashlib
import importlib.metadata as metadata
import io
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import onnx
import pandas as pd
import torch
from PIL import Image
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[4]
RUN = Path(__file__).resolve().parent
DATA = Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-')
FEATURES = ['speed_kmph', 'accel_x', 'accel_y', 'brake_pressure',
            'steering_angle', 'throttle', 'lane_deviation', 'headway_distance']
LABELS = ['Safe', 'Aggressive', 'Distracted']
CLASSES = [f'c{i}' for i in range(10)]
CHECKS = []


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check(name, condition, actual):
    CHECKS.append({'check': name, 'passed': bool(condition), 'actual': actual})
    if not condition:
        raise RuntimeError(f'{name}: {actual}')


def snapshot(path):
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def main():
    check('cwd', Path.cwd().resolve() == ROOT, str(Path.cwd()))
    check('branch', git('branch', '--show-current') == 'fyp2/ml-training', git('branch', '--show-current'))
    config = json.loads((RUN / 'config.json').read_text())
    hashes = {path: sha(Path(path) if Path(path).is_absolute() else ROOT / path)
              for path in config['protected_hashes']}
    for path, expected in config['protected_hashes'].items():
        check(f'hash:{path}', hashes[path] == expected, hashes[path])
    evidence = {
        'run_id': RUN.name, 'phase': 'P0_WEEK2_PREPARATION',
        'checked_at': datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).isoformat(),
        'command': f'./.venv/bin/python -B {Path(__file__).relative_to(ROOT)}',
        'git': {'branch': git('branch', '--show-current'), 'head': git('rev-parse', 'HEAD'),
                'dirty_state': git('status', '--short'), 'staged_paths': git('diff', '--cached', '--name-only')},
        'versions': {'python': platform.python_version(), 'platform': platform.platform(),
                     **{name: metadata.version(name) for name in ['torch', 'torchvision', 'scikit-learn',
                        'xgboost', 'onnx', 'onnxruntime', 'pandas', 'numpy', 'Pillow']}},
        'device': {'mps_built': torch.backends.mps.is_built(), 'mps_available': torch.backends.mps.is_available(),
                   'cuda_available': torch.cuda.is_available(), 'training_device': 'NOT_SELECTED'},
        'classifier_training_runs': 0, 'hpo_trials': 0, 'test_prediction_runs': 0,
        'e1_runs': 0, 'protected_hashes_before': hashes, 'checks': CHECKS,
        'gitignore_before_change': config.get('gitignore_before_change', []),
        'authorities': {},
    }
    for name in ['CODEX_ML_TRACK_PROMPT.md', 'CODEX_ML_TRACK_ADDENDUM_R4.md']:
        ref = f'fyp2/live-system:docs/fyp2/review/{name}'
        content = subprocess.check_output(['git', 'show', ref], cwd=ROOT)
        evidence['authorities'][name] = {'git_object': ref, 'sha256': hashlib.sha256(content).hexdigest()}
    evidence['authorities']['ref_commit'] = git('rev-parse', 'fyp2/live-system')

    old = json.loads((ROOT / 'docs/fyp2/evidence/data_artifact_audit.json').read_text())
    vision_path = DATA / 'eda_outputs/processed/vision/vision_metadata_with_split.csv'
    vision = pd.read_csv(vision_path)
    groups = {s: vision[vision.split == s] for s in ['train', 'val', 'test']}
    drivers = {s: set(frame.driver_id) for s, frame in groups.items()}
    counts = {s: len(frame) for s, frame in groups.items()}
    overlaps = {f'{a}_{b}': len(drivers[a] & drivers[b]) for a, b in [('train', 'val'), ('train', 'test'), ('val', 'test')]}
    check('vision_sizes_reused', counts == old['vision']['rows'], counts)
    check('vision_splits_only', set(vision.split) == set(groups), sorted(vision.split.unique()))
    check('vision_driver_disjoint', all(value == 0 for value in overlaps.values()), overlaps)
    check('vision_driver_counts_reused', {s: len(values) for s, values in drivers.items()} == old['vision']['drivers'],
          {s: len(values) for s, values in drivers.items()})
    check('vision_unique_paths', not vision.image_path.duplicated().any(), int(vision.image_path.duplicated().sum()))
    check('vision_source_ids_unique', not vision[['class_id', 'filename']].duplicated().any(),
          int(vision[['class_id', 'filename']].duplicated().sum()))
    missing = sum(not Path(path).is_file() for path in vision.image_path)
    check('vision_paths_exist', missing == 0, missing)
    check('vision_class_order', sorted(vision.class_id.unique()) == CLASSES, sorted(vision.class_id.unique()))
    for split, frame in groups.items():
        check(f'vision_class_coverage:{split}', set(frame.class_id) == set(CLASSES), sorted(frame.class_id.unique()))
    evidence['vision_split'] = {**snapshot(vision_path), 'status': 'REUSED_AND_VERIFIED', 'rows': counts,
        'driver_ids': {s: sorted(values) for s, values in drivers.items()}, 'driver_overlap': overlaps,
        'source_id_rule': 'vision-v1:<class_id>/<filename>; existing CSV is canonical membership manifest',
        'content_and_near_duplicate_pixel_audit': 'NOT_RUN',
        'class_counts': {s: frame.class_id.value_counts().sort_index().to_dict() for s, frame in groups.items()}}

    telemetry = {}
    row_sets = {}
    for split in ['train', 'val', 'test']:
        path = DATA / f'eda_outputs/processed/telemetry/telemetry_{split}.csv'
        frame = pd.read_csv(path)
        telemetry[split] = frame
        check(f'telemetry_columns:{split}', list(frame) == FEATURES + ['behavior_label'], list(frame))
        check(f'telemetry_hash_reused:{split}', sha(path) == old['telemetry'][split]['sha256'], sha(path))
        check(f'telemetry_rows:{split}', len(frame) == old['telemetry'][split]['rows'], len(frame))
        check(f'telemetry_missing:{split}', int(frame.isna().sum().sum()) == 0, int(frame.isna().sum().sum()))
        check(f'telemetry_finite:{split}', np.isfinite(frame[FEATURES].to_numpy()).all(), bool(np.isfinite(frame[FEATURES].to_numpy()).all()))
        check(f'telemetry_labels:{split}', set(frame.behavior_label) == set(LABELS), sorted(frame.behavior_label.unique()))
        row_sets[split] = set(frame.itertuples(index=False, name=None))
        check(f'telemetry_unique_rows:{split}', len(row_sets[split]) == len(frame), len(row_sets[split]))
    tel_overlaps = {f'{a}_{b}': len(row_sets[a] & row_sets[b]) for a, b in [('train', 'val'), ('train', 'test'), ('val', 'test')]}
    check('telemetry_no_exact_overlap', all(value == 0 for value in tel_overlaps.values()), tel_overlaps)
    feature_path = DATA / 'eda_outputs/processed/telemetry/telemetry_feature_order.csv'
    check('feature_order_csv', pd.read_csv(feature_path).feature.tolist() == FEATURES, pd.read_csv(feature_path).feature.tolist())
    evidence['telemetry_splits'] = {s: {**snapshot(DATA / f'eda_outputs/processed/telemetry/telemetry_{s}.csv'),
        'status': 'REUSED_AND_VERIFIED', 'rows': len(frame), 'class_counts': frame.behavior_label.value_counts().to_dict(),
        'source_id_rule': f'telemetry-v1:{sha(DATA / f"eda_outputs/processed/telemetry/telemetry_{s}.csv")}:{s}:<zero-based CSV data row>',
        'source_id_limitation': 'Positional split IDs, not recovered original generator/person IDs'} for s, frame in telemetry.items()}
    evidence['telemetry_exact_row_overlap'] = tel_overlaps
    raw_path = DATA / 'Driver_Behavior.csv'
    raw = pd.read_csv(raw_path)
    check('raw_8_features_missing', int(raw[FEATURES].isna().sum().sum()) == 0, int(raw[FEATURES].isna().sum().sum()))
    evidence['raw_telemetry'] = {**snapshot(raw_path), 'rows': len(raw), 'missing_retained_features': 0, 'synthetic': True}

    imputer = SimpleImputer(strategy='median').fit(telemetry['train'][FEATURES])
    train_values = imputer.transform(telemetry['train'][FEATURES])
    scaler = StandardScaler().fit(train_values)
    toy = SimpleImputer(strategy='median').fit([[0.0], [2.0]])
    check('imputer_train_only_oracle', toy.transform([[100.0], [1000.0], [np.nan]])[-1, 0] == 1.0
          and toy.transform([[-999.0], [9999.0], [np.nan]])[-1, 0] == 1.0, {'train': [0, 2], 'expected_missing_fill': 1.0})
    evidence['train_only_statistics'] = {'fit_split': 'train', 'fit_rows': len(train_values),
        'train_split_sha256': sha(DATA / 'eda_outputs/processed/telemetry/telemetry_train.csv'),
        'feature_order': FEATURES, 'median': imputer.statistics_.tolist(), 'lr_scaler_mean': scaler.mean_.tolist(),
        'lr_scaler_scale': scaler.scale_.tolist(), 'sd_ddof0': np.std(train_values, axis=0).tolist(),
        'mean_global': np.mean(train_values, axis=0).tolist(),
        'mean_by_class': {label: train_values[telemetry['train'].behavior_label.to_numpy() == label].mean(axis=0).tolist() for label in LABELS},
        'purpose': 'Preparation evidence only; future trainers must fit their own train-only Pipeline, not load pickle',
        'upstream_provenance': 'EDA computes whole-dataset median before splitting; raw retained features have no NaN; contamination of existing .9993 is not demonstrated'}

    checkpoint = torch.load(ROOT / 'ml/outputs/vision/mobilenetv3_large_vision.pt', map_location='cpu', weights_only=True)
    check('checkpoint_class_order', checkpoint['classes'] == CLASSES, checkpoint['classes'])
    vision_metrics = json.loads((ROOT / 'ml/outputs/vision/metrics.json').read_text())
    telemetry_metrics = json.loads((ROOT / 'ml/outputs/telemetry/metrics.json').read_text())
    check('checkpoint_label_names', [checkpoint['idx_to_name'][c] for c in CLASSES] == vision_metrics['class_names'], checkpoint['idx_to_name'])
    names = vision.groupby('class_id').class_name.agg(lambda values: sorted(set(values))).to_dict()
    check('dataset_checkpoint_label_mapping', names == {c: [checkpoint['idx_to_name'][c]] for c in CLASSES}, names)
    check('baseline_feature_metadata', telemetry_metrics['features'] == FEATURES and telemetry_metrics['classes'] == LABELS,
          {'features': telemetry_metrics['features'], 'classes': telemetry_metrics['classes']})
    graph = onnx.load(str(ROOT / 'ml/outputs/vision/mobilenetv3_large_vision.onnx'))
    onnx.checker.check_model(graph)
    shape = lambda value: [dimension.dim_value or dimension.dim_param for dimension in value.type.tensor_type.shape.dim]
    inp, out = graph.graph.input[0], graph.graph.output[0]
    check('onnx_input_contract', inp.name == 'input' and inp.type.tensor_type.elem_type == 1 and shape(inp)[1:] == [3, 224, 224]
          and isinstance(shape(inp)[0], str), {'name': inp.name, 'shape': shape(inp), 'dtype': inp.type.tensor_type.elem_type})
    check('onnx_output_contract', out.name == 'logits' and out.type.tensor_type.elem_type == 1 and shape(out)[1:] == [10]
          and isinstance(shape(out)[0], str), {'name': out.name, 'shape': shape(out)})
    check('onnx_raw_logits_no_softmax', not any(node.op_type in ['Softmax', 'LogSoftmax'] for node in graph.graph.node),
          'No Softmax / LogSoftmax nodes; notebook exports raw model forward')
    evidence['contracts'] = {'vision_class_to_idx': {c: i for i, c in enumerate(checkpoint['classes'])},
        'training_label_names': checkpoint['idx_to_name'], 'runtime_label_names': ['safe_driving', *vision_metrics['class_names'][1:]],
        'telemetry_feature_order': FEATURES, 'telemetry_class_to_idx': {c: i for i, c in enumerate(LABELS)},
        'vision_preprocessing': 'RGB -> direct PIL bilinear 224x224, no crop -> /255 -> ImageNet Normalize -> NCHW float32',
        'mean': [0.485, 0.456, 0.406], 'std': [0.229, 0.224, 0.225]}
    # Reuse the actual provider's preprocessing method without importing backend,
    # constructing a provider, evaluating models, or exercising fusion/FSM.
    provider = ROOT / 'backend/app/providers/trained.py'
    tree = ast.parse(provider.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'TrainedProvider')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'preprocess')
    method.decorator_list = []
    namespace = {'base64': base64, 'binascii': binascii, 'io': io, 'InvalidFrame': ValueError}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(provider), 'exec'), namespace)
    image = Image.fromarray(np.random.default_rng(42).integers(0, 256, (137, 319, 3), dtype=np.uint8))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    runtime_values = namespace['preprocess'](base64.b64encode(buffer.getvalue()).decode())
    evaluation = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(),
                                     transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    notebook_values = evaluation(image)[None].numpy()
    check('synthetic_preprocessing_byte_parity', runtime_values.tobytes() == notebook_values.tobytes(),
          {'seed': 42, 'shape': list(runtime_values.shape), 'max_abs_difference': float(np.max(np.abs(runtime_values - notebook_values)))})
    evidence['preprocessing_source'] = snapshot(provider)
    evidence['baseline_metrics'] = {name: {'status': 'STORED_NOT_RERUN', 'path': f'ml/outputs/{name}/metrics.json',
        'sha256': sha(ROOT / f'ml/outputs/{name}/metrics.json'),
        'metrics': {split: {k: values[k] for k in ['accuracy', 'macro_f1', 'weighted_f1']} for split, values in metrics['metrics'].items()}}
        for name, metrics in [('vision', vision_metrics), ('telemetry', telemetry_metrics)]}
    evidence['reused_evidence'] = [snapshot(ROOT / path) for path in config['reused_evidence']]
    evidence['model_inventory'] = [snapshot(path) for path in sorted((ROOT / 'ml/outputs').glob('*/*')) if path.is_file()]
    evidence['pretraining_cache'] = [snapshot(path) for path in sorted((Path.home() / '.cache/torch/hub/checkpoints').glob('*.pth'))]
    hpo = json.loads((ROOT / 'ml/configs/bounded_hpo.json').read_text())
    products = {name: int(np.prod([len(values) for values in model['grid'].values()])) for name, model in hpo['models'].items()}
    check('hpo_grid_exact_budgets', products == {'mobilenet_v3_large': 6, 'resnet18': 6, 'xgboost': 8, 'random_forest': 6, 'logistic_regression': 6}, products)
    check('hpo_run_caps', {name: model['max_total_runs'] for name, model in hpo['models'].items()} ==
          {'mobilenet_v3_large': 8, 'resnet18': 8, 'xgboost': 10, 'random_forest': 8, 'logistic_regression': 8},
          {name: model['max_total_runs'] for name, model in hpo['models'].items()})
    check('hpo_launch_disabled', hpo['launch_authorized'] is False and all(value is None for value in hpo['wall_time_limits_seconds'].values()), hpo['wall_time_limits_seconds'])
    evidence['hpo_config'] = snapshot(ROOT / 'ml/configs/bounded_hpo.json')
    evidence['gitignore_checks'] = []
    for filename, expected in [('model.pt', True), ('model.onnx', True), ('weights.pth', True), ('arbitrary_xgb.json', True),
        ('rf.joblib', True), ('lr.pkl', True), ('model.ubj', True), ('features.npz', True), ('config.json', False),
        ('runtime_manifest.json', False), ('evaluation_metrics.json', False), ('validation_metrics.json', False),
        ('selection_log.json', False), ('trials.csv', False), ('predictions_test.csv', False), ('timing_samples.csv', False)]:
        path = f'ml/outputs/runs/_ignore_probe/nested/{filename}'
        result = subprocess.run(['git', 'check-ignore', '--no-index', path], cwd=ROOT, capture_output=True, text=True)
        check(f'ignore:{filename}', result.returncode in [0, 1] and (result.returncode == 0) == expected,
              {'ignored': result.returncode == 0, 'expected': expected})
        evidence['gitignore_checks'].append({'path': path, 'expected_ignored': expected, 'actual_ignored': result.returncode == 0})
    after = {path: sha(Path(path) if Path(path).is_absolute() else ROOT / path) for path in hashes}
    check('protected_hashes_unchanged', after == hashes, after)
    check('nothing_staged', not git('diff', '--cached', '--name-only'), git('diff', '--cached', '--name-only'))
    evidence['protected_hashes_after'] = after
    evidence['reproduction_inputs'] = [snapshot(Path(__file__)), snapshot(RUN / 'config.json')]
    evidence['exit_code'] = 0
    (RUN / 'preparation_evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    print(json.dumps({'checks_passed': len(CHECKS), 'failed': 0, 'vision_rows': counts,
          'telemetry_rows': {s: len(frame) for s, frame in telemetry.items()}, 'mps_available': evidence['device']['mps_available'],
          'training_runs': 0, 'hpo_trials': 0, 'test_prediction_runs': 0, 'output': str(RUN / 'preparation_evidence.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
