"""The PERF scripts' pure parts (deferred minor M10): the Server-Timing parser, a short run that must
say so instead of reporting as if complete, and a completeness ratio with nothing to divide by."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(f"_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


perf01, perf02 = load("perf01"), load("perf02")


@pytest.mark.parametrize("header,expected", [
    ("infer;dur=8.2, commit;dur=3.1, total;dur=12.5", {"infer": 8.2, "commit": 3.1, "total": 12.5}),
    ('db;desc="read, then write";dur=2', {"db": 2.0}),
    ('cache;dur="1.5"', {"cache": 1.5}),
    ("miss", {}),
    ("a;dur=abc, b;dur=4", {"b": 4.0}),
    ("", {}),
    # Review R16: the Python parser must agree with parseServerTiming in
    # ai/src/liveTiming.ts on the same header, token for token.
    ("infer;dur=1, infer;dur=2.5", {"infer": 3.5}),  # repeated names sum, not last-wins
    ('db;desc="a\\";b";dur=2', {"db": 2.0}),          # a backslash-escaped quote stays quoted
    ("a;dur=inf", {}),                                # non-finite, like Number() + isFinite
    ("a;dur=nan", {}),
    ("a;dur=1_0", {}),                                # Python float() reads 1_0; JS Number() does not
    ('a;dur=""', {"a": 0.0}),                         # Number("") is 0
    ('a;dur="1.5""', {}),                             # one quote per side is stripped, not all of them
    ("a;dur=0x10", {"a": 16.0}),                      # JS Number() reads hex
])
def test_parse_server_timing(header, expected):
    assert perf01.parse_server_timing(header) == expected


def _timings(n):
    return {i: {"windowId": i, "capturedAtMs": 1000.0 * i, "renderedAtMs": 1000.0 * i + 30, "captureToSendMs": 2,
                "networkMs": 25, "renderMs": 3, "attemptIndex": 1} for i in range(1, n + 1)}


def _raw(n):
    return {"timings": _timings(n), "records": [], "server_timing": {}}


def test_a_short_run_is_flagged_not_reported_as_complete():
    result = perf01.analyse(_raw(50), windows=600, warmup=20)
    assert result["windows_measured"] == 30
    assert result["windows_requested"] == 600
    assert result["short_run"] is True


def test_a_full_run_is_not_flagged():
    result = perf01.analyse(_raw(620), windows=600, warmup=20)
    assert result["windows_measured"] == 600 and result["short_run"] is False


def test_main_exits_non_zero_on_a_short_run(tmp_path, monkeypatch):
    monkeypatch.setattr(perf01, "collect", lambda windows, warmup, active_vision="stable": {
        **_raw(50), "browser": "x", "console_errors": [], "sid": "s", "vision_model": {}})
    assert perf01.main(["--windows", "600", "--warmup", "20", "--out", str(tmp_path)]) == 1
    assert (tmp_path / "perf01.json").exists()  # the partial measurement is still written, marked short


@pytest.mark.parametrize("logged,denominator,expected", [
    (211, 211, {"denominator": 211, "logged": 211, "completeness": 1.0, "meets_99_percent": True}),
    (98, 100, {"denominator": 100, "logged": 98, "completeness": 0.98, "meets_99_percent": False}),
    (0, 0, {"denominator": 0, "logged": 0, "completeness": None, "meets_99_percent": False}),
])
def test_completeness_with_and_without_a_denominator(logged, denominator, expected):
    assert perf02.completeness(logged, denominator) == expected


# ---- Task 10A Stage 3: run the perf scripts with a chosen vision model, and prove which one ran ----
from e2e_support import check_vision_identity, vision_env  # noqa: E402

RN = "resnet18_search004_seed42"


def test_vision_env_is_empty_for_stable_and_names_a_candidate():
    assert vision_env("stable") is None
    assert vision_env(RN) == {"DRA_ACTIVE_VISION": RN}


@pytest.mark.parametrize("active,info", [
    ("stable", {"model_id": "stable_mobilenet_v3_large", "source": "stable", "sha256": "b3a4"}),
    (RN, {"model_id": RN, "source": "candidate:p5_resnet18_search004_seed42_20261023", "sha256": "5e22"}),
])
def test_check_vision_identity_accepts_the_model_that_was_asked_for(active, info):
    assert check_vision_identity(active, info) == {"model_id": info["model_id"], "source": info["source"],
                                                   "sha256": info["sha256"]}


@pytest.mark.parametrize("active,info", [
    (RN, {"model_id": "stable_mobilenet_v3_large", "source": "stable", "sha256": "b3a4"}),
    ("stable", {"model_id": RN, "source": "candidate:x", "sha256": "5e22"}),
    (RN, {}),
])
def test_check_vision_identity_refuses_a_different_model(active, info):
    with pytest.raises(RuntimeError, match="vision model"):
        check_vision_identity(active, info)


def test_perf01_main_runs_the_chosen_model_and_records_it(tmp_path, monkeypatch):
    seen = {}

    def fake_collect(windows, warmup, active_vision="stable"):
        seen["active"] = active_vision
        return {**_raw(650), "browser": "x", "console_errors": [], "sid": "s",
                "vision_model": {"model_id": RN, "source": "candidate:p", "sha256": "5e22"}}
    monkeypatch.setattr(perf01, "collect", fake_collect)
    assert perf01.main(["--active-vision", RN, "--out", str(tmp_path)]) == 0
    import json
    result = json.loads((tmp_path / "perf01.json").read_text())
    assert seen["active"] == RN
    assert result["active_vision"] == RN and result["vision_model"]["model_id"] == RN


def test_perf02_main_runs_the_chosen_model(tmp_path, monkeypatch):
    seen = {}

    def fake_run(active_vision="stable"):
        seen["active"] = active_vision
        return {"D1_server_seen": {"logged": 1, "denominator": 1, "completeness": 1.0},
                "D2_all_logical": {"logged": 1, "denominator": 1, "completeness": 1.0},
                "server": {"faults_by_category": {}}, "active_vision": active_vision}
    monkeypatch.setattr(perf02, "run", fake_run)
    assert perf02.main(["--active-vision", RN, "--out", str(tmp_path)]) == 0
    assert seen["active"] == RN


def test_perf01_writes_the_measured_windows_raw_timings_and_they_reproduce_the_quantiles(tmp_path, monkeypatch):
    """CX-A3 R-1: the summary alone cannot be re-derived. The run must keep, beside perf01.json,
    the raw per-window timings of exactly the measured windows (after the warm-up), bound by hash,
    so that an auditor recomputes the quantiles from them."""
    import hashlib
    import json
    # Durations that differ per window (review O-7): with a constant duration any 600 rows would
    # reproduce the same statistics, so the equality below would prove nothing. Warm-up windows get
    # durations far outside the measured range, so a file that kept them would change min/max.
    timings = _timings(650)
    for i, row in timings.items():
        row["renderedAtMs"] = row["capturedAtMs"] + (500 + i if i <= 20 else 20 + (i * 37) % 61)
    monkeypatch.setattr(perf01, "collect", lambda windows, warmup, active_vision="stable": {
        "timings": timings, "records": [], "server_timing": {}, "browser": "x", "console_errors": [],
        "sid": "s", "vision_model": {}})
    assert perf01.main(["--windows", "600", "--warmup", "20", "--out", str(tmp_path)]) == 0
    result = json.loads((tmp_path / "perf01.json").read_text())
    assert result["stages"]["capture_to_render_ms"]["max"] < 500  # the warm-up was excluded
    assert len({r["renderedAtMs"] - r["capturedAtMs"] for r in timings.values()}) > 50
    raw_file = tmp_path / result["raw_timings"]["file"]
    assert result["raw_timings"]["sha256"] == hashlib.sha256(raw_file.read_bytes()).hexdigest()
    rows = json.loads(raw_file.read_text())
    assert [r["windowId"] for r in rows] == list(range(21, 621))  # the measured 600, warm-up excluded
    recomputed = perf01.summarise([r["renderedAtMs"] - r["capturedAtMs"] for r in rows])
    assert recomputed == result["stages"]["capture_to_render_ms"]
    assert result["raw_timings"]["windows"] == 600
    assert "p95" in result["raw_timings"]["quantile_rule"]
