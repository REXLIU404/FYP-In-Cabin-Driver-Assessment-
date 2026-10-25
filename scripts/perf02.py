#!/usr/bin/env python3
"""PERF-02 (sprint plan v3, W6 / G-W6-A): every request ends in a durable outcome - a stored window
or a recorded fault - measured against two denominators, under injected faults. Reports; asserts nothing.

    .venv/bin/python scripts/perf02.py [--out docs/evidence/<date>/perf]

One Live session (fake camera, throw-away database, the e2e uvicorn) goes through four phases:
  1 normal monitoring;
  2 a transport burst: the next two deliveries are lost in transit, the third (automatic retry) lands;
  3 the backend is stopped mid-session: the loop stops after three deliveries; the backend is restarted
    on the same database and port and Retry is pressed;
  4 one request is rewritten (by the test's network tap) so that the server rejects it with 422 and
    records the fault; the loop stops (422 is not retryable).

Denominators (the CNT default: an unavailable window counts as accepted, outcome "unavailable"):
  D1 requests the SERVER saw (any HTTP answer from it): logged = a stored window or a fault row;
  D2 every logical request the page issued (unique request_id): the same, plus those that never
     reached the server - which no server-side log can hold by construction (they are visible on the
     page as the stop panel and in this report as client-side-only).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "tests"))
from e2e_support import FAKE_CAMERA_ARGS, Chrome, build_dist, db_connection, db_records, start_server  # noqa: E402

TARGET = 0.99


def completeness(logged: int, denominator: int) -> dict:
    """One denominator's share of durably logged requests. With nothing to divide by there is no
    completeness to report (None) and the 99 % target is not met - never a ZeroDivisionError."""
    ratio = logged / denominator if denominator else None
    return {"denominator": denominator, "logged": logged,
            "completeness": None if ratio is None else round(ratio, 6),
            "meets_99_percent": ratio is not None and ratio >= TARGET}


def run() -> dict:
    from playwright.sync_api import sync_playwright

    build_dist()
    workdir = Path(tempfile.mkdtemp(prefix="perf02-"))
    server = start_server(workdir)
    port = urlparse(server.base_url).port
    phases = {}
    try:
        with sync_playwright() as pw:
            chrome = Chrome(pw, server, FAKE_CAMERA_ARGS)
            chrome.tap.drop_images = True
            tap = chrome.tap
            try:
                chrome.open()
                chrome.top_button("Start Monitoring").click()
                chrome.wait_until(lambda: len(tap.answered()) >= 100, "phase 1: 100 windows", 90)
                sid = tap.session_posts[0].response["id"]
                phases["1_normal"] = len(tap.answered(sid))

                tap.abort_infer = 2
                mark = len(tap.answered(sid))
                chrome.wait_until(lambda: tap.abort_infer == 0 and len(tap.answered(sid)) >= mark + 50,
                                  "phase 2: the burst absorbed and 50 more windows", 90, tolerate_stop_panel=True)
                phases["2_transport_burst"] = len(tap.answered(sid))

                server.stop()
                chrome.wait_until(lambda: chrome.stop_panel().count() == 1, "phase 3: the stop panel", 60, tolerate_stop_panel=True)
                stopped_text = chrome.stop_panel_text()
                server = start_server(workdir, port=port, log_name="uvicorn-restart.log")
                chrome.server = server
                mark = len(tap.answered(sid))
                chrome.stop_panel().get_by_role("button", name="Retry", exact=True).click()
                chrome.wait_until(lambda: len(tap.answered(sid)) >= mark + 50, "phase 3: 50 windows after Retry", 90,
                                  tolerate_stop_panel=True)
                phases["3_backend_restart"] = len(tap.answered(sid))

                target: dict = {}

                def reject_one(body):  # pure per request id: a re-send of the same request is rewritten the same way
                    if not target and body.get("telemetry_features") is not None:
                        target["request_id"] = body["request_id"]
                    if body["request_id"] == target.get("request_id"):
                        return {**body, "telemetry_features": None, "telemetry_timestamp": None, "telemetry_source": "missing"}
                    return body
                tap.rewrite_infer = reject_one
                chrome.wait_until(lambda: chrome.stop_panel().count() == 1, "phase 4: the 422 stop panel", 60, tolerate_stop_panel=True)
                rejected_text = chrome.stop_panel_text()
                tap.rewrite_infer = None
                chrome.wait(1000)
                calls = [c for c in tap.infer if c.sid == sid]
            finally:
                chrome.close()
        with closing(db_connection(server)) as conn:
            faults = [dict(r) for r in conn.execute(
                "SELECT request_id, attempt_index, error_category, http_status FROM fault_events WHERE session_id=?", (sid,))]
        records = db_records(server, sid)
    finally:
        server.stop()

    logical = {c.request_id for c in calls if c.outcome != "held"}
    seen = {c.request_id for c in calls if c.outcome == "ok"}  # an HTTP answer came back from the server
    stored = {r["request_id"] for r in records}
    faulted = {f["request_id"] for f in faults if f["request_id"]}
    logged = stored | faulted
    unavailable = sum(1 for r in records if not r["payload"]["assessment_available"])
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": sid, "phases_windows_after": phases,
        "stop_panel_after_backend_stop": stopped_text, "stop_panel_after_rejected_request": rejected_text,
        "client": {"logical_requests": len(logical), "deliveries": len(calls),
                   "delivery_outcomes": dict(Counter(c.outcome for c in calls)),
                   "deliveries_by_attempt_index": dict(Counter(c.attempt for c in calls)),
                   "http_status_of_answered": dict(Counter(str(c.status) for c in calls if c.outcome == "ok"))},
        "server": {"stored_windows": len(records), "unavailable_windows_counted_as_accepted": unavailable,
                   "fault_rows": len(faults), "faults_by_category": dict(Counter(f["error_category"] for f in faults))},
        "D1_server_seen": {**completeness(len(seen & logged), len(seen)), "not_logged": sorted(seen - logged)},
        "D2_all_logical": {**completeness(len(logical & logged), len(logical)),
                           "client_side_only": sorted(logical - logged)},
        "stored_without_a_201_seen_by_the_page": sorted(stored - {c.request_id for c in calls if c.status == 201}),
        "duplicate_request_ids_in_database": len(records) - len(stored),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "docs" / "evidence" / datetime.now(timezone.utc).strftime("%Y-%m-%d") / "perf")
    args = parser.parse_args(argv)
    result = run()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "perf02.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    print(f"PERF-02: D1 {result['D1_server_seen']['logged']}/{result['D1_server_seen']['denominator']} = "
          f"{result['D1_server_seen']['completeness']}; D2 {result['D2_all_logical']['logged']}/{result['D2_all_logical']['denominator']} = "
          f"{result['D2_all_logical']['completeness']}; faults {result['server']['faults_by_category']} -> {args.out / 'perf02.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
