"""scripts/dmd_dataset.py / dmd_train.py: dataset, transforms, BN lock, checkpoint.

Torch is imported at module scope by this file. On macOS, torch 2.12 leaves the pytest
process in a state that segfaults later tests of the shared suite (reproduced at ~46%%,
in ``test_fusion_vectors.py``, long after this module finishes; ``set_num_threads(1)``
only moves the crash). The module is therefore gated behind ``DRA_DMD_TORCH=1`` so the
shared suite stays green; run it explicitly:

    DRA_DMD_TORCH=1 pytest backend/tests/test_dmd_dataset.py -q
"""
import csv
import importlib.util
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("DRA_DMD_TORCH") != "1",
    reason="torch tests poison the shared pytest process on macOS; run with DRA_DMD_TORCH=1")

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "scripts" / "dmd_dataset.py"


def _load():
    spec = importlib.util.spec_from_file_location("dmd_dataset", DATASET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_manifest(tmp_path, rows):
    path = tmp_path / "sampling_manifest.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "subject", "session", "split", "action", "class_id",
            "annotation_frame_idx", "body_frame_idx", "effective_shift", "video", "file"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def _tiny_jpeg(path):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), (10, 20, 30)).save(path, "JPEG")


def test_dataset_filters_by_split_and_maps_class_to_index(tmp_path):
    d = _load()
    rows = []
    for i, (split, cls) in enumerate([("train", "c0"), ("train", "c7"),
                                      ("val", "c3"), ("test", "c9")]):
        rel = f"gA_1/s{i}/c/cls_{i}.jpg"
        _tiny_jpeg(tmp_path / "frames" / rel)
        rows.append({"subject": "gA_1", "session": f"s{i}", "split": split,
                     "action": "x", "class_id": cls, "annotation_frame_idx": i + 40,
                     "body_frame_idx": i, "effective_shift": 40,
                     "video": "v.mp4", "file": rel})
    manifest = _write_manifest(tmp_path, rows)
    train = d.DMDFrames(manifest, "train", transform=None, root=tmp_path / "frames")
    assert len(train) == 2
    assert train.labels() == [0, 7]
    assert len(d.DMDFrames(manifest, "test", transform=None,
                           root=tmp_path / "frames")) == 1


def test_train_transform_never_flips_horizontally():
    d = _load()
    names = [type(t).__name__ for t in d.build_transform(train=True).transforms]
    assert "RandomHorizontalFlip" not in names
    assert "RandomRotation" not in names
    assert "RandomResizedCrop" in names


def test_eval_transform_is_deterministic_resize_only():
    d = _load()
    names = [type(t).__name__ for t in d.build_transform(train=False).transforms]
    assert names[0] == "Resize"
    assert "RandomResizedCrop" not in names


TRAIN = REPO / "scripts" / "dmd_train.py"


def _load_train():
    spec = importlib.util.spec_from_file_location("dmd_train", TRAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tiny_model():
    """A MobileNetV3-shaped stand-in: `features` is a Sequential of 3 blocks.

    The real 5.5M-parameter model is created a dozen times in this module and crashes
    torch 2.12 on macOS inside `_load_from_state_dict` when the full suite runs first.
    The logic under test (`features[-2:]` freezing, BatchNorm locking) depends only on
    the shape, so a tiny network exercises it without the runtime risk.
    """
    import torch
    from torch import nn

    torch.set_num_threads(1)

    class TinyNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(
                nn.Sequential(nn.Conv2d(3, 8, 3, padding=1), nn.BatchNorm2d(8), nn.ReLU()),
                nn.Sequential(nn.Conv2d(8, 8, 3, padding=1), nn.BatchNorm2d(8), nn.ReLU()),
                nn.Sequential(nn.Conv2d(8, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU()),
            )
            self.classifier = nn.Linear(16, 10)

    return TinyNet()


def test_lock_batchnorm_puts_every_bn_in_eval():
    import torch
    t = _load_train()
    model = _tiny_model()
    model.train()
    t.lock_batchnorm(model)
    bns = [m for m in model.modules() if isinstance(m, torch.nn.BatchNorm2d)]
    assert bns and all(not m.training for m in bns)


def test_assert_batchnorm_locked_raises_when_one_epoch_leaves_bn_training():
    import torch
    t = _load_train()
    model = _tiny_model()
    t.lock_batchnorm(model)
    t.assert_batchnorm_locked(model)
    next(m for m in model.modules() if isinstance(m, torch.nn.BatchNorm2d)).train()
    with pytest.raises(AssertionError, match="BatchNorm"):
        t.assert_batchnorm_locked(model)


def test_unfreeze_last_blocks_keeps_early_features_frozen():
    t = _load_train()
    model = _tiny_model()
    t.unfreeze_last_blocks(model, blocks=2)
    assert all(not p.requires_grad for p in model.features[:-2].parameters())
    assert all(p.requires_grad for p in model.features[-2:].parameters())
    assert all(p.requires_grad for p in model.classifier.parameters())


def test_load_stable_checkpoint_rejects_a_bare_state_dict(tmp_path):
    import torch
    t = _load_train()
    torch.save(_tiny_model().state_dict(), tmp_path / "bare.pt")
    with pytest.raises(ValueError, match="state_dict"):
        t.load_stable_checkpoint(_tiny_model(), tmp_path / "bare.pt")


def test_load_stable_checkpoint_rejects_a_wrong_class_order(tmp_path):
    import torch
    t = _load_train()
    torch.save({"state_dict": _tiny_model().state_dict(),
                "arch": "mobilenet_v3_large", "classes": ["c1", "c0"]},
               tmp_path / "bad.pt")
    with pytest.raises(ValueError, match="class"):
        t.load_stable_checkpoint(_tiny_model(), tmp_path / "bad.pt")


def test_load_stable_checkpoint_accepts_the_real_stable_layout(tmp_path):
    import torch
    t = _load_train()
    model = _tiny_model()
    torch.save({"state_dict": model.state_dict(), "arch": "mobilenet_v3_large",
                "classes": [f"c{i}" for i in range(10)],
                "idx_to_name": {f"c{i}": f"n{i}" for i in range(10)}},
               tmp_path / "good.pt")
    raw = t.load_stable_checkpoint(model, tmp_path / "good.pt")
    assert raw["arch"] == "mobilenet_v3_large"
