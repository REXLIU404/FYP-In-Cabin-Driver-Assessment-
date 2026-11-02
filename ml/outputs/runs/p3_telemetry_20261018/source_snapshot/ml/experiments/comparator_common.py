"""Shared, bounded P1 comparator contracts. No test loader or HPO entry point."""
import hashlib
import json
import math
import os
import platform
import re
import resource
import signal
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'ml/outputs/runs'
DEFAULT_DATA = Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-')
FREEZE = RUNS / 'w2_preparation_20261015/config.json'
FEATURES = ['speed_kmph', 'accel_x', 'accel_y', 'brake_pressure',
            'steering_angle', 'throttle', 'lane_deviation', 'headway_distance']
LABELS = ['Safe', 'Aggressive', 'Distracted']
CLASSES = [f'c{i}' for i in range(10)]
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
MODELS = ['resnet18', 'random_forest', 'logistic_regression']
COMBINED_SECONDS = 1200
APPROVED = {
    'resnet18': {'train_samples': 200, 'validation_samples': 100, 'seed': 42, 'epochs': 1,
                 'batch_size': 16, 'training_steps': 16, 'validation_steps': 8, 'threads': 2, 'wall_seconds': 600},
    'random_forest': {'train_samples': 300, 'validation_samples': 90, 'seed': 42, 'n_estimators': 20,
                      'max_depth': 6, 'n_jobs': 2, 'fits': 1, 'wall_seconds': 120},
    'logistic_regression': {'train_samples': 300, 'validation_samples': 90, 'seed': 42,
                           'max_iter': 200, 'solver': 'lbfgs', 'fits': 1, 'wall_seconds': 120},
}


class TimeBudgetExceeded(RuntimeError):
    pass


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_record(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha256(path), 'bytes': path.stat().st_size}


def write_json(path, value, replace=False):
    path = Path(path)
    if path.is_symlink() or (path.exists() and not replace):
        raise FileExistsError(path)
    temporary = path.with_name(f'.{path.name}.tmp')
    with temporary.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    os.replace(temporary, path)


def validate_smoke_budget(model, overrides=None):
    if model not in APPROVED:
        raise ValueError('Only the three approved P1 comparators are supported')
    config = dict(APPROVED[model])
    for key, value in (overrides or {}).items():
        if key not in config:
            raise ValueError(f'Unapproved budget field: {key}')
        maximum = config[key]
        if key in ['seed', 'solver', 'batch_size', 'train_samples', 'validation_samples']:
            if value != maximum:
                raise ValueError(f'{key} is fixed by the P1 approval')
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= maximum:
            raise ValueError(f'{key} exceeds the P1 approval or is invalid')
        config[key] = value
    return config


