"""Read saved P1 outputs only; no model load, fit, forward or test-data read."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

RUN = Path(__file__).resolve().parent.parent
ROOT = RUN.parents[3]
checks = []


def check(name, value):
    checks.append({'check': name, 'passed': bool(value)})
    if not value:
        raise AssertionError(name)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


ledger = json.loads((RUN / 'artifact_manifest.json').read_text())
configuration = json.loads((RUN / 'config.json').read_text())
check('supervisor_pass', ledger['status'] == 'VERIFIED_PASS')
check('combined_budget', 0 < ledger['used_wall_seconds'] < 1200)
check('three_primary_attempts_no_rerun', len(ledger['attempts']) == 3 and all(a['attempt'] == 1 for a in ledger['attempts']))
check('no_hpo_or_test_predictions', ledger['formal_hpo_trials'] == ledger['test_predictions'] == 0)
for relative, expected in configuration['source_hashes'].items():
    check(f'source_hash:{relative}', sha(ROOT / relative) == expected)
for relative, expected in configuration['protected_hashes_before'].items():
    check(f'protected_hash:{relative}', sha(ROOT / relative) == expected == ledger['protected_hashes_after'][relative])
summaries = {}
for attempt in ledger['attempts']:
    model = attempt['model']
    directory = RUN / model / 'attempt_01'
    metrics = json.loads((directory / 'validation_metrics.json').read_text())
    config = json.loads((directory / 'config.json').read_text())
    sample = pd.read_csv(directory / 'sample_manifest.csv')
    predictions = pd.read_csv(directory / 'predictions_validation.csv')
    budget = configuration['approved_budgets'][model]
    classes = [f'c{i}' for i in range(10)] if model == 'resnet18' else ['Safe', 'Aggressive', 'Distracted']
    check(f'{model}:pass_non_comparative', metrics['status'] == 'VERIFIED_PASS' and not metrics['formal_comparison_valid'])
    check(f'{model}:no_test_or_hpo', metrics['test_predictions'] == metrics['formal_hpo_trials'] == 0)
    check(f'{model}:seed', config['budget']['seed'] == 42)
    check(f'{model}:approved_counts', metrics['train_samples'] == budget['train_samples'] and metrics['validation_samples'] == budget['validation_samples'])
    check(f'{model}:stratified_unique_sources', sample.source_id.is_unique and set(sample.split) == {'train', 'val'}
          and all(sample[sample.split == split].label.value_counts().to_dict() == {label: n // len(classes) for label in classes}
                  for split, n in [('train', budget['train_samples']), ('val', budget['validation_samples'])]))
    val_ids = sample[sample.split == 'val'].source_id.tolist()
    check(f'{model}:prediction_ids', predictions.source_id.tolist() == val_ids)
    probs = predictions[[f'probability_{label}' for label in classes]].to_numpy()
    check(f'{model}:shape_and_class_order', list(probs.shape) == metrics['output_shape'] == [budget['validation_samples'], len(classes)]
          and metrics['class_order'] == classes)
    check(f'{model}:finite_probability_simplex', np.isfinite(probs).all() and (probs >= 0).all() and (probs <= 1).all()
          and np.allclose(probs.sum(axis=1), 1.0, atol=1e-6, rtol=0))
    check(f'{model}:diagnostics_finite', all(np.isfinite(metrics[key]) for key in ['accuracy', 'macro_f1', 'log_loss']))
    check(f'{model}:hard_wall_limit', attempt['execution']['wall_seconds'] < budget['wall_seconds'])
    check(f'{model}:checkpoint_hash', sha(metrics['checkpoint']['path']) == metrics['checkpoint']['sha256'])
    if model == 'resnet18':
        check('resnet18:epoch_steps_and_reload', metrics['epochs_completed'] == 1 and metrics['training_steps'] == 13
              and metrics['validation_steps'] == 7 and metrics['reload_validation_steps'] == 1 and metrics['total_validation_steps'] == 8)
        check('resnet18:loss_logits_and_reload_finite', np.isfinite(metrics['train_loss']) and np.isfinite(metrics['validation_loss'])
              and np.isfinite(predictions[[f'logit_{label}' for label in classes]].to_numpy()).all()
              and metrics['reload_max_abs_logit_difference'] <= 1e-6)
        check('resnet18:cpu_resource_limit', metrics['device'] != 'cpu' or metrics['threads'] <= 2)
    else:
        stats = json.loads((directory / 'train_statistics.json').read_text())
        check(f'{model}:single_fit_train_only_reload', metrics['fits_completed'] == 1 and metrics['train_only_preprocessing']
              and stats['fit_split'] == 'train_smoke_subset' and stats['fit_rows'] == 300
              and metrics['reload_max_abs_probability_difference'] <= 1e-12)
        check(f'{model}:threadpools_bounded', all(pool['num_threads'] <= 2 for pool in metrics['threadpools']))
    for record in attempt['artifact_records']:
        check(f'{model}:artifact:{Path(record["path"]).name}', sha(record['path']) == record['sha256'])
    summaries[model] = {'wall_seconds': attempt['execution']['wall_seconds'], 'diagnostic_accuracy': metrics['accuracy'],
                        'diagnostic_macro_f1': metrics['macro_f1'], 'formal_comparison_valid': False}
check('rf_lr_same_samples', sha(RUN / 'random_forest/attempt_01/sample_manifest.csv') == sha(RUN / 'logistic_regression/attempt_01/sample_manifest.csv'))
output = {'status': 'VERIFIED_PASS', 'scope': 'SAVED_SMOKE_ARTIFACTS_ONLY', 'classifier_fits': 0, 'model_forwards': 0,
          'heldout_data_reads': 0, 'checks': checks, 'summary': summaries}
(RUN / 'verification/artifact_manifest.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'checks_passed': len(checks), 'failures': 0, 'classifier_fits': 0, 'model_forwards': 0}))
