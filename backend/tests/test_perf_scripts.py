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
    monkeypatch.setattr(perf01, "collect", lambda windows, warmup: {**_raw(50), "browser": "x", "console_errors": [], "sid": "s"})
    assert perf01.main(["--windows", "600", "--warmup", "20", "--out", str(tmp_path)]) == 1
    assert (tmp_path / "perf01.json").exists()  # the partial measurement is still written, marked short


@pytest.mark.parametrize("logged,denominator,expected", [
    (211, 211, {"denominator": 211, "logged": 211, "completeness": 1.0, "meets_99_percent": True}),
    (98, 100, {"denominator": 100, "logged": 98, "completeness": 0.98, "meets_99_percent": False}),
    (0, 0, {"denominator": 0, "logged": 0, "completeness": None, "meets_99_percent": False}),
])
def test_completeness_with_and_without_a_denominator(logged, denominator, expected):
    assert perf02.completeness(logged, denominator) == expected
