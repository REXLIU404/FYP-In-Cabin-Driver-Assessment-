"""Vision worker recipe/early-stop software checks; no images, model fit, or MPS."""
import importlib
import json
from pathlib import Path

import pytest


def worker():
    try:return importlib.import_module('ml.vision.train_hpo')
    except ModuleNotFoundError:pytest.fail('Vision worker has not been implemented')


def configuration():
    return json.loads((Path(__file__).resolve().parents[1]/'configs/bounded_hpo.json').read_text())


def plan():
    return {'model':'resnet18','role':'SEARCH','seed':42,'max_epochs':8,
            'config':{'learning_rate':.0001,'weight_decay':.0001}}


@pytest.mark.parametrize('change',[{'seed':45},{'max_epochs':9},{'config':{'learning_rate':.1,'weight_decay':.0001}},
                                  {'model':'efficientnet'},{'role':'SEARCH','seed':43}])
def test_worker_rejects_unapproved_recipe_without_loading_data(change):
    p=plan();p.update(change)
    with pytest.raises(ValueError):worker().validate_plan(p,'search',configuration())


def test_probe_recipe_is_fixed_and_not_a_search_trial():
    p=plan();p.update(role='PROBE',max_epochs=1,config={'learning_rate':.0008,'weight_decay':.0001})
    worker().validate_plan(p,'probe',configuration())
    with pytest.raises(ValueError):worker().validate_plan(p,'search',configuration())


def test_best_epoch_ties_do_not_reset_patience():
    w=worker()
    assert w.advance_early_stop(.7,0,.7)==(.7,1,False,False)
    assert w.advance_early_stop(.7,1,.69)==(.7,2,False,True)
    assert w.advance_early_stop(.7,1,.71)==(.71,0,True,False)


def test_nonfinite_score_is_rejected():
    with pytest.raises(ValueError):worker().advance_early_stop(.7,0,float('nan'))
