"""Pure E1 preparation generators: validation/synthetic inputs, no model or I/O.

These functions deliberately refuse test inputs in P3. Formal P4 execution needs
separate authorization and a frozen protocol, including QC and physical bounds.
"""
import hashlib
import math

import numpy as np
from PIL import Image, ImageEnhance, ImageDraw

from ml.experiments.comparator_common import FEATURES, LABELS

VERSION = 'e1-preparation-v1'
VISION_STRENGTHS = {
    'brightness_up': [1.2, 1.5, 1.8], 'brightness_down': [.8, .5, .3],
    'motion_blur': [3, 7, 11], 'occlusion': [.05, .1, .2],
    'rotation_crop': [3, 7, 12], 'grayscale_blend': [.3, .6, 1.],
}


def _preparation_split(split):
    if split not in ('synthetic', 'val'):
        raise ValueError('E1 preparation permits synthetic/val inputs only')


def _rng(source_id, family, seed):
    digest = hashlib.sha256(f'{seed}\0{source_id}\0{family}'.encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:16], 'big'))


def qc_decision(valid=None, reviewer=None, reason=None):
    """Record a supplied independent judgement; never infer label validity."""
    if valid is not None and (not isinstance(valid, bool) or not reviewer or not reason):
        raise ValueError('QC decisions require a reviewer, reason and boolean validity')
    return {'status': 'PENDING' if valid is None else ('VALID' if valid else 'INVALID'),
            'f1_eligible': valid is True, 'reviewer': reviewer, 'reason': reason,
            'retain_for_flip_analysis': True}


