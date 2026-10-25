"""P4-A boundaries: synthetic arrays/images; never real checkpoint/ONNX export."""
import importlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def module():
    return importlib.import_module('ml.experiments.p4_preflight')


def test_validation_selection_rejects_duplicate_ids_and_never_selects_test():
    p = module()
    rows = [dict(split='val', class_id=f'c{i}', filename=f'{j}.jpg', driver_id='v')
            for i in range(10) for j in range(11)]
    rows += [dict(split='test', class_id='c0', filename='heldout.jpg', driver_id='t')]
    selected = p.select_validation(rows)
    assert len(selected) == 100
    assert all(row['split'] == 'val' for row in selected)
    assert {f'c{i}': sum(x['class_id'] == f'c{i}' for x in selected) for i in range(10)} == {f'c{i}': 10 for i in range(10)}
    assert [x['filename'] for x in selected] == [x['filename'] for x in p.select_validation(rows[::-1])]
    with pytest.raises(ValueError, match='Duplicate'):
        p.select_validation(rows + [rows[0]])


def test_preprocess_matches_hand_computed_constant_rgb():
    values = module().preprocess(Image.new('RGB', (7, 4), (255, 0, 0)))
    assert values.shape == (3, 224, 224)
    assert values.dtype == np.float32 and values.flags.c_contiguous
    np.testing.assert_allclose(values[:, 5, 9], [2.2489083, -2.0357143, -1.8044444], atol=1e-6)


def test_parity_checks_full_batch_plan_and_catches_tail_corruption():
    p = module()
    bank = np.zeros((100, 3, 2, 2), dtype=np.float32)
    def reference(x):
        result = np.zeros((len(x), 10), dtype=np.float32)
        result[:, 0] = 2
        return result
    seen = []
    def runtime(x):
        seen.append(len(x))
        return reference(x)
    report, predictions = p.check_parity(bank, reference, runtime)
    assert seen == [1] * 100 + [32, 32, 32, 4, 2, 9]
    assert report['samples_compared'] == 211
    assert report['argmax_equal'] and report['max_absolute_error'] == 0
    assert predictions.shape == (100, 10)
    def bad_tail(x):
        result = reference(x)
        if len(x) == 9:
            result[0, 1] = .001
        return result
    with pytest.raises(ValueError, match='parity'):
        p.check_parity(bank, reference, bad_tail)


@pytest.mark.parametrize('bad', ['argmax', 'nan', 'dtype', 'shape'])
def test_parity_rejects_argmax_flip_even_within_tolerance_and_malformed_logits(bad):
    p = module()
    def reference(x):
        return np.zeros((len(x), 10), dtype=np.float32)
    def runtime(x):
        result = reference(x)
        if bad == 'argmax': result[:, 1] = 1e-6
        if bad == 'nan': result[:, 1] = np.nan
        if bad == 'dtype': result = result.astype(np.float64)
        if bad == 'shape': result = result[:, :9]
        return result
    with pytest.raises(ValueError):
        p.check_parity(np.zeros((100, 1), np.float32), reference, runtime)


def test_export_permit_is_exclusive_and_refuses_stable(tmp_path):
    p = module()
    with pytest.raises(ValueError, match='stable'):
        p.reserve_export(tmp_path, 'MN-STABLE')
    target = p.reserve_export(tmp_path, 'MN-HPO42')
    assert target.name == 'model.onnx'
    with pytest.raises(FileExistsError):
        p.reserve_export(tmp_path, 'MN-HPO42')
    assert not target.exists()


def test_logits_contract_rejects_softmax_static_batch_external_weights():
    import onnx
    from onnx import TensorProto, helper
    p = module()
    def graph(op='Identity', dynamic=True):
        return helper.make_model(helper.make_graph(
            [helper.make_node(op, ['input'], ['logits'])], 'tiny',
            [helper.make_tensor_value_info('input', TensorProto.FLOAT, ['N' if dynamic else 1, 3, 224, 224])],
            [helper.make_tensor_value_info('logits', TensorProto.FLOAT, ['N' if dynamic else 1, 10])]),
            opset_imports=[helper.make_opsetid('', 17)])
    p.validate_graph(graph())
    for model in [graph('Softmax'), graph('LogSoftmax'), graph(dynamic=False)]:
        with pytest.raises(ValueError): p.validate_graph(model)
    model = graph()
    weight = helper.make_tensor('weight', TensorProto.FLOAT, [1], [0])
    weight.data_location = TensorProto.EXTERNAL
    model.graph.initializer.append(weight)
    with pytest.raises(ValueError, match='external'): p.validate_graph(model)


