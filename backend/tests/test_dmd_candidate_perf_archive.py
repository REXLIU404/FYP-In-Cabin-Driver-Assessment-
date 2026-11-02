"""DMD candidate evidence, item D: the perf01 archive verifier.

The six perf01 runs are evidence, not tests. These tests pin the recomputation rule used
to audit them: sha256 of the raw timings file, the p50/p95 rule of ``e2e_support.summarise``
(``p95 = sorted[min(n-1, round(0.95*(n-1)))]``) and the exact match with the summary.
"""
import hashlib
import importlib.util
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def load_runner():
    path = SCRIPTS / "dmd_candidate_perf_archive.py"
    assert path.is_file(), f"missing runner {path}"
    spec = importlib.util.spec_from_file_location("_dmd_candidate_perf_archive", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(tmp_path, name, durations, model_id="stable_mobilenet_v3_large"):
    directory = tmp_path / name
    directory.mkdir()
    rows = [{"windowId": i, "capturedAtMs": 1000.0 * i,
             "renderedAtMs": 1000.0 * i + duration, "captureToSendMs": 1.0,
             "networkMs": 2.0, "renderMs": 0.5, "attemptIndex": 1}
            for i, duration in enumerate(durations)]
    raw = json.dumps(rows, indent=1).encode()
    (directory / "perf01_timings.json").write_bytes(raw)
    summary = {"n": len(durations),
               "min": round(min(durations), 3),
               "median": round(statistics.median(durations), 3),
               "p95": round(sorted(durations)[min(len(durations) - 1,
                                                  int(round(0.95 * (len(durations) - 1))))], 3),
               "max": round(max(durations), 3)}
    document = {"vision_model": {"model_id": model_id},
                "stages": {"capture_to_render_ms": summary},
                "raw_timings": {"file": "perf01_timings.json",
                                "sha256": hashlib.sha256(raw).hexdigest()},
                "short_run": False, "console_errors": [],
                "attempts_other_than_1": 0, "windows_measured": len(durations)}
    (directory / "perf01.json").write_text(json.dumps(document))
    return directory


def test_quantiles_follow_the_perf01_rule():
    runner = load_runner()
    assert runner.quantiles([1, 2, 3, 4]) == {"n": 4, "min": 1.0, "median": 2.5, "p95": 4.0, "max": 4.0}
    values = list(range(100))
    # int(round(0.95 * 99)) = 94: the perf01 rule, not a 95th-value interpolation.
    assert runner.quantiles(values)["p95"] == 94.0
    assert runner.quantiles(values)["median"] == 49.5


def test_verify_run_accepts_a_hash_bound_matching_run(tmp_path):
    runner = load_runner()
    directory = _run(tmp_path, "stable-r1", [10, 20, 30, 40])
    result = runner.verify_run(directory)
    assert result["sha256_ok"] and result["summary_matches"] and result["ok"]
    assert result["model_id"] == "stable_mobilenet_v3_large"
    assert result["recomputed"] == result["summary"]


def test_verify_run_rejects_a_changed_timings_file(tmp_path):
    runner = load_runner()
    directory = _run(tmp_path, "stable-r1", [10, 20, 30, 40])
    timings = json.loads((directory / "perf01_timings.json").read_text())
    timings[0]["renderedAtMs"] += 1
    (directory / "perf01_timings.json").write_text(json.dumps(timings))
    result = runner.verify_run(directory)
    assert not result["sha256_ok"] and not result["ok"]


def test_verify_archive_reports_every_round(tmp_path):
    runner = load_runner()
    _run(tmp_path, "stable-r1", [10, 20, 30])
    _run(tmp_path, "dmd_adapted_mobilenet_v3_20261029-r1", [11, 21, 31],
         model_id="dmd_adapted_mobilenet_v3_20261029")
    result = runner.verify_archive(tmp_path)
    assert len(result["runs"]) == 2 and result["all_ok"]
    assert {r["model_id"] for r in result["runs"]} == {
        "stable_mobilenet_v3_large", "dmd_adapted_mobilenet_v3_20261029"}
