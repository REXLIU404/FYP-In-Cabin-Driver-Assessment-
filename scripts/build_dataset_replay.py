#!/usr/bin/env python3
"""Build a constructed-scenario bundle: dataset images and telemetry rows pinned by a scenario.

Usage:

    python3 scripts/build_dataset_replay.py <scenario_id> [--out demo/bundles] [--data-root PATH]

The scenario is ``demo/scenarios/<scenario_id>.json``. The data root defaults to the
same location ``scripts/freeze_manifest.py`` resolves (``FYP_DATA_ROOT``, then the repo
root, then the sibling ``FYP-In-Cabin-Driver-Assessment-`` directory).

Rules (design doc section 4.2, pinned by ``backend/tests/test_build_dataset_replay.py``):

- only the **test split** is used, and every driver in the scenario must never appear
  in train / val;
- frames are picked **by label only** (driver + class), sorted by file name, and cycled
  in the same order when a driver has fewer images than the segment needs;
- telemetry rows are picked by label with ``random.Random(seed * 1000 + segment_index)``
  sampling without replacement, in the drawn order;
- the same seed always produces the same bundle (byte-identical except ``generated_at``);
- this script is standard library only: it never imports model code or touches the ML
  workspace. Output goes to ``demo/bundles/``, which is git-ignored (images never enter git).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Same-directory import (scripts/ is not a package): resolve_data_root must follow the
# exact same rules as the manifest freezer so the two tools always agree on the data root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from freeze_manifest import DataRootError, resolve_data_root  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SCHEMA = "constructed-scenario/1"

# The spec's class naming (section 3 / design doc): the metadata CSV uses the raw State
# Farm names (``normal_driving`` for c0), the pipeline uses these labels.
CLASS_LABELS = {
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
TELEMETRY_LABELS = ("Safe", "Aggressive", "Distracted")
TELEMETRY_FEATURES = ("speed_kmph", "accel_x", "accel_y", "brake_pressure",
                      "steering_angle", "throttle", "lane_deviation", "headway_distance")


class BuilderError(Exception):
    """The scenario or the data cannot be used; the message is the refusal reason."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_vision_metadata(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle))


def read_telemetry_rows(path: Path) -> list[dict]:
    """Data rows (header excluded), in file order; the row's 0-based index is its identity."""
    with path.open("r", newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle))


def _validate_scenario(scenario: dict) -> tuple[int, int, int, list[dict]]:
    try:
        scenario_id = scenario["scenario_id"]
        seed = scenario["seed"]
        frame_period_ms = scenario["frame_period_ms"]
        telemetry_period_ms = scenario["telemetry_period_ms"]
        segments = scenario["segments"]
    except (KeyError, TypeError) as exc:
        raise BuilderError(f"scenario is missing the {exc.args[0]!r} field") from None
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise BuilderError("scenario_id must be a non-empty string")
    if not isinstance(seed, int) or not isinstance(frame_period_ms, int) or not isinstance(telemetry_period_ms, int):
        raise BuilderError("seed, frame_period_ms and telemetry_period_ms must be integers")
    if frame_period_ms <= 0 or telemetry_period_ms <= 0:
        raise BuilderError("frame_period_ms and telemetry_period_ms must be positive")
    if not isinstance(segments, list) or not segments:
        raise BuilderError("scenario needs at least one segment")
    parsed = []
    for index, segment in enumerate(segments):
        try:
            duration_s = segment["duration_s"]
            vision_class = segment["vision_class"]
            telemetry_label = segment["telemetry_label"]
            driver_id = segment["driver_id"]
            title = segment["title"]
        except (KeyError, TypeError) as exc:
            raise BuilderError(f"segment {index} is missing the {exc.args[0]!r} field") from None
        duration_ms = duration_s * 1000
        if duration_ms % frame_period_ms or duration_ms % telemetry_period_ms:
            raise BuilderError(
                f"segment {index} ({duration_s}s) must be a multiple of both "
                f"{frame_period_ms} ms and {telemetry_period_ms} ms"
            )
        if vision_class not in CLASS_LABELS:
            raise BuilderError(f"segment {index}: unknown vision_class {vision_class!r}")
        if telemetry_label not in TELEMETRY_LABELS:
            raise BuilderError(f"segment {index}: unknown telemetry_label {telemetry_label!r}")
        if not isinstance(driver_id, str) or not driver_id.strip():
            raise BuilderError(f"segment {index}: driver_id must be a non-empty string")
        if not isinstance(title, str) or not title.strip():
            raise BuilderError(f"segment {index}: title must be a non-empty string")
        parsed.append({"index": index, "title": title, "duration_ms": int(duration_ms),
                       "driver_id": driver_id, "vision_class": vision_class,
                       "telemetry_label": telemetry_label})
    duration_ms = sum(segment["duration_ms"] for segment in parsed)
    return int(seed), int(frame_period_ms), int(telemetry_period_ms), parsed, int(duration_ms)