def stratified_sample(frame, label_column, count, seed, classes):
    if count <= 0 or count % len(classes) or not frame.index.is_unique:
        raise ValueError('Require a positive class-balanced count and unique source indices')
    generator = np.random.default_rng(seed)
    positions = []
    for label in classes:
        available = frame.index[frame[label_column] == label].to_numpy()
        if len(available) < count // len(classes):
            raise ValueError(f'Insufficient training/validation records for {label}')
        positions.extend(generator.choice(available, count // len(classes), replace=False).tolist())
    return frame.loc[generator.permutation(positions)].copy()


def telemetry_pipeline(model):
    if model == 'random_forest':
        estimator = RandomForestClassifier(n_estimators=20, max_depth=6, min_samples_leaf=2,
                                           random_state=42, n_jobs=2)
        return Pipeline([('imputer', SimpleImputer(strategy='median')), ('classifier', estimator)])
    if model == 'logistic_regression':
        estimator = LogisticRegression(max_iter=200, solver='lbfgs', C=1.0, random_state=42)
        return Pipeline([('imputer', SimpleImputer(strategy='median')),
                         ('scaler', StandardScaler()), ('classifier', estimator)])
    raise ValueError('Expected random_forest or logistic_regression')


def fit_train_preprocessing(pipeline, train):
    return pipeline[:-1].fit_transform(train)


def vision_transforms(training=False):
    from torchvision import transforms
    operations = [transforms.Resize((224, 224))]
    if training:
        operations.extend([transforms.RandomRotation(8), transforms.ColorJitter(brightness=0.2, contrast=0.2)])
    return transforms.Compose([*operations, transforms.ToTensor(), transforms.Normalize(MEAN, STD)])


def validate_probabilities(probabilities, sample_count, classes, actual_classes):
    probabilities = np.asarray(probabilities)
    if list(actual_classes) != list(range(len(classes))):
        raise ValueError('Model output columns do not have the canonical class order')
    if probabilities.shape != (sample_count, len(classes)) or not np.isfinite(probabilities).all():
        raise ValueError('Invalid/non-finite probability output dimensions')
    if (probabilities < 0).any() or (probabilities > 1).any() or not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError('Probability range or row sum is invalid')


def frozen_hashes():
    return json.loads(FREEZE.read_text())['protected_hashes']


def checked_source(path, expected_hashes):
    actual = sha256(path)
    expected = expected_hashes.get(str(path))
    if expected is None or actual != expected:
        raise ValueError(f'Frozen source hash mismatch: {path}')
    return {'path': str(path), 'sha256': actual}


def load_telemetry(data_root, expected_hashes=None):
    expected_hashes = frozen_hashes() if expected_hashes is None else expected_hashes
    frames, sources = {}, {}
    for split in ['train', 'val']:
        path = Path(data_root) / f'eda_outputs/processed/telemetry/telemetry_{split}.csv'
        sources[split] = checked_source(path, expected_hashes)
        frame = pd.read_csv(path)
        if list(frame) != FEATURES + ['behavior_label'] or set(frame.behavior_label) != set(LABELS):
            raise ValueError('Telemetry feature/label contract mismatch')
        if not np.isfinite(frame[FEATURES].to_numpy()).all():
            raise ValueError('Frozen clean telemetry contains unexpected NaN/Inf')
        frames[split] = frame
    return frames, sources


def load_vision(data_root, expected_hashes=None):
    expected_hashes = frozen_hashes() if expected_hashes is None else expected_hashes
    path = Path(data_root) / 'eda_outputs/processed/vision/vision_metadata_with_split.csv'
    source = checked_source(path, expected_hashes)
    metadata = pd.read_csv(path)
    # Membership contains test rows; no held-out image is opened or returned.
    metadata = metadata[metadata.split.isin(['train', 'val'])].copy()
    frames = {split: metadata[metadata.split == split].copy() for split in ['train', 'val']}
    if set(frames['train'].driver_id) & set(frames['val'].driver_id):
        raise ValueError('Vision train/validation drivers overlap')
    if any(set(frame.class_id) != set(CLASSES) for frame in frames.values()):
        raise ValueError('Vision class coverage mismatch')
    names = metadata.groupby('class_id').class_name.agg(lambda values: sorted(set(values))).to_dict()
    if any(len(values) != 1 for values in names.values()):
        raise ValueError('Inconsistent class-to-name mapping')
    return frames, {'metadata': source}, {label: values[0] for label, values in names.items()}


def steps_for_samples(count, batch_size, limit, extra=0):
    if count <= 0 or batch_size <= 0:
        raise ValueError('Invalid sample or batch count')
    steps = math.ceil(count / batch_size) + extra
    if steps > limit:
        raise ValueError('The planned passes exceed the approved step budget')
    return steps


def reject_symlink_path(path):
    path = Path(path)
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise ValueError('Output paths must not contain symbolic links')


def create_run_directory(run_id, root=RUNS):
    root = Path(root)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', run_id) or '..' in run_id:
        raise ValueError('run_id must be a single safe directory name')
    reject_symlink_path(root)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / run_id
    directory.mkdir(exist_ok=False)
    return directory


def validate_worker_directory(path):
    path = Path(path).absolute()
    reject_symlink_path(path)
    path = path.resolve()
    if not path.is_relative_to(RUNS.resolve()) or path == RUNS.resolve() or not path.is_dir():
        raise ValueError('Worker output must be an existing isolated runs directory')
    if (path / 'config.json').exists():
        raise FileExistsError('An attempt directory cannot be reused')
    return path


def check_deadline(deadline, now=None):
    if (time.monotonic() if now is None else now) >= deadline:
        raise TimeBudgetExceeded('TIME_BUDGET_EXCEEDED')


def run_bounded_command(command, log_path, timeout, env=None):
    if timeout <= 0:
        raise TimeBudgetExceeded('TIME_BUDGET_EXCEEDED')
    started = time.monotonic()
    deadline = started + timeout
    environment = dict(os.environ if env is None else env)
    environment['FYP_P1_DEADLINE_MONOTONIC'] = str(deadline)
    with Path(log_path).open('x') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   env=environment, start_new_session=True)
        status = 'VERIFIED_PASS'
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            status = 'TIME_BUDGET_EXCEEDED'
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        if status != 'TIME_BUDGET_EXCEEDED' and process.returncode:
            status = 'IMPLEMENTATION_FAILED'
    elapsed = time.monotonic() - started
    if elapsed >= timeout:
        status = 'TIME_BUDGET_EXCEEDED'
    return {'status': status, 'returncode': process.returncode, 'wall_seconds': elapsed,
            'timeout_seconds': timeout, 'command': command, 'log': str(log_path)}


def next_attempt(ledger, model, fix_note='', source_hashes=None):
    if float(ledger['used_wall_seconds']) >= COMBINED_SECONDS:
        raise TimeBudgetExceeded('TIME_BUDGET_EXCEEDED')
    attempts = [attempt for attempt in ledger['attempts'] if attempt['model'] == model]
    if not attempts:
        return 1
    if len(attempts) != 1 or attempts[0]['status'] != 'IMPLEMENTATION_FAILED':
        raise ValueError('Only one rerun after an implementation failure is authorized')
    if not fix_note.strip() or not source_hashes or source_hashes == attempts[0]['source_hashes']:
        raise ValueError('Rerun requires a documented genuine code fix')
    return 2


def git_snapshot():
    def read(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if read('branch', '--show-current') != 'fyp2/ml-training':
        raise ValueError('P1 must execute on fyp2/ml-training')
    return {'branch': read('branch', '--show-current'), 'head': read('rev-parse', 'HEAD'),
            'dirty_state': read('status', '--short'), 'staged_paths': read('diff', '--cached', '--name-only')}


def protected_snapshot():
    expected = frozen_hashes()
    records = {}
    for relative in ['ml/outputs/vision/mobilenetv3_large_vision.pt', 'ml/outputs/vision/mobilenetv3_large_vision.onnx',
                     'ml/outputs/telemetry/xgb_telemetry.json', 'docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md']:
        actual = sha256(ROOT / relative)
        if actual != expected[relative]:
            raise ValueError(f'Protected artifact changed: {relative}')
        records[relative] = actual
    return records


def diagnostics(labels, probabilities, class_names):
    validate_probabilities(probabilities, len(labels), class_names, range(len(class_names)))
    predictions = np.asarray(probabilities).argmax(axis=1)
    indices = list(range(len(class_names)))
    return {'interpretation': 'NON_COMPARATIVE_PIPELINE_SMOKE_ONLY', 'formal_comparison_valid': False,
            'samples': len(labels), 'accuracy': float(accuracy_score(labels, predictions)),
            'macro_f1': float(f1_score(labels, predictions, labels=indices, average='macro', zero_division=0)),
            'log_loss': float(log_loss(labels, probabilities, labels=indices)),
            'confusion_matrix': confusion_matrix(labels, predictions, labels=indices).tolist(),
            'class_report': classification_report(labels, predictions, labels=indices, target_names=class_names,
                                                    output_dict=True, zero_division=0)}


def resource_usage(started_usage=None):
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {'max_rss_bytes': int(usage.ru_maxrss if platform.system() == 'Darwin' else usage.ru_maxrss * 1024),
            'user_cpu_seconds': usage.ru_utime - (started_usage.ru_utime if started_usage else 0),
            'system_cpu_seconds': usage.ru_stime - (started_usage.ru_stime if started_usage else 0)}


def software_versions():
    import importlib.metadata as metadata
    return {'python': platform.python_version(), 'platform': platform.platform(),
            **{name: metadata.version(name) for name in ['torch', 'torchvision', 'scikit-learn', 'numpy', 'pandas',
                                                       'Pillow', 'joblib', 'threadpoolctl']}}
