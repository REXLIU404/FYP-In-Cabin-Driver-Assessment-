"""Vision orchestration boundaries: fake MPS, synthetic artifacts, no training/data."""
import importlib
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def vision():
    try:
        return importlib.import_module('ml.experiments.run_vision_hpo')
    except ModuleNotFoundError as error:
        if error.name != 'ml.experiments.run_vision_hpo':
            raise
        class MissingVision:
            def __getattr__(self, name):
                pytest.fail('Missing bounded vision HPO orchestration implementation')
        return MissingVision()


@pytest.fixture
def context():
    return {'environment': {'git': {'head': 'synthetic', 'dirty_state': ''}},
            'weights_manifest': {}, 'source_hashes': {}, 'protocol_sha256': 'synthetic',
            'data_root': '/synthetic/not-opened'}


def plan(trial_id='search_001'):
    return {'trial_id': trial_id, 'model': 'resnet18', 'role': 'SEARCH', 'seed': 42,
            'config': {'learning_rate': 0.0001, 'weight_decay': 0.0001},
            'max_epochs': 8, 'is_p2': trial_id == 'search_001'}


def synthetic_worker(command, log_path, timeout):
    """Only filesystem contract outputs; never import a trainer or load data."""
    attempt = Path(command[command.index('--attempt-dir') + 1])
    metrics = {'status': 'COMPLETED', 'macro_f1': 0.75, 'log_loss': 0.5,
               'best_epoch': 1, 'all_losses_and_probabilities_finite': True,
               'reload_verified': True, 'test_predictions': 0,
               'epochs': [{'epoch': 1, 'train_seconds': 2.0, 'validation_seconds': 1.0}]}
    (attempt / 'validation_metrics.json').write_text(json.dumps(metrics))
    (attempt/'checkpoint.pt').write_bytes(b'synthetic artifact, no model')
    for name in ['class_report.json','selection_log.json','predictions_validation.csv','timing_samples.csv','trials.csv']:
        (attempt/name).write_text('{}\n' if name.endswith('.json') else 'synthetic\n')
    records={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in attempt.iterdir() if p.is_file()}
    (attempt / 'artifact_manifest.json').write_text(json.dumps({'status': 'COMPLETED', 'test_images_opened': 0,'artifacts':records}))
    Path(log_path).write_text('synthetic worker only\n')
    return {'status': 'COMPLETED', 'returncode': 0, 'wall_seconds': 0.02,
            'timeout_seconds': timeout}


def test_missing_numeric_budget_refuses_without_creating_approval(vision, tmp_path):
    path = tmp_path / 'approved_vision_budget.json'
    with pytest.raises((ValueError, FileNotFoundError), match='budget|预算|approved'):
        vision.load_approved_budget(path)
    assert not path.exists()


@pytest.mark.parametrize('payload', [
    {'launch_authorized': False, 'per_trial': 1, 'per_model': 2, 'total': 3},
    {'launch_authorized': True, 'per_trial': None, 'per_model': 2, 'total': 3},
    {'launch_authorized': True, 'per_trial': True, 'per_model': 2, 'total': 3},
    {'launch_authorized': True, 'per_trial': 1, 'per_model': 2, 'total': float('inf')},
])
def test_incomplete_or_nonfinite_budget_is_not_authorization(vision, tmp_path, payload):
    path = tmp_path / 'approval.json'
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        vision.load_approved_budget(path)


def test_no_mps_refuses_even_when_cpu_is_available(vision, monkeypatch):
    fake = SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)))
    monkeypatch.setitem(sys.modules, 'torch', fake)
    with pytest.raises(ValueError, match='MPS'):
        vision.require_mps()


def test_resume_skips_completed_attempt_and_preserves_directory(vision, tmp_path, context):
    budget = {'per_trial': 10.0, 'per_model': 20.0, 'total': 30.0}
    first = vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=synthetic_worker)
    assert first['attempts'][0]['status'] == 'COMPLETED'
    attempt = tmp_path / first['attempts'][0]['directory']
    before = {str(p.relative_to(attempt)): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in attempt.rglob('*') if p.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail('A completed trial must not launch another worker')

    again = vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=forbidden)
    after = {str(p.relative_to(attempt)): (p.read_bytes(), p.stat().st_mtime_ns)
             for p in attempt.rglob('*') if p.is_file()}
    assert len(again['attempts']) == 1
    assert before == after


def test_ctrl_c_is_retained_as_interrupted_then_new_attempt(vision, tmp_path, context):
    budget = {'per_trial': 5.0, 'per_model': 20.0, 'total': 30.0}

    def interrupt(*args, **kwargs):
        time.sleep(0.02)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=interrupt)
    state = json.loads((tmp_path / 'search_state.json').read_text())
    assert state['attempts'][0]['status'] == 'INTERRUPTED'
    assert state['attempts'][0]['wall_seconds'] > 0
    previous_usage = state['used_wall_seconds']
    seen_timeout = []

    def rerun(command, log_path, timeout):
        seen_timeout.append(timeout)
        return synthetic_worker(command, log_path, timeout)

    again = vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=rerun)
    assert [row['status'] for row in again['attempts']] == ['INTERRUPTED', 'COMPLETED']
    assert again['attempts'][0]['directory'] != again['attempts'][1]['directory']
    assert seen_timeout[0] < 5.0
    assert again['used_wall_seconds'] >= previous_usage