def build_bundle(scenario: dict, *, scenario_file: Path, out_root: Path, data_root: Path) -> Path:
    """Build ``<out_root>/<scenario_id>`` and return the manifest path.

    Raises ``BuilderError`` when the scenario or the data breaks the rules above. The
    bundle directory is rebuilt from scratch, so repeated runs never leave stale frames.
    """
    seed, frame_period_ms, telemetry_period_ms, segments, duration_ms = _validate_scenario(scenario)
    scenario_id = scenario["scenario_id"]

    vision_csv = data_root / "eda_outputs" / "processed" / "vision" / "vision_metadata_with_split.csv"
    telemetry_csv = data_root / "eda_outputs" / "processed" / "telemetry" / "telemetry_test.csv"
    if not vision_csv.exists():
        raise BuilderError(f"vision metadata not found at {vision_csv}; "
                           "pass --data-root (the directory that contains eda_outputs/)")
    if not telemetry_csv.exists():
        raise BuilderError(f"telemetry test CSV not found at {telemetry_csv}")

    metadata = read_vision_metadata(vision_csv)
    telemetry = read_telemetry_rows(telemetry_csv)

    # Refusal 1: a driver who appears anywhere in train / val is not a test-only driver.
    used_drivers = sorted({segment["driver_id"] for segment in segments})
    for row in metadata:
        if row["driver_id"] in used_drivers and row["split"] != "test":
            raise BuilderError(
                f"driver {row['driver_id']} appears in the {row['split']} split of the train/val "
                "splits; constructed scenarios use test-only drivers"
            )

    frames, frame_entries = [], []
    telemetry_entries = []
    segment_entries = []
    first_frame = first_telemetry = 0
    for segment in segments:
        driver, vision_class = segment["driver_id"], segment["vision_class"]
        available = [row for row in metadata
                     if row["split"] == "test" and row["driver_id"] == driver
                     and row["class_id"] == vision_class]
        needed = segment["duration_ms"] // frame_period_ms
        if not available:
            raise BuilderError(
                f"no test images for driver {driver} class {vision_class}; only the test split is used"
            )
        available.sort(key=lambda row: row["filename"])
        frame_cycles = max(0, needed - len(available))
        for n in range(needed):
            row = available[n % len(available)]
            source = Path(row["image_path"])
            if not source.exists():
                raise BuilderError(f"image {source} from the metadata does not exist")
            file_name = f"{len(frames):04d}_{row['filename']}"
            frames.append((source, file_name))
            frame_entries.append({
                "n": len(frames) - 1,
                "file": file_name,
                "source_file": row["filename"],
                "driver_id": row["driver_id"],
                "class_id": row["class_id"],
                "vision_label": CLASS_LABELS[row["class_id"]],
                "segment_index": segment["index"],
                "sha256": sha256_of(source),
            })

        # Refusal 2 / selection: telemetry rows of the label, drawn with the per-segment seed.
        label_rows = [(n, row) for n, row in enumerate(telemetry)
                      if row["behavior_label"] == segment["telemetry_label"]]
        telemetry_needed = segment["duration_ms"] // telemetry_period_ms
        if len(label_rows) < telemetry_needed:
            raise BuilderError(
                f"only {len(label_rows)} {segment['telemetry_label']} rows in telemetry_test.csv; "
                f"segment {segment['index']} needs {telemetry_needed}"
            )
        rng = random.Random(seed * 1000 + segment["index"])
        for _, (n, row) in enumerate(rng.sample(label_rows, telemetry_needed)):
            telemetry_entries.append({
                "n": len(telemetry_entries),
                "row": n,
                "label": row["behavior_label"],
                "segment_index": segment["index"],
                "features": {name: float(row[name]) for name in TELEMETRY_FEATURES},
            })

        segment_entries.append({
            "index": segment["index"],
            "title": segment["title"],
            "start_ms": first_frame * frame_period_ms,
            "duration_ms": segment["duration_ms"],
            "driver_id": driver,
            "vision_class": vision_class,
            "vision_label": CLASS_LABELS[vision_class],
            "telemetry_label": segment["telemetry_label"],
            "first_frame": first_frame,
            "frame_count": needed,
            "frame_cycles": frame_cycles,
            "first_telemetry": first_telemetry,
            "telemetry_count": telemetry_needed,
        })
        first_frame += needed
        first_telemetry += telemetry_needed

    bundle_dir = out_root / scenario_id
    frames_dir = bundle_dir / "frames"
    shutil.rmtree(bundle_dir, ignore_errors=True)  # only the generated bundle, never sources
    frames_dir.mkdir(parents=True, exist_ok=True)
    for source, file_name in frames:
        shutil.copyfile(source, frames_dir / file_name)

    manifest = {
        "schema": SCHEMA,
        "scenario_id": scenario_id,
        "scenario_sha256": sha256_of(scenario_file),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frame_period_ms": frame_period_ms,
        "telemetry_period_ms": telemetry_period_ms,
        "duration_ms": duration_ms,
        "sources": {
            "split": "test",
            "vision_metadata_sha256": sha256_of(vision_csv),
            "telemetry_csv_sha256": sha256_of(telemetry_csv),
        },
        "segments": segment_entries,
        "frames": frame_entries,
        "telemetry": telemetry_entries,
    }
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a constructed-scenario bundle.")
    parser.add_argument("scenario_id", help="name of a file demo/scenarios/<scenario_id>.json")
    parser.add_argument("--out", type=Path, default=REPO / "demo" / "bundles",
                        help="output root (default: demo/bundles)")
    parser.add_argument("--data-root", type=Path, default=None,
                        help="directory that contains eda_outputs/ (default: resolve_data_root())")
    args = parser.parse_args(argv)

    scenario_file = REPO / "demo" / "scenarios" / f"{args.scenario_id}.json"
    if not scenario_file.exists():
        print(f"error: no scenario file at {scenario_file}", file=sys.stderr)
        return 2
    try:
        scenario = json.loads(scenario_file.read_text(encoding="utf-8"))
        if args.data_root is not None:
            data_root = args.data_root.expanduser().resolve()
        else:
            data_root, _tried = resolve_data_root()
            if data_root is None:
                print("error: data root not found (set FYP_DATA_ROOT or pass --data-root)",
                      file=sys.stderr)
                return 2
        manifest_path = build_bundle(scenario, scenario_file=scenario_file,
                                     out_root=args.out, data_root=data_root)
    except (BuilderError, DataRootError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"built {manifest_path} ({len(json.loads(manifest_path.read_text(encoding='utf-8'))['frames'])} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
