"""DMD candidate evidence, item B: runtime compatibility and provider parity.

Pins the sample rule, the parity decision rule (FUD-01: max_abs_prob_delta <= 1e-4 AND
argmax agreement == 1.0), the independent preprocessing comparison and the manifest
validation before the real model is loaded.
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
PACKAGE = REPO / "ml" / "outputs" / "candidates" / "dmd_adapted_mobilenet_v3_20261029"
MANIFEST = PACKAGE / "runtime_manifest.json"
MODEL = PACKAGE / "model.onnx"


def load_runner():
    path = SCRIPTS / "dmd_candidate_runtime_check.py"
    assert path.is_file(), f"missing runner {path}"
    spec = importlib.util.spec_from_file_location("_dmd_candidate_runtime_check", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return load_runner()


def _probs(value, n=10):
    row = [value] * n
    return row


def test_parity_sample_is_20_per_class_sorted_and_deterministic(runner):
    sources = [{"source_id": f"vision-v1:c{c}/img_{i:03d}.jpg", "class_id": f"c{c}",
                "filename": f"img_{i:03d}.jpg", "image_path": f"/x/c{c}/img_{i:03d}.jpg"}
               for c in range(10) for i in [5, 1, 9] + list(range(20, 45))]
    sample = runner.select_parity_sample(sources, per_class=20)
    assert len(sample) == 200
    assert len({s["source_id"] for s in sample}) == 200
    assert [s["source_id"] for s in sample] == [s["source_id"] for s in runner.select_parity_sample(sources, 20)]
    for c in range(10):
        picked = [s["filename"] for s in sample if s["class_id"] == f"c{c}"]
        assert picked == sorted(picked)[:20]


def test_parity_requires_both_the_probability_and_argmax_conditions(runner):
    ids = ["a", "b"]
    same = {sid: _probs(0.1) for sid in ids}
    result = runner.compare_distributions(same, same)
    assert result["pass_numeric"] and result["max_abs_prob_delta"] == 0.0
    assert result["argmax_agreement"] == 1.0

    tiny = {sid: _probs(0.1) for sid in ids}
    tiny["a"] = _probs(0.1)
    tiny["a"][0] = 0.1 + 5e-5
    assert runner.compare_distributions(tiny, same)["pass_numeric"]

    too_big = {sid: _probs(0.1) for sid in ids}
    too_big["a"][0] = 0.1 + 1.1e-4
    failed = runner.compare_distributions(too_big, same)
    assert not failed["pass_numeric"] and failed["max_abs_prob_delta"] > 1e-4

    flipped = {sid: _probs(0.1) for sid in ids}
    flipped["a"] = [0.11, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.09]
    zero_one = {sid: _probs(0.1) for sid in ids}
    zero_one["a"] = [0.10, 0.11, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.09]
    argmax_failed = runner.compare_distributions(flipped, zero_one)
    assert not argmax_failed["pass_numeric"] and argmax_failed["argmax_mismatches"] == ["a"]

    missing = runner.compare_distributions({"a": _probs(0.1)}, same)
    assert not missing["pass_numeric"] and missing["missing_fresh"] == ["b"]


def test_independent_preprocessing_matches_the_provider_on_a_synthetic_jpeg(runner, tmp_path):
    from PIL import Image

    from app.providers.trained import TrainedProvider

    path = tmp_path / "frame.jpg"
    Image.fromarray(np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)).save(path, quality=90)
    import base64
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    provider = TrainedProvider.preprocess(encoded)
    independent = runner.independent_preprocess(path)
    assert provider.shape == independent.shape == (1, 3, 224, 224)
    assert float(np.max(np.abs(provider - independent))) <= 1e-6


def test_the_real_candidate_manifest_is_valid(runner):
    result = runner.validate_manifest(package_dir=PACKAGE, manifest_path=MANIFEST,
                                      validator=SCRIPTS / "validate_runtime_manifest.py")
    assert result["exit_code"] == 0, result
    assert "valid" in result["stdout"]


def test_model_identity_matches_the_protocol(runner):
    assert runner.DMD_MODEL_ID == "dmd_adapted_mobilenet_v3_20261029"
    assert runner.DMD_SHA256 == "01f1d6a3a57936590d29f1a86856fd6e67c8c9fd382f48bd601f9c66ed2b4d55"
    assert json.loads(MANIFEST.read_text())["model"]["sha256"] == runner.DMD_SHA256


@pytest.mark.candidates
def test_real_provider_and_direct_onnx_agree_on_two_state_farm_images(runner):
    """Heavy: builds the real provider (marked candidates; deselect unless -m candidates)."""
    if not runner.DEFAULT_STATE_FARM_SOURCES.is_file():
        pytest.skip("frozen State Farm input list not installed")
    sources = runner.load_state_farm_sources(runner.DEFAULT_STATE_FARM_SOURCES)
    picked = []
    for class_id in ("c0", "c1"):
        picked.append(next(s for s in sources if s["class_id"] == class_id))
    result = runner.provider_parity_in_process(picked)
    assert result["provider_vs_direct"]["pass_numeric"], result
    assert result["identity"]["model_id"] == runner.DMD_MODEL_ID
