"""Read saved P3 preparation evidence; no model or original held-out data."""
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]
count = 0


def check(value, message):
    global count
    if not value:
        raise AssertionError(message)
    count += 1


def read(name):
    return json.loads((RUN / name).read_text())


manifest = read('artifact_manifest.json')
for record in manifest['files'] + manifest['source_files']:
    path = Path(record['path'])
    check(path.stat().st_size == record['bytes'], f'bytes: {path}')
    check(hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256'], f'hash: {path}')
config, checks = read('config.json'), read('preparation_checks.json')
for key in ['fits', 'model_loads', 'model_forwards', 'held_out_observations_opened', 'qc_f1_eligible_count']:
    check(checks[key] == 0, key)
check(config['profile']['formal_execution_authorized'] is False, 'preparation scope')
check(config['protected_hashes_before'] == checks['protected_hashes_after'], 'protected hashes')
check(checks['train_statistics'] == 'REUSED_AND_VERIFIED', 'stats reuse')
check(config['git']['head'] == '335da4e3de203836c045452f84cc291bcd352a26', 'base HEAD')
check(bool(config['git']['dirty_state']), 'preparation source truthfully dirty')
check(config['git']['staged_paths'] == '', 'no staging')
vision = list(csv.DictReader((RUN/'vision_manifest.csv').open()))
telemetry = list(csv.DictReader((RUN/'telemetry_variants.csv').open()))
check(len(vision) == 190 and len(telemetry) == 300, 'counts')
check(len(set(row['variant_id'] for row in vision)) == 190, 'vision IDs')
check(len(set(row['variant_id'] for row in telemetry)) == 300, 'telemetry IDs')
check(set(Counter(row['source_id'] for row in vision).values()) == {19}, '19 per source')
check(Counter(row['class_id'] for row in vision) == {f'c{i}':19 for i in range(10)}, 'class balance')
check(set(Counter(row['source_id'] for row in telemetry).values()) == {10}, '10 per source')
check(Counter(row['source_label'] for row in telemetry) == {label:100 for label in ['Safe','Aggressive','Distracted']}, 'telemetry balance')
for row in vision:
    check(row['source_split'] == 'val' and row['horizontal_flip'] == 'False', 'vision scope')
    check(row['f1_eligible'] == 'False', 'vision QC gate')
    check(len(row['pixel_sha256']) == len(row['shared_tensor_sha256']) == 64, 'vision hashes')
    check(json.loads(row['shared_models']) == ['mobilenet_v3_large','resnet18'], 'shared vision')
    json.loads(row['params'])
stats = json.loads(Path(next(r['path'] for r in manifest['source_files']
                            if r['path'].endswith('preparation_evidence.json'))).read_text())['train_only_statistics']
groups = defaultdict(list)
for row in telemetry:
    features, observed, mask = [json.loads(row[key]) for key in ['features','observed_features','missing_mask']]
    check(len(features) == len(observed) == len(mask) == 8, 'telemetry shape')
    check(all(math.isfinite(x) for x in features), 'finite')
    check(all(math.isclose(value, stats['median'][i] if mask[i] else observed[i], rel_tol=1e-12, abs_tol=1e-12)
              for i,value in enumerate(features)), 'shared train median')
    check(row['source_split'] == 'val' and row['synthetic'] == 'True' and row['f1_eligible'] == 'False', 'telemetry scope')
    check(row['perturbed'] == ('False' if row['domain']=='D0' else 'True'), 'D0 flags')
    check(row['bounds_policy'] == 'UNRESOLVED' and int(row['clipped_cells']) == 0, 'bounds pending')
    check(json.loads(row['shared_models']) == ['xgboost','random_forest','logistic_regression'], 'shared telemetry')
    if row['domain'] == 'D2':
        check(row['label_conditioned'] == 'True' and row['interpretation'] == 'LABEL_CONDITIONED_STRESS', 'D2 label')
        expected = [x+float(row['strength'])*(g-c) for x,g,c in zip(json.loads(row['raw_source_features']),stats['mean_global'],stats['mean_by_class'][row['source_label']])]
        check(all(math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12) for a,b in zip(features,expected)), 'D2 formula')
    if row['domain'] == 'D3':
        groups[row['source_id']].append(mask)
for masks in groups.values():
    check(all(a<=b<=c for a,b,c in zip(*masks)), 'nested D3 masks')
print(f'PREPARATION_EVIDENCE_VERIFIED {count} checks; no model/test execution')
