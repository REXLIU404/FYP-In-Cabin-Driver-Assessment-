"""P2/P3 telemetry boundaries; synthetic data and fake classifiers only."""
import importlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.experiments import comparator_common as common


@pytest.fixture
def modules():
    return (importlib.import_module('ml.experiments.run_telemetry_hpo'),
            importlib.import_module('ml.telemetry.train_hpo'))


@pytest.fixture
def cfg():
    return json.loads((common.ROOT / 'ml/configs/bounded_hpo.json').read_text())


def test_schedule_counts_first_grid_entry_once_as_p2(modules, cfg):
    runner, _ = modules
    rows = runner.build_schedule(cfg)
    assert len(rows) == 26
    assert [sum(r['model'] == m for r in rows) for m in runner.MODELS] == [10, 8, 8]
    xgb = [r for r in rows if r['model'] == 'xgboost']
    assert xgb[0]['config'] == {'max_depth': 3, 'learning_rate': 0.03, 'subsample': 0.8}
    assert xgb[1]['config'] == {'max_depth': 3, 'learning_rate': 0.03, 'subsample': 1.0}
    assert [r['phase'] for r in xgb] == ['P2'] + ['P3'] * 9
    assert [r['seed'] for r in xgb] == [42] * 8 + [43, 44]
    assert [r['role'] for r in xgb] == ['SEARCH'] * 8 + ['CONFIRMATION'] * 2


@pytest.mark.parametrize('model,config,expected', [
    ('xgboost', {'max_depth': 3, 'learning_rate': 0.03, 'subsample': 0.8},
     {'n_estimators': 400, 'early_stopping_rounds': 30, 'eval_metric': 'mlogloss', 'n_jobs': 2}),
    ('random_forest', {'n_estimators': 400, 'max_depth': None},
     {'n_estimators': 400, 'max_depth': None, 'min_samples_leaf': 2, 'n_jobs': 2}),
    ('logistic_regression', {'C': 0.01}, {'solver': 'lbfgs', 'max_iter': 1000, 'C': 0.01}),
])
def test_estimators_use_preregistered_fit_parameters_without_fitting(modules, cfg, model, config, expected):
    _, worker = modules
    pipeline = worker.build_pipeline(model, config, 43, cfg)
    params = pipeline.named_steps['classifier'].get_params()
    assert {k: params[k] for k in expected} == expected
    assert params['random_state'] == 43
    assert list(pipeline.named_steps) == (['imputer', 'scaler', 'classifier']
                                          if model == 'logistic_regression' else ['imputer', 'classifier'])


@pytest.mark.parametrize('change', [
    {'seed': 45}, {'config': {'C': 3.0}}, {'threads': 3},
    {'role': 'SEARCH', 'seed': 43}, {'phase': 'P4'}, {'train_rows': 300},
])
def test_worker_rejects_unapproved_requests_before_loading_data(modules, cfg, change):
    runner, worker = modules
    request = {**runner.build_schedule(cfg)[18], 'threads': 2, 'train_rows': 21000, 'validation_rows': 4500}
    request.update(change)
    with pytest.raises(ValueError):
        worker.validate_request(request, cfg)


def test_preprocessing_only_fits_train_and_records_all_statistics(modules, cfg):
    _, worker = modules
    pipeline = worker.build_pipeline('logistic_regression', {'C': 1}, 42, cfg)
    train = pd.DataFrame([[0.0] * 8, [2.0] * 8, [np.nan] * 8], columns=common.FEATURES)
    validation = pd.DataFrame([[9999.0] * 8, [np.nan] * 8], columns=common.FEATURES)
    x_train, x_val, stats = worker.fit_preprocessor(pipeline, train, validation, 'train-hash')
    assert stats['fit_split'] == 'train'
    assert stats['fit_rows'] == 3
    assert stats['median'] == [1.0] * 8
    assert stats['scaler_mean'] == [1.0] * 8
    assert stats['scaler_var'] == [2 / 3] * 8
    assert stats['scaler_samples_seen'] == 3
    assert stats['missing_values_per_feature'] == [1] * 8
    assert stats['train_csv_sha256'] == 'train-hash'
    assert x_train.shape == (3, 8)
    assert x_val[0, 0] > 1000
    assert x_val[1, 0] == 0


