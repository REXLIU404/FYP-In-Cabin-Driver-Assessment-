"""Task 3 (constructed scenario): the scenario definitions and the bundle builder.

The builder is a standalone standard-library script; these tests drive its functions
directly through importlib (scripts/ is not a package) and pin its behaviour on a tiny
synthetic dataset laid out like the real data root. Nothing here reads or writes the
real State Farm data, the ML workspace or any database.
"""
import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
BUILDER = REPO / "scripts" / "build_dataset_replay.py"

METADATA_HEADER = ["image_path", "filename", "class_id", "class_name", "driver_id",
                   "driver_csv_classname", "width", "height", "aspect_ratio", "split"]
TELEMETRY_HEADER = ["speed_kmph", "accel_x", "accel_y", "brake_pressure", "steering_angle",
                    "throttle", "lane_deviation", "headway_distance", "behavior_label"]


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_dataset_replay", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return _load_builder()


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _jpg(path: Path, color=(80, 130, 180)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color).save(path, format="JPEG")
    return path


def _meta_row(path: Path, class_id: str, driver_id: str, split: str) -> list:
    return [str(path), path.name, class_id, class_id, driver_id, class_id,
            "16", "16", "1.0", split]


def _tele_row(label: str, speed: float) -> list:
    return [speed, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, label]


class Dataset:
    """A tiny data root in the same layout the builder expects (eda_outputs/processed/...)."""

    def __init__(self, root: Path):
        self.root = root
        self.vision_dir = root / "eda_outputs" / "processed" / "vision"
        self.tele_dir = root / "eda_outputs" / "processed" / "telemetry"
        self.meta_rows: list[list] = []
        self.tele_rows: list[list] = []

    def add_vision(self, driver: str, class_id: str, split: str, names: list[str],
                   colors=None) -> list[Path]:
        paths = []
        for i, name in enumerate(names):
            color = colors[i] if colors else (80 + i, 130, 180)
            path = _jpg(self.root / "imgs" / split / driver / class_id / name, color)
            self.meta_rows.append(_meta_row(path, class_id, driver, split))
            paths.append(path)
        return paths

    def add_telemetry(self, label: str, count: int = 5, base_speed: float = 40.0) -> None:
        for i in range(count):
            self.tele_rows.append(_tele_row(label, base_speed + i))

    def write(self) -> None:
        _write_csv(self.vision_dir / "vision_metadata_with_split.csv", METADATA_HEADER, self.meta_rows)
        _write_csv(self.tele_dir / "telemetry_test.csv", TELEMETRY_HEADER, self.tele_rows)


@pytest.fixture
def dataset(tmp_path):
    yield Dataset(tmp_path / "data")


@pytest.fixture
def tiny_scenario(tmp_path):
    """Writes a scenario file and returns (scenario dict, scenario file path)."""
    def make(**over) -> tuple[dict, Path]:
        scenario = {
            "scenario_id": "tiny",
            "seed": 7,
            "frame_period_ms": 200,
            "telemetry_period_ms": 2000,
            "segments": [
                {"title": "Baseline", "duration_s": 2, "driver_id": "p050",
                 "vision_class": "c0", "telemetry_label": "Safe"},
            ],
        }
        scenario.update(over)
        path = tmp_path / "scenario.json"
        path.write_text(json.dumps(scenario), encoding="utf-8")
        return scenario, path
    return make


def build(builder, dataset: Dataset, scenario: dict, scenario_file: Path, out: Path) -> dict:
    dataset.write()
    manifest_path = builder.build_bundle(
        scenario, scenario_file=scenario_file, out_root=out, data_root=dataset.root)
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read())
    return digest.hexdigest()


# ----------------------------------------------------------------------------------- tests

def test_the_same_seed_builds_the_same_bundle(builder, dataset, tiny_scenario, tmp_path):
    dataset.add_vision("p050", "c0", "test", ["img_1.jpg", "img_2.jpg", "img_3.jpg"])
    dataset.add_telemetry("Safe")
    scenario, scenario_file = tiny_scenario()

    first = build(builder, dataset, scenario, scenario_file, tmp_path / "out1")
    second = build(builder, dataset, scenario, scenario_file, tmp_path / "out2")

    first_stable = {k: v for k, v in first.items() if k != "generated_at"}
    second_stable = {k: v for k, v in second.items() if k != "generated_at"}
    assert first_stable == second_stable
    for frame in first["frames"]:
        a = tmp_path / "out1" / "tiny" / "frames" / frame["file"]
        b = tmp_path / "out2" / "tiny" / "frames" / frame["file"]
        assert sha256_of(a) == sha256_of(b)


