"""Task 10A: manifest-driven vision candidates (plan docs/plans/2026-10-25-task-10a-candidate-integration.md,
corrections C-1..C-8 in docs/plans/2026-10-26-task-10a-analysis-and-collaboration.zh.md).

The stable MobileNetV3 stays the default; a candidate is selected by DRA_ACTIVE_VISION at process
start. Synthetic packages (tmp_path) test the loader's contract and always run; tests that need the
real copied packages under ml/outputs/candidates/ carry the ``candidates`` marker (deselected unless
``-m candidates``, see conftest)."""
from app.config import Settings


def test_default_active_vision_is_stable():
    # The class defaults: no instance is built, no environment variable is read.
    assert Settings.model_fields["active_vision"].default == "stable"
    assert Settings.model_fields["vision_candidates_root"].default.name == "candidates"
    assert Settings.model_fields["vision_candidates_root"].default.parent == Settings.model_fields["model_root"].default


# ====================================================================== the loader (Task 1.2)
import copy  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.providers.trained import ModelUnavailable  # noqa: E402

STABLE_LABELS = ["safe_driving", "texting_right", "talking_phone_right", "texting_left", "talking_phone_left",
                 "operating_radio", "drinking", "reaching_behind", "hair_makeup", "talking_to_passenger"]
CLASSES = [f"c{i}" for i in range(10)]
REAL_ROOT = Path(__file__).resolve().parents[2] / "ml" / "outputs" / "candidates"
REAL = {"resnet18_search004_seed42": ("p5_resnet18_search004_seed42_20261023",
                                      "5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3"),
        "mobilenet_v3_large_search006_seed42": ("p5_mobilenet_v3_large_search006_seed42_20261023",
                                                "9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828")}


def _logits_onnx(path: Path, bias=None, outputs: int = 10) -> None:
    """X(1,3,224,224) -> flatten -> MatMul(zeros) + bias: constant logits whatever the image.
    Zero bias gives uniform probabilities (P_distraction = 0.9)."""
    import onnx
    from onnx import TensorProto, helper
    weight = np.zeros((3 * 224 * 224, outputs), dtype=np.float32)
    bias = np.zeros(outputs, dtype=np.float32) if bias is None else np.asarray(bias, dtype=np.float32)
    graph = helper.make_graph(
        [helper.make_node("Reshape", ["input", "shape"], ["flat"]),
         helper.make_node("MatMul", ["flat", "W"], ["raw"]),
         helper.make_node("Add", ["raw", "b"], ["logits"])],
        "constant_logits",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, ["N", 3, 224, 224])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["N", outputs])],
        initializer=[helper.make_tensor("W", TensorProto.FLOAT, weight.shape, weight.tobytes(), raw=True),
                     helper.make_tensor("b", TensorProto.FLOAT, bias.shape, bias.tobytes(), raw=True),
                     helper.make_tensor("shape", TensorProto.INT64, [2],
                                        np.array([-1, 3 * 224 * 224], dtype=np.int64).tobytes(), raw=True)])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    onnx.checker.check_model(model)
    onnx.save(model, str(path))