def test_parent_hard_deadline_includes_process_startup(modules, tmp_path, monkeypatch):
    runner, _ = modules
    original = runner.subprocess.Popen

    def delayed(*args, **kwargs):
        time.sleep(0.1)
        return original(*args, **kwargs)

    monkeypatch.setattr(runner.subprocess, 'Popen', delayed)
    started = time.monotonic()
    result = runner.supervise_command([sys.executable, '-c', 'import time; time.sleep(5)'],
                                      tmp_path / 'startup.log', started + 0.05)
    assert result['status'] == 'TIME_BUDGET_EXCEEDED'
    assert result['returncode'] != 0
    assert result['wall_seconds'] < 1.0


def test_expired_budget_cannot_start_a_process(modules, tmp_path):
    runner, _ = modules
    result = runner.supervise_command([sys.executable, '-c', 'raise RuntimeError()'],
                                      tmp_path / 'never.log', time.monotonic() - 1)
    assert result['status'] == 'NOT_RUN_BUDGET'
    assert result['command_started'] is False
    assert not (tmp_path / 'never.log').exists()


def fake_trial(directory, row, probabilities, f1=0.5):
    directory.mkdir(parents=True, exist_ok=True)
    np.save(directory / 'probabilities_validation.npy', probabilities, allow_pickle=False)
    pd.DataFrame({'source_id': [f'val:{i}' for i in range(len(probabilities))],
                  'probability_Safe': probabilities[:, 0],
                  'probability_Aggressive': probabilities[:, 1],
                  'probability_Distracted': probabilities[:, 2]}).to_csv(directory / 'predictions_validation.csv', index=False)
    return {**row, 'status': 'COMPLETED', 'directory': str(directory),
            'metrics': {'macro_f1': f1, 'log_loss': 0.5}, 'checkpoint': str(directory / 'checkpoint.joblib')}


def test_timeout_stops_all_remaining_trials_without_refit(modules, cfg, tmp_path, monkeypatch):
    runner, _ = modules
    started = []

    def timeout(row, directory, *args):
        started.append(row['trial_id'])
        return {**row, 'status': 'TIME_BUDGET_EXCEEDED', 'directory': str(directory), 'metrics': {}}

    monkeypatch.setattr(runner, 'run_one_trial', timeout)
    result = runner.execute_schedule(tmp_path, cfg, {}, common.DEFAULT_DATA, time.monotonic() + 10)
    assert started == ['xgboost_01']
    assert result['status'] == 'TIME_BUDGET_EXCEEDED'
    assert len(result['trials']) == 26
    assert [r['status'] for r in result['trials'][1:]] == ['NOT_RUN_BUDGET'] * 25
    assert result['selection']['xgboost']['status'] == 'INCOMPLETE_SEARCH'


def test_lr_identical_seed43_is_labelled_duplicate_and_seed44_is_skipped(modules, cfg, tmp_path, monkeypatch):
    runner, _ = modules
    calls = []

    def completed(row, directory, *args):
        calls.append((row['model'], row['seed'], row['config']))
        return fake_trial(directory, row, np.array([[0.2, 0.3, 0.5]]), 0.5 if row['seed'] == 42 else 0.9)

    monkeypatch.setattr(runner, 'run_one_trial', completed)
    result = runner.execute_schedule(tmp_path, cfg, {}, common.DEFAULT_DATA, time.monotonic() + 10)
    lr = result['selection']['logistic_regression']
    assert len(calls) == 25
    assert lr['selected_trial_id'] == 'logistic_regression_01'
    assert lr['frozen_seed'] == 42
    assert lr['config'] == {'C': 0.01}
    assert lr['confirmation_seeds_completed'] == [43]
    assert lr['confirmation_macro_f1_mean'] == pytest.approx(0.7)
    assert lr['confirmation_macro_f1_std'] == pytest.approx(0.2)
    assert result['trials'][-2]['status'] == 'DETERMINISTIC_DUPLICATE'
    assert result['trials'][-2]['independent_evidence'] is False
    assert result['trials'][-1]['status'] == 'SKIPPED_DETERMINISTIC_DUPLICATE'


