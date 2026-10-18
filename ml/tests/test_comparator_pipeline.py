"""P1 boundary tests: no classifier fit and no project held-out data access."""
import hashlib
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from ml.experiments import comparator_common as common

FEATURES = ['speed_kmph', 'accel_x', 'accel_y', 'brake_pressure',
            'steering_angle', 'throttle', 'lane_deviation', 'headway_distance']


@pytest.mark.parametrize('model,override', [
    ('resnet18', {'train_samples': 201}), ('resnet18', {'epochs': 2}),
    ('resnet18', {'validation_steps': 9}), ('resnet18', {'threads': 3}),
    ('random_forest', {'fits': 2}), ('random_forest', {'wall_seconds': 121}),
    ('logistic_regression', {'max_iter': 201}),
])
def test_budget_gate_rejects_expansion(model, override):
    with pytest.raises(ValueError):
        common.validate_smoke_budget(model, override)


def test_stratification_preserves_each_class_and_is_reproducible():
    frame = pd.DataFrame({'class_id': np.repeat([f'c{i}' for i in range(10)], 25),
                          'source_id': range(250)})
    sample = common.stratified_sample(frame, 'class_id', 200, 42, [f'c{i}' for i in range(10)])
    again = common.stratified_sample(frame, 'class_id', 200, 42, [f'c{i}' for i in range(10)])
    assert sample.class_id.value_counts().to_dict() == {f'c{i}': 20 for i in range(10)}
    assert sample.source_id.nunique() == 200
    assert sample.source_id.tolist() == again.source_id.tolist()
    assert sample.index.tolist() == sample.source_id.tolist()


def test_sampling_rejects_missing_class_instead_of_silently_undersampling():
    frame = pd.DataFrame({'label': ['Safe'] * 10 + ['Aggressive'] * 10})
    with pytest.raises(ValueError):
        common.stratified_sample(frame, 'label', 9, 42, ['Safe', 'Aggressive', 'Distracted'])


@pytest.mark.parametrize('model', ['random_forest', 'logistic_regression'])
def test_validation_extremes_do_not_refit_training_median_or_scaler(model):
    pipeline = common.telemetry_pipeline(model)
    train = pd.DataFrame([[0.0] * 8, [2.0] * 8], columns=FEATURES)
    common.fit_train_preprocessing(pipeline, train)
    validation = pd.DataFrame([[100.0] * 8, [1000.0] * 8, [np.nan] * 8], columns=FEATURES)
    transformed = pipeline[:-1].transform(validation)
    np.testing.assert_array_equal(pipeline.named_steps['imputer'].statistics_, [1.0] * 8)
    if model == 'logistic_regression':
        np.testing.assert_array_equal(pipeline.named_steps['scaler'].mean_, [1.0] * 8)
        np.testing.assert_array_equal(transformed[:, 0], [99.0, 999.0, 0.0])
    else:
        np.testing.assert_array_equal(transformed[:, 0], [100.0, 1000.0, 1.0])
    pipeline[:-1].transform(pd.DataFrame([[-9999.0] * 8, [np.nan] * 8], columns=FEATURES))
    np.testing.assert_array_equal(pipeline.named_steps['imputer'].statistics_, [1.0] * 8)


def test_evaluation_transform_has_rgb_224_imagenet_contract():
    image = Image.new('RGB', (319, 137), (255, 0, 128))
    tensor = common.vision_transforms()(image)
    assert tuple(tensor.shape) == (3, 224, 224)
    assert str(tensor.dtype) == 'torch.float32'
    np.testing.assert_allclose(tensor[:, 0, 0].numpy(), [2.2489083, -2.0357143, 0.4264924], atol=1e-6)


@pytest.mark.parametrize('probabilities,actual_classes', [
    ([[0.5, 0.5]], [0, 1]),
    ([[0.2, np.nan, 0.8]], [0, 1, 2]),
    ([[0.2, 0.3, 0.5]], [1, 0, 2]),
    ([[0.2, 0.3, 0.8]], [0, 1, 2]),
])
def test_probability_contract_rejects_wrong_shape_nonfinite_order_or_sum(probabilities, actual_classes):
    with pytest.raises(ValueError):
        common.validate_probabilities(np.array(probabilities), 1, ['Safe', 'Aggressive', 'Distracted'], actual_classes)


