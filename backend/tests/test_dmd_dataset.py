"""scripts/dmd_dataset.py: manifest-driven dataset, transforms and split filtering."""
import csv
import importlib.util
from pathlib import Path

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
