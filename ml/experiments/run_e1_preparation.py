"""Bounded P3 generator check; never load models or held-out observations."""
import argparse
import csv
import json
import resource
import sys
import time
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from PIL import Image

from ml.experiments import comparator_common as common
from ml.experiments import e1_generators as e1

PROFILE = common.ROOT / 'ml/configs/e1_preparation.json'
STATISTICS = common.RUNS / 'w2_preparation_20261015/preparation_evidence.json'


def validate_profile(profile):
    fixed = {'formal_execution_authorized': False, 'source_split': 'val', 'seed': 42,
             'vision_source_count': 10, 'telemetry_source_count': 30}
    if any(profile.get(key) != value for key, value in fixed.items()):
        raise ValueError('Profile exceeds the bounded P3 preparation scope')


def verify_reused_statistics(frozen, computed):
    try:
        for key in ['fit_split', 'fit_rows', 'train_split_sha256', 'feature_order']:
            if frozen[key] != computed[key]:
                raise ValueError(key)
        if set(frozen['mean_by_class']) != set(computed['mean_by_class']):
            raise ValueError('class means')
        for key in ['median', 'mean_global', 'sd_ddof0']:
            if not np.allclose(frozen[key], computed[key], atol=1e-12, rtol=1e-12):
                raise ValueError(key)
        for label in computed['mean_by_class']:
            if not np.allclose(frozen['mean_by_class'][label], computed['mean_by_class'][label], atol=1e-12, rtol=1e-12):
                raise ValueError(label)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f'Frozen train statistics mismatch: {error}') from error
    return 'REUSED_AND_VERIFIED'