def test_telemetry_loader_uses_train_val_only_and_keeps_feature_order(tmp_path):
    directory = tmp_path / 'eda_outputs/processed/telemetry'
    directory.mkdir(parents=True)
    expected = {}
    for split in ['train', 'val']:
        frame = pd.DataFrame([[float(i)] * 8 for i in range(3)], columns=FEATURES)
        frame['behavior_label'] = ['Safe', 'Aggressive', 'Distracted']
        path = directory / f'telemetry_{split}.csv'
        frame.to_csv(path, index=False)
        expected[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Any attempt to open the held-out CSV fails, even for hashing.
    (directory / 'telemetry_test.csv').mkdir()
    frames, sources = common.load_telemetry(tmp_path, expected)
    assert set(frames) == {'train', 'val'}
    assert set(sources) == {'train', 'val'}
    assert list(frames['train']) == FEATURES + ['behavior_label']
    assert frames['val'].behavior_label.tolist() == ['Safe', 'Aggressive', 'Distracted']


def test_existing_run_is_not_overwritten(tmp_path):
    path = common.create_run_directory('p1_test', tmp_path)
    marker = path / 'marker.txt'
    marker.write_text('preserve')
    with pytest.raises(FileExistsError):
        common.create_run_directory('p1_test', tmp_path)
    assert marker.read_text() == 'preserve'


def test_vision_membership_loader_excludes_test_records(tmp_path):
    directory = tmp_path / 'eda_outputs/processed/vision'
    directory.mkdir(parents=True)
    rows = [{'image_path': f'/not-opened/{split}/{c}.jpg', 'filename': f'{c}.jpg',
             'class_id': c, 'class_name': 'normal_driving' if c == 'c0' else c,
             'driver_id': split, 'split': split}
            for split in ['train', 'val', 'test'] for c in [f'c{i}' for i in range(10)]]
    path = directory / 'vision_metadata_with_split.csv'
    pd.DataFrame(rows).to_csv(path, index=False)
    frames, sources, names = common.load_vision(tmp_path, {str(path): hashlib.sha256(path.read_bytes()).hexdigest()})
    assert set(frames) == {'train', 'val'}
    assert len(frames['train']) == len(frames['val']) == 10
    assert set(frames['val'].split) == {'val'}
    assert names['c0'] == 'normal_driving'
    assert sources['metadata']['path'] == str(path)


def test_validation_step_budget_includes_reload_prediction():
    assert common.steps_for_samples(200, 16, 16) == 13
    assert common.steps_for_samples(100, 16, 8, extra=1) == 8
    with pytest.raises(ValueError):
        common.steps_for_samples(100, 16, 7, extra=1)


@pytest.mark.parametrize('run_id', ['../vision', 'a/b', '..', ''])
def test_run_directory_cannot_escape_output_root(tmp_path, run_id):
    with pytest.raises(ValueError):
        common.create_run_directory(run_id, tmp_path)


def test_symlink_output_root_is_rejected(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    linked = tmp_path / 'linked'
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        common.create_run_directory('p1_test', linked)
    assert list(outside.iterdir()) == []


def test_deadline_boundary_stops_before_another_training_step():
    common.check_deadline(10.0, now=9.999)
    with pytest.raises(common.TimeBudgetExceeded):
        common.check_deadline(10.0, now=10.0)


def test_supervisor_kills_a_stalled_process_and_reports_timeout(tmp_path):
    result = common.run_bounded_command([sys.executable, '-c', 'import time; time.sleep(10)'],
                                        tmp_path / 'timeout.log', 0.1)
    assert result['status'] == 'TIME_BUDGET_EXCEEDED'
    assert result['wall_seconds'] < 3.0
    assert result['returncode'] != 0


def test_rerun_requires_fix_note_and_changed_source_and_is_allowed_once():
    ledger = {'used_wall_seconds': 1.0, 'attempts': [
        {'model': 'resnet18', 'status': 'IMPLEMENTATION_FAILED', 'source_hashes': {'trainer': 'old'}}]}
    with pytest.raises(ValueError):
        common.next_attempt(ledger, 'resnet18')
    with pytest.raises(ValueError):
        common.next_attempt(ledger, 'resnet18', 'fixed loader', {'trainer': 'old'})
    assert common.next_attempt(ledger, 'resnet18', 'fixed loader', {'trainer': 'new'}) == 2
    ledger['attempts'].append({'model': 'resnet18', 'status': 'IMPLEMENTATION_FAILED', 'source_hashes': {'trainer': 'new'}})
    with pytest.raises(ValueError):
        common.next_attempt(ledger, 'resnet18', 'another fix', {'trainer': 'newer'})


@pytest.mark.parametrize('status', ['VERIFIED_PASS', 'TIME_BUDGET_EXCEEDED'])
def test_success_or_timeout_cannot_trigger_an_extra_smoke_run(status):
    ledger = {'used_wall_seconds': 1.0, 'attempts': [{'model': 'random_forest', 'status': status, 'source_hashes': {}}]}
    with pytest.raises(ValueError):
        common.next_attempt(ledger, 'random_forest', 'arbitrary change', {'trainer': 'new'})


def test_combined_budget_exhaustion_blocks_a_new_model():
    with pytest.raises(common.TimeBudgetExceeded):
        common.next_attempt({'used_wall_seconds': 1200.0, 'attempts': []}, 'logistic_regression')


def test_worker_directory_rejects_parent_traversal():
    with pytest.raises(ValueError):
        common.validate_worker_directory(common.RUNS / '..' / 'vision')


@pytest.mark.parametrize('script,extra', [
    ('ml/vision/train_resnet18.py', []),
    ('ml/telemetry/train_comparator.py', ['--model', 'random_forest']),
])
def test_p1_cli_rejects_full_training_before_opening_data(tmp_path, script, extra):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-B', str(root / script), '--run-dir', str(tmp_path),
                             *extra, '--full-dataset'], text=True, capture_output=True)
    assert result.returncode == 2
    assert 'unrecognized arguments: --full-dataset' in result.stderr


def test_supervisor_rejects_hpo_without_creating_a_run():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-B', str(root / 'ml/experiments/run_p1_smoke.py'),
                             '--run-id', 'unit_cli_rejection', '--hpo'], text=True, capture_output=True)
    assert result.returncode == 2
    assert 'unrecognized arguments: --hpo' in result.stderr
    assert not (common.RUNS / 'unit_cli_rejection').exists()


def test_process_startup_cannot_hide_exceeded_wall_budget(tmp_path, monkeypatch):
    original = common.subprocess.Popen

    def delayed_start(*args, **kwargs):
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(common.subprocess, 'Popen', delayed_start)
    result = common.run_bounded_command([sys.executable, '-c', 'pass'], tmp_path / 'startup.log', 0.1)
    assert result['status'] == 'TIME_BUDGET_EXCEEDED'
