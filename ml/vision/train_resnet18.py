"""ResNet18 P1 smoke trainer. Run through run_p1_smoke.py; no downloads/HPO."""
import argparse
import os
import sys
import time
from pathlib import Path

for variable in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[variable] = '2'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.experiments import comparator_common as common


def train_smoke(directory, data_root, deadline):
    import resource
    import numpy as np
    import pandas as pd
    import torch
    from PIL import Image
    from torch.utils.data import DataLoader, Dataset
    from torchvision import models

    started = time.monotonic()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    budget = common.validate_smoke_budget('resnet18')
    common.check_deadline(deadline)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(42)
    np.random.seed(42)
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    frames, sources, names = common.load_vision(data_root)
    train = common.stratified_sample(frames['train'], 'class_id', 200, 42, common.CLASSES)
    validation = common.stratified_sample(frames['val'], 'class_id', 100, 42, common.CLASSES)
    common.steps_for_samples(len(train), 16, budget['training_steps'])
    common.steps_for_samples(len(validation), 16, budget['validation_steps'], extra=1)
    class_to_idx = {label: index for index, label in enumerate(common.CLASSES)}
    source_rows = []
    for split, selected in [('train', train), ('val', validation)]:
        for index, row in selected.iterrows():
            common.check_deadline(deadline)
            source_rows.append({'source_id': f'vision-v1:{row.class_id}/{row.filename}', 'source_row': int(index),
                'split': split, 'label': row.class_id, 'driver_id': row.driver_id,
                'image_path': row.image_path, 'image_sha256': common.sha256(row.image_path)})
    pd.DataFrame(source_rows).to_csv(directory / 'sample_manifest.csv', index=False)
    model = models.resnet18(weights=None)
    cache = Path.home() / '.cache/torch/hub/checkpoints/resnet18-f37072fd.pth'
    initialization = {'weights': None, 'status': 'RANDOM_INITIALIZATION_SMOKE_ONLY',
                      'comparison_validity': 'NOT_VALID_FOR_FORMAL_MODEL_COMPARISON'}
    if cache.is_file():
        fingerprint = common.sha256(cache)
        if not fingerprint.startswith('f37072fd'):
            raise ValueError('Local ResNet18 pretraining checksum does not match its known recipe')
        model.load_state_dict(torch.load(cache, map_location='cpu', weights_only=True), strict=True)
        initialization = {'weights': 'ResNet18_Weights.IMAGENET1K_V1', 'sha256': fingerprint,
                          'path': str(cache), 'comparison_validity': 'NOT_VALID_FOR_FORMAL_MODEL_COMPARISON'}
    model.fc = torch.nn.Linear(model.fc.in_features, 10)
    model.to(device)
    configuration = {'phase': 'P1', 'model': 'resnet18', 'smoke': True, 'formal_comparison_valid': False,
        'counts_toward_hpo': False, 'budget': budget, 'data_root': str(data_root), 'sources': sources,
        'class_to_idx': class_to_idx, 'training_label_names': names,
        'runtime_label_names': ['safe_driving', *[names[c] for c in common.CLASSES[1:]]],
        'initialization': initialization, 'device': str(device), 'torch_threads': torch.get_num_threads(),
        'torch_interop_threads': torch.get_num_interop_threads(), 'workers': 0,
        'preprocessing': {'rgb': True, 'resize': [224, 224], 'interpolation': 'PIL bilinear', 'crop': False,
                         'mean': common.MEAN, 'std': common.STD, 'layout': 'NCHW', 'dtype': 'float32'},
        'train_augmentation': {'rotation_degrees': 8, 'brightness': 0.2, 'contrast': 0.2, 'horizontal_flip': False},
        'optimizer': {'name': 'AdamW', 'lr': 0.0008, 'weight_decay': 0.0001},
        'git': common.git_snapshot(), 'versions': common.software_versions(), 'test_images_opened': 0}
    common.write_json(directory / 'config.json', configuration)

    class Frames(Dataset):
        def __init__(self, frame, training):
            self.frame = frame
            self.transform = common.vision_transforms(training)

        def __len__(self):
            return len(self.frame)

        def __getitem__(self, index):
            row = self.frame.iloc[index]
            with Image.open(row.image_path) as image:
                values = self.transform(image.convert('RGB'))
            return values, class_to_idx[row.class_id]

    generator = torch.Generator().manual_seed(42)
    train_loader = DataLoader(Frames(train, True), batch_size=16, shuffle=True, generator=generator, num_workers=0)
    val_loader = DataLoader(Frames(validation, False), batch_size=16, shuffle=False, num_workers=0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.0008, weight_decay=0.0001)
    criterion = torch.nn.CrossEntropyLoss()
    timings, train_losses = [], []
    train_steps, train_seen = 0, 0
    model.train()
    for inputs, labels in train_loader:
        common.check_deadline(deadline)
        if train_steps >= budget['training_steps']:
            raise ValueError('Training step budget exhausted before all approved samples')
        step_start = time.monotonic()
        inputs, labels = inputs.to(device), labels.to(device)
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(model(inputs), labels)
        if not torch.isfinite(loss):
            raise ValueError('Non-finite training loss')
        loss.backward()
        optimizer.step()
        if device.type == 'mps':
            torch.mps.synchronize()
        train_losses.append((float(loss.detach().cpu()), len(labels)))
        train_steps += 1
        train_seen += len(labels)
        timings.append({'phase': 'train', 'step': train_steps, 'samples': len(labels),
                        'seconds': time.monotonic() - step_start, 'warmup': False})
        common.check_deadline(deadline)
    model.eval()
    outputs, labels_all, val_steps = [], [], 0
    reload_input = None
    with torch.inference_mode():
        for inputs, labels in val_loader:
            common.check_deadline(deadline)
            if val_steps + 1 >= budget['validation_steps']:
                raise ValueError('Validation budget must leave one step for checkpoint reload')
            step_start = time.monotonic()
            logits = model(inputs.to(device)).cpu()
            if not torch.isfinite(logits).all():
                raise ValueError('Non-finite validation logits')
            if reload_input is None:
                reload_input = inputs.clone()
                reload_reference = logits.clone()
            outputs.append(logits)
            labels_all.append(labels)
            val_steps += 1
            timings.append({'phase': 'validation', 'step': val_steps, 'samples': len(labels),
                            'seconds': time.monotonic() - step_start, 'warmup': False})
    logits = torch.cat(outputs)
    labels = torch.cat(labels_all)
    probabilities = logits.softmax(1).numpy()
    common.validate_probabilities(probabilities, 100, common.CLASSES, range(10))
    validation_loss = float(criterion(logits, labels))
    if not np.isfinite(validation_loss) or train_seen != 200 or len(labels) != 100:
        raise ValueError('Incomplete or non-finite smoke pass')
    common.check_deadline(deadline)
    checkpoint = directory / 'resnet18_smoke.pt'
    temporary = directory / 'resnet18_smoke.tmp.pt'
    torch.save({'state_dict': {k: v.detach().cpu() for k, v in model.state_dict().items()},
                'arch': 'resnet18', 'classes': common.CLASSES, 'class_to_idx': class_to_idx,
                'idx_to_name': names, 'smoke': True, 'formal_comparison_valid': False}, temporary)
    os.replace(temporary, checkpoint)
    fingerprint = common.sha256(checkpoint)
    reloaded = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if reloaded['classes'] != common.CLASSES or reloaded['class_to_idx'] != class_to_idx:
        raise ValueError('Saved checkpoint class mapping mismatch')
    restored = models.resnet18(weights=None)
    restored.fc = torch.nn.Linear(restored.fc.in_features, 10)
    restored.load_state_dict(reloaded['state_dict'], strict=True)
    restored.to(device).eval()
    step_start = time.monotonic()
    with torch.inference_mode():
        recovered_logits = restored(reload_input.to(device)).cpu()
    reload_difference = float((recovered_logits - reload_reference).abs().max())
    if not torch.allclose(recovered_logits, reload_reference, atol=1e-6, rtol=1e-6):
        raise ValueError('Reload changed validation logits')
    timings.append({'phase': 'reload_validation', 'step': 1, 'samples': len(reload_input),
                    'seconds': time.monotonic() - step_start, 'warmup': False})
    if val_steps + 1 > budget['validation_steps'] or common.sha256(checkpoint) != fingerprint:
        raise ValueError('Reload budget or checkpoint integrity failure')
    predicted = pd.DataFrame({'source_id': [f'vision-v1:{r.class_id}/{r.filename}' for r in validation.itertuples()],
                              'true_label_index': labels.numpy(), 'predicted_label_index': probabilities.argmax(1)})
    for index, label in enumerate(common.CLASSES):
        predicted[f'logit_{label}'] = logits.numpy()[:, index]
        predicted[f'probability_{label}'] = probabilities[:, index]
    predicted.to_csv(directory / 'predictions_validation.csv', index=False)
    pd.DataFrame(timings).to_csv(directory / 'timing_samples.csv', index=False)
    metrics = common.diagnostics(labels.numpy(), probabilities, common.CLASSES)
    common.write_json(directory / 'class_report.json', metrics.pop('class_report'))
    common.write_json(directory / 'selection_log.json', {'selection': 'NONE_SMOKE_FINAL_EPOCH_ONLY', 'test_used': False, 'hpo_trials': 0})
    pd.DataFrame([{'record_kind': 'PIPELINE_SMOKE', 'counts_toward_hpo': False, 'seed': 42, 'epochs': 1,
                   'training_steps': train_steps, 'validation_steps': val_steps, 'reload_steps': 1}]).to_csv(directory / 'trials.csv', index=False)
    metrics.update({'status': 'VERIFIED_PASS', 'model': 'resnet18', 'initialization': initialization,
        'train_samples': train_seen, 'validation_samples': len(labels), 'epochs_completed': 1,
        'training_steps': train_steps, 'validation_steps': val_steps, 'reload_validation_steps': 1,
        'total_validation_steps': val_steps + 1, 'train_loss': sum(loss * count for loss, count in train_losses) / train_seen,
        'validation_loss': validation_loss, 'output_shape': list(probabilities.shape), 'class_order': common.CLASSES,
        'reload_max_abs_logit_difference': reload_difference, 'all_losses_and_probabilities_finite': True,
        'checkpoint': common.file_record(checkpoint), 'device': str(device), 'threads': torch.get_num_threads(),
        'worker_wall_seconds': time.monotonic() - started, 'resource_usage': common.resource_usage(usage),
        'test_predictions': 0, 'formal_hpo_trials': 0, 'candidate_package': False})
    common.check_deadline(deadline)
    common.write_json(directory / 'validation_metrics.json', metrics)
    print(f'ResNet18 smoke VERIFIED_PASS: {train_steps} train + {val_steps}+1 validation steps; {initialization["status"] if "status" in initialization else "local pretrained"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, default=Path(os.environ.get('FYP_DATA_ROOT', common.DEFAULT_DATA)))
    args = parser.parse_args()
    directory = common.validate_worker_directory(args.run_dir)
    if 'FYP_P1_DEADLINE_MONOTONIC' not in os.environ:
        parser.error('Launch through ml/experiments/run_p1_smoke.py for hard process/global budget enforcement')
    try:
        train_smoke(directory, args.data_root, float(os.environ['FYP_P1_DEADLINE_MONOTONIC']))
        return 0
    except Exception as error:
        import traceback
        status = 'TIME_BUDGET_EXCEEDED' if isinstance(error, common.TimeBudgetExceeded) else 'IMPLEMENTATION_FAILED'
        common.write_json(directory / 'validation_metrics.json', {'status': status, 'error': str(error), 'formal_comparison_valid': False})
        traceback.print_exc()
        return 124 if status == 'TIME_BUDGET_EXCEEDED' else 1


if __name__ == '__main__':
    sys.exit(main())
