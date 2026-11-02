"""scripts/dmd_export_candidate.py: the package must satisfy the runtime contract.

ONNX export imports torch. torch 2.12 on macOS leaves the pytest process in a state
that segfaults later tests of the shared suite, so the export test is gated behind
``DRA_DMD_TORCH=1``; run it explicitly:

    DRA_DMD_TORCH=1 pytest backend/tests/test_dmd_export.py -q
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# torch 2.12 on macOS segfaults during ONNX export in a long pytest process;
# a single thread removes the openmp race.
pytestmark = pytest.mark.skipif(
    os.environ.get("DRA_DMD_TORCH") != "1",
    reason="torch tests poison the shared pytest process on macOS; run with DRA_DMD_TORCH=1")

REPO = Path(__file__).resolve().parents[2]
EXPORT = REPO / "scripts" / "dmd_export_candidate.py"

sys.path.insert(0, str(REPO / "backend"))

from app.runtime_manifest import validate_package  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("dmd_export_candidate", EXPORT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_manifest_has_every_required_key_and_legal_provenance():
    e = _load()
    manifest = e.build_manifest(
        run_id="pkg", model_sha256="a" * 64, parent_sha256="b" * 64,
        smoke={"split": "val", "selection": "s", "n": 3,
               "sample_ids_sha256": "c" * 64, "rule": "per_class_mode_equals_label"})
    assert set(manifest) == {
        "manifest_version", "kind", "run_id", "architecture", "model", "input",
        "preprocess", "output", "classes", "class_to_idx", "safe_class",
        "contract_smoke_set", "provenance"}
    assert manifest["provenance"]["parent_model_sha256"] == "b" * 64
    assert not [k for k in manifest["provenance"] if "metric" in k.lower()]


def _tiny_net():
    """Same shape as the production factory, 1/1000 the parameters.

    Exporting the real MobileNetV3 inside a long pytest process crashes torch 2.12 on
    macOS; the manifest contract under test does not depend on the network size.
    """
    import torch
    from torch import nn

    torch.set_num_threads(1)

    class TinyNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(3, 8, 3, padding=1), nn.BatchNorm2d(8), nn.ReLU(),
            )
            self.classifier = nn.Linear(8, 10)

        def forward(self, x):
            x = self.features(x)
            x = torch.nn.functional.adaptive_avg_pool2d(x, 1).flatten(1)
            return self.classifier(x)

    return TinyNet()


def test_export_writes_a_package_that_validate_package_accepts(tmp_path):
    torch = pytest.importorskip("torch")

    e = _load()
    checkpoint = tmp_path / "best.pt"
    torch.save(_tiny_net().state_dict(), checkpoint)
    out_dir = tmp_path / "pkg"
    e.export(checkpoint, out_dir=out_dir, parent_sha256="b" * 64, smoke_n=1,
             model_factory=_tiny_net)
    manifest = json.loads((out_dir / "runtime_manifest.json").read_text())
    assert validate_package(manifest, out_dir) == []
    assert (out_dir / "model.onnx").is_file()
    assert (out_dir / "class_metadata.json").is_file()
    metadata = json.loads((out_dir / "class_metadata.json").read_text())
    # vision_candidates._labels refuses a package without a training label per class
    assert sorted(metadata["training_labels"]) == [f"c{i}" for i in range(10)]
    assert metadata["training_labels"]["c0"] == "safe_driving"
    assert metadata["dmd_actions"]["c2"] == "phonecall_right"


def test_export_refuses_a_zero_sized_smoke_set(tmp_path):
    e = _load()
    with pytest.raises(ValueError, match="smoke_n"):
        e.export(tmp_path / "missing.pt", out_dir=tmp_path / "pkg",
                 parent_sha256="b" * 64, smoke_n=0)
