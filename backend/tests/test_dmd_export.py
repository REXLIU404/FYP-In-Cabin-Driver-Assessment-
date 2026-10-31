"""scripts/dmd_export_candidate.py: the package must satisfy the runtime contract."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

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


def test_export_writes_a_package_that_validate_package_accepts(tmp_path):
    torch = pytest.importorskip("torch")
    from torchvision.models import mobilenet_v3_large

    e = _load()
    model = mobilenet_v3_large(weights=None, num_classes=10)
    checkpoint = tmp_path / "best.pt"
    torch.save(model.state_dict(), checkpoint)
    out_dir = tmp_path / "pkg"
    e.export(checkpoint, out_dir=out_dir, parent_sha256="b" * 64, smoke_n=1)
    manifest = json.loads((out_dir / "runtime_manifest.json").read_text())
    assert validate_package(manifest, out_dir) == []
    assert (out_dir / "model.onnx").is_file()
    assert (out_dir / "class_metadata.json").is_file()


def test_export_refuses_a_zero_sized_smoke_set(tmp_path):
    e = _load()
    with pytest.raises(ValueError, match="smoke_n"):
        e.export(tmp_path / "missing.pt", out_dir=tmp_path / "pkg",
                 parent_sha256="b" * 64, smoke_n=0)