def _package(root: Path, model_id: str = "synthetic", *, onnx_kwargs=None, manifest_edit=None, metadata_edit=None,
             package: str = "p5_synthetic_seed0_20260101") -> Path:
    """A package with the REAL layout and file formats of the P5 packages (runtime_manifest.json,
    class_metadata.json with training_labels + runtime_aliases), plus its index.json entry."""
    pkg = root / package
    pkg.mkdir(parents=True, exist_ok=True)
    _logits_onnx(pkg / "model.onnx", **(onnx_kwargs or {}))
    manifest = {
        "architecture": "synthetic", "class_to_idx": {c: i for i, c in enumerate(CLASSES)}, "classes": list(CLASSES),
        "contract_smoke_set": {"n": 200, "rule": "per_class_mode_equals_label", "sample_ids_sha256": "0" * 64,
                               "selection": "synthetic", "split": "val"},
        "input": {"color": "RGB", "dtype": "float32", "layout": "NCHW", "shape": [1, 3, 224, 224]},
        "kind": "vision_classifier", "manifest_version": 1,
        "model": {"format": "onnx", "path": "model.onnx",
                  "sha256": hashlib.sha256((pkg / "model.onnx").read_bytes()).hexdigest()},
        "output": {"kind": "logits", "shape": [1, 10]},
        "preprocess": "rgb_resize_224_bilinear_no_crop_div255_imagenet",
        "provenance": {"seed": 0, "source_run_id": "synthetic"},
        "run_id": package, "safe_class": "c0",
    }
    if manifest_edit:
        manifest_edit(manifest)
    (pkg / "runtime_manifest.json").write_text(json.dumps(manifest))
    training = ["normal_driving", *STABLE_LABELS[1:]]
    metadata = {"class_to_idx": {c: i for i, c in enumerate(CLASSES)}, "classes": list(CLASSES),
                "meaning": "Runtime alias does not rename the original training label normal_driving.",
                "runtime_aliases": {"c0": "safe_driving"}, "safe_class": "c0",
                "training_labels": dict(zip(CLASSES, training))}
    if metadata_edit:
        metadata_edit(metadata)
    (pkg / "class_metadata.json").write_text(json.dumps(metadata))
    index_path = root / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    index[model_id] = {"package": package, "role": "TEST", "architecture": "synthetic", "source_zip_sha256": "0" * 64}
    index_path.write_text(json.dumps(index))
    return pkg


def _load(model_id, root):
    from app.vision_candidates import load_candidate
    return load_candidate(model_id, root)


def test_unknown_model_id_is_refused(tmp_path):
    _package(tmp_path)
    with pytest.raises(ModelUnavailable, match="'nope' is not in"):
        _load("nope", tmp_path)


def test_a_missing_index_is_refused(tmp_path):
    with pytest.raises(ModelUnavailable, match="index.json"):
        _load("synthetic", tmp_path)


def test_a_package_path_outside_the_root_is_refused(tmp_path):
    _package(tmp_path)
    (tmp_path / "index.json").write_text(json.dumps({"synthetic": {"package": "../elsewhere", "role": "TEST",
                                                                   "architecture": "x", "source_zip_sha256": "0" * 64}}))
    with pytest.raises(ModelUnavailable, match="package"):
        _load("synthetic", tmp_path)


def test_a_tampered_hash_is_refused(tmp_path):
    _package(tmp_path, manifest_edit=lambda m: m["model"].update(sha256="f" * 64))
    with pytest.raises(ModelUnavailable, match="sha256 mismatch"):
        _load("synthetic", tmp_path)


def test_a_schema_violation_is_refused(tmp_path):
    _package(tmp_path, manifest_edit=lambda m: m.pop("output"))
    with pytest.raises(ModelUnavailable, match="output"):
        _load("synthetic", tmp_path)


def test_a_class_order_other_than_c0_to_c9_is_refused(tmp_path):
    def reverse(m):
        m["classes"] = CLASSES[::-1]
        m["class_to_idx"] = {c: i for i, c in enumerate(CLASSES[::-1])}
    _package(tmp_path, manifest_edit=reverse)
    with pytest.raises(ModelUnavailable, match="c0"):
        _load("synthetic", tmp_path)


def test_class_metadata_must_agree_with_the_manifest(tmp_path):
    _package(tmp_path, metadata_edit=lambda d: d.update(classes=CLASSES[::-1]))
    with pytest.raises(ModelUnavailable, match="class_metadata"):
        _load("synthetic", tmp_path)


def test_c0_must_carry_the_runtime_alias_safe_driving(tmp_path):
    _package(tmp_path, metadata_edit=lambda d: d.update(runtime_aliases={}))
    with pytest.raises(ModelUnavailable, match="safe_driving"):
        _load("synthetic", tmp_path)


def test_a_model_whose_output_is_not_ten_logits_fails_its_warm_up(tmp_path):
    _package(tmp_path, onnx_kwargs={"outputs": 9})
    with pytest.raises(ModelUnavailable, match="warm-up"):
        _load("synthetic", tmp_path)


