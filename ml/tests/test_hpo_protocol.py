"""Protocol guards: pure software checks, no classifier fitting or test data."""
import copy
import importlib
import json
from pathlib import Path

import pytest


def protocol_module():
    try:
        return importlib.import_module('ml.experiments.hpo_protocol')
    except ModuleNotFoundError:
        pytest.fail('Shared HPO protocol is not implemented')


def test_grid_order_and_p2_first_configuration():
    h = protocol_module()
    p = h.load_protocol()
    assert h.search_configs('random_forest', p) == [
        {'n_estimators': n, 'max_depth': d} for n in [200, 400] for d in [None, 12, 24]]
    assert h.search_configs('resnet18', p)[0] == {'learning_rate': .0001, 'weight_decay': .0001}
    assert len(h.search_configs('xgboost', p)) == 8


def row(n, f1, loss, depth=12, seed=42, role='SEARCH'):
    return {'trial_id': n, 'status': 'COMPLETED', 'role': role, 'seed': seed,
            'config': {'n_estimators': 200, 'max_depth': depth},
            'metrics': {'macro_f1': f1, 'log_loss': loss}}


def test_tied_f1_uses_logloss_then_simplicity_and_id():
    h = protocol_module()
    p = h.load_protocol()
    values = [row(1, .9, .11), row(2, .89995, .10), row(3, .89994, .10, 6)]
    assert h.select_trial(values, 'random_forest', p)['trial_id'] == 3
    values.append(row(4, .8998, .01, 2))
    assert h.select_trial(values, 'random_forest', p)['trial_id'] == 3
    values.append(row(5, 1.0, .001, 2, seed=43, role='CONFIRMATION'))
    assert h.select_trial(values, 'random_forest', p)['trial_id'] == 3


def test_none_depth_is_most_complex_and_no_confirmation_reselection():
    h = protocol_module()
    values = [row(1, .9, .1, None), row(2, .9, .1, 24), row(3, 1, .001, 2, seed=43)]
    assert h.select_trial(values, 'random_forest', h.load_protocol())['trial_id'] == 2


@pytest.mark.parametrize('bad', [None, {}, {'launch_authorized': False},
    {'launch_authorized': True, 'per_trial': 1, 'per_model': 2},
    {'launch_authorized': True, 'per_trial': True, 'per_model': 2, 'total': 3},
    {'launch_authorized': True, 'per_trial': 1, 'per_model': 2, 'total': float('inf')}])
def test_unapproved_or_invalid_vision_budget_is_rejected(bad):
    with pytest.raises(ValueError):
        protocol_module().validate_vision_budget(bad)


def test_numeric_budget_and_separate_model_caps():
    h = protocol_module()
    b = {'launch_authorized': True, 'per_trial': 5,
         'per_model': {'resnet18': 10, 'mobilenet_v3_large': 12}, 'total': 22}
    assert h.validate_vision_budget(b) == b


@pytest.mark.parametrize('run_id', ['../escape', '/tmp/escape', 'a/b', '', 'a..b'])
def test_run_path_rejects_escape(run_id):
    with pytest.raises(ValueError):
        protocol_module().safe_run(run_id)


def test_run_path_rejects_symlink_ancestor(tmp_path, monkeypatch):
    h = protocol_module()
    target = tmp_path / 'real'
    target.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(h.common, 'RUNS', link)
    with pytest.raises(ValueError):
        h.safe_run('trial')


def test_mps_gate_refuses_cpu(monkeypatch):
    h = protocol_module()
    import torch
    monkeypatch.setattr(torch.backends.mps, 'is_available', lambda: False)
    with pytest.raises(ValueError, match='MPS'):
        h.guard_environment(require_mps=True)


def test_load_protocol_rejects_uncommitted_rules(tmp_path):
    h = protocol_module()
    p = tmp_path / 'bounded_hpo.json'
    p.write_text(json.dumps({'status': 'DRAFT', 'launch_authorized': False}))
    with pytest.raises(ValueError):
        h.load_protocol(p)


def test_invalid_validation_scores_are_not_selectable():
    h = protocol_module()
    bad = row(1, float('nan'), .1)
    with pytest.raises(ValueError):
        h.select_trial([bad], 'random_forest', h.load_protocol())
