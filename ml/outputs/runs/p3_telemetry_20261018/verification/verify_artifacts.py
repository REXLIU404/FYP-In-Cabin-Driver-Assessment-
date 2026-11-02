"""Independent, repeatable P2/P3 artifact audit; never fit or open held-out test.

Run from the ML repository with:
  ./.venv/bin/python -B ml/outputs/runs/p3_telemetry_20261018/verification/verify_artifacts.py

Only this directory's artifact_manifest.json and execution.log are rewritten.
The training implementation is never imported. Self-generated benchmark joblib
files are loaded only after their recorded byte count and SHA-256 both match.
"""
import ast
import collections
import datetime
import hashlib
import importlib.metadata
import itertools
import json
import math
import os
import platform
from pathlib import Path
import subprocess
import sys
import time
import traceback

for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
             'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[name] = '2'
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RUN = HERE.parent
ROOT = RUN.parents[3]
OUTPUTS = {HERE / 'artifact_manifest.json', HERE / 'execution.log'}
LABELS = ['Safe', 'Aggressive', 'Distracted']
FEATURES = ['speed_kmph', 'accel_x', 'accel_y', 'brake_pressure',
            'steering_angle', 'throttle', 'lane_deviation', 'headway_distance']
MODELS = ['xgboost', 'random_forest', 'logistic_regression']
CHECKS = []
RECORDS = {}
TRIAL_RESULTS = []
RELOADS = []
STARTED = time.monotonic()
INITIAL_PLATFORM = platform.platform()