def test_a_valid_package_loads_forwards_and_describes_itself(tmp_path):
    pkg = _package(tmp_path)
    candidate = _load("synthetic", tmp_path)
    assert (candidate.model_id, candidate.run_id) == ("synthetic", "p5_synthetic_seed0_20260101")
    assert candidate.package_dir == pkg.resolve()
    assert candidate.labels == STABLE_LABELS  # runtime alias over training label, c0..c9 order
    logits = np.asarray(candidate.session.run(None, {candidate.input_name: np.zeros((1, 3, 224, 224), np.float32)})[0])
    assert logits.shape == (1, 10) and np.isfinite(logits).all()
    probs = np.exp(logits - logits.max()) / np.exp(logits - logits.max()).sum()
    assert abs((1 - float(probs[0, 0])) - 0.9) < 1e-6  # uniform -> P_distraction = 1 - P(c0) = 0.9
    sha = hashlib.sha256((pkg / "model.onnx").read_bytes()).hexdigest()
    assert candidate.info == {
        "architecture": "synthetic", "model_id": "synthetic", "run_id": "p5_synthetic_seed0_20260101",
        "source": "candidate:p5_synthetic_seed0_20260101", "sha256": sha, "runtime": "onnxruntime_cpu",
        "classes": STABLE_LABELS, "input": "RGB NCHW float32 224x224",
        "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]}


@pytest.mark.candidates
@pytest.mark.parametrize("model_id", sorted(REAL))
def test_the_real_p5_packages_load_and_forward(model_id):
    """Run with ``-m candidates``: the copied P5 packages (Task 1.1) must be present - a run that asks
    for these tests and lacks them fails, it does not skip."""
    assert (REAL_ROOT / "index.json").exists(), f"missing {REAL_ROOT}/index.json: copy the P5 packages (Task 1.1)"
    package, sha = REAL[model_id]
    candidate = _load(model_id, REAL_ROOT)
    assert (candidate.run_id, candidate.info["sha256"]) == (package, sha)
    assert candidate.labels == STABLE_LABELS
    logits = np.asarray(candidate.session.run(None, {candidate.input_name: np.zeros((1, 3, 224, 224), np.float32)})[0])
    assert logits.shape == (1, 10) and np.isfinite(logits).all()


# ====================================================================== the provider (Task 1.3)
import base64  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml/outputs"
# All three stable files (test_model_gate.py checks every ``requires_models`` for it).
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)
STABLE_NAME = "MobileNetV3ONNX+XGBoost"
BACKEND = Path(__file__).resolve().parents[1]


def _metadata_only_root(tmp_path: Path, *, with_xgb: bool) -> Path:
    """A model root with the two (tracked) metrics.json files and, optionally, the real XGBoost model -
    but NO stable vision ONNX: a provider that reaches for the stable model here fails loudly."""
    root = tmp_path / "model_root"
    for branch in ("vision", "telemetry"):
        (root / branch).mkdir(parents=True)
        shutil.copy(MODEL_ROOT / branch / "metrics.json", root / branch / "metrics.json")
    if with_xgb:
        (root / "telemetry" / "xgb_telemetry.json").symlink_to((MODEL_ROOT / "telemetry/xgb_telemetry.json").resolve())
    return root


def _jpeg() -> str:
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (80, 130, 180)).save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def _live_input(**over):
    from app.schemas import LiveInput
    data = {"request_id": "r1", "image_base64": _jpeg(), "captured_at": "2026-10-26T00:00:00+00:00",
            "telemetry_features": {"speed_kmph": 52, "accel_x": .7, "accel_y": .2, "brake_pressure": 20,
                                   "steering_angle": 7.5, "throttle": 40, "lane_deviation": .21, "headway_distance": 18},
            "telemetry_timestamp": "2026-10-26T00:00:00+00:00", "telemetry_source": "prepared_replay"}
    return LiveInput(**{**data, **over})


@requires_models
def test_the_stable_default_is_unchanged_and_says_so():
    from app.config import settings
    from app.providers.trained import TrainedProvider
    assert settings.active_vision == "stable"
    provider = TrainedProvider()
    assert provider.name == STABLE_NAME
    vision = provider.info["vision"]
    assert (vision["model_id"], vision["run_id"], vision["source"], vision["architecture"]) == \
        ("stable_mobilenet_v3_large", None, "stable", "mobilenet_v3_large")
    assert vision["sha256"] == hashlib.sha256((MODEL_ROOT / "vision/mobilenetv3_large_vision.onnx").read_bytes()).hexdigest()
    assert vision["classes"] == STABLE_LABELS
    _, provenance = provider.infer(_live_input())
    assert (provenance["vision_model_id"], provenance["vision_model_sha256"]) == ("stable_mobilenet_v3_large", vision["sha256"])