def test_lr_changed_seed43_requires_seed44_and_never_reselects(modules, cfg, tmp_path, monkeypatch):
    runner, _ = modules

    def completed(row, directory, *args):
        probabilities = [[0.2, 0.3, 0.5]] if row['seed'] == 42 else [[0.3, 0.3, 0.4]]
        return fake_trial(directory, row, np.array(probabilities), 0.5 if row['seed'] == 42 else 0.99)

    monkeypatch.setattr(runner, 'run_one_trial', completed)
    result = runner.execute_schedule(tmp_path, cfg, {}, common.DEFAULT_DATA, time.monotonic() + 10)
    lr = result['selection']['logistic_regression']
    assert lr['selected_trial_id'] == 'logistic_regression_01'
    assert lr['confirmation_seeds_completed'] == [43, 44]
    assert lr['confirmation_macro_f1_mean'] == pytest.approx((0.5 + 0.99 + 0.99) / 3)
    assert result['trials'][-1]['status'] == 'COMPLETED'


def test_budget_placeholder_declares_test_predictions_not_due(modules, cfg, tmp_path):
    runner, _ = modules
    row = {**runner.build_schedule(cfg)[0], 'status': 'NOT_RUN_BUDGET'}
    runner.write_unrun_artifacts(tmp_path, row)
    manifest = json.loads((tmp_path / 'artifact_manifest.json').read_text())
    assert manifest['artifacts']['predictions_test.csv']['status'] == 'NOT_YET_DUE'
    assert manifest['artifacts']['checkpoint']['status'] == 'NOT_CREATED_BUDGET'
    assert not (tmp_path / 'predictions_test.csv').exists()
    assert set(['config.json', 'trials.csv', 'validation_metrics.json', 'class_report.json',
                'selection_log.json', 'timing_samples.csv']).issubset({p.name for p in tmp_path.iterdir()})


@pytest.mark.parametrize('extra', [['--per-trial', '301'], ['--resume'], ['--model', 'random_forest']])
def test_cli_rejects_unapproved_budget_resume_or_partial_grid(modules, extra):
    script = common.ROOT / 'ml/experiments/run_telemetry_hpo.py'
    result = subprocess.run([sys.executable, '-B', str(script), '--run-id', 'p3_telemetry_20990101', *extra],
                            text=True, capture_output=True)
    assert result.returncode == 2
    assert not (common.RUNS / 'p3_telemetry_20990101').exists()


def test_worker_cli_rejects_direct_unsupervised_training(modules, tmp_path):
    script = common.ROOT / 'ml/telemetry/train_hpo.py'
    result = subprocess.run([sys.executable, '-B', str(script), '--run-dir', str(tmp_path)],
                            text=True, capture_output=True)
    assert result.returncode == 2
    assert list(tmp_path.iterdir()) == []


def test_outer_supervisor_preserves_an_inner_trial_timeout(modules):
    runner, _ = modules
    assert runner.final_status('IMPLEMENTATION_FAILED', 'TIME_BUDGET_EXCEEDED') == 'TIME_BUDGET_EXCEEDED'


def test_global_deadline_kills_nested_term_ignoring_worker(modules,tmp_path):
    import os
    import signal
    runner,_=modules
    beat=tmp_path/'heartbeat';pidfile=tmp_path/'worker.pid'
    worker=tmp_path/'worker.py'
    worker.write_text('import os,signal,time\nfrom pathlib import Path\n'
        'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
        f'Path({str(pidfile)!r}).write_text(str(os.getpid()))\n'
        f'path=Path({str(beat)!r})\n'
        'while True:\n path.write_text(str(time.monotonic()));time.sleep(.01)\n')
    coordinator=tmp_path/'coordinator.py'
    coordinator.write_text('import sys,time,signal,os\n'
        f'sys.path.insert(0,{str(common.ROOT)!r})\n'
        'from ml.experiments.run_telemetry_hpo import supervise_command\n'
        'def stop(s,f):raise KeyboardInterrupt\n'
        'signal.signal(signal.SIGTERM,stop)\n'
        f'supervise_command([sys.executable,{str(worker)!r}],{str(tmp_path/"nested.log")!r},time.monotonic()+30,dict(os.environ,FYP_TELEMETRY_NESTED="1"))\n')
    try:
        result=runner.supervise_command([sys.executable,'-B',str(coordinator)],tmp_path/'outer.log',time.monotonic()+3)
        assert result['status']=='TIME_BUDGET_EXCEEDED'
        assert beat.exists(),'Synthetic worker must start to exercise the nested termination boundary'
        first=beat.read_text();time.sleep(.08)
        assert beat.read_text()==first,'Worker survived global deadline and continued work'
    finally:
        if pidfile.exists():
            try:os.kill(int(pidfile.read_text()),signal.SIGKILL)
            except ProcessLookupError:pass
