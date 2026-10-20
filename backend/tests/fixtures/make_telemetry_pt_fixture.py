#!/usr/bin/env python3
"""Generate ``telemetry_pt_by_row.json``: the frozen per-row telemetry probabilities of the
prepared replay, as the trained XGBoost (``ml/outputs/telemetry/xgb_telemetry.json``) produces them.

Why it exists. ``test_live_single_branch.py`` (Task 10 part 2b, ST-BRANCH-T-SMOKE and -T-CONTINUITY)
asserts that a window which carries telemetry only has ``P_telemetry_anomaly`` EQUAL to the value
the frozen model gives for that replay row. The test must not call the model to compute its own
expectation, so the expectation is this file: committed, bound to the model's SHA-256, and produced
by this separate script.

What it does. It reads the replay CSV (``ai/prototype-data/prepared_sessions/session_001/
telemetry.csv``) and the model file - both READ ONLY - and, for each of the 25 rows, runs the booster
exactly the way ``backend/app/providers/trained.py`` does (the eight features in the model's own
order as float32, ``iteration_range=(0, best_iteration + 1)``, ``P = float(1 - probs[0])`` where
``probs`` is float32). It does NOT import the product provider, so the fixture is an independent
computation; ``--cross-check-provider`` imports it once and proves the two agree bit for bit.

A row whose ``telemetry_available`` is 0 (CSV window_id 14 and 17, i.e. rows 13 and 16 counting from
0) has no features and no probability: it is written as ``null`` fields, because the front end sends
such a row with ``telemetry_source: "missing"``.

Each row also carries the eight features. The test finds the row of a window by looking its
``telemetry_features`` up here (not by counting time), then checks that row against
``telemetry_seq % 25``.

Usage (from the repository root; the interpreter must be the project's ``.venv``):

    .venv/bin/python backend/tests/fixtures/make_telemetry_pt_fixture.py            # write the fixture
    .venv/bin/python backend/tests/fixtures/make_telemetry_pt_fixture.py --check     # compare, write nothing
    .venv/bin/python backend/tests/fixtures/make_telemetry_pt_fixture.py --check --cross-check-provider

``--cross-check-provider`` can be combined with either mode.
Exit status: 0 on success (``--check``: the committed file equals a fresh computation), 1 otherwise.
Regenerate the fixture ONLY together with a deliberate model change; it is what makes a silently
different model - or a silently different runtime - visible.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).with_name("telemetry_pt_by_row.json")
MODEL = REPO / "ml" / "outputs" / "telemetry" / "xgb_telemetry.json"
REPLAY_CSV = REPO / "ai" / "prototype-data" / "prepared_sessions" / "session_001" / "telemetry.csv"
FEATURES = ["speed_kmph", "accel_x", "accel_y", "brake_pressure", "steering_angle", "throttle",
            "lane_deviation", "headway_distance"]
CLASSES = ["Safe", "Aggressive", "Distracted"]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_rows() -> list[dict]:
    """The CSV rows ordered by window_id (row index = window_id - 1), features parsed with
    ``float`` exactly as the front end's ``Number()`` parses them (it forwards them unchanged)."""
    with REPLAY_CSV.open(newline="") as handle:
        rows = sorted(csv.DictReader(handle), key=lambda r: int(r["window_id"]))
    out = []
    for index, row in enumerate(rows):
        assert int(row["window_id"]) == index + 1, "the replay CSV must number its windows 1..N"
        available = row["telemetry_available"] == "1"
        out.append({"row": index, "window_id": int(row["window_id"]),
                    "telemetry_features": {name: float(row[name]) for name in FEATURES} if available else None})
    return out