def write_csv(path, rows):
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, allow_nan=False, sort_keys=True)
                             if isinstance(value, (dict, list)) else value for key, value in row.items()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args(argv)
    started, usage = time.monotonic(), resource.getrusage(resource.RUSAGE_SELF)
    profile = json.loads(PROFILE.read_text())
    validate_profile(profile)
    if profile['vision_strengths'] != e1.VISION_STRENGTHS:
        raise ValueError('Preparation profile and R4 vision strengths differ')
    protected = common.protected_snapshot()
    git = common.git_snapshot()
    if git['staged_paths']:
        raise ValueError('Unexpected staged files at preparation start')
    telemetry, telemetry_sources = common.load_telemetry(common.DEFAULT_DATA)
    vision, vision_sources, class_names = common.load_vision(common.DEFAULT_DATA)
    statistics = json.loads(STATISTICS.read_text())['train_only_statistics']
    computed = e1.fit_train_statistics(telemetry['train'][common.FEATURES].to_numpy(),
        telemetry['train'].behavior_label.to_numpy(), split='train',
        source_sha256=telemetry_sources['train']['sha256'])
    reuse = verify_reused_statistics(statistics, computed)
    hpo_statistics = []
    for model, trial in [('xgboost','xgboost_02'), ('random_forest','random_forest_06'),
                          ('logistic_regression','logistic_regression_06')]:
        path = common.RUNS / 'p3_telemetry_20261018' / model / trial / 'train_statistics.json'
        saved = json.loads(path.read_text())
        if (saved['feature_order'] != common.FEATURES or saved['fit_split'] != 'train'
                or saved['train_csv_sha256'] != statistics['train_split_sha256']
                or not np.allclose(saved['median'], statistics['median'], atol=1e-12, rtol=1e-12)):
            raise ValueError(f'Formal HPO train median mismatch: {path}')
        hpo_statistics.append(common.file_record(path))
    selected_v = common.stratified_sample(vision['val'], 'class_id', 10, 42, common.CLASSES)
    selected_t = common.stratified_sample(telemetry['val'], 'behavior_label', 30, 42, common.LABELS)
    directory = common.create_run_directory(args.run_id)
    sources = [common.file_record(PROFILE), common.file_record(STATISTICS),
               *hpo_statistics, *[common.file_record(common.ROOT / path) for path in
                ['ml/experiments/e1_generators.py', 'ml/experiments/run_e1_preparation.py',
                 'ml/experiments/comparator_common.py', 'ml/tests/test_e1_generators.py',
                 'ml/tests/test_e1_preparation.py']]]
    common.write_json(directory / 'config.json', {
        'run_id': args.run_id, 'stage': 'P3_E1_GENERATOR_PREPARATION_ONLY', 'profile': profile,
        'command': ['./.venv/bin/python', '-B', 'ml/experiments/run_e1_preparation.py', *sys.argv[1:]]
                   if argv is None else argv,
        'git': git, 'versions': common.software_versions(), 'source_files': sources,
        'dataset_ids': {'vision':'StateFarm/frozen-v1', 'telemetry':'synthetic-telemetry/frozen-v1'},
        'dataset_sources': {'vision':vision_sources, 'telemetry':telemetry_sources},
        'protected_hashes_before': protected, 'reused_train_statistics': reuse,
        'class_names': class_names, 'class_to_idx': {label:i for i,label in enumerate(common.CLASSES)},
        'clip_ids_available': False, 'threads': 2, 'device': 'CPU; no model execution',
        'authorization': 'User next-step approval; P3 val/synthetic preparation only; P4/P5 not authorized',
    })
    import hashlib
    import torch
    torch.set_num_threads(2)
    transform = common.vision_transforms(False)
    vision_rows, image_sources = [], []
    for index, row in selected_v.iterrows():
        if row.split != 'val':
            raise ValueError('Preparation image is not validation')
        image_sources.append(common.file_record(row.image_path))
        with Image.open(row.image_path) as original:
            for image, record in e1.vision_variants(original, f'vision-v1:{row.class_id}/{row.filename}',
                                                   row.driver_id, source_split='val'):
                first, second = transform(image).unsqueeze(0), transform(image).unsqueeze(0)
                if (first.shape != (1,3,224,224) or first.dtype != torch.float32
                        or not torch.isfinite(first).all() or not torch.equal(first,second)):
                    raise ValueError('Shared vision preprocessing mismatch')
                record.update({'source_row': int(index), 'class_id': row.class_id, 'class_name': row.class_name,
                               'source_sha256': image_sources[-1]['sha256'],
                               'shared_models': ['mobilenet_v3_large','resnet18'],
                               'shared_tensor_sha256': hashlib.sha256(first.numpy().tobytes()).hexdigest()})
                vision_rows.append(record)
    example = profile['preparation_example_only']
    telemetry_rows = list(e1.telemetry_variants(selected_t[common.FEATURES].to_numpy(),
        selected_t.behavior_label.tolist(),
        [f'telemetry-v1:{telemetry_sources["val"]["sha256"]}:val:{i}' for i in selected_t.index],
        statistics, missing_rates=example['D3_record_missing_rates'], drift_direction=example['D3_drift_direction'],
        bounds=example['bounds'], source_split='val'))
    for row in telemetry_rows:
        row['shared_models'] = ['xgboost','random_forest','logistic_regression']
        row['protocol_status'] = 'PREPARATION_EXAMPLES_NOT_FORMAL_FREEZE'
    if len(vision_rows) != 190 or len(telemetry_rows) != 300:
        raise ValueError('Preparation variant count mismatch')
    missingness_checks = []
    for severity, rate in enumerate(example['D3_record_missing_rates']):
        rows = [row for row in telemetry_rows if row['domain'] == 'D3' and row['severity'] == severity]
        affected = [row for row in rows if row['record_affected']]
        if (len(affected) != int(np.floor(len(selected_t) * rate + .5))
                or any(sum(row['injected_missing_mask']) != int(row['record_affected']) for row in rows)):
            raise ValueError('D3 record-level missingness mismatch')
        missingness_checks.append({'requested_record_rate':rate,'affected_records':len(affected),
            'population':len(selected_t),'realized_record_rate':len(affected)/len(selected_t),
            'injected_cells_per_affected_record':1})
    write_csv(directory / 'vision_manifest.csv', vision_rows)
    write_csv(directory / 'telemetry_variants.csv', telemetry_rows)
    common.write_json(directory / 'source_images.json', image_sources)
    after = common.protected_snapshot()
    if after != protected:
        raise ValueError('Protected files changed during preparation')
    common.write_json(directory / 'preparation_checks.json', {
        'status': 'VERIFIED_PASS_PREPARATION_ONLY', 'vision_sources': 10, 'vision_variants': len(vision_rows),
        'telemetry_sources': 30, 'telemetry_variants': len(telemetry_rows),
        'shared_vision_tensor_checks': 190, 'shared_telemetry_dataset_copies': 1,
        'D3_record_missingness': missingness_checks,
        'class_balanced_validation_only': True, 'source_images': image_sources,
        'train_statistics': reuse, 'train_rows_for_statistics_verification': len(telemetry['train']),
        'qc_f1_eligible_count': sum(row['f1_eligible'] for row in vision_rows + telemetry_rows),
        'fits': 0, 'model_loads': 0, 'model_forwards': 0, 'held_out_observations_opened': 0,
        'metadata_test_membership_read': True, 'formal_metrics': None,
        'runtime_seconds': time.monotonic()-started, 'resources': common.resource_usage(usage),
        'protected_hashes_after': after, 'formal_protocol_pending': profile['formal_protocol_pending'],
    })
    common.write_json(directory / 'artifact_manifest.json', {
        'stage':'PREPARATION_ONLY', 'files':[common.file_record(p) for p in sorted(directory.iterdir())],
        'source_files':sources, 'test_predictions':0, 'formal_execution_authorized':False})
    print('E1_PREPARATION_COMPLETE', directory)
    return 0


if __name__ == '__main__':
    sys.exit(main())
