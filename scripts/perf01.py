#!/usr/bin/env python3
"""PERF-01 (sprint plan v3, W6 / G-W6-A): capture -> render latency of the Live loop, per stage, and
the 2 / 3 / 5 s freshness-threshold sensitivity. Records and reports; asserts nothing.

    .venv/bin/python scripts/perf01.py [--windows 600] [--warmup 20] [--out docs/evidence/<date>/perf]

Declared load: one uvicorn (the API and the freshly built dist/) on a throw-away database, Chromium
with the default fake camera (20 fps), the app's own loop (target 10 requests/s, one in flight), the
frozen models, this machine. Stages come from the page's timing buffer (window.__draLiveTimings,
Task 10 part 1): capture -> send, send -> response (network + the server's whole stay), response ->
committed to the UI, and the server's Server-Timing stages. capture -> render = renderedAt - capturedAt.

The target "<= 1 s end to end" is judged on capture -> render p95, the statistic the evaluation
matrix fixes for E4 (docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md, addendum 2026-10-22, per D07). The
maximum is reported beside it, as information only. Model forward time and the Server-Timing stages
are reported separately and are never the latency figure.

Sensitivity: the evidence ages the server recorded (provenance vision_age_s / telemetry_age_s,
measured from the canonical acquisition time) against 2, 3 and 5 s. NOTE: telemetry age is 0-2 s
BY CONSTRUCTION (the prepared replay's acquisition time is the start of its 2 s sample), so it is
not a sensor age.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "tests"))
from e2e_support import FAKE_CAMERA_ARGS, Chrome, build_dist, db_records, start_server, summarise  # noqa: E402

TARGET_MS = 1000.0
THRESHOLDS_S = (2.0, 3.0, 5.0)


def machine() -> dict:
    def sysctl(key):
        try:
            return subprocess.run(["sysctl", "-n", key], capture_output=True, text=True).stdout.strip()
        except OSError:
            return None
    return {"platform": platform.platform(), "cpu": sysctl("machdep.cpu.brand_string"),
            "logical_cpus": sysctl("hw.logicalcpu"), "memory_bytes": sysctl("hw.memsize"),
            "python": platform.python_version()}


def collect(windows: int, warmup: int) -> dict:
    from playwright.sync_api import sync_playwright

    build_dist()
    server = start_server(Path(tempfile.mkdtemp(prefix="perf01-")))
    timings: dict[int, dict] = {}
    server_timing: dict[str, str] = {}  # request_id -> Server-Timing header, read off the network

    def on_response(response) -> None:
        # The page's own buffer never receives the header (the loop does not pass TimingInput.serverTiming,
        # a known gap), so the stages are taken from the response as it crosses the network.
        if response.request.method == "POST" and response.url.rstrip("/").endswith("/infer"):
            try:
                request_id = json.loads(response.request.post_data or "{}").get("request_id")
            except ValueError:
                request_id = None
            header = response.headers.get("server-timing")
            if request_id and header:
                server_timing[request_id] = header
    try:
        with sync_playwright() as pw:
            chrome = Chrome(pw, server, FAKE_CAMERA_ARGS)
            chrome.page.on("response", on_response)
            try:
                chrome.open()
                chrome.top_button("Start Monitoring").click()
                wanted = warmup + windows
                deadline = time.time() + wanted / 2 + 120
                while time.time() < deadline:
                    chrome.wait(3000)  # the buffer keeps 500 windows: read it well before it wraps
                    for entry in chrome.page.evaluate("() => window.__draLiveTimings") or []:
                        if entry.get("renderedAtMs") is not None:
                            timings[entry["windowId"]] = entry
                    if len(timings) >= wanted:
                        break
                chrome.top_button("Pause").click()
                chrome.wait(500)
                sid = chrome.tap.session_posts[0].response["id"]
                browser = chrome.version
                console_errors = list(chrome.console_errors)
            finally:
                chrome.close()
        records = db_records(server, sid)
    finally:
        server.stop()
    return {"timings": timings, "records": records, "sid": sid, "browser": browser, "console_errors": console_errors,
            "server_timing": server_timing}


def parse_server_timing(header: str) -> dict[str, float]:
    out = {}
    for part in header.split(","):
        name, _, rest = part.strip().partition(";")
        for param in rest.split(";"):
            key, _, value = param.strip().partition("=")
            if key == "dur":
                out[name.strip()] = float(value)
    return out


def analyse(raw: dict, windows: int, warmup: int) -> dict:
    ids = sorted(raw["timings"])[warmup:warmup + windows]
    rows = [raw["timings"][i] for i in ids]
    total = [t["renderedAtMs"] - t["capturedAtMs"] for t in rows]
    stages = {
        "capture_to_send_ms": summarise([t["captureToSendMs"] for t in rows]),
        "network_including_server_ms": summarise([t["networkMs"] for t in rows]),
        "render_ms": summarise([t["renderMs"] for t in rows]),
        "capture_to_render_ms": summarise(total),
    }
    by_id = {r["window_id"]: r["payload"] for r in raw["records"]}
    request_of = {r["window_id"]: r["request_id"] for r in raw["records"]}
    parsed = [parse_server_timing(raw["server_timing"][request_of[i]]) for i in ids
              if i in request_of and request_of[i] in raw["server_timing"]]
    stages["server_timing_ms"] = {k: summarise([p[k] for p in parsed if k in p])
                                  for k in sorted({k for p in parsed for k in p})}
    stages["server_timing_windows"] = len(parsed)
    measured = [by_id[i] for i in ids if i in by_id]
    ages = {branch: [p["provenance"].get(f"{branch}_age_s") for p in measured] for branch in ("vision", "telemetry")}
    sensitivity = {}
    for threshold in THRESHOLDS_S:
        row = {}
        for branch, values in ages.items():
            known = [v for v in values if v is not None]
            row[f"{branch}_older_than"] = round(sum(v > threshold for v in known) / len(known), 4) if known else None
        both = [p for p in measured if p["provenance"].get("vision_age_s") is not None and p["provenance"].get("telemetry_age_s") is not None]
        row["both_older_than"] = round(sum(p["provenance"]["vision_age_s"] > threshold and p["provenance"]["telemetry_age_s"] > threshold
                                           for p in both) / len(both), 4) if both else None
        sensitivity[f"{threshold:g}s"] = row
    p95, worst = stages["capture_to_render_ms"]["p95"], stages["capture_to_render_ms"]["max"]
    return {
        "windows_measured": len(rows), "warmup_windows_skipped": warmup,
        "achieved_rate_hz": round((len(rows) - 1) / ((rows[-1]["capturedAtMs"] - rows[0]["capturedAtMs"]) / 1000), 2) if len(rows) > 1 else None,
        "stages": stages,
        "target_1s": {"statistic": "capture_to_render_p95", "p95_ms": p95, "met": p95 <= TARGET_MS,
                      "max_ms_information_only": worst,
                      "source": "docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md addendum 2026-10-22 (E4, D07)"},
        "evidence_age_s": {b: summarise([v for v in a if v is not None]) for b, a in ages.items()},
        "freshness_sensitivity": sensitivity,
        "freshness_at_default_3s": {k: sum(1 for p in measured if p["modality_freshness"][k] == "fresh") for k in ("vision", "telemetry")},
        "attempts_other_than_1": sum(1 for t in rows if t.get("attemptIndex") != 1),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--windows", type=int, default=600)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--out", type=Path, default=REPO / "docs" / "evidence" / datetime.now(timezone.utc).strftime("%Y-%m-%d") / "perf")
    args = parser.parse_args(argv)
    raw = collect(args.windows, args.warmup)
    result = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "machine": machine(),
              "browser": raw["browser"], "camera": "Chromium --use-fake-device-for-media-stream (default 20 fps)",
              "loop": "app default: target 10 requests/s, one in flight", "console_errors": raw["console_errors"],
              **analyse(raw, args.windows, args.warmup)}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "perf01.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    c2r = result["stages"]["capture_to_render_ms"]
    print(f"PERF-01: {result['windows_measured']} windows at {result['achieved_rate_hz']} Hz; capture->render p50 {c2r['median']} ms, "
          f"p95 {c2r['p95']} ms, max {c2r['max']} ms -> {args.out / 'perf01.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
