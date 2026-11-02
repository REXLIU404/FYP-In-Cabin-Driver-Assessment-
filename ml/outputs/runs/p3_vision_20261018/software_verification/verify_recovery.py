"""Verify the controller-only migration; never fit, predict, or load a model."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from ml.experiments import comparator_common as common
from ml.experiments import run_vision_hpo as vision

run = Path(__file__).resolve().parents[1]
evidence = Path(__file__).resolve().parent
before = json.loads((evidence / 'config.json').read_text())
state = json.loads((run / 'probe_state.json').read_text())
checks = []


def check(name, condition):
    assert condition, name
    checks.append(name)


check('status', state['status'] == 'INTERRUPTED')
check('no_new_attempt', len(state['attempts']) == len(before['before_state']['attempts']) == 2)
check('no_budget_reset_or_extra_charge', state['used_wall_seconds'] == before['before_state']['used_wall_seconds'])
for name, record in before['unchanged_files'].items():
    path = run / name
    check('unchanged:' + name, path.stat().st_size == record['bytes'] and common.sha256(path) == record['sha256'])
for name, expected in before['protected_hashes'].items():
    check('protected:' + name, common.sha256(ROOT / name) == expected)
audit = (run / state['context_file']).parent
saved = json.loads((audit / 'probe_state.json').read_text())
check('original_state', saved == before['before_state'])
manifest = json.loads((audit / 'artifact_manifest.json').read_text())
for name, record in manifest['artifacts'].items():
    path = audit / name
    check('audit:' + name, path.stat().st_size == record['bytes'] and common.sha256(path) == record['sha256'])
context = json.loads((run / state['context_file']).read_text())
for name, expected in context['source_hashes'].items():
    check('active_source:' + name, common.sha256(ROOT / name) == expected)
check('active_signature', state['signature'] == vision.plan_signature(vision.probe_plans(), vision.PROBE_BUDGET, context))
for old, new in zip(saved['attempts'], state['attempts']):
    if old['status'] == 'IMPLEMENTATION_FAILED':
        check('preserved_signal_result', new['execution'] == old['execution'] and new['execution']['returncode'] == -15)
        check('corrected_interruption', new['status'] == 'INTERRUPTED' and new['original_status'] == old['status'])
    else:
        check('earlier_attempt_unchanged', new == old)
check('no_checkpoint_or_epoch_result', not list((run / 'probe').rglob('checkpoint.pt')) and not list((run / 'probe').rglob('validation_metrics.json')))
check('no_search_approval', not (ROOT / 'ml/configs/approved_vision_budget.json').exists())
check('empty_staging', not subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=ROOT).strip())
print(json.dumps({'status': 'VERIFIED_PASS', 'scope': 'non-training recovery only',
                  'checks_passed': len(checks), 'checks': checks,
                  'used_wall_seconds': state['used_wall_seconds'],
                  'remaining_total_seconds': vision.PROBE_BUDGET['total'] - state['used_wall_seconds'],
                  'probe_completed': False, 'new_training_attempts': 0,
                  'test_data_opened': False}, ensure_ascii=False, indent=2))