@requires_models
def test_a_candidate_replaces_only_the_vision_model_and_never_touches_the_stable_one(tmp_path, monkeypatch):
    from app.config import settings
    from app.providers.trained import TrainedProvider
    bias = [0.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # c3 (texting_left) dominant, whatever the image
    pkg = _package(tmp_path / "candidates", onnx_kwargs={"bias": bias})
    monkeypatch.setattr(settings, "model_root", _metadata_only_root(tmp_path, with_xgb=True))
    monkeypatch.setattr(settings, "vision_candidates_root", tmp_path / "candidates")
    monkeypatch.setattr(settings, "active_vision", "synthetic")
    provider = TrainedProvider()
    sha = hashlib.sha256((pkg / "model.onnx").read_bytes()).hexdigest()
    assert provider.info["vision"]["model_id"] == "synthetic"
    assert provider.info["vision"]["source"] == "candidate:p5_synthetic_seed0_20260101"
    assert provider.info["vision"]["sha256"] == sha
    assert "MobileNet" not in provider.name and provider.info["provider"] == provider.name
    # The telemetry side is the stable XGBoost, untouched.
    assert provider.info["telemetry"]["sha256"] == hashlib.sha256((MODEL_ROOT / "telemetry/xgb_telemetry.json").read_bytes()).hexdigest()
    window, provenance = provider.infer(_live_input())
    expected = np.exp(np.array(bias)) / np.exp(np.array(bias)).sum()
    assert window.P_distraction == pytest.approx(1 - expected[0], abs=1e-6)
    assert [c.label for c in window.visual_top_classes] == STABLE_LABELS
    assert max(window.visual_top_classes, key=lambda c: c.probability).label == "texting_left"
    assert (provenance["vision_model_id"], provenance["vision_model_sha256"]) == ("synthetic", sha)
    assert provenance["provider"] == provider.name


def test_a_refused_candidate_raises_and_never_falls_back(tmp_path, monkeypatch):
    """No model files at all are needed: the stable ONNX is absent from this model root, so a fallback
    would fail differently; the candidate's own reason must surface."""
    from app.config import settings
    from app.providers.trained import TrainedProvider
    _package(tmp_path / "candidates", manifest_edit=lambda m: m["model"].update(sha256="f" * 64))
    monkeypatch.setattr(settings, "model_root", _metadata_only_root(tmp_path, with_xgb=False))
    monkeypatch.setattr(settings, "vision_candidates_root", tmp_path / "candidates")
    monkeypatch.setattr(settings, "active_vision", "synthetic")
    with pytest.raises(ModelUnavailable, match="sha256 mismatch"):
        TrainedProvider()


@pytest.mark.candidates
@requires_models
def test_switching_to_a_candidate_and_back_in_fresh_processes():
    """Task 1.3 Step 4 / Stage 5 rollback: the switch is read at process start (DRA_ACTIVE_VISION);
    unsetting it brings back the stable model with its own hash. Each load in its own process."""
    script = ("import json; from app.providers.trained import TrainedProvider; "
              "p = TrainedProvider(); print(json.dumps({'name': p.name, **p.info['vision']}))")

    def load(active):
        env = {k: v for k, v in os.environ.items() if not k.startswith("DRA_ACTIVE_VISION")}
        if active is not None:
            env["DRA_ACTIVE_VISION"] = active
        env.update(PYTHONPATH=".", PYTHONDONTWRITEBYTECODE="1")
        done = subprocess.run([sys.executable, "-c", script], cwd=BACKEND, env=env, capture_output=True, text=True,
                              timeout=180)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout.strip().splitlines()[-1])

    candidate = load("resnet18_search004_seed42")
    assert (candidate["model_id"], candidate["sha256"]) == ("resnet18_search004_seed42", REAL["resnet18_search004_seed42"][1])
    stable = load(None)
    assert (stable["model_id"], stable["source"], stable["name"]) == ("stable_mobilenet_v3_large", "stable", STABLE_NAME)
    assert stable["sha256"] == hashlib.sha256((MODEL_ROOT / "vision/mobilenetv3_large_vision.onnx").read_bytes()).hexdigest()
