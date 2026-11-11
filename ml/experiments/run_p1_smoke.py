"""Supervise P1-only smoke attempts with per-model and combined hard deadlines.

No automatic reruns. --resume requires --fix-note and a genuine changed-source
implementation fix; one failed-model rerun is permitted within the same budget.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ENTRY_STARTED = time.monotonic()
for variable in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[variable] = '2'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.experiments import comparator_common as common

SOURCE_FILES = ['ml/experiments/comparator_common.py', 'ml/experiments/run_p1_smoke.py',
                'ml/vision/train_resnet18.py', 'ml/telemetry/train_comparator.py']


def source_hashes():
    return {name: common.sha256(common.ROOT / name) for name in SOURCE_FILES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--data-root', type=Path, default=Path(os.environ.get('FYP_DATA_ROOT', common.DEFAULT_DATA)))
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--fix-note', default='')
    args = parser.parse_args()
    before = common.protected_snapshot()
    git = common.git_snapshot()
    sources = source_hashes()
    if args.resume:
        if not args.fix_note.strip():
            parser.error('--resume requires a documented genuine implementation fix')
        # Validate run_id without creating or overwriting an existing directory.
        if not args.run_id or '/' in args.run_id or '..' in args.run_id:
            parser.error('Invalid run_id')
        directory = common.RUNS / args.run_id
        common.reject_symlink_path(directory)
        ledger = json.loads((directory / 'artifact_manifest.json').read_text())
        config = json.loads((directory / 'config.json').read_text())
        if config['phase'] != 'P1' or config['data_root'] != str(args.data_root):
            parser.error('Resume must use the original P1 data root and budget')
        if ledger['status'] != 'IMPLEMENTATION_FAILED':
            parser.error('Only an implementation-failed run can resume')
    else:
        if args.fix_note:
            parser.error('--fix-note is only for an explicitly resumed failed attempt')
        directory = common.create_run_directory(args.run_id)
        config = {'run_id': args.run_id, 'phase': 'P1', 'scope': 'NON_COMPARATIVE_PIPELINE_SMOKE_ONLY',
            'approval': 'User approved exact P1 budget and confirmed seven audit-package deletions',
            'approved_budgets': common.APPROVED, 'combined_wall_seconds': 1200, 'data_root': str(args.data_root),
            'started_at': datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).isoformat(), 'git': git,
            'source_hashes': sources, 'protected_hashes_before': before,
            'formal_hpo_trials': 0, 'test_access_for_training_or_selection': False,
            'pretrained_downloads': False, 'candidate_package': False, 'automatic_reruns': False}
        config['authorities'] = {}
        import subprocess
        import hashlib
        for name in ['CODEX_ML_TRACK_PROMPT.md', 'CODEX_ML_TRACK_ADDENDUM_R4.md']:
            ref = f'fyp2/live-system:docs/fyp2/review/{name}'
            content = subprocess.check_output(['git', 'show', ref], cwd=common.ROOT)
            config['authorities'][name] = {'ref': ref, 'sha256': hashlib.sha256(content).hexdigest()}
        common.write_json(directory / 'config.json', config)
        ledger = {'run_id': args.run_id, 'phase': 'P1', 'status': 'RUNNING', 'used_wall_seconds': 0.0,
                  'attempts': [], 'formal_hpo_trials': 0, 'test_predictions': 0}
        common.write_json(directory / 'artifact_manifest.json', ledger)
    prior_used = ledger['used_wall_seconds']
    for model in common.MODELS:
        previous = [attempt for attempt in ledger['attempts'] if attempt['model'] == model]
        if previous and previous[-1]['status'] == 'VERIFIED_PASS':
            continue
        ledger['used_wall_seconds'] = prior_used + time.monotonic() - ENTRY_STARTED
        try:
            attempt_number = common.next_attempt(ledger, model, args.fix_note, sources)
        except common.TimeBudgetExceeded:
            ledger['status'] = 'TIME_BUDGET_EXCEEDED'
            common.write_json(directory / 'artifact_manifest.json', ledger, replace=True)
            return 124
        attempt_dir = directory / model / f'attempt_{attempt_number:02d}'
        attempt_dir.mkdir(parents=True, exist_ok=False)
        budget = common.validate_smoke_budget(model)
        timeout = min(budget['wall_seconds'], 1200 - ledger['used_wall_seconds'])
        script = 'ml/vision/train_resnet18.py' if model == 'resnet18' else 'ml/telemetry/train_comparator.py'
        command = [str(common.ROOT / '.venv/bin/python'), '-B', str(common.ROOT / script),
                   '--run-dir', str(attempt_dir), '--data-root', str(args.data_root)]
        if model != 'resnet18':
            command.extend(['--model', model])
        print(f'START {model} attempt={attempt_number} wall_limit={timeout:.3f}s', flush=True)
        process = common.run_bounded_command(command, attempt_dir / 'execution.log', timeout)
        metrics_path = attempt_dir / 'validation_metrics.json'
        metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
        status = process['status']
        if metrics.get('status') == 'TIME_BUDGET_EXCEEDED':
            status = 'TIME_BUDGET_EXCEEDED'
        elif status == 'VERIFIED_PASS' and metrics.get('status') != 'VERIFIED_PASS':
            status = 'IMPLEMENTATION_FAILED'
        attempt = {'model': model, 'attempt': attempt_number, 'status': status, 'source_hashes': sources,
                   'fix_note': args.fix_note if attempt_number == 2 else '', 'execution': process,
                   'metrics': str(metrics_path), 'artifact_records': [common.file_record(path) for path in sorted(attempt_dir.iterdir())
                                                                     if path.is_file() and not path.name.startswith('.')],
                   'formal_hpo_trials': 0}
        ledger['attempts'].append(attempt)
        ledger['used_wall_seconds'] = prior_used + time.monotonic() - ENTRY_STARTED
        ledger['status'] = status if status != 'VERIFIED_PASS' else 'RUNNING'
        common.write_json(directory / 'artifact_manifest.json', ledger, replace=True)
        print(f'END {model}: {status}, subprocess_wall={process["wall_seconds"]:.3f}s', flush=True)
        if status != 'VERIFIED_PASS':
            return 124 if status == 'TIME_BUDGET_EXCEEDED' else 1
    rf = directory / 'random_forest' / 'attempt_01/sample_manifest.csv'
    lr = directory / 'logistic_regression' / 'attempt_01/sample_manifest.csv'
    # On a repaired attempt, compare the latest successful sample manifests.
    for model in ['random_forest', 'logistic_regression']:
        latest = [attempt for attempt in ledger['attempts'] if attempt['model'] == model][-1]
        selected = directory / model / f'attempt_{latest["attempt"]:02d}/sample_manifest.csv'
        if model == 'random_forest':
            rf = selected
        else:
            lr = selected
    if common.sha256(rf) != common.sha256(lr):
        raise ValueError('RF/LR must use identical smoke source samples and order')
    after = common.protected_snapshot()
    if before != after:
        raise ValueError('Protected artifacts changed during smoke')
    ledger.update({'status': 'VERIFIED_PASS', 'protected_hashes_after': after, 'rf_lr_identical_samples': True,
                   'used_wall_seconds': prior_used + time.monotonic() - ENTRY_STARTED,
                   'finished_at': datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).isoformat()})
    if ledger['used_wall_seconds'] > 1200:
        ledger['status'] = 'TIME_BUDGET_EXCEEDED'
    common.write_json(directory / 'artifact_manifest.json', ledger, replace=True)
    print(json.dumps({'run_id': args.run_id, 'status': ledger['status'], 'combined_wall_seconds': ledger['used_wall_seconds'],
                      'attempts': len(ledger['attempts']), 'formal_hpo_trials': 0}, ensure_ascii=False), flush=True)
    return 0 if ledger['status'] == 'VERIFIED_PASS' else 124


if __name__ == '__main__':
    sys.exit(main())
