"""ST-LONG-01 (sprint plan v3, W6 / G-W6-A): a long Live session persists and exports completely.

Run with ``-m long`` (deselected otherwise; see conftest). One Live session on the fake camera
for ``DRA_LONG_MINUTES`` minutes (default 15, about 9,000 windows at 10 Hz). Asserted:
  * every window the browser received is stored once: window ids 1..N with no gap, the database,
    the session's total, every page of ``GET /windows``, the JSON export and the CSV export all
    hold exactly 1..N;
  * a sample of windows (every 97th and the last 20) agrees field by field across the five homes;
  * the page keeps the newest 500 windows; no fault, no re-send, no stop panel, no console error.
Recorded, not judged (no threshold): per-minute window count, round trip and render p50 / p95 from
the page's timing buffer, the JS heap, and the database file size. With ``DRA_E2E_EVIDENCE_DIR``
set the measurement is written there as ``long-session.json``.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from e2e_support import (FAKE_CAMERA_ARGS, Chrome, LiveRun, api_client, csv_row_diffs, db_count, db_records,
                         deep_diff, evidence_dir, parse_csv, record_diffs, summarise)

MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml/outputs"
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)
pytestmark = [pytest.mark.long, pytest.mark.e2e, requires_models]

MINUTES = float(os.environ.get("DRA_LONG_MINUTES", "15"))
PAGE_HISTORY = 500


def all_windows(client, sid: str) -> list[dict]:
    out, after = [], 0
    while True:
        page = client.get(f"/api/sessions/{sid}/windows", params={"after": after, "limit": 1000}).json()
        if not page:
            return out
        out += page
        after = page[-1]["window_id"]


def db_bytes(server) -> int:
    return sum(os.path.getsize(p) for p in (str(server.db_path), f"{server.db_path}-wal") if os.path.exists(p))


def test_st_long_01_a_long_session_is_stored_and_exported_completely(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)
    chrome.tap.drop_images = True
    run = LiveRun(chrome)
    page, tap = chrome.page, chrome.tap
    samples: list[dict] = []
    try:
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: len(tap.answered()) >= 5, "the first windows", 60)
        run.sid = sid = tap.session_posts[0].response["id"]
        started = time.time()
        next_sample = started + 60
        while time.time() - started < MINUTES * 60:
            chrome.wait(1000)  # keeps the page and the request tap running
            assert chrome.stop_panel().count() == 0, f"monitoring stopped: {chrome.stop_panel_text()}"
            if time.time() >= next_sample:
                timings = page.evaluate("() => window.__draLiveTimings") or []
                recent = timings[-600:]
                samples.append({
                    "minute": round((time.time() - started) / 60, 2),
                    "windows": len(tap.answered(sid)),
                    "network_including_server_ms": summarise([t["networkMs"] for t in recent]),
                    "render_ms": summarise([t["renderMs"] for t in recent if t["renderMs"] is not None]),
                    "js_heap_bytes": page.evaluate("() => performance.memory ? performance.memory.usedJSHeapSize : null"),
                    "db_bytes": db_bytes(e2e_server),
                })
                next_sample += 60
        run.settle()

        calls = tap.answered(sid)
        count = len(calls)
        ids = list(range(1, count + 1))
        assert [c.response["window_id"] for c in calls] == ids
        assert len({c.request_id for c in calls}) == count
        assert all(c.attempt == "1" for c in tap.infer if c.sid == sid)
        assert db_count(e2e_server, "SELECT COUNT(*) FROM inference_records WHERE session_id=?", sid) == count
        assert db_count(e2e_server, "SELECT COUNT(*) FROM fault_events WHERE session_id=?", sid) == 0
        with api_client(e2e_server) as client:
            assert client.get(f"/api/sessions/{sid}").json()["total_windows"] == count
            windows = {w["window_id"]: w for w in all_windows(client, sid)}
            export_json = {r["window_id"]: r for r in client.get(f"/api/sessions/{sid}/export", params={"format": "json"}).json()["records"]}
            export_csv = {int(r["window_id"]): r for r in parse_csv(client.get(f"/api/sessions/{sid}/export", params={"format": "csv"}).text)}
            latest = client.get(f"/api/sessions/{sid}/risk/latest").json()
        assert sorted(windows) == sorted(export_json) == sorted(export_csv) == ids
        db = {row["window_id"]: row for row in db_records(e2e_server, sid)}
        assert sorted(db) == ids
        sample_ids = sorted(set(ids[::97] + ids[-20:]))
        diffs = []
        for window_id in sample_ids:
            want = calls[window_id - 1].response
            for name, home in (("database payload", db[window_id]["payload"]), ("GET /windows", windows[window_id]),
                               ("export JSON", export_json[window_id])):
                diffs += [f"window {window_id} {name}: {d}" for d in deep_diff(want, home)]
            diffs += [f"window {window_id}: {d}" for d in record_diffs(db[window_id], want)]
            diffs += [f"window {window_id}: {d}" for d in csv_row_diffs(export_csv[window_id], want)]
        assert not diffs, f"{len(diffs)} differences, first {diffs[:10]}"
        assert deep_diff(latest, calls[-1].response) == []

        page.get_by_role("button", name="Signal Inspector", exact=True).click()
        chrome.wait(500)
        assert page.locator(".window-list button").count() == PAGE_HISTORY
        assert chrome.console_errors == [] and chrome.page_errors == []

        measurement = {"minutes": MINUTES, "windows": count, "rate_hz": round(count / (MINUTES * 60), 2),
                       "sampled_windows_reconciled": len(sample_ids), "per_minute": samples}
        print("ST-LONG-01 " + json.dumps({k: v for k, v in measurement.items() if k != "per_minute"}))
        out = evidence_dir()
        if out:
            (out / "long-session.json").write_text(json.dumps(measurement, indent=2, sort_keys=True))
    finally:
        chrome.close()
