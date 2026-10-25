"""Gated P4 data adapters. No models, fitting, or implicit held-out reads.

The P3 generator source stays immutable. A function-local globals mapping adapts
only its split guard, retaining the actual split in every output record. This is
not a global monkeypatch and never passes a test observation as validation.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
from types import FunctionType

import numpy as np
from PIL import Image

from ml.experiments import e1_generators as e1
from ml.experiments.comparator_common import FEATURES, LABELS

VERSION = 'p4-protocol-v1-adapter-1'
DOMAIN_BOUNDS = [(0., None)] + [(None, None)] * 6 + [(0., None)]
TELEMETRY_SHA256 = {
    'train':'97dd20ee9c0832ba33455e5c31088f9b4abb65c198bf988699a959d545d1e5b5',
    'val':'1b02792df846b5af138bae59e4f4ccfa8fa421fbb4fd6d42fad88d57722774f1',
    'test':'3bc3d47680a87359e1470fd8ffaf5ff330dc4419b37cc645e5736d51a91c96de'}
METADATA_SHA256 = 'b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4'


def _gate(split, authorization):
    if split == 'test':
        from ml.experiments.p4_core import P4Authorization
        if not isinstance(authorization, P4Authorization):
            raise PermissionError('Held-out access requires explicit P4-B authorization')
        authorization.require_heldout()
    elif split not in ('val', 'train', 'synthetic'):
        raise ValueError('Unknown source split')


def _verified_bytes(path, expected_sha256):
    if not expected_sha256:
        raise ValueError('Expected source SHA256 is mandatory')
    blob = Path(path).read_bytes()
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected_sha256:
        raise ValueError('Source SHA256 mismatch')
    return blob, actual


def read_vision_metadata(path, *, split, authorization=None, expected_sha256=None):
    _gate(split, authorization)  # Must precede even existence/hash reads.
    if Path(path).name == 'vision_metadata_with_split.csv' and expected_sha256 != METADATA_SHA256:
        raise ValueError('Frozen production metadata hash binding mismatch')
    if split not in ('val', 'test'):
        raise ValueError('Vision metadata reader supports val/test only')
    blob, sha = _verified_bytes(path, expected_sha256)
    rows = list(csv.DictReader(blob.decode('utf-8-sig').splitlines()))
    required = {'split', 'class_id', 'filename', 'driver_id', 'image_path'}
    if not rows or not required.issubset(rows[0]):
        raise ValueError('Vision metadata schema mismatch')
    drivers = {s: {r['driver_id'] for r in rows if r['split'] == s} for s in ('train','val','test')}
    if any(drivers[a] & drivers[b] for a,b in [('train','val'),('train','test'),('val','test')]):
        raise ValueError('Vision driver split overlap')
    output = []
    for index, row in enumerate(rows):
        if row['split'] != split:
            continue
        if row['class_id'] not in [f'c{i}' for i in range(10)] or not row['driver_id']:
            raise ValueError('Vision label/driver contract mismatch')
        filename = row['filename']
        if Path(filename).name != filename:
            raise ValueError('Vision filename must not contain a directory')
        output.append(dict(row, source_id=f"vision-v1:{row['class_id']}/{filename}",
                           source_row=index, source_split=split, metadata_sha256=sha,
                           metadata_path=str(Path(path).resolve())))
    if len({r['source_id'] for r in output}) != len(output):
        raise ValueError('Duplicate vision source ID')
    return output


def load_validation_image(record):
    if record.get('source_split') != 'val' or record.get('split') != 'val':
        raise PermissionError('Validation image requires proven val membership')
    # Re-read the small membership source rather than trusting a caller's dict.
    verified = read_vision_metadata(record['metadata_path'], split='val',
                                   expected_sha256=record['metadata_sha256'])
    if record not in verified:
        raise PermissionError('Validation image membership differs from frozen metadata')
    with Image.open(record['image_path']) as image:
        return image.convert('RGB').copy()


def read_telemetry_csv(path, *, split, authorization=None, expected_sha256=None):
    _gate(split, authorization)
    # Bind the frozen source identity as well as the caller's split string.
    # No source bytes (even a hash read) are allowed through a mislabeled path.
    for actual_split, sha in TELEMETRY_SHA256.items():
        if Path(path).name == f'telemetry_{actual_split}.csv' or expected_sha256 == sha:
            if actual_split != split:
                raise PermissionError('Telemetry path/hash split binding mismatch')
            if expected_sha256 != sha:
                raise ValueError('Frozen telemetry source SHA256 binding mismatch')
    if split not in ('train','val','test'):
        raise ValueError('CSV requires a real split')
    blob, sha = _verified_bytes(path, expected_sha256)
    reader = csv.DictReader(blob.decode('utf-8-sig').splitlines())
    if reader.fieldnames != FEATURES + ['behavior_label']:
        raise ValueError('Telemetry feature order mismatch')
    output = []
    for index, row in enumerate(reader):
        values = [float(row[key]) for key in FEATURES]
        if not np.isfinite(values).all() or row['behavior_label'] not in LABELS:
            raise ValueError('Telemetry clean source must be finite with canonical label')
        output.append({'source_id':f'telemetry-v1:{sha}:{split}:{index}', 'source_row':index,
                       'source_split':split, 'source_sha256':sha, 'features':values,
                       'source_label':row['behavior_label']})
    return output


def _adapt(function, split, authorization):
    _gate(split, authorization)
    if split == 'train':
        raise ValueError('Evaluation generation cannot use training observations')
    environment = dict(function.__globals__)
    environment['_preparation_split'] = lambda actual: _gate(actual, authorization)
    return FunctionType(function.__code__, environment, function.__name__,
                        function.__defaults__, function.__closure__)


def vision_bank(image, record, *, authorization=None, seed=42):
    split = record['source_split']
    generate = _adapt(e1.vision_variants, split, authorization)
    for output, row in generate(image, record['source_id'], record['driver_id'], source_split=split, seed=seed):
        row['adapter_version'] = VERSION
        for key in ('class_id','source_row','metadata_sha256','source_sha256'):
            if key in record:
                row[key] = record[key]
        if row['condition'] == 'rotation_crop':
            row['params']['geometry_protocol'] = 'P4-PROTOCOL-v1'
            row['params'].pop('formal_geometry_approval', None)
        yield output, row


def rotation_geometry_check():
    results = []
    for angle in (-12,-7,-3,3,7,12):
        radians = math.radians(abs(angle))
        side = math.floor(224/(math.cos(radians)+math.sin(radians)))
        left = (224-side)//2
        mask = Image.new('L',(224,224),255).rotate(angle, resample=Image.Resampling.BILINEAR,
            expand=False, fillcolor=0).crop((left,left,left+side,left+side)).resize((224,224),Image.Resampling.BILINEAR)
        fill = int(np.count_nonzero(np.asarray(mask) != 255))
        results.append({'angle':angle,'side':side,'crop_box':[left,left,left+side,left+side],
                        'fill_pixels':fill,'minimum_coverage':int(np.asarray(mask).min()),
                        'status':'PASS' if fill == 0 else 'FAILED_STOP_PROTOCOL_REVIEW'})
    if any(r['fill_pixels'] for r in results):
        raise ValueError('Frozen rotation geometry contains fill; stop for protocol review: '+json.dumps(results))
    return results


def verify_train_statistics(statistics, *, expected_train_sha256, pipeline_medians=(), computed_statistics=None):
    if (statistics.get('fit_split') != 'train' or statistics.get('train_split_sha256') != expected_train_sha256
            or statistics.get('feature_order') != FEATURES or statistics.get('fit_rows',0) <= 0
            or set(statistics.get('mean_by_class',{})) != set(LABELS)):
        raise ValueError('Frozen train-only statistics provenance mismatch')
    arrays = [statistics[k] for k in ('median','mean_global','sd_ddof0')]
    arrays += list(statistics['mean_by_class'].values())
    if any(np.asarray(a).shape != (8,) or not np.isfinite(a).all() for a in arrays):
        raise ValueError('Invalid frozen train statistic arrays')
    if any(x < 0 for x in statistics['sd_ddof0']):
        raise ValueError('Negative train SD')
    if any(np.asarray(a).shape != (8,) or not np.allclose(a, statistics['median'],atol=1e-12,rtol=1e-12)
           for a in pipeline_medians):
        raise ValueError('HPO pipeline median differs from frozen train median')
    if computed_statistics is not None:
        verify_train_statistics(computed_statistics,expected_train_sha256=expected_train_sha256)
        if computed_statistics['fit_rows'] != statistics['fit_rows']:
            raise ValueError('Train statistic row count mismatch')
        for key in ('median','mean_global','sd_ddof0'):
            if not np.allclose(statistics[key],computed_statistics[key],atol=1e-12,rtol=1e-12):
                raise ValueError(f'Frozen train statistic mismatch: {key}')
        for label in LABELS:
            if not np.allclose(statistics['mean_by_class'][label],computed_statistics['mean_by_class'][label],atol=1e-12,rtol=1e-12):
                raise ValueError(f'Frozen train class mean mismatch: {label}')
    return 'REUSED_AND_VERIFIED'


def _bound(value, lower, upper):
    if value is None or not np.isfinite(value):
        return {'status':'MISSING','lower_excess':None,'upper_excess':None}
    low = None if lower is None else max(float(lower)-value,0.)
    high = None if upper is None else max(value-float(upper),0.)
    status = ('OUT_OF_BOUNDS' if (low or high) else
              'UNKNOWN' if lower is None and upper is None else
              'WITHIN_KNOWN_BOUNDS_UPPER_UNKNOWN' if upper is None else
              'WITHIN_KNOWN_BOUNDS_LOWER_UNKNOWN' if lower is None else 'WITHIN_BOUNDS')
    return {'status':status,'lower_excess':low,'upper_excess':high}


def telemetry_bank(values, labels, source_ids, statistics, *, source_split,
                   authorization=None, empirical_bounds=None, seed=42):
    generate = _adapt(e1.telemetry_variants, source_split, authorization)
    x = np.asarray(values,dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 8 or not np.isfinite(x).all():
        raise ValueError('Clean source features must be finite; stop protocol check')
    verify_train_statistics(statistics, expected_train_sha256=statistics.get('train_split_sha256'))
    if empirical_bounds is not None:
        bounds = np.asarray(empirical_bounds,dtype=float)
        if bounds.shape != (8,2) or not np.isfinite(bounds).all() or (bounds[:,0] > bounds[:,1]).any():
            raise ValueError('Invalid train empirical bounds')
    else:
        bounds = [(None,None)]*8
    ranks = {sid:i for i,sid in enumerate(sorted(source_ids,key=lambda sid:(
        hashlib.sha256(f'{seed}\0{sid}\0D3_record_selection'.encode()).digest(),sid)))}
    for row in generate(x,labels,source_ids,statistics,missing_rates=[.05,.1,.2],
                        drift_direction=[1]*8,bounds=None,source_split=source_split,seed=seed):
        row['adapter_version'] = VERSION
        row['bounds_policy'] = 'REPORT_ONLY_NO_CLIP'
        row['record_selection_rank'] = ranks[row['source_id']]
        pre = (np.asarray(row['raw_source_features'])+np.asarray(row['perturbation_delta'])).tolist()
        stages = {'source':row['raw_source_features'],'pre_mask':pre,
                  'observed':row['observed_features'],'imputed':row['features']}
        row['pre_mask_features'] = pre
        row['bounds'] = {stage:[{'feature':FEATURES[i],
            'domain':_bound(v,*DOMAIN_BOUNDS[i]),'empirical':_bound(v,*bounds[i])}
            for i,v in enumerate(array)] for stage,array in stages.items()}
        row['label_validity'] = 'SOURCE_SYNTHETIC_LABEL' if row['domain']=='D0' else 'LABEL_VALIDITY_UNVERIFIED'
        row['f1_eligible'] = row['domain']=='D0'
        if row['domain']=='D3':
            row['interpretation'] = 'COMBINED_POSITIVE_BIAS_AND_RECORD_MISSINGNESS'
        yield row
