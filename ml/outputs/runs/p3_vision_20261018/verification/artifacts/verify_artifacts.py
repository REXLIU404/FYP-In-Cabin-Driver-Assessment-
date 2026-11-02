"""S3 saved-file audit: CPU weights_only inspection; no fit/forward/test loader."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

for variable in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[variable] = '2'
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT))
import torch
from ml.experiments import comparator_common as common
from ml.experiments import run_vision_hpo as vision

torch.set_num_threads(2)
torch.set_num_interop_threads(1)
started = time.monotonic()
run = Path(__file__).resolve().parents[2]
state = json.loads((run / 'search_state.json').read_text())
context = json.loads((run / 'search_config.json').read_text())
checks = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


def record_check(name, path, record):
    check(name + ':exists', path.is_file() and not path.is_symlink())
    check(name + ':bytes', path.stat().st_size == record['bytes'])
    check(name + ':sha256', common.sha256(path) == record['sha256'])


check('completed_run', state['status'] == 'COMPLETED' and len(state['attempts']) == 16)
execution_commit = context['environment']['git']['execution_commit']
for name, expected in context['source_hashes'].items():
    check('source_current:' + name, common.sha256(ROOT / name) == expected)
    saved = subprocess.check_output(['git', 'show', f'{execution_commit}:{name}'], cwd=ROOT)
    import hashlib
    check('source_committed:' + name, hashlib.sha256(saved).hexdigest() == expected)
for name, expected in context['environment']['protected_hashes'].items():
    check('protected:' + name, common.sha256(ROOT / name) == expected)
for name, record in context['weights_manifest'].items():
    record_check('pretraining:' + name, Path(record['path']), record)

models = []
vision_records = 0
for attempt in state['attempts']:
    directory = run / attempt['directory']
    plan, metrics = attempt['plan'], attempt['metrics']
    vision.verify_completed(run, attempt)
    manifest = json.loads((directory / 'artifact_manifest.json').read_text())
    for name, record in manifest['artifacts'].items():
        if 'sha256' not in record:
            check('deferred_test:' + attempt['key'], name == 'predictions_test.csv' and record['created'] is False)
            continue
        vision_records += 1
        record_check(attempt['key'] + ':' + name, directory / name, record)
    checkpoint = torch.load(directory / 'checkpoint.pt', map_location='cpu', weights_only=True)
    check(attempt['key'] + ':arch', checkpoint['arch'] == plan['model'])
    check(attempt['key'] + ':seed', checkpoint['seed'] == plan['seed'])
    check(attempt['key'] + ':epoch', checkpoint['best_epoch'] == metrics['best_epoch'])
    check(attempt['key'] + ':not_probe', checkpoint['probe'] is False)
    check(attempt['key'] + ':classes', checkpoint['classes'] == common.CLASSES)
    check(attempt['key'] + ':class_order', checkpoint['class_to_idx'] == {c: i for i, c in enumerate(common.CLASSES)})
    check(attempt['key'] + ':names', checkpoint['idx_to_name'] == manifest['training_label_names'])
    check(attempt['key'] + ':weights', checkpoint['pretraining'] == context['weights_manifest'][plan['model']])
    expected_preprocessing = {'rgb': True, 'resize': [224, 224], 'interpolation': 'PIL bilinear', 'crop': False,
                              'mean': common.MEAN, 'std': common.STD, 'layout': 'NCHW', 'dtype': 'float32'}
    check(attempt['key'] + ':preprocessing', checkpoint['preprocessing'] == expected_preprocessing)
    tensors = checkpoint['state_dict']
    head = 'fc.weight' if plan['model'] == 'resnet18' else 'classifier.3.weight'
    check(attempt['key'] + ':head', list(tensors[head].shape) == [10, 512 if plan['model'] == 'resnet18' else 1280])
    for name, tensor in tensors.items():
        check(attempt['key'] + ':finite_tensor:' + name, torch.is_tensor(tensor) and tensor.device.type == 'cpu' and bool(torch.isfinite(tensor).all()))
    log = (directory / 'execution.log').read_text()
    check(attempt['key'] + ':worker_success', 'TRIAL_COMPLETE ' + plan['model'] + ' ' + plan['trial_id'] in log and 'Traceback' not in log)
    check(attempt['key'] + ':reload_record', metrics['reload_verified'] and metrics['reload_samples'] == 16 and metrics['reload_max_abs_logit_difference'] <= 1e-5)
    check(attempt['key'] + ':no_test', metrics['test_predictions'] == metrics['test_images_opened'] == manifest['test_images_opened'] == 0 and not (directory / 'predictions_test.csv').exists())
    models.append({'key': attempt['key'], 'role': plan['role'], 'seed': plan['seed'], 'checkpoint_bytes': (directory / 'checkpoint.pt').stat().st_size,
                   'checkpoint_sha256': common.sha256(directory / 'checkpoint.pt'), 'tensor_count': len(tensors),
                   'reload_max_abs_logit_difference_recorded': metrics['reload_max_abs_logit_difference'],
                   'max_rss_bytes': metrics['resource_usage']['max_rss_bytes'],
                   'mps_observed_driver_bytes': metrics['mps_max_observed_driver_bytes']})
    del checkpoint, tensors

telemetry = ROOT / 'ml/outputs/runs/p3_telemetry_20261018'
telemetry_state = json.loads((telemetry / 'artifact_manifest.json').read_text())
telemetry_records = 0
for row in telemetry_state['trials']:
    if not row.get('execution', {}).get('command_started'):
        continue
    directory = Path(row['directory'])
    check('telemetry_path:' + row['trial_id'], directory.resolve().is_relative_to(telemetry.resolve()))
    manifest = json.loads((directory / 'artifact_manifest.json').read_text())
    for name, record in manifest['artifacts'].items():
        if 'sha256' not in record:
            continue
        path = Path(record['path'])
        check('telemetry_artifact_path:' + row['trial_id'] + ':' + name, path.resolve().is_relative_to(directory.resolve()))
        record_check('telemetry:' + row['trial_id'] + ':' + name, path, record)
        telemetry_records += 1
old_verification = json.loads((telemetry / 'verification/artifact_manifest.json').read_text())
for name, record in old_verification['source_identity'].items():
    check('telemetry_executed_source:' + name, common.sha256(record['snapshot_path']) == record['as_executed_sha256'])

print(json.dumps({'status': 'VERIFIED_PASS', 'checks_passed': len(checks), 'failures': [],
                  'runtime_seconds': time.monotonic() - started, 'execution_commit': execution_commit,
                  'vision_artifact_records': vision_records, 'vision_checkpoints_inspected_weights_only_cpu': len(models),
                  'telemetry_artifact_records_rehashed': telemetry_records, 'models': models,
                  'new_fits': 0, 'new_model_forward_calls': 0, 'test_csv_or_images_opened': False,
                  'scope': 'Saved artifacts and CPU tensor inspection; worker reload evidence reused, no independent numerical retraining'}, indent=2))