def test_throughput_has_one_warmup_two_measurements_and_true_loop_counts():
    p = module()
    bank = np.zeros((100, 1), np.float32)
    calls = []
    def runtime(x):
        calls.append(len(x))
        return np.zeros((len(x), 10), np.float32)
    result = p.measure_throughput(bank, runtime)
    assert calls == [32, 32, 32, 4] * 3
    assert result['warmup_images'] == 100 and result['measured_images'] == 200
    assert len(result['rounds']) == 3 and len(result['batch_nanoseconds']) == 8
    assert result['images_per_second'] > 0


def test_projection_preserves_all_three_identities_and_caps():
    result = module().project_budget({name: {'seconds_per_100': 1.0} for name in ['MN-HPO42', 'RN-HPO42', 'MN-STABLE']}, generation_seconds_per_1900=1.0)
    assert result['vision_input_count'] == 69483
    assert result['vision_prediction_count'] == 208449
    assert result['margin'] == 1.25
    assert result['formal_runtime_benchmark_completed'] is False
    assert result['stage_caps_seconds']['vision_clean'] == 1200
    assert result['per_model_caps_seconds']['vision_stress'] == 2400
    with pytest.raises(ValueError): module().project_budget({'MN-HPO42': {'seconds_per_100': 1}}, 1)


def test_resource_gate_rejects_before_creating_outputs(tmp_path):
    p = module()
    with pytest.raises(RuntimeError, match='RAM'):
        p.check_resources(tmp_path, available_ram=8 * 1024**3 - 1, free_disk=30 * 1024**3)
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(RuntimeError, match='disk'):
        p.check_resources(tmp_path, available_ram=9 * 1024**3, free_disk=20 * 1024**3 - 1)


def test_access_guard_denies_test_csv_and_unlisted_image_before_open(tmp_path):
    p = module()
    allowed = tmp_path / 'val.jpg'
    Image.new('RGB', (2, 2)).save(allowed)
    test = tmp_path / 'test.jpg'
    Image.new('RGB', (2, 2)).save(test)
    guard = p.ValidationAccess([allowed])
    with Image.open(guard.checked_image(allowed)) as image:
        assert image.size == (2, 2)
    with pytest.raises(PermissionError): guard.checked_image(test)
    with pytest.raises(PermissionError): guard.audit('open', (str(test), 'r', 0))
    with pytest.raises(PermissionError): guard.audit('open', (str(tmp_path / 'telemetry_test.csv'), 'r', 0))
    assert len(guard.accessed) == 1


def test_bank_loader_detects_changed_tensor_and_hash(tmp_path):
    p = module()
    bank = np.zeros((100, 3, 224, 224), np.float32)
    path = tmp_path / 'validation_bank.npy'
    np.save(path, bank)
    manifest = {'bank_file_sha256': p.sha256(path), 'tensor_sha256': __import__('hashlib').sha256(bank.tobytes()).hexdigest()}
    (tmp_path / 'validation_manifest.json').write_text(json.dumps(manifest))
    assert p.load_bank(tmp_path).shape == (100, 3, 224, 224)
    bank[0, 0, 0, 0] = 1
    np.save(path, bank)
    with pytest.raises(ValueError, match='bank'):
        p.load_bank(tmp_path)


def test_checkpoint_rejects_seed_class_index_head_and_name_mismatch():
    p = module()
    names = {f'c{i}': 'normal_driving' if i == 0 else f'action_{i}' for i in range(10)}
    saved = {'arch': 'resnet18', 'classes': [f'c{i}' for i in range(10)], 'seed': 42,
             'class_to_idx': {f'c{i}': i for i in range(10)}, 'idx_to_name': names,
             'state_dict': {'fc.weight': np.zeros((10, 2), np.float32)}}
    p.validate_checkpoint(saved, 'RN-HPO42', names)
    for changed in [dict(saved, seed=43), dict(saved, class_to_idx={f'c{i}': 9-i for i in range(10)}),
                    dict(saved, state_dict={'fc.weight': np.zeros((9, 2))}), dict(saved, idx_to_name={})]:
        with pytest.raises(ValueError): p.validate_checkpoint(changed, 'RN-HPO42', names)


def test_cli_resource_failure_precedes_any_observation_or_export(tmp_path, monkeypatch):
    p = module()
    monkeypatch.setattr(p, 'RUN', tmp_path)
    def insufficient(_):
        raise RuntimeError('BLOCKED: RAM')
    monkeypatch.setattr(p, 'check_resources', insufficient)
    monkeypatch.setenv('P4_BUDGET_WORKER', '1')
    with pytest.raises(RuntimeError, match='RAM'):
        p.main(['export', '--identity', 'MN-HPO42', '--run-dir', str(tmp_path)])
    assert list(tmp_path.iterdir()) == []