def motion_kernel(size, angle):
    if size not in (3, 7, 11) or angle not in (0, 45, 90, 135):
        raise ValueError('Unsupported preparation motion kernel')
    kernel = np.zeros((size, size), dtype=np.float64)
    if angle == 0:
        kernel[size // 2, :] = 1
    elif angle == 90:
        kernel[:, size // 2] = 1
    else:
        np.fill_diagonal(kernel, 1)
        if angle == 135:
            kernel = np.fliplr(kernel)
    return kernel / size


def _motion_blur(image, size, angle):
    kernel = motion_kernel(size, angle)
    array = np.asarray(image, dtype=np.float64)
    padded = np.pad(array, ((size // 2, size // 2), (size // 2, size // 2), (0, 0)), mode='edge')
    result = np.zeros_like(array)
    for y, x in np.argwhere(kernel):
        result += kernel[y, x] * padded[y:y + 224, x:x + 224]
    return Image.fromarray(np.rint(result).clip(0, 255).astype(np.uint8))


def vision_variants(image, source_id, driver_id, *, source_split, seed=42):
    _preparation_split(source_split)
    base = image.convert('RGB').resize((224, 224), Image.Resampling.BILINEAR)
    for condition, strengths in [('clean', [None]), *VISION_STRENGTHS.items()]:
        for severity, strength in enumerate(strengths):
            rng = _rng(source_id, condition, seed)
            output, params, clipped = base.copy(), {}, 0
            if condition.startswith('brightness_'):
                clipped = int((np.asarray(base, dtype=float) * strength > 255).sum())
                output = ImageEnhance.Brightness(base).enhance(strength)
                params = {'factor': strength, 'saturation_policy': 'PIL_UINT8_CLAMP'}
            elif condition == 'motion_blur':
                angle = int(rng.choice([0, 45, 90, 135]))
                output = _motion_blur(base, strength, angle)
                params = {'kernel_size': strength, 'direction_degrees': angle,
                          'padding': 'edge', 'rounding': 'nearest_even'}
            elif condition == 'occlusion':
                side = round(math.sqrt(strength) * 224)
                x, y = (rng.random(2) * (225 - side)).astype(int).tolist()
                ImageDraw.Draw(output).rectangle((x, y, x + side - 1, y + side - 1), fill=(0, 0, 0))
                params = {'box_xywh': [x, y, side, side], 'actual_area_fraction': side * side / 224**2,
                          'fill_rgb': [0, 0, 0]}
            elif condition == 'rotation_crop':
                angle = int(rng.choice([-1, 1])) * strength
                radians = math.radians(abs(angle))
                side = math.floor(224 / (math.cos(radians) + math.sin(radians)))
                left = (224 - side) // 2
                box = [left, left, left + side, left + side]
                output = base.rotate(angle, resample=Image.Resampling.BILINEAR, expand=False,
                                     fillcolor=(0, 0, 0)).crop(box).resize((224, 224), Image.Resampling.BILINEAR)
                params = {'angle_degrees': angle, 'crop_box_xyxy': box,
                          'geometry_policy': 'centered_inscribed_square',
                          'formal_geometry_approval': 'PENDING', 'interpolation': 'PIL_BILINEAR'}
            elif condition == 'grayscale_blend':
                output = Image.blend(base, base.convert('L').convert('RGB'), strength)
                params = {'alpha': strength, 'grayscale': 'PIL_L', 'interpretation': 'NOT_INFRARED'}
            yield output, {
                'generator_version': VERSION, 'variant_id': f'{source_id}:{condition}:{severity}',
                'source_id': source_id, 'driver_id': driver_id, 'source_split': source_split,
                'condition': condition, 'strength': strength, 'severity': severity, 'seed': seed,
                'params': params, 'horizontal_flip': False, 'clipped_channel_values': clipped,
                'pixel_sha256': hashlib.sha256(output.tobytes()).hexdigest(),
                'qc_status': 'SOURCE_LABEL_UNREVIEWED' if condition == 'clean' else 'PENDING',
                'f1_eligible': False, 'retain_for_flip_analysis': True,
            }


def fit_train_statistics(values, labels, *, split, source_sha256):
    if split != 'train':
        raise ValueError('Statistics must be fitted on train only')
    x = np.asarray(values, dtype=np.float64)
    labels = np.asarray(labels)
    if (x.ndim != 2 or x.shape[1] != 8 or not len(x) or len(labels) != len(x)
            or np.isinf(x).any() or np.isnan(x).all(axis=0).any()
            or not set(labels).issubset(LABELS) or not source_sha256):
        raise ValueError('Invalid train statistics inputs')
    median = np.nanmedian(x, axis=0)
    imputed = np.where(np.isnan(x), median, x)
    return {'fit_split': 'train', 'fit_rows': len(x), 'train_split_sha256': source_sha256,
            'feature_order': FEATURES.copy(), 'median': median.tolist(),
            'mean_global': imputed.mean(axis=0).tolist(), 'sd_ddof0': imputed.std(axis=0).tolist(),
            'mean_by_class': {label: imputed[labels == label].mean(axis=0).tolist()
                              for label in LABELS if (labels == label).any()}}


def _nullable(values):
    return [None if np.isnan(value) else float(value) for value in values]


def telemetry_variants(values, labels, source_ids, statistics, *, missing_rates,
                       drift_direction, bounds, source_split, seed=42):
    _preparation_split(source_split)
    x = np.asarray(values, dtype=np.float64)
    if (x.ndim != 2 or x.shape[1] != 8 or np.isinf(x).any()
            or len(labels) != len(x) or len(source_ids) != len(x)
            or len(set(source_ids)) != len(x)):
        raise ValueError('Invalid telemetry inputs or duplicate source IDs')
    if (missing_rates is None or len(missing_rates) != 3 or
            any(not np.isfinite(r) or not 0 <= r <= 1 for r in missing_rates) or
            sorted(missing_rates) != list(missing_rates)):
        raise ValueError('Explicit ordered missing_rates required')
    direction = np.asarray(drift_direction, dtype=float)
    if direction.shape != (8,) or not np.isin(direction, [-1, 0, 1]).all():
        raise ValueError('Explicit eight-feature drift_direction required')
    if statistics['fit_split'] != 'train' or statistics['feature_order'] != FEATURES:
        raise ValueError('Train-only canonical statistics required')
    median = np.asarray(statistics['median'], dtype=float)
    mean = np.asarray(statistics['mean_global'], dtype=float)
    sd = np.asarray(statistics['sd_ddof0'], dtype=float)
    if any(a.shape != (8,) or not np.isfinite(a).all() for a in (median, mean, sd)) or (sd < 0).any():
        raise ValueError('Invalid train statistics')
    limits = None if bounds is None else np.asarray(bounds, dtype=float)
    if limits is not None and (limits.shape != (8, 2) or not np.isfinite(limits).all() or
                               (limits[:, 0] > limits[:, 1]).any()):
        raise ValueError('Invalid physical bounds')
    for raw, label, source_id in zip(x, labels, source_ids):
        if label not in LABELS or label not in statistics['mean_by_class']:
            raise ValueError('Unknown source label')
        noise = _rng(source_id, 'D1', seed).normal(size=8)
        uniforms = _rng(source_id, 'D3', seed).random(8)
        class_mean = np.asarray(statistics['mean_by_class'][label], dtype=float)
        for domain, strengths in [('D0', [0.]), ('D1', [.1, .3, .5]),
                                  ('D2', [.25, .5, .75]), ('D3', [.25, .5, 1.])]:
            for severity, strength in enumerate(strengths):
                delta = np.zeros(8)
                rate = 0.
                mask = np.isnan(raw).copy()
                if domain == 'D1':
                    delta = strength * sd * noise
                elif domain == 'D2':
                    delta = strength * (mean - class_mean)
                elif domain == 'D3':
                    delta = strength * sd * direction
                    rate = float(missing_rates[severity])
                    mask |= uniforms < rate
                observed = raw + delta
                observed[mask] = np.nan
                final = np.where(mask, median, observed)
                if not np.isfinite(final).all():
                    raise ValueError('Non-finite generated features')
                yield {
                    'generator_version': VERSION, 'variant_id': f'{source_id}:{domain}:{severity}',
                    'source_id': source_id, 'source_split': source_split, 'source_label': str(label),
                    'domain': domain, 'severity': severity, 'strength': strength, 'seed': seed,
                    'synthetic': True, 'perturbed': domain != 'D0', 'feature_order': FEATURES.copy(),
                    'raw_source_features': _nullable(raw), 'observed_features': _nullable(observed),
                    'features': final.tolist(), 'perturbation_delta': delta.tolist(),
                    'missing_mask': mask.tolist(), 'missing_rate': rate,
                    'drift_direction': direction.tolist() if domain == 'D3' else None,
                    'train_split_sha256': statistics['train_split_sha256'],
                    'label_conditioned': domain == 'D2',
                    'interpretation': 'LABEL_CONDITIONED_STRESS' if domain == 'D2' else 'SYNTHETIC_STRESS',
                    'bounds_policy': 'REPORT_ONLY_NO_CLIP' if limits is not None else 'UNRESOLVED',
                    'bounds_violations': None if limits is None else int(((final < limits[:, 0]) | (final > limits[:, 1])).sum()),
                    'clipped_cells': 0, 'qc_status': 'SOURCE_LABEL_UNREVIEWED' if domain == 'D0' else 'PENDING',
                    'f1_eligible': False, 'retain_for_flip_analysis': True,
                }
