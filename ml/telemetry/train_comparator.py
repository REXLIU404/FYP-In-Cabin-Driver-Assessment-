"""RF/LR P1 smoke pipelines. Train/val only; execute through run_p1_smoke.py."""
import argparse
import os
import sys
import time
from pathlib import Path

for variable in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[variable] = '2'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.experiments import comparator_common as common


def train_smoke(model_name, directory, data_root, deadline):
    import resource
    import warnings
    import joblib
    import numpy as np
    import pandas as pd
    from threadpoolctl import threadpool_info, threadpool_limits

    started = time.monotonic()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    budget = common.validate_smoke_budget(model_name)
    common.check_deadline(deadline)
    frames, sources = common.load_telemetry(data_root)
    train = common.stratified_sample(frames['train'], 'behavior_label', 300, 42, common.LABELS)
    validation = common.stratified_sample(frames['val'], 'behavior_label', 90, 42, common.LABELS)
    source_rows = [{'source_id': f'telemetry-v1:{sources[split]["sha256"]}:{split}:{index}',
                    'source_row': int(index), 'split': split, 'label': row.behavior_label}
                   for split, frame in [('train', train), ('val', validation)] for index, row in frame.iterrows()]
    pd.DataFrame(source_rows).to_csv(directory / 'sample_manifest.csv', index=False)
    pipeline = common.telemetry_pipeline(model_name)
    labels = {label: index for index, label in enumerate(common.LABELS)}
    x_train, x_val = train[common.FEATURES], validation[common.FEATURES]
    y_train = train.behavior_label.map(labels).to_numpy()
    y_val = validation.behavior_label.map(labels).to_numpy()
    config = {'phase': 'P1', 'model': model_name, 'smoke': True, 'formal_comparison_valid': False,
        'counts_toward_hpo': False, 'budget': budget, 'data_root': str(data_root), 'sources': sources,
        'feature_order': common.FEATURES, 'class_to_idx': labels, 'preprocessing_fit_split': 'train_smoke_subset',
        'preprocessing_fit_rows': 300, 'versions': common.software_versions(), 'git': common.git_snapshot(),
        'estimator_params': pipeline.named_steps['classifier'].get_params(), 'test_csv_opened': False}
    common.write_json(directory / 'config.json', config)
    timings = []
    with threadpool_limits(limits=2):
        common.check_deadline(deadline)
        start = time.monotonic()
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter('always')
            pipeline.fit(x_train, y_train)  # Exactly one classifier fit.
        timings.append({'phase': 'fit', 'samples': 300, 'seconds': time.monotonic() - start, 'warmup': False})
        common.check_deadline(deadline)
        imputer_before = pipeline.named_steps['imputer'].statistics_.copy()
        start = time.monotonic()
        probabilities = pipeline.predict_proba(x_val)
        timings.append({'phase': 'validation', 'samples': 90, 'seconds': time.monotonic() - start, 'warmup': False})
        common.validate_probabilities(probabilities, 90, common.LABELS, pipeline.classes_)
        if not np.array_equal(imputer_before, np.median(x_train.to_numpy(), axis=0)):
            raise ValueError('Imputer was not fit only on the training subset')
        if not np.array_equal(imputer_before, pipeline.named_steps['imputer'].statistics_):
            raise ValueError('Validation refit the imputer')
        statistics = {'fit_split': 'train_smoke_subset', 'fit_rows': 300, 'feature_order': common.FEATURES,
                      'median': imputer_before.tolist(), 'train_csv_sha256': sources['train']['sha256']}
        if 'scaler' in pipeline.named_steps:
            scaler = pipeline.named_steps['scaler']
            imputed_train = pipeline.named_steps['imputer'].transform(x_train)
            if not np.allclose(scaler.mean_, imputed_train.mean(axis=0)) or int(scaler.n_samples_seen_) != 300:
                raise ValueError('Scaler fit provenance is not the training subset')
            statistics.update({'scaler_mean': scaler.mean_.tolist(), 'scaler_scale': scaler.scale_.tolist()})
        common.write_json(directory / 'train_statistics.json', statistics)
        artifact = directory / f'{model_name}_smoke.joblib'
        temporary = directory / f'{model_name}_smoke.tmp.joblib'
        joblib.dump(pipeline, temporary)
        os.replace(temporary, artifact)
        fingerprint = common.sha256(artifact)
        common.check_deadline(deadline)
        # Benchmark-only pickle: only our just-written local artifact is loaded.
        if common.sha256(artifact) != fingerprint:
            raise ValueError('Serialized pipeline integrity changed')
        restored = joblib.load(artifact)
        start = time.monotonic()
        recovered = restored.predict_proba(x_val)
        timings.append({'phase': 'reload_validation', 'samples': 90, 'seconds': time.monotonic() - start, 'warmup': False})
        common.validate_probabilities(recovered, 90, common.LABELS, restored.classes_)
        reload_difference = float(np.max(np.abs(recovered - probabilities)))
        if not np.allclose(recovered, probabilities, atol=1e-12, rtol=1e-12):
            raise ValueError('Reload changed validation probabilities')
        pools = threadpool_info()
    predicted = pd.DataFrame({'source_id': [f'telemetry-v1:{sources["val"]["sha256"]}:val:{index}' for index in validation.index],
                              'true_label_index': y_val, 'predicted_label_index': probabilities.argmax(1)})
    for index, label in enumerate(common.LABELS):
        predicted[f'probability_{label}'] = probabilities[:, index]
    predicted.to_csv(directory / 'predictions_validation.csv', index=False)
    pd.DataFrame(timings).to_csv(directory / 'timing_samples.csv', index=False)
    metrics = common.diagnostics(y_val, probabilities, common.LABELS)
    common.write_json(directory / 'class_report.json', metrics.pop('class_report'))
    common.write_json(directory / 'selection_log.json', {'selection': 'NONE_SMOKE_SINGLE_FIT_ONLY', 'test_used': False, 'hpo_trials': 0})
    pd.DataFrame([{'record_kind': 'PIPELINE_SMOKE', 'counts_toward_hpo': False, 'seed': 42, 'fits': 1}]).to_csv(directory / 'trials.csv', index=False)
    metrics.update({'status': 'VERIFIED_PASS', 'model': model_name, 'train_samples': 300, 'validation_samples': 90,
        'fits_completed': 1, 'output_shape': list(probabilities.shape), 'class_order': common.LABELS,
        'all_losses_and_probabilities_finite': bool(np.isfinite(metrics['log_loss'])),
        'train_only_preprocessing': True, 'reload_max_abs_probability_difference': reload_difference,
        'checkpoint': common.file_record(artifact), 'artifact_scope': 'BENCHMARK_ONLY_NOT_CANDIDATE_PACKAGE',
        'warnings': [str(warning.message) for warning in recorded],
        'n_iter': pipeline.named_steps['classifier'].n_iter_.tolist() if model_name == 'logistic_regression' else None,
        'threadpools': pools, 'device': 'cpu', 'worker_wall_seconds': time.monotonic() - started,
        'resource_usage': common.resource_usage(usage), 'test_predictions': 0, 'formal_hpo_trials': 0, 'candidate_package': False})
    common.check_deadline(deadline)
    common.write_json(directory / 'validation_metrics.json', metrics)
    print(f'{model_name} smoke VERIFIED_PASS: one fit, 300 train / 90 validation', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['random_forest', 'logistic_regression'], required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, default=Path(os.environ.get('FYP_DATA_ROOT', common.DEFAULT_DATA)))
    args = parser.parse_args()
    directory = common.validate_worker_directory(args.run_dir)
    if 'FYP_P1_DEADLINE_MONOTONIC' not in os.environ:
        parser.error('Launch through ml/experiments/run_p1_smoke.py for hard process/global budget enforcement')
    try:
        train_smoke(args.model, directory, args.data_root, float(os.environ['FYP_P1_DEADLINE_MONOTONIC']))
        return 0
    except Exception as error:
        import traceback
        status = 'TIME_BUDGET_EXCEEDED' if isinstance(error, common.TimeBudgetExceeded) else 'IMPLEMENTATION_FAILED'
        common.write_json(directory / 'validation_metrics.json', {'status': status, 'error': str(error), 'formal_comparison_valid': False})
        traceback.print_exc()
        return 124 if status == 'TIME_BUDGET_EXCEEDED' else 1


if __name__ == '__main__':
    sys.exit(main())
