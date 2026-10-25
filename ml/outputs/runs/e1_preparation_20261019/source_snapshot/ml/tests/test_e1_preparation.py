"""Preparation gates: refuse altered train statistics and formal E1 profiles."""
import copy
import importlib

import numpy as np
import pytest

from ml.experiments.e1_generators import fit_train_statistics


@pytest.fixture
def preparation():
    try:
        return importlib.import_module('ml.experiments.run_e1_preparation')
    except ModuleNotFoundError as error:
        if error.name != 'ml.experiments.run_e1_preparation':
            raise
        class Missing:
            def __getattr__(self, name):
                pytest.fail('Missing validation-only E1 preparation evidence runner')
        return Missing()


def toy_stats():
    return fit_train_statistics(np.arange(24).reshape(3,8),
        ['Safe','Aggressive','Distracted'],split='train',source_sha256='train-hash')


def test_reuse_preserves_original_statistics(preparation):
    frozen=toy_stats();before=copy.deepcopy(frozen)
    assert preparation.verify_reused_statistics(frozen,toy_stats())=='REUSED_AND_VERIFIED'
    assert frozen==before


@pytest.mark.parametrize('field,value',[
    ('fit_split','val'),('train_split_sha256','changed'),('fit_rows',4),
    ('median',[0.]*8),('sd_ddof0',[1.]*8),('mean_global',[1.]*8),
    ('mean_by_class',{'Safe':[0.]*8})])
def test_corrupted_train_statistics_refuse(preparation,field,value):
    frozen=toy_stats();frozen[field]=value
    with pytest.raises(ValueError,match='statistics'):
        preparation.verify_reused_statistics(frozen,toy_stats())


@pytest.mark.parametrize('field,value',[
    ('formal_execution_authorized',True),('source_split','test'),('seed',43),
    ('vision_source_count',1000),('telemetry_source_count',4500)])
def test_profile_cannot_expand_preparation_scope(preparation,field,value):
    profile={'formal_execution_authorized':False,'source_split':'val','seed':42,
             'vision_source_count':10,'telemetry_source_count':30}
    profile[field]=value
    with pytest.raises(ValueError,match='preparation'):
        preparation.validate_profile(profile)