def test_hard_wall_kills_blocked_child_including_pre_training_load(vision, tmp_path):
    started = time.monotonic()
    result = vision.supervise([sys.executable, '-c', 'import time; time.sleep(30)'],
                              tmp_path / 'child.log', 0.08)
    assert result['status'] == 'TIME_BUDGET_EXCEEDED'
    assert time.monotonic() - started < 2.0
    assert result['wall_seconds'] >= 0.08


def test_wall_limit_stops_and_marks_remaining_without_reset(vision, tmp_path, context):
    budget = {'per_trial': 0.1, 'per_model': 1.0, 'total': 2.0}

    def timeout(command, log_path, seconds):
        return {'status': 'TIME_BUDGET_EXCEEDED', 'returncode': -9,
                'wall_seconds': 0.1, 'timeout_seconds': seconds}

    state = vision.run_plan(tmp_path, 'search', [plan(), plan('search_002')],
                            budget, context, runner=timeout)
    assert state['status'] == 'NOT_RUN_BUDGET'
    assert state['attempts'][0]['status'] == 'TIME_BUDGET_EXCEEDED'
    assert state['trials']['resnet18/search_001']['status'] == 'NOT_RUN_BUDGET'
    assert state['trials']['resnet18/search_002']['status'] == 'NOT_RUN_BUDGET'
    assert len(state['attempts']) == 1
    state = vision.run_plan(tmp_path, 'search', [plan(), plan('search_002')],
                            budget, context, runner=lambda *a: pytest.fail('budget must not reset'))
    assert len(state['attempts']) == 1


def test_running_attempt_after_parent_crash_becomes_interrupted(vision, tmp_path, context):
    budget = {'per_trial': 10.0, 'per_model': 20.0, 'total': 30.0}
    # Simulate a parent dying between launching the worker and saving its result.
    def crash(command, log_path, timeout):
        raise SystemExit(9)

    with pytest.raises(SystemExit):
        vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=crash)
    state = vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=synthetic_worker)
    assert [a['status'] for a in state['attempts']] == ['INTERRUPTED', 'COMPLETED']


def test_changed_resume_config_refuses_instead_of_mixing_evidence(vision, tmp_path, context):
    budget = {'per_trial': 10.0, 'per_model': 20.0, 'total': 30.0}
    vision.run_plan(tmp_path, 'search', [plan()], budget, context, runner=synthetic_worker)
    changed = plan()
    changed['config']['learning_rate'] = 0.9
    with pytest.raises(ValueError, match='changed|mismatch|改变'):
        vision.run_plan(tmp_path, 'search', [changed], budget, context, runner=synthetic_worker)


def test_probe_estimate_is_time_only_and_eight_by_eight(vision):
    proposal = vision.budget_proposal({'mobilenet_v3_large': {'epochs': [
        {'epoch': 1, 'train_seconds': 10.0, 'validation_seconds': 2.0}]},
        'resnet18': {'epochs': [{'epoch': 1, 'train_seconds': 20.0, 'validation_seconds': 4.0}]}})
    assert proposal['models']['mobilenet_v3_large']['estimated_seconds'] == pytest.approx(883.2)
    assert proposal['models']['resnet18']['estimated_seconds'] == pytest.approx(1766.4)
    assert proposal['estimated_total_seconds'] == pytest.approx(2649.6)
    assert proposal['launch_authorized'] is False
    assert proposal['probe_used_for_selection'] is False


def test_weight_integrity_failure_never_rewrites_manifest(vision, tmp_path, monkeypatch):
    cache = tmp_path / 'cache'
    cache.mkdir()
    (cache / 'mobilenet_v3_large-5c1a4163.pth').write_bytes(b'corrupt')
    monkeypatch.setattr(vision, 'weights_cache', lambda: cache)
    with pytest.raises(ValueError, match='hash|checksum|SHA'):
        vision.cached_weight_records(require_resnet=False)
    assert not (tmp_path / 'weights_manifest.json').exists()


def test_attempt_preparation_cannot_add_time_outside_trial_budget(vision,tmp_path,context,monkeypatch):
    original=vision.atomic_json
    def slow(path,value):
        time.sleep(.02)
        return original(path,value)
    monkeypatch.setattr(vision,'atomic_json',slow)
    state=vision.run_plan(tmp_path,'probe',[plan()],{'per_trial':.01,'per_model':1.,'total':2.},context,
                          runner=lambda *a:pytest.fail('Expired preparation budget must not start a worker'))
    assert state['status']=='NOT_RUN_BUDGET'


@pytest.mark.parametrize('damage',['delete','change'])
def test_completed_checkpoint_damage_refuses_resume_without_retraining(vision,tmp_path,context,damage):
    budget={'per_trial':10.,'per_model':20.,'total':30.}
    state=vision.run_plan(tmp_path,'search',[plan()],budget,context,runner=synthetic_worker)
    checkpoint=tmp_path/state['attempts'][0]['directory']/'checkpoint.pt'
    if damage=='delete':checkpoint.unlink()
    else:checkpoint.write_bytes(b'changed')
    with pytest.raises(ValueError,match='artifact|checkpoint|integrity'):
        vision.run_plan(tmp_path,'search',[plan()],budget,context,
                        runner=lambda *a:pytest.fail('Damaged completed artifact cannot trigger automatic retraining'))