def test_export_writes_fixed_legacy_fp32_benchmark_provenance_without_extra_attempt(tmp_path, monkeypatch):
    # Export is the scarce/expensive external operation; fake just that boundary.
    import torch
    import onnx
    from onnx import helper, TensorProto
    p = module()
    monkeypatch.setattr(p, 'torch_model', lambda identity, run: object())
    monkeypatch.setattr(p, 'load_bank', lambda directory: np.zeros((100, 3, 224, 224), np.float32))
    observed = []
    def exporter(model, example, target, **settings):
        assert example.dtype == torch.float32 and tuple(example.shape) == (1, 3, 224, 224)
        assert settings == {'export_params': True, 'opset_version': 17, 'input_names': ['input'],
            'output_names': ['logits'], 'dynamic_axes': {'input': {0: 'N'}, 'logits': {0: 'N'}},
            'keep_initializers_as_inputs': False, 'dynamo': False, 'external_data': False}
        observed.append(target)
        graph = helper.make_model(helper.make_graph([helper.make_node('Identity', ['input'], ['logits'])], 'fake-export',
            [helper.make_tensor_value_info('input', TensorProto.FLOAT, ['N', 3, 224, 224])],
            [helper.make_tensor_value_info('logits', TensorProto.FLOAT, ['N', 10])]), opset_imports=[helper.make_opsetid('', 17)])
        onnx.save(graph, target)
    monkeypatch.setattr(torch.onnx, 'export', exporter)
    report = p.export_model(tmp_path, 'RN-HPO42')
    manifest = json.loads((Path(observed[0]).parent / 'benchmark_manifest.json').read_text())
    assert manifest['identity'] == 'RN-HPO42' and manifest['candidate_package'] is False
    assert manifest['deployment_eligible'] is False and manifest['onnx_bytes'] > 0
    assert manifest['source_checkpoint_sha256'] == '008d831c98ea5e4b6c5c821787b3dc9a1dcbc6ca47a74dd1d8f7110eb4ac7d20'
    assert report['onnx_sha256'] == p.sha256(observed[0])
    with pytest.raises(FileExistsError): p.export_model(tmp_path, 'RN-HPO42')


def test_supervised_preflight_runs_exact_two_exports_then_three_parity_before_timing(tmp_path):
    p = module()
    calls = []
    class Supervisor:
        def __init__(self, path, **settings):
            assert settings['total_seconds'] == 1200
            assert settings['stage_caps'] == {'preflight': 600, 'timing': 600}
            assert settings['output_root'] == tmp_path
        def run(self, command, **limits):
            action = command[5]
            calls.append((action, command, limits))
            return {'returncode': 0}
    p.run_preflight(tmp_path, supervisor_factory=Supervisor)
    assert [c[0] for c in calls] == ['prepare', 'export', 'export', 'parity', 'parity', 'parity',
                                    'throughput', 'throughput', 'throughput', 'generation', 'projection']
    assert [c[2]['stage'] for c in calls] == ['preflight'] * 6 + ['timing'] * 5
    assert all(c[2]['rss_cap_bytes'] == 8 * 1024**3 for c in calls)
    assert all(c[2]['worker_cap_seconds'] == (600 if c[0] == 'generation' else 120) for c in calls)
    assert calls[1][2]['model'] != calls[3][2]['model']  # export/parity have separate caps
    with pytest.raises(FileExistsError): p.run_preflight(tmp_path, supervisor_factory=Supervisor)


def test_supervised_parity_failure_stops_before_timing_and_never_retries_export(tmp_path):
    p = module()
    calls = []
    class Supervisor:
        def __init__(self, *args, **kwargs): pass
        def run(self, command, **limits):
            action = command[5]
            calls.append(action)
            if action == 'parity': raise RuntimeError('failed parity')
    with pytest.raises(RuntimeError, match='parity'):
        p.run_preflight(tmp_path, supervisor_factory=Supervisor)
    assert calls == ['prepare', 'export', 'export', 'parity']


def test_cli_refuses_unsupervised_model_worker(tmp_path, monkeypatch):
    p = module()
    monkeypatch.setattr(p, 'RUN', tmp_path)
    monkeypatch.delenv('P4_BUDGET_WORKER', raising=False)
    with pytest.raises(ValueError, match='supervis'):
        p.main(['export', '--identity', 'MN-HPO42', '--run-dir', str(tmp_path)])
    assert list(tmp_path.iterdir()) == []
