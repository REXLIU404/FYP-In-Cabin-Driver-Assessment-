"""Manifest-driven dataset for the DMD body frames.

The split column is authoritative: a subject appears in exactly one split (Task 1), so
filtering by `split` is a subject-level holdout. Horizontal flip and rotation are
forbidden - left/right hand is label-bearing and the camera angle is fixed.
"""
from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image
from torch.utils.data import Dataset

CLASS_IDS = tuple(f"c{i}" for i in range(10))
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def build_transform(train: bool):
    from torchvision import transforms

    if train:
        return transforms.Compose([
            transforms.RandomResizedCrop(224, scale=(0.7, 1.0), ratio=(0.85, 1.18)),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])
    return transforms.Compose([
        transforms.Resize((224, 224), interpolation=transforms.InterpolationMode.BILINEAR),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])


class DMDFrames(Dataset):
    def __init__(self, manifest_csv: Path, split: str, transform=None, root: Path | None = None):
        if split not in ("train", "val", "test"):
            raise ValueError(f"unknown split {split!r}")
        self.root = Path(root) if root is not None else Path(manifest_csv).parent / "frames"
        self.transform = transform
        self.rows = [r for r in csv.DictReader(Path(manifest_csv).open())
                     if r["split"] == split]
        if not self.rows:
            raise ValueError(f"no rows for split {split!r} in {manifest_csv}")

    def __len__(self) -> int:
        return len(self.rows)

    def labels(self) -> list[int]:
        return [CLASS_IDS.index(r["class_id"]) for r in self.rows]

    def __getitem__(self, index: int):
        row = self.rows[index]
        image = Image.open(self.root / row["file"]).convert("RGB")
        tensor = self.transform(image) if self.transform is not None else image
        return tensor, CLASS_IDS.index(row["class_id"])
