"""Fine-tune the stable MobileNetV3 on DMD body frames.

Two rules this file exists to enforce:

* only ``features[-2:]`` (blocks 15 and 16) and ``classifier`` train - a 2.2k-frame set
  cannot carry a full fine-tune without dragging the backbone off its source distribution;
* every ``BatchNorm2d`` stays in eval mode for the whole run. ``requires_grad=False``
  does NOT stop ``running_mean`` / ``running_var`` from being updated, so ``model.train()``
  would silently replace statistics learned on 15,899 State Farm images with three
  subjects' cabin lighting. The assertion is checked every epoch and aborts the run.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import torch
from torch import nn


def load_stable_checkpoint(model, checkpoint: Path) -> dict:
    """Load the stable checkpoint and verify its arch and class order.

    The stable file is NOT a bare state_dict: it is
    ``{"state_dict": ..., "classes": [...], "idx_to_name": {...}, "arch": "mobilenet_v3_large"}``.
    Passing it straight to ``load_state_dict`` raises a confusing RuntimeError; this
    function fails with a named reason instead.
    """
    raw = torch.load(checkpoint, map_location="cpu")
    if not isinstance(raw, dict) or "state_dict" not in raw:
        raise ValueError(
            "checkpoint must be the stable dict with a 'state_dict' key, not a bare state_dict")
    if raw.get("arch") != "mobilenet_v3_large":
        raise ValueError(f"checkpoint arch is {raw.get('arch')!r}, expected 'mobilenet_v3_large'")
    classes = list(raw.get("classes") or [])
    if classes != [f"c{i}" for i in range(10)]:
        raise ValueError(f"checkpoint class order is {classes}, expected c0..c9")
    model.load_state_dict(raw["state_dict"])
    return raw


def unfreeze_last_blocks(model, blocks: int = 2) -> None:
    """Freeze all, then unfreeze the last ``blocks`` feature blocks and the classifier.

    ``torchvision.mobilenet_v3_large().features`` is a Sequential of 17 blocks (0-16),
    so ``blocks=2`` means block 15 (last inverted residual) and block 16 (final 1x1 conv
    + BN + Hardswish). This is NOT two "stages" in the paper's sense.
    """
    for param in model.parameters():
        param.requires_grad = False
    for module in list(model.features.children())[-blocks:]:
        for param in module.parameters():
            param.requires_grad = True
    for param in model.classifier.parameters():
        param.requires_grad = True


def lock_batchnorm(model) -> None:
    for module in model.modules():
        if isinstance(module, nn.BatchNorm2d):
            module.eval()


def assert_batchnorm_locked(model) -> None:
    offenders = [m for m in model.modules()
                 if isinstance(m, nn.BatchNorm2d) and m.training]
    assert not offenders, (
        f"BatchNorm layers left in training mode after model.train(): {len(offenders)}")


def _epoch(model, loader, criterion, optimizer, device, train: bool):
    model.train() if train else model.eval()
    for block in list(model.features.children())[:-2]:
        block.eval()
    lock_batchnorm(model)          # MUST be last: model.train() re-enables BN
    assert_batchnorm_locked(model)
    total, preds, labels = 0.0, [], []
    torch.set_grad_enabled(train)
    for images, target in loader:
        images, target = images.to(device), target.to(device)
        logits = model(images)
        loss = criterion(logits, target)
        if train:
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        total += float(loss) * target.size(0)
        preds.extend(logits.argmax(1).tolist())
        labels.extend(target.tolist())
    torch.set_grad_enabled(True)
    return total / len(loader.dataset), preds, labels


def _macro_f1(preds: list[int], labels: list[int]) -> float:
    from sklearn.metrics import f1_score

    return float(f1_score(labels, preds, average="macro", zero_division=0))


def train(manifest_csv: Path, frames_root: Path, out_dir: Path, *, epochs: int = 30,
          batch_size: int = 32, patience: int = 8, seed: int = 42,
          checkpoint: Path | None = None) -> dict:
    """Train, early-stop on val macro-F1, save the best checkpoint. Returns history."""
    from torch.utils.data import DataLoader
    from torchvision.models import mobilenet_v3_large

    from dmd_dataset import DMDFrames, build_transform

    torch.manual_seed(seed)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = mobilenet_v3_large(weights=None, num_classes=10)
    if checkpoint is not None:
        load_stable_checkpoint(model, checkpoint)
    unfreeze_last_blocks(model, blocks=2)
    model.to(device)

    params = [
        {"params": model.features[-2:].parameters(), "lr": 1e-4},
        {"params": model.classifier.parameters(), "lr": 1e-3},
    ]
    optimizer = torch.optim.AdamW(params, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    train_ds = DMDFrames(manifest_csv, "train", build_transform(True), frames_root)
    val_ds = DMDFrames(manifest_csv, "val", build_transform(False), frames_root)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    history, best_f1, best_epoch, stale = [], -1.0, 0, 0
    for epoch in range(1, epochs + 1):
        started = time.perf_counter()
        train_loss, train_preds, train_labels = _epoch(
            model, train_loader, criterion, optimizer, device, train=True)
        val_loss, val_preds, val_labels = _epoch(
            model, val_loader, criterion, optimizer, device, train=False)
        scheduler.step()
        entry = {"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss,
                 "val_macro_f1": _macro_f1(val_preds, val_labels),
                 "train_macro_f1": _macro_f1(train_preds, train_labels),
                 "seconds": round(time.perf_counter() - started, 1)}
        history.append(entry)
        print(json.dumps(entry), flush=True)
        if entry["val_macro_f1"] > best_f1:
            best_f1, best_epoch, stale = entry["val_macro_f1"], epoch, 0
            torch.save(model.state_dict(), out_dir / "best.pt")
        else:
            stale += 1
            if stale >= patience:
                break

    result = {"epochs_run": len(history), "best_epoch": best_epoch,
              "best_val_macro_f1": best_f1, "converged": stale < patience,
              "history": history, "device": str(device), "seed": seed,
              "batch_size": batch_size, "checkpoint": str(out_dir / "best.pt")}
    (out_dir / "training_history.json").write_text(json.dumps(result, indent=2))
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("manifest_csv", type=Path)
    parser.add_argument("frames_root", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True,
                        help="stable mobilenetv3_large_vision.pt")
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()
    train(args.manifest_csv, args.frames_root, args.out_dir,
          epochs=args.epochs, checkpoint=args.checkpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