def compute() -> dict:
    import numpy as np
    import xgboost as xgb

    booster = xgb.Booster()
    booster.load_model(MODEL)
    booster.set_param({"nthread": 1})
    iteration_end = int(booster.attr("best_iteration")) + 1
    assert booster.feature_names == FEATURES, booster.feature_names
    rows = replay_rows()
    seen = set()
    for row in rows:
        features = row["telemetry_features"]
        if features is None:
            row["P_telemetry_anomaly"] = None
            row["behavior_classes"] = None
            continue
        key = tuple(features.values())
        assert key not in seen, f"row {row['row']} repeats the features of an earlier row: not identifiable"
        seen.add(key)
        matrix = xgb.DMatrix(np.array([[features[name] for name in FEATURES]], dtype=np.float32),
                             feature_names=FEATURES)
        probs = np.asarray(booster.predict(matrix, iteration_range=(0, iteration_end))[0], dtype=np.float32)
        assert probs.shape == (3,) and np.isfinite(probs).all()
        row["P_telemetry_anomaly"] = float(1 - probs[0])
        row["behavior_classes"] = {label: float(p) for label, p in zip(CLASSES, probs)}
    return {
        "what": "Frozen P_telemetry_anomaly (= 1 - P(Safe)) and the three class probabilities of the "
                "trained XGBoost for each of the 25 rows of the prepared replay, produced by "
                "backend/tests/fixtures/make_telemetry_pt_fixture.py. Rows 13 and 16 (0-based) have no "
                "telemetry and carry null. A window's row is telemetry_seq % 25.",
        "telemetry_model_file": "ml/outputs/telemetry/xgb_telemetry.json",
        "telemetry_model_sha256": sha256_of(MODEL),
        "replay_csv": "ai/prototype-data/prepared_sessions/session_001/telemetry.csv",
        "replay_csv_sha256": sha256_of(REPLAY_CSV),
        "generated_with": {"xgboost": xgb.__version__, "numpy": np.__version__, "best_iteration": iteration_end - 1},
        "rows": rows,
    }


def cross_check_provider(fixture: dict) -> list[str]:
    """Run the same rows through the product's ``TrainedProvider`` and report every row whose
    ``P_telemetry_anomaly`` or class probabilities are not bit-identical to the fixture's."""
    sys.path.insert(0, str(REPO / "backend"))
    from app.providers.trained import get_provider
    from app.schemas import LiveInput, TelemetryFeatures

    provider = get_provider()
    problems = []
    for row in fixture["rows"]:
        if row["telemetry_features"] is None:
            continue
        data = LiveInput(request_id=f"fixture-row-{row['row']}", telemetry_features=TelemetryFeatures(**row["telemetry_features"]),
                         telemetry_timestamp="2026-01-01T00:00:00Z", telemetry_source="prepared_replay")
        window, _ = provider.infer(data)
        classes = {c.label: c.probability for c in window.telemetry_behavior_classes}
        if window.P_telemetry_anomaly != row["P_telemetry_anomaly"] or classes != row["behavior_classes"]:
            problems.append(f"row {row['row']}: provider {window.P_telemetry_anomaly!r} {classes!r} "
                            f"!= fixture {row['P_telemetry_anomaly']!r} {row['behavior_classes']!r}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="compare the committed fixture with a fresh computation; write nothing")
    parser.add_argument("--cross-check-provider", action="store_true",
                        help="also run every row through app.providers.trained and require bit-identical output")
    args = parser.parse_args()
    fresh = compute()
    if args.cross_check_provider:
        problems = cross_check_provider(fresh)
        for line in problems:
            print("MISMATCH", line)
        print(f"cross-check against app.providers.trained: {'FAILED' if problems else 'identical on all 23 telemetry rows'}")
        if problems:
            return 1
    text = json.dumps(fresh, indent=2) + "\n"
    if args.check:
        if not FIXTURE.exists() or FIXTURE.read_text() != text:
            print(f"{FIXTURE.name} is NOT what a fresh computation gives")
            return 1
        print(f"{FIXTURE.name} equals a fresh computation (model {fresh['telemetry_model_sha256'][:8]})")
        return 0
    FIXTURE.write_text(text)
    print(f"wrote {FIXTURE.relative_to(REPO)} (model {fresh['telemetry_model_sha256'][:8]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