def test_frames_are_chosen_by_label_and_filename_order(builder, dataset, tiny_scenario, tmp_path):
    dataset.add_vision("p050", "c0", "test", ["img_3.jpg", "img_1.jpg", "img_2.jpg"])
    dataset.add_vision("p050", "c1", "test", ["img_9.jpg", "img_8.jpg"])  # must be ignored
    dataset.add_telemetry("Safe")
    scenario, scenario_file = tiny_scenario(segments=[
        {"title": "Baseline", "duration_s": 2, "driver_id": "p050",
         "vision_class": "c0", "telemetry_label": "Safe"},
    ])

    manifest = build(builder, dataset, scenario, scenario_file, tmp_path / "out")

    sources = [frame["source_file"] for frame in manifest["frames"]]
    assert sources == ["img_1.jpg", "img_2.jpg", "img_3.jpg"] * 3 + ["img_1.jpg"]
    assert {frame["class_id"] for frame in manifest["frames"]} == {"c0"}
    assert {frame["driver_id"] for frame in manifest["frames"]} == {"p050"}


def test_frames_cycle_when_a_driver_has_too_few_and_it_is_recorded(builder, dataset, tiny_scenario, tmp_path):
    dataset.add_vision("p050", "c0", "test", ["img_1.jpg", "img_2.jpg", "img_3.jpg"])
    dataset.add_telemetry("Safe")
    scenario, scenario_file = tiny_scenario()

    manifest = build(builder, dataset, scenario, scenario_file, tmp_path / "out")

    assert len(manifest["frames"]) == 10  # 2 s at 200 ms
    assert manifest["segments"][0]["frame_cycles"] == 7  # 10 needed, 3 available
    assert [f["source_file"] for f in manifest["frames"]] == \
        ["img_1.jpg", "img_2.jpg", "img_3.jpg"] * 3 + ["img_1.jpg"]


def test_it_refuses_a_split_other_than_test(builder, dataset, tiny_scenario, tmp_path):
    dataset.add_vision("p099", "c0", "train", ["img_1.jpg", "img_2.jpg"])
    dataset.add_telemetry("Safe")
    scenario, scenario_file = tiny_scenario(segments=[
        {"title": "Baseline", "duration_s": 2, "driver_id": "p099",
         "vision_class": "c0", "telemetry_label": "Safe"},
    ])

    with pytest.raises(builder.BuilderError) as error:
        build(builder, dataset, scenario, scenario_file, tmp_path / "out")
    assert "train/val" in str(error.value) and "p099" in str(error.value)


def test_it_refuses_a_driver_seen_in_training(builder, dataset, tiny_scenario, tmp_path):
    dataset.add_vision("p050", "c0", "test", ["img_1.jpg", "img_2.jpg", "img_3.jpg"])
    dataset.add_vision("p050", "c0", "train", ["img_4.jpg", "img_5.jpg"])
    dataset.add_telemetry("Safe")
    scenario, scenario_file = tiny_scenario()

    with pytest.raises(builder.BuilderError) as error:
        build(builder, dataset, scenario, scenario_file, tmp_path / "out")
    assert "train/val" in str(error.value) and "p050" in str(error.value)


@pytest.mark.parametrize("duration_s", [15, 3])
def test_durations_must_be_multiples_of_both_periods(builder, dataset, tiny_scenario, tmp_path, duration_s):
    dataset.add_vision("p050", "c0", "test", ["img_1.jpg", "img_2.jpg", "img_3.jpg"])
    dataset.add_telemetry("Safe")
    scenario, scenario_file = tiny_scenario(segments=[
        {"title": "Baseline", "duration_s": duration_s, "driver_id": "p050",
         "vision_class": "c0", "telemetry_label": "Safe"},
    ])

    with pytest.raises(builder.BuilderError) as error:
        build(builder, dataset, scenario, scenario_file, tmp_path / "out")
    assert "multiple of" in str(error.value)


def test_manifest_hashes_match_the_copied_files(builder, dataset, tiny_scenario, tmp_path):
    sources = dataset.add_vision("p050", "c0", "test", ["img_1.jpg", "img_2.jpg", "img_3.jpg"])
    dataset.add_telemetry("Safe", count=5, base_speed=41.0)
    scenario, scenario_file = tiny_scenario()

    manifest = build(builder, dataset, scenario, scenario_file, tmp_path / "out")
    bundle = tmp_path / "out" / "tiny"

    for frame in manifest["frames"]:
        copied = bundle / "frames" / frame["file"]
        assert frame["sha256"] == sha256_of(copied)
    # the copied bytes are the source bytes: every source sha appears in the manifest
    assert {sha256_of(p) for p in sources} <= {f["sha256"] for f in manifest["frames"]}

    assert manifest["sources"]["split"] == "test"
    assert manifest["sources"]["vision_metadata_sha256"] == sha256_of(
        dataset.vision_dir / "vision_metadata_with_split.csv")
    assert manifest["sources"]["telemetry_csv_sha256"] == sha256_of(
        dataset.tele_dir / "telemetry_test.csv")

    assert len(manifest["telemetry"]) == 1
    [row] = manifest["telemetry"]
    assert row["label"] == "Safe"
    # the drawn row must be one of the CSV data rows, and the features its exact values
    csv_rows = list(csv.DictReader((dataset.tele_dir / "telemetry_test.csv").open(newline="", encoding="utf-8")))
    source_row = csv_rows[row["row"]]
    assert row["features"] == {name: float(source_row[name]) for name in TELEMETRY_HEADER[:-1]}
    assert manifest["segments"][0]["telemetry_count"] == 1


