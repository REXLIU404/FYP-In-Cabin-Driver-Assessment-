"""One supervised, preregistered telemetry fit. No held-out test access."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

for variable in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[variable] = '2'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.experiments import comparator_common as common
from ml.experiments import hpo_protocol as protocol


def build_pipeline(model, config, seed, cfg):
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    if model == 'xgboost':
        from xgboost import XGBClassifier
        classifier = XGBClassifier(**config, random_state=seed, n_jobs=2,
            n_estimators=400, early_stopping_rounds=30, eval_metric='mlogloss',
            colsample_bytree=.9, reg_lambda=1., tree_method='hist', objective='multi:softprob')
    elif model == 'random_forest':
        classifier = RandomForestClassifier(**config, min_samples_leaf=2, random_state=seed, n_jobs=2)
    elif model == 'logistic_regression':
        classifier = LogisticRegression(**config, solver='lbfgs', max_iter=1000, random_state=seed)
    else:
        raise ValueError('Unapproved telemetry model')
    steps = [('imputer', SimpleImputer(strategy='median'))]
    if model == 'logistic_regression':
        steps.append(('scaler', StandardScaler()))
    return Pipeline([*steps, ('classifier', classifier)])


def validate_request(request, cfg):
    name = request['model']
    if name not in ['xgboost', 'random_forest', 'logistic_regression']:
        raise ValueError('Unapproved telemetry model')
    if request.get('config') not in protocol.search_configs(name, cfg):
        raise ValueError('Configuration is outside the registered grid')
    if request.get('threads') != 2 or request.get('train_rows') != 21000 or request.get('validation_rows') != 4500:
        raise ValueError('Unapproved resources or frozen split sizes')
    role, seed = request.get('role'), request.get('seed')
    if not ((role == 'SEARCH' and seed == 42) or (role == 'CONFIRMATION' and seed in [43, 44])):
        raise ValueError('Unapproved trial role or seed')
    if request.get('phase') not in ['P2', 'P3']:
        raise ValueError('Only P2/P3 are authorized')
    if request['phase'] == 'P2' and (role != 'SEARCH' or request['config'] != protocol.search_configs(name, cfg)[0]):
        raise ValueError('P2 must be the first registered search configuration')


def fit_preprocessor(pipeline, train, validation, train_hash):
    import numpy as np
    pre = pipeline[:-1]
    x_train = pre.fit_transform(train)
    stats = {'fit_split': 'train', 'fit_rows': len(train), 'feature_order': common.FEATURES,
             'median': pipeline.named_steps['imputer'].statistics_.tolist(),
             'missing_values_per_feature': train.isna().sum().to_list(), 'train_csv_sha256': train_hash}
    if 'scaler' in pipeline.named_steps:
        scaler = pipeline.named_steps['scaler']
        stats.update(scaler_mean=scaler.mean_.tolist(), scaler_var=scaler.var_.tolist(),
                     scaler_scale=scaler.scale_.tolist(), scaler_samples_seen=int(scaler.n_samples_seen_))
    median = pipeline.named_steps['imputer'].statistics_.copy()
    x_val = pre.transform(validation)
    if not np.array_equal(median, pipeline.named_steps['imputer'].statistics_):
        raise ValueError('Validation changed train-only preprocessing')
    return x_train, x_val, stats


def train(directory, deadline):
    import importlib.metadata
    import joblib
    import numpy as np
    import pandas as pd
    import warnings
    from threadpoolctl import threadpool_limits, threadpool_info
    request = json.loads((directory / 'config.json').read_text())
    cfg = protocol.load_protocol()
    validate_request(request, cfg)
    environment = protocol.guard_environment()
    common.check_deadline(deadline)
    frames, sources = common.load_telemetry(Path(request['data_root']))
    train_frame, validation = frames['train'], frames['val']
    if (len(train_frame), len(validation)) != (21000, 4500):
        raise ValueError('Frozen split sizes changed')
    indices = {label: i for i, label in enumerate(common.LABELS)}
    y_train = train_frame.behavior_label.map(indices).to_numpy()
    y_val = validation.behavior_label.map(indices).to_numpy()
    pipeline = build_pipeline(request['model'], request['config'], request['seed'], cfg)
    timings = []
    with threadpool_limits(2):
        started = time.monotonic()
        x_train, x_val, stats = fit_preprocessor(pipeline, train_frame[common.FEATURES], validation[common.FEATURES], sources['train']['sha256'])
        timings.append({'phase': 'train_preprocessing', 'seconds': time.monotonic()-started, 'samples': len(train_frame)})
        common.write_json(directory / 'train_statistics.json', stats)
        classifier = pipeline.named_steps['classifier']
        common.check_deadline(deadline)
        started = time.monotonic()
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            if request['model'] == 'xgboost':
                classifier.fit(x_train, y_train, eval_set=[(x_val, y_val)], verbose=False)
            else:
                classifier.fit(x_train, y_train)
        timings.append({'phase': 'fit', 'seconds': time.monotonic()-started, 'samples': len(y_train)})
        common.check_deadline(deadline)
        started = time.monotonic()
        probabilities = pipeline.predict_proba(validation[common.FEATURES])
        common.validate_probabilities(probabilities, len(validation), common.LABELS, pipeline.classes_)
        timings.append({'phase': 'validation', 'seconds': time.monotonic()-started, 'samples': len(y_val)})
        np.save(directory / 'probabilities_validation.npy', probabilities, allow_pickle=False)
        output = pd.DataFrame({'source_id': [f'telemetry-v1:{sources["val"]["sha256"]}:val:{i}' for i in validation.index],
                               'source_row': validation.index, 'true_label_index': y_val,
                               'predicted_label_index': probabilities.argmax(1)})
        for i, label in enumerate(common.LABELS): output[f'probability_{label}'] = probabilities[:, i]
        output.to_csv(directory / 'predictions_validation.csv', index=False)
        artifact = directory / 'checkpoint.joblib'
        joblib.dump(pipeline, artifact)
        digest = common.sha256(artifact)
        common.check_deadline(deadline)
        started = time.monotonic()
        if digest != common.sha256(artifact): raise ValueError('Checkpoint integrity mismatch')
        restored = joblib.load(artifact)  # Our own just-written benchmark, never a deployment artifact.
        recovered = restored.predict_proba(validation[common.FEATURES])
        difference = float(np.abs(recovered-probabilities).max())
        if not np.allclose(recovered, probabilities, atol=1e-12, rtol=1e-12): raise ValueError('Reload changed probabilities')
        timings.append({'phase': 'reload_validation', 'seconds': time.monotonic()-started, 'samples': len(y_val)})
        pools = threadpool_info()
    metrics = common.diagnostics(y_val, probabilities, common.LABELS)
    report = metrics.pop('class_report')
    metrics.update(status='COMPLETED', interpretation='FORMAL_VALIDATION_ONLY', formal_comparison_valid=True,
                   train_samples=len(y_train), validation_samples=len(y_val), fits_completed=1,
                   seed=request['seed'], class_order=common.LABELS, output_shape=list(probabilities.shape),
                   reload_max_abs_difference=difference, all_probabilities_finite=True,
                   resource_usage=common.resource_usage(), thread_pools=pools, warnings=[str(w.message) for w in captured],
                   test_predictions=0, test_csv_opened=False, synthetic_telemetry=True, benchmark_only=True)
    if request['model'] == 'xgboost':
        metrics.update(trees_used=int(classifier.best_iteration)+1,
                       trees_built=classifier.get_booster().num_boosted_rounds(),
                       best_validation_mlogloss=float(classifier.best_score))
    if request['model'] == 'logistic_regression':metrics['n_iter']=classifier.n_iter_.tolist()
    common.write_json(directory / 'validation_metrics.json', metrics)
    common.write_json(directory / 'class_report.json', report)
    common.write_json(directory / 'selection_log.json', {'status': 'AWAITING_MODEL_SEARCH_COMPLETION',
        'trial_id': request['trial_id'], 'selection_split': 'val', 'test_predictions': 'NOT_YET_DUE',
        'confirmation_cannot_reselect': True})
    pd.DataFrame([{**t, 'warmup': False, 'device': 'cpu', 'threads': 2, 'provider': request['model'], 'batch': 'full_split'} for t in timings]).to_csv(directory / 'timing_samples.csv', index=False)
    pd.DataFrame([{'trial_id': request['trial_id'], 'model': request['model'], 'phase': request['phase'],
        'role': request['role'], 'seed': request['seed'], 'status': 'COMPLETED', 'counts_toward_hpo': True,
        'macro_f1': metrics['macro_f1'], 'log_loss': metrics['log_loss'], 'fits': 1}]).to_csv(directory / 'trials.csv', index=False)
    common.check_deadline(deadline)
    records = {p.name: common.file_record(p) for p in sorted(directory.iterdir()) if p.is_file() and p.name != 'execution.log'}
    records['predictions_test.csv']={'status': 'NOT_YET_DUE', 'phase': 'P4', 'created': False}
    common.write_json(directory / 'artifact_manifest.json', {'status': 'COMPLETED', 'artifacts': records,
        'sources': sources, 'train_source_ids': {'split_sha256': sources['train']['sha256'], 'row_range': [0, 20999]},
        'class_to_idx': indices, 'feature_order': common.FEATURES, 'preprocessing_fit_split': 'train',
        'git': environment['git'], 'protected_hashes': environment['protected_hashes'],
        'versions': {**common.software_versions(), 'xgboost': importlib.metadata.version('xgboost')},
        'source_hashes': request['context']['source_hashes'], 'test_csv_opened': False,
        'serialization_warning': 'Self-generated benchmark joblib; never a candidate package'})
    common.check_deadline(deadline)
    print(json.dumps({'trial_id': request['trial_id'], 'status': 'COMPLETED', 'macro_f1': metrics['macro_f1'], 'log_loss': metrics['log_loss']}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    deadline = os.environ.get('FYP_TELEMETRY_DEADLINE')
    if not deadline: parser.error('Supervised telemetry runner required')
    common.reject_symlink_path(args.run_dir)
    if not args.run_dir.resolve().is_relative_to(common.RUNS.resolve()):parser.error('Isolated ML run directory required')
    try:
        train(args.run_dir, float(deadline))
        return 0
    except Exception:
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':sys.exit(main())