def guard(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).absolute()
        if path.name == 'telemetry_test.csv' or 'FYP2-Live-System' in path.parts:
            raise PermissionError(f'Forbidden input: {path}')
        mode = args[1] or ''
        flags = args[2] or 0
        writing = (any(c in str(mode) for c in 'wax+') or
                   bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        if writing and path not in OUTPUTS:
            raise PermissionError(f'Audit writes are restricted to two output files: {path}')


sys.addaudithook(guard)
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import accuracy_score, f1_score, log_loss, confusion_matrix, classification_report
from threadpoolctl import threadpool_limits, threadpool_info


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check(name, passed, detail=None):
    value = {'name': name, 'passed': bool(passed)}
    if detail is not None:
        value['detail'] = detail
    CHECKS.append(value)
    if not passed:
        print('FAIL', name, json.dumps(detail, ensure_ascii=False), flush=True)
    return bool(passed)


def close(actual, expected, atol=1e-12, rtol=1e-12):
    return bool(np.allclose(actual, expected, atol=atol, rtol=rtol, equal_nan=False))


def compare_tree(name, actual, expected):
    if isinstance(expected, dict):
        check(name + '.keys', isinstance(actual, dict) and set(actual) == set(expected))
        if isinstance(actual, dict):
            for key in expected:
                if key in actual:
                    compare_tree(name + '.' + str(key), actual[key], expected[key])
    elif isinstance(expected, list):
        check(name, close(actual, expected) if expected and isinstance(expected[0], (int, float, list)) else actual == expected)
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        check(name, isinstance(actual, (int, float)) and math.isfinite(actual) and close(actual, expected))
    else:
        check(name, actual == expected)


def recorded_file(name, path, record):
    path = Path(path)
    exists = check(name + '.exists', path.is_file() and not path.is_symlink(), str(path))
    if not exists:
        return False
    actual = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
    RECORDS[str(path)] = actual
    size = check(name + '.bytes', actual['bytes'] == record['bytes'])
    digest = check(name + '.sha256', actual['sha256'] == record['sha256'])
    return size and digest


def identity():
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    return {'root': git('rev-parse', '--show-toplevel'), 'branch': git('branch', '--show-current'),
            'head': git('rev-parse', 'HEAD'), 'dirty_state': git('status', '--short'),
            'worktrees': git('worktree', 'list')}


def independent_selection(rows, model):
    highest = max(r['metrics']['macro_f1'] for r in rows)
    tied = [r for r in rows if highest - r['metrics']['macro_f1'] < 1e-4]
    def rank(row):
        c = row['config']
        simple = ((c['max_depth'], row['metrics']['trees_used']) if model == 'xgboost'
                  else ((math.inf if c['max_depth'] is None else c['max_depth'], c['n_estimators'])
                        if model == 'random_forest' else (c['C'],)))
        return (row['metrics']['log_loss'], *simple, int(row['trial_id'].rsplit('_', 1)[1]))
    return min(tied, key=rank)


def main():
    current = identity()
    cfg = read(ROOT / 'ml/configs/bounded_hpo.json')
    context = read(RUN / 'config.json')
    ledger = read(RUN / 'artifact_manifest.json')
    selection = read(RUN / 'selection_log.json')
    p0 = read(ROOT / 'ml/outputs/runs/w2_preparation_20261015/config.json')
    protected = p0['protected_hashes']
    versions = {'python': platform.python_version(), 'platform': INITIAL_PLATFORM,
                **{n: importlib.metadata.version(n) for n in ['torch', 'torchvision', 'scikit-learn',
                   'numpy', 'pandas', 'Pillow', 'joblib', 'threadpoolctl', 'xgboost']}}
    check('repository.root', current['root'] == str(ROOT))
    check('repository.branch', current['branch'] == 'fyp2/ml-training')
    training_head = context['environment']['git']['head']
    training_is_ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', training_head, 'HEAD'], cwd=ROOT, check=False).returncode == 0
    check('source.training_head_retained', training_is_ancestor)
    check('protocol.preregistered', cfg['status'] == 'PREREGISTERED' and cfg['launch_authorized'] is True)
    committed = subprocess.check_output(['git', 'show', 'HEAD:ml/configs/bounded_hpo.json'], cwd=ROOT)
    check('protocol.committed_before_training', committed == (ROOT / 'ml/configs/bounded_hpo.json').read_bytes())
    check('protocol.fixed_limits', cfg['wall_time_limits_seconds']['per_trial'] == 300 and
          cfg['wall_time_limits_seconds']['total'] == 2700 and cfg['wall_time_limits_seconds']['threads'] == 2)
    check('protocol.selection_rules', cfg['selection']['split'] == 'val' and
          cfg['selection']['tie_macro_f1_absolute_tolerance'] == 1e-4 and
          cfg['selection']['frozen_model'] == 'selected configuration at seed 42' and
          cfg['selection']['confirmation_must_not_reselect'] is True)
    check('run.status', ledger['status'] == 'COMPLETED')
    compare_tree('run.root_selection', ledger['selection'], selection)
    check('run.combined_budget', math.isfinite(ledger['combined_wall_seconds']) and
          0 < ledger['combined_wall_seconds'] < 2700, ledger['combined_wall_seconds'])
    check('run.supervisor_success', ledger['execution']['status'] == 'COMPLETED' and
          ledger['execution']['returncode'] == 0 and ledger['execution']['wall_seconds'] < 2700)
    check('run.test_flag', context['test_csv_opened'] is False)
    source_identity = {}
    for relative, expected in context['source_hashes'].items():
        current_sha = sha(ROOT / relative)
        snapshot = RUN / 'source_snapshot' / relative
        snapshot_sha = sha(snapshot) if snapshot.is_file() else None
        source_identity[relative] = {'as_executed_sha256':expected, 'current_sha256':current_sha,
            'source_current_match':current_sha == expected, 'snapshot_path':str(snapshot),
            'snapshot_sha256':snapshot_sha, 'source_snapshot_match':snapshot_sha == expected}
        check('source.as_executed_sha256.' + relative, current_sha == expected or snapshot_sha == expected,
              source_identity[relative])
        if snapshot.is_file():
            check('source.snapshot_sha256.' + relative, snapshot_sha == expected)
    for name, expected in context['environment']['protected_hashes'].items():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        check('protected.P0_reference.' + name, protected.get(name) == expected)
        check('protected.current_sha256.' + name, sha(path) == expected)
    for name, expected in ledger['protected_hashes_after'].items():
        check('protected.after.' + name, protected.get(name) == expected and sha(ROOT / name) == expected)

    data_root = Path(context['data_root'])
    frames, source_hashes = {}, {}
    for split, count in [('train', 21000), ('val', 4500)]:
        path = data_root / f'eda_outputs/processed/telemetry/telemetry_{split}.csv'
        source_hashes[split] = sha(path)
        check('data.' + split + '.P0_sha256', source_hashes[split] == protected[str(path)])
        frame = pd.read_csv(path)
        frames[split] = frame
        check('data.' + split + '.shape', frame.shape == (count, 9))
        check('data.' + split + '.canonical_columns', list(frame) == FEATURES + ['behavior_label'])
        check('data.' + split + '.labels', set(frame.behavior_label) == set(LABELS))
        check('data.' + split + '.balanced_labels', frame.behavior_label.value_counts().to_dict() == {x: count // 3 for x in LABELS})
        check('data.' + split + '.finite', np.isfinite(frame[FEATURES].to_numpy()).all())
    x_train = frames['train'][FEATURES].to_numpy()
    median = np.nanmedian(x_train, axis=0)
    imputed = np.where(np.isnan(x_train), median, x_train)
    mean, var = np.mean(imputed, axis=0), np.var(imputed, axis=0, ddof=0)
    scale = np.where(var == 0, 1, np.sqrt(var))
    missing = np.isnan(x_train).sum(axis=0).tolist()
    y_val = frames['val'].behavior_label.map(dict(zip(LABELS, range(3)))).to_numpy()
    expected_ids = [f'telemetry-v1:{source_hashes["val"]}:val:{i}' for i in range(4500)]
    root_csv = pd.read_csv(RUN / 'trials.csv')
    rows = ledger['trials']
    check('schedule.26_planned_records', len(rows) == 26)
    check('schedule.unique_trial_ids', len({r['trial_id'] for r in rows}) == len(rows))
    check('schedule.root_csv_ids_order', root_csv.trial_id.tolist() == [r['trial_id'] for r in rows])
    probabilities = {}
    executed = []
    log = (RUN / 'execution.log').read_text()
    for model in MODELS:
        spec = cfg['models'][model]
        grid = [dict(zip(spec['grid'], values)) for values in itertools.product(*spec['grid'].values())]
        searches = [r for r in rows if r['model'] == model and r['role'] == 'SEARCH']
        confirmations = [r for r in rows if r['model'] == model and r['role'] == 'CONFIRMATION']
        check(model + '.grid_count', len(grid) == spec['search_trials'] == len(searches))
        check(model + '.grid_order', [r['config'] for r in searches] == grid)
        check(model + '.search_seed42', all(r['seed'] == 42 for r in searches))
        check(model + '.p2_first_only', [r['phase'] for r in searches] == ['P2'] + ['P3'] * (len(searches)-1))
        check(model + '.confirmation_seeds', [r['seed'] for r in confirmations] == [43, 44])
        check(model + '.trial_cap', len(searches) + len(confirmations) <= spec['max_total_runs'])
        frozen = independent_selection(searches, model)
        selected = selection[model]
        check(model + '.independent_selection', selected['selected_trial_id'] == frozen['trial_id'], frozen['trial_id'])
        check(model + '.frozen_config_seed_checkpoint', selected['frozen_seed'] == 42 and
              selected['config'] == frozen['config'] and selected['checkpoint'] == frozen['checkpoint'])
        check(model + '.confirmations_do_not_reselect', all(r['config'] == frozen['config'] and r['phase'] == 'P3' for r in confirmations))
        check(model + '.selected_f1', close(selected['validation_macro_f1'], frozen['metrics']['macro_f1']))
        check(model + '.selected_logloss', close(selected['validation_log_loss'], frozen['metrics']['log_loss']))
        check(model + '.no_test_selection', selected['test_used'] is False)

    for row in rows:
        trial = row['trial_id']
        csv_row = root_csv.loc[root_csv.trial_id == trial].iloc[0]
        check(trial + '.root_csv_metadata', all(csv_row[k] == row[k] for k in ['model', 'phase', 'role', 'seed', 'status']) and json.loads(csv_row['config']) == row['config'])
        if row['status'] == 'SKIPPED_DETERMINISTIC_DUPLICATE':
            check(trial + '.skipped_no_fit', row['seed'] == 44 and row.get('independent_evidence') is False and not (RUN / row['model'] / trial).exists())
            continue
        try:
            executed.append(row)
            directory = Path(row['directory'])
            check(trial + '.directory', directory == RUN / row['model'] / trial and directory.is_dir())
            manifest = read(directory / 'artifact_manifest.json')
            request = read(directory / 'config.json')
            stats = read(directory / 'train_statistics.json')
            metrics = read(directory / 'validation_metrics.json')
            check(trial + '.worker_completed', manifest['status'] == metrics['status'] == 'COMPLETED')
            check(trial + '.resource_request', request['threads'] == 2 and request['train_rows'] == 21000 and request['validation_rows'] == 4500)
            check(trial + '.request_metadata', all(request[k] == row[k] for k in ['trial_id', 'model', 'phase', 'role', 'seed', 'config']))
            compare_tree(trial + '.context', request['context'], context)
            check(trial + '.source_hash_identity', manifest['source_hashes'] == context['source_hashes'])
            check(trial + '.versions', manifest['versions'] == versions)
            check(trial + '.git_identity', manifest['git']['branch'] == current['branch'] and manifest['git']['head'] == current['head'])
            check(trial + '.protected_identity', manifest['protected_hashes'] == context['environment']['protected_hashes'])
            check(trial + '.preprocessing_contract', manifest['class_to_idx'] == dict(zip(LABELS, range(3))) and manifest['feature_order'] == FEATURES and manifest['preprocessing_fit_split'] == 'train')
            check(trial + '.train_ids_complete_range', manifest['train_source_ids'] == {'split_sha256': source_hashes['train'], 'row_range': [0,20999]})
            check(trial + '.train_stat_contract', stats['fit_split'] == 'train' and stats['fit_rows'] == 21000 and stats['feature_order'] == FEATURES and stats['train_csv_sha256'] == source_hashes['train'])
            check(trial + '.independent_median', close(stats['median'], median))
            check(trial + '.independent_missing_counts', stats['missing_values_per_feature'] == missing)
            if row['model'] == 'logistic_regression':
                check(trial + '.independent_scaler_mean', close(stats['scaler_mean'], mean))
                check(trial + '.independent_scaler_variance', close(stats['scaler_var'], var))
                check(trial + '.independent_scaler_scale', close(stats['scaler_scale'], scale))
                check(trial + '.independent_scaler_count', stats['scaler_samples_seen'] == 21000)
            for split in ['train', 'val']:
                check(trial + '.source.' + split, manifest['sources'][split] == {'path': str(data_root / f'eda_outputs/processed/telemetry/telemetry_{split}.csv'), 'sha256': source_hashes[split]})
            integrity = {}
            for name, record in manifest['artifacts'].items():
                if name == 'predictions_test.csv':
                    check(trial + '.test_not_yet_due', record.get('status') == 'NOT_YET_DUE' and record.get('created') is False and not (directory / name).exists())
                    continue
                check(trial + '.artifact_path.' + name, Path(record['path']) == directory / name)
                integrity[name] = recorded_file(trial + '.' + name, directory / name, record)
            check(trial + '.required_files', set(integrity) == {'checkpoint.joblib','class_report.json','config.json','predictions_validation.csv','probabilities_validation.npy','selection_log.json','timing_samples.csv','train_statistics.json','trials.csv','validation_metrics.json'})
            probs = np.load(directory / 'probabilities_validation.npy', allow_pickle=False)
            probabilities[trial] = probs
            check(trial + '.probability_shape', probs.shape == (4500, 3))
            check(trial + '.finite_probabilities', np.isfinite(probs).all())
            check(trial + '.probability_range_sum', np.all((probs >= 0) & (probs <= 1)) and np.allclose(probs.sum(axis=1), 1, atol=1e-6))
            predictions = pd.read_csv(directory / 'predictions_validation.csv', float_precision='round_trip')
            check(trial + '.prediction_columns', list(predictions) == ['source_id','source_row','true_label_index','predicted_label_index'] + ['probability_' + x for x in LABELS])
            check(trial + '.val_source_ids_order', predictions.source_id.tolist() == expected_ids and predictions.source_row.tolist() == list(range(4500)))
            check(trial + '.val_true_labels', np.array_equal(predictions.true_label_index.to_numpy(), y_val))
            check(trial + '.csv_npy_probabilities', np.array_equal(predictions[['probability_' + x for x in LABELS]].to_numpy().astype(probs.dtype), probs))
            pred = probs.argmax(axis=1)
            check(trial + '.stored_argmax', np.array_equal(predictions.predicted_label_index.to_numpy(), pred))
            calculated = {'accuracy': float(accuracy_score(y_val, pred)),
                          'macro_f1': float(f1_score(y_val, pred, labels=[0,1,2], average='macro', zero_division=0)),
                          'log_loss': float(log_loss(y_val, probs, labels=[0,1,2])),
                          'confusion_matrix': confusion_matrix(y_val, pred, labels=[0,1,2]).tolist()}
            for key, value in calculated.items():
                check(trial + '.independent_' + key, close(metrics[key], value))
            report = classification_report(y_val, pred, labels=[0,1,2], target_names=LABELS, output_dict=True, zero_division=0)
            compare_tree(trial + '.independent_class_report', read(directory / 'class_report.json'), report)
            compare_tree(trial + '.ledger_metrics', row['metrics'], metrics)
            check(trial + '.formal_validation_scope', metrics['interpretation'] == 'FORMAL_VALIDATION_ONLY' and metrics['formal_comparison_valid'] is True and metrics['synthetic_telemetry'] is True and metrics['benchmark_only'] is True)
            check(trial + '.counts_labels_shape', metrics['train_samples'] == 21000 and metrics['validation_samples'] == metrics['samples'] == 4500 and metrics['fits_completed'] == 1 and metrics['class_order'] == LABELS and metrics['output_shape'] == [4500,3] and metrics['seed'] == row['seed'])
            check(trial + '.no_test_predictions', metrics['test_predictions'] == 0 and metrics['test_csv_opened'] is False and manifest['test_csv_opened'] is False)
            check(trial + '.recorded_reload_within_contract', math.isfinite(metrics['reload_max_abs_difference']) and metrics['reload_max_abs_difference'] <= 1e-12)
            check(trial + '.worker_thread_limits', all(p['num_threads'] <= 2 for p in metrics['thread_pools']))
            check(trial + '.per_trial_budget', row['execution']['status'] == 'COMPLETED' and row['execution']['returncode'] == 0 and 0 < row['execution']['wall_seconds'] < 300)
            timing = pd.read_csv(directory / 'timing_samples.csv')
            check(trial + '.timing_one_fit', timing.phase.tolist() == ['train_preprocessing','fit','validation','reload_validation'] and timing.samples.tolist() == [21000,21000,4500,4500])
            check(trial + '.timing_resources', (timing.threads == 2).all() and (timing.device == 'cpu').all() and (timing.provider == row['model']).all() and not timing.warmup.any() and (timing.batch == 'full_split').all())
            check(trial + '.timing_finite', np.isfinite(timing.seconds).all() and (timing.seconds >= 0).all() and timing.seconds.sum() < row['execution']['wall_seconds'])
            trial_csv = pd.read_csv(directory / 'trials.csv', float_precision='round_trip')
            check(trial + '.one_fit_csv', len(trial_csv) == 1 and int(trial_csv.iloc[0]['fits']) == 1 and bool(trial_csv.iloc[0]['counts_toward_hpo']))
            check(trial + '.execution_logged', f'START {trial} ' in log and f'END {trial} COMPLETED' in log and read(directory / 'execution.log')['status'] == 'COMPLETED')
            check(trial + '.worker_selection_deferred', read(directory / 'selection_log.json') == {'status':'AWAITING_MODEL_SEARCH_COMPLETION','trial_id':trial,'selection_split':'val','test_predictions':'NOT_YET_DUE','confirmation_cannot_reselect':True})
            if integrity.get('checkpoint.joblib'):
                with threadpool_limits(2):
                    restored = joblib.load(directory / 'checkpoint.joblib')
                    recovered = restored.predict_proba(frames['val'][FEATURES])
                    pools = threadpool_info()
                difference = float(np.abs(recovered - probs).max())
                check(trial + '.independent_reload_within_contract', close(recovered, probs), difference)
                check(trial + '.independent_inference_threads', all(p['num_threads'] <= 2 for p in pools))
                check(trial + '.checkpoint_classes_features', list(restored.classes_) == [0,1,2] and restored.n_features_in_ == 8 and list(restored.feature_names_in_) == FEATURES)
                expected_steps = ['imputer','scaler','classifier'] if row['model'] == 'logistic_regression' else ['imputer','classifier']
                check(trial + '.checkpoint_steps', list(restored.named_steps) == expected_steps)
                check(trial + '.checkpoint_medians', close(restored.named_steps['imputer'].statistics_, median) and restored.named_steps['imputer'].strategy == 'median')
                classifier = restored.named_steps['classifier']
                params = classifier.get_params()
                check(trial + '.checkpoint_config', all(params[k] == v for k,v in row['config'].items()) and params['random_state'] == row['seed'])
                if row['model'] == 'xgboost':
                    fixed = {'n_estimators':400,'early_stopping_rounds':30,'eval_metric':'mlogloss','colsample_bytree':.9,'reg_lambda':1.,'tree_method':'hist','objective':'multi:softprob','n_jobs':2}
                    check(trial + '.checkpoint_xgb_fixed', all(params[k] == v for k,v in fixed.items()))
                    check(trial + '.checkpoint_tree_counts', classifier.best_iteration + 1 == metrics['trees_used'] and classifier.get_booster().num_boosted_rounds() == metrics['trees_built'] and 1 <= metrics['trees_used'] <= metrics['trees_built'] <= 400)
                    losses = classifier.evals_result()['validation_0']['mlogloss']
                    check(trial + '.finite_training_val_loss', np.isfinite(losses).all() and len(losses) == metrics['trees_built'] and close(min(losses), metrics['best_validation_mlogloss']))
                elif row['model'] == 'random_forest':
                    check(trial + '.checkpoint_rf_fixed', params['min_samples_leaf'] == 2 and params['n_jobs'] == 2 and len(classifier.estimators_) == row['config']['n_estimators'])
                else:
                    sc = restored.named_steps['scaler']
                    check(trial + '.checkpoint_lr_fixed', params['solver'] == 'lbfgs' and params['max_iter'] == 1000 and max(classifier.n_iter_) <= 1000)
                    check(trial + '.checkpoint_scaler_stats', close(sc.mean_, mean) and close(sc.var_, var) and close(sc.scale_, scale) and int(sc.n_samples_seen_) == 21000)
                RELOADS.append({'trial_id': trial, 'exact_array_equal': bool(np.array_equal(recovered, probs)),
                                'within_contract_atol_rtol_1e_12':close(recovered, probs), 'max_abs_difference': difference})
            else:
                check(trial + '.independent_reload_not_attempted', False, 'Checkpoint integrity did not pass')
            TRIAL_RESULTS.append({'trial_id':trial, 'metrics_recomputed':calculated, 'probability_dtype':str(probs.dtype)})
            print('VERIFIED', trial, 'val_macro_f1', calculated['macro_f1'], 'reload_max_abs_difference', RELOADS[-1]['max_abs_difference'] if RELOADS else None, flush=True)
        except Exception as exc:
            check(trial + '.audit_exception', False, repr(exc))
            traceback.print_exc()

    check('run.actual_fit_count_25', len(executed) == 25 and sum(r['metrics']['fits_completed'] for r in executed) == 25)
    check('run.fit_counts_by_model', dict(collections.Counter(r['model'] for r in executed)) == {'xgboost':10,'random_forest':8,'logistic_regression':7})
    check('run.25_checkpoint_reloads', len(RELOADS) == 25)
    check('run.25_logged_starts_ends', len([x for x in log.splitlines() if x.startswith('START ')]) == 25 and len([x for x in log.splitlines() if x.startswith('END ')]) == 25)
    check('run.no_unrun_or_interrupted', all(r['status'] in ['COMPLETED','DETERMINISTIC_DUPLICATE','SKIPPED_DETERMINISTIC_DUPLICATE'] for r in rows))
    lr42 = selection['logistic_regression']['selected_trial_id']
    lr43 = next(r for r in rows if r['model'] == 'logistic_regression' and r['seed'] == 43)
    lr44 = next(r for r in rows if r['model'] == 'logistic_regression' and r['seed'] == 44)
    check('logistic_regression.exact_deterministic_duplicate', np.array_equal(probabilities[lr42], probabilities[lr43['trial_id']]) and lr43['status'] == 'DETERMINISTIC_DUPLICATE' and lr43['independent_evidence'] is False)
    check('logistic_regression.seed44_skip', lr44['status'] == 'SKIPPED_DETERMINISTIC_DUPLICATE' and selection['logistic_regression']['deterministic_duplicate'] is True)
    for model in MODELS:
        selected = selection[model]
        values = [next(r for r in executed if r['trial_id'] == selected['selected_trial_id'])['metrics']['macro_f1']]
        confirms = [r for r in executed if r['model'] == model and r['role'] == 'CONFIRMATION']
        values.extend(r['metrics']['macro_f1'] for r in confirms)
        check(model + '.confirmation_mean', close(selected['confirmation_macro_f1_mean'], np.mean(values)))
        check(model + '.confirmation_std', selected['confirmation_std_ddof'] == 0 and close(selected['confirmation_macro_f1_std'], np.std(values, ddof=0)))
        check(model + '.confirmation_seeds_report', selected['confirmation_seed_values'] == [42] + [r['seed'] for r in confirms] and selected['confirmation_seeds_completed'] == [r['seed'] for r in confirms])
    tree = ast.parse(Path(__file__).read_text())
    check('audit.no_fit_calls', not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ['fit','fit_transform','partial_fit'] for n in ast.walk(tree)))
    inventory = {}
    for path in sorted(RUN.rglob('*')):
        if path.is_file() and not path.is_relative_to(HERE):
            check('inventory.no_symlink.' + str(path.relative_to(RUN)), not path.is_symlink())
            inventory[str(path.relative_to(RUN))] = {'bytes':path.stat().st_size, 'sha256':sha(path)}
    check('inventory.no_test_predictions', not any(Path(name).name == 'predictions_test.csv' for name in inventory))
    return {'run_id': RUN.name, 'repository': current, 'software_versions': versions,
            'training_source_hashes':context['source_hashes'], 'source_identity':source_identity,
            'source_current_match':all(x['source_current_match'] for x in source_identity.values()),
            'source_snapshot_match':all(x['source_snapshot_match'] for x in source_identity.values()),
            'training_head':training_head, 'current_head_matches_training':current['head'] == training_head,
            'data_source_hashes':source_hashes,
            'protected_hashes_verified_without_test_read':context['environment']['protected_hashes'],
            'training_combined_wall_seconds':ledger['combined_wall_seconds'],
            'training_budget_seconds':2700, 'planned_records':len(rows), 'actual_fits':len(executed),
            'fits_by_model':dict(collections.Counter(r['model'] for r in executed)),
            'selection':selection, 'trial_results':TRIAL_RESULTS, 'independent_reloads':RELOADS,
            'recorded_artifact_integrity':RECORDS, 'run_file_inventory':inventory,
            'train_statistics_independently_recomputed':{'median':median.tolist(),'scaler_mean':mean.tolist(),
              'scaler_var_ddof0':var.tolist(),'scaler_scale':scale.tolist(),'rows':21000},
            'test_csv_opened_by_verifier':False, 'test_images_opened_by_verifier':False,
            'new_fits_by_verifier':0, 'joblib_load_policy':'Only this run self-generated benchmark checkpoints after recorded bytes and SHA-256 match; inference threadpool_limits(2)',
            'limitations':['Synthetic telemetry is close to linearly separable; high val scores do not establish real-world generalization or safety.',
               'Held-out test was previously exposed according to protocol; verifier did not open or rehash telemetry_test.csv and did not open any images.',
               'Evidence validates saved artifacts and model reloads, not an independent retraining; original training wall time is verified from supervisor records and logs.',
               'LR seed43 is an exact deterministic duplicate and is not independent evidence; seed44 was skipped.',
               'Random Forest parallel prediction may differ by floating-point accumulation order; all reloads use original atol=rtol=1e-12 contract, with exact equality and actual maximum differences recorded separately.',
               'Per-trial selection_log.json intentionally remains AWAITING_MODEL_SEARCH_COMPLETION; final frozen selection is the root selection_log.json.',
               'P4, P5, E1, model replacement, and visual training are outside this audit scope.']}


if __name__ == '__main__':
    if any(p.is_symlink() for p in [HERE, RUN, *HERE.parents]):
        raise SystemExit('Symlink paths are forbidden')
    with (HERE / 'execution.log').open('w') as output:
        sys.stdout = output
        sys.stderr = output
        print('INDEPENDENT_ARTIFACT_VERIFICATION', datetime.datetime.now(datetime.timezone.utc).isoformat(), flush=True)
        try:
            result = main()
        except Exception as exc:
            check('audit.fatal_exception', False, repr(exc))
            traceback.print_exc()
            result = {'run_id':RUN.name, 'limitations':['Audit stopped with a fatal exception; inspect execution.log.']}
        failures = [c for c in CHECKS if not c['passed']]
        result.update(status='VERIFIED_PASS' if not failures else 'VERIFICATION_FAILED',
                      independent_check_count=len(CHECKS), failures=failures, checks=CHECKS,
                      verifier_wall_seconds=time.monotonic()-STARTED,
                      verifier_source={'path':str(Path(__file__).resolve()), 'bytes':Path(__file__).stat().st_size,'sha256':sha(__file__)})
        (HERE / 'artifact_manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        print(json.dumps({k:result.get(k) for k in ['status','independent_check_count','failures','actual_fits','fits_by_model','training_combined_wall_seconds','verifier_wall_seconds']}, ensure_ascii=False), flush=True)
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
    print(result['status'], 'checks=', len(CHECKS), 'failures=', len(failures), 'manifest=', HERE / 'artifact_manifest.json')
    raise SystemExit(0 if not failures else 1)
