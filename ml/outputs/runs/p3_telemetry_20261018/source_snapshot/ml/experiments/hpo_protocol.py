"""Preregistered P2/P3 rules shared by offline runners; no fitting or test loader."""
import itertools
import json
import math
import re
import subprocess
from pathlib import Path

from ml.experiments import comparator_common as common

CONFIG = common.ROOT / 'ml/configs/bounded_hpo.json'


def load_protocol(path=CONFIG):
    path = Path(path)
    cfg = json.loads(path.read_text())
    if cfg.get('status') != 'PREREGISTERED' or cfg.get('launch_authorized') is not True:
        raise ValueError('HPO protocol is not preregistered and authorized')
    if not path.resolve().is_relative_to(common.ROOT):
        raise ValueError('Protocol must be committed inside the ML repository')
    relative = str(path.resolve().relative_to(common.ROOT))
    committed = subprocess.check_output(['git', 'show', f'HEAD:{relative}'], cwd=common.ROOT)
    if committed != path.read_bytes():
        raise ValueError('Protocol must be committed before any training')
    return cfg


def search_configs(model, protocol):
    spec = protocol['models'][model]
    grid = spec['grid']
    configurations = [dict(zip(grid, values)) for values in itertools.product(*grid.values())]
    if len(configurations) != spec['search_trials']:
        raise ValueError('Grid size differs from the preregistered trial ceiling')
    return configurations


def _simpler(row, model):
    cfg = row['config']
    if model == 'xgboost':
        return (cfg['max_depth'], row.get('trees_used', row.get('metrics', {}).get('trees_used', 400)))
    if model == 'random_forest':
        return (float('inf') if cfg['max_depth'] is None else cfg['max_depth'], cfg['n_estimators'])
    if model == 'logistic_regression':
        return (cfg['C'],)
    return (row.get('best_epoch', row.get('metrics', {}).get('best_epoch', 8)),)


def _trial_order(value):
    if isinstance(value, int):
        return value
    match = re.search(r'(\d+)$', str(value))
    return int(match.group(1)) if match else str(value)


def select_trial(rows, model, protocol):
    eligible = [r for r in rows if r.get('status') == 'COMPLETED'
                and r.get('role') == 'SEARCH' and r.get('seed') == 42]
    if not eligible:
        raise ValueError('No completed seed42 search trial to select')
    for r in eligible:
        f1, loss = r['metrics']['macro_f1'], r['metrics']['log_loss']
        if not math.isfinite(f1) or not math.isfinite(loss) or not 0 <= f1 <= 1 or loss < 0:
            raise ValueError('Non-finite or invalid validation scores')
    highest = max(r['metrics']['macro_f1'] for r in eligible)
    tolerance = protocol['selection']['tie_macro_f1_absolute_tolerance']
    tied = [r for r in eligible if highest - r['metrics']['macro_f1'] < tolerance]
    return min(tied, key=lambda r: (r['metrics']['log_loss'], *_simpler(r, model), _trial_order(r['trial_id'])))


def validate_vision_budget(value):
    if not isinstance(value, dict) or value.get('launch_authorized') is not True:
        raise ValueError('Explicit approved vision budget is required')

    def positive(number):
        return isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number) and number > 0

    if not all(positive(value.get(k)) for k in ['per_trial', 'total']):
        raise ValueError('Vision per_trial/total must be positive finite numeric seconds')
    models = value.get('per_model')
    if isinstance(models, dict):
        valid = all(positive(models.get(m)) for m in ['mobilenet_v3_large', 'resnet18'])
    else:
        valid = positive(models)
    if not valid:
        raise ValueError('Vision per_model must declare both positive finite caps')
    return value


def safe_run(run_id, create=False):
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', run_id) or '..' in run_id:
        raise ValueError('run_id must be one safe directory name')
    root = common.RUNS
    common.reject_symlink_path(root)
    directory = root / run_id
    common.reject_symlink_path(directory)
    if create:
        root.mkdir(parents=True, exist_ok=True)
        directory.mkdir(exist_ok=False)
    return directory


def guard_environment(require_mps=False):
    if require_mps:
        import torch
        if not torch.backends.mps.is_available():
            raise ValueError('MPS is required; CPU fallback is not authorized')
    result = {'git': common.git_snapshot(), 'protected_hashes': common.protected_snapshot()}
    expected = common.frozen_hashes()
    # Startup Section 1 separately checks all three split byte hashes. During
    # training we never reopen telemetry_test.csv, even for another checksum.
    for path, wanted in expected.items():
        if Path(path).is_absolute() and Path(path).name != 'telemetry_test.csv':
            if common.sha256(path) != wanted:
                raise ValueError(f'Frozen input changed: {path}')
            result['protected_hashes'][path] = wanted
    result['test_split_integrity'] = 'P0 reference; startup byte hash checked separately; not reopened here'
    return result