def test_the_builder_imports_no_model_code(tmp_path):
    probe = (
        "import json, sys; sys.path.insert(0, sys.argv[1]); "
        "import build_dataset_replay; "
        "print(json.dumps([m for m in ('onnxruntime', 'xgboost', 'torch') if m in sys.modules]))"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe, str(BUILDER.parent)],
        cwd=tmp_path, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


def test_the_class_name_mapping(builder):
    assert builder.CLASS_LABELS == {
        "c0": "safe_driving",
        "c1": "texting_right",
        "c2": "talking_phone_right",
        "c3": "texting_left",
        "c4": "talking_phone_left",
        "c5": "operating_radio",
        "c6": "drinking",
        "c7": "reaching_behind",
        "c8": "hair_makeup",
        "c9": "talking_to_passenger",
    }


def test_viva_v1_is_the_table_of_the_spec():
    viva = json.loads((REPO / "demo" / "scenarios" / "viva_v1.json").read_text(encoding="utf-8"))
    assert viva["scenario_id"] == "viva_v1"
    assert viva["seed"] == 20261022
    assert viva["frame_period_ms"] == 200
    assert viva["telemetry_period_ms"] == 2000
    assert [(s["duration_s"], s["driver_id"], s["vision_class"], s["telemetry_label"])
            for s in viva["segments"]] == [
        (20, "p050", "c0", "Safe"),
        (16, "p026", "c1", "Safe"),
        (16, "p035", "c4", "Distracted"),
        (26, "p026", "c0", "Safe"),
        (16, "p012", "c0", "Aggressive"),
        (16, "p035", "c7", "Distracted"),
        (26, "p050", "c0", "Safe"),
    ]
    assert [s["title"] for s in viva["segments"]] == [
        "Baseline", "Vision only", "Both", "Recovery", "Telemetry only", "Both", "Recovery",
    ]
    assert sum(s["duration_s"] for s in viva["segments"]) == 136


def test_viva_compact_is_the_single_driver_sixty_second_table():
    """The short demo script: one test-split driver, 60 s, every risk situation once.

    ``viva_v1`` stays the 136 s spec table; this one is the viva shorthand. Pinning the
    segments here is what stops a later edit from silently changing what the demo shows.
    """
    compact = json.loads((REPO / "demo" / "scenarios" / "viva_compact.json").read_text(encoding="utf-8"))
    assert compact["scenario_id"] == "viva_compact"
    assert compact["frame_period_ms"] == 200
    assert compact["telemetry_period_ms"] == 2000
    assert [(s["duration_s"], s["driver_id"], s["vision_class"], s["telemetry_label"])
            for s in compact["segments"]] == [
        (10, "p050", "c0", "Safe"),
        (4, "p050", "c0", "Aggressive"),
        (4, "p050", "c0", "Safe"),
        (4, "p050", "c0", "Aggressive"),
        (10, "p050", "c1", "Safe"),
        (10, "p050", "c4", "Distracted"),
        (18, "p050", "c0", "Safe"),
    ]
    assert [s["title"] for s in compact["segments"]] == [
        "Baseline", "Telemetry only", "Telemetry wavers", "Telemetry only",
        "Vision only", "Both", "Recovery",
    ]
    assert sum(s["duration_s"] for s in compact["segments"]) == 60
    # ONE driver for the whole run: the viva story is a single trip of one test subject.
    assert {s["driver_id"] for s in compact["segments"]} == {"p050"}
    # The telemetry-only stretch alternates labels, so that branch is not one single step
    # from Safe to not-Safe: the EMA has to show the intermediate readings.
    labels = [s["telemetry_label"] for s in compact["segments"]]
    assert labels.count("Safe") == 4
    assert labels.count("Aggressive") == 2 and labels.count("Distracted") == 1
    # Recovery is long enough for the 10 s NORMAL latch, with room left to show it settled.
    assert compact["segments"][-1]["duration_s"] >= 10 + 2
    # Every duration must stay a whole number of both periods (the builder refuses otherwise).
    for segment in compact["segments"]:
        assert segment["duration_s"] * 1000 % compact["frame_period_ms"] == 0
        assert segment["duration_s"] * 1000 % compact["telemetry_period_ms"] == 0


def test_bundles_are_git_ignored():
    done = subprocess.run(
        ["git", "check-ignore", "-q", "demo/bundles/x/manifest.json"],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    assert done.returncode == 0
