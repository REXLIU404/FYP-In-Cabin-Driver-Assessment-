"""Task 10 part 2a: the Live system end to end.

One uvicorn serves the API and the freshly built ``dist/``; Chromium (fake camera) drives the
dashboard exactly as a person would, and everything it sends and receives is recorded from the
outside (Playwright routes + an injected probe). No product code was touched for any of this.

ST-LIVE-E2E-01 (class ``TestStLiveE2E01``, one monitoring run, many assertions)
    * every ``/infer`` answer, the database row, ``GET /windows``, the JSON export and the CSV
      export agree on ALL fields of every window; ``GET /risk/latest`` is the last window; the
      numbers the Live Monitor shows are ``GET /risk/latest`` in the dashboard's display format
      (the IT-UI-01 oracle);
    * the contract (mode, sources, 10 + 3 classes, D01, frozen model hashes) and the R10 wire
      behaviour (frame identity, telemetry sequence and time, new / repeat);
    * a flag set through the UI reaches both exports; all five views open without errors.
    No score is asserted: the fake camera draws a moving pattern, so P_distraction is not reproducible.

E2 (module-level tests): the stop panel by real clicks - a transport fault and Retry, a failed
    New Session and Retry, an unexpected camera loss against Stop Camera.
E3: rVFC behaviour on the fake camera, recorded and not judged. Part 2b adds the five-way
    reconciliation at its end, on this default (20 fps) camera.

The E1 run uses a 5 fps fake camera: the default one is a 20 fps pattern and the loop (about
10 Hz) never outruns it, so a frame is never sent twice and the vision REPEAT path would not be
exercised. E2 and E3 use the default camera.

Expected values are literals in this file; the only thing computed is the dashboard's display
rounding, by an independent implementation (``e2e_support.half_up``).

Evidence (part 2b): with ``DRA_E2E_EVIDENCE_DIR`` set, ``test_06`` leaves a screenshot of each of the
five views and the session's JSON / CSV export in that directory, and E3 its measurement JSON.
Unset, nothing is written outside tmp.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

import pytest

from e2e_support import (
    FAKE_CAMERA_ARGS,
    RISK_UPDATE_FIELDS,
    SLOW_FAKE_CAMERA_ARGS,
    Chrome,
    LiveRun,
    Parties,
    api_client,
    assert_reconciled,
    assert_ui_shows_latest,
    db_count,
    deep_diff,
    evidence_dir,
    expected_latest_panel,
    fixed,
    frame_key,
    instant,
    parties_diffs,
    percent,
    session_ids,
    summarise,
)

MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml/outputs"
# All three frozen files: test_02 reads the bytes of each, so a missing one must be a counted
# model skip (fatal under DRA_REQUIRE_MODELS=1), not a FileNotFoundError.
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)
pytestmark = [pytest.mark.e2e, requires_models]

# The frozen baseline of the three model files (docs/evidence/2026-10-19/w3-gate/freeze_manifest.txt).
VISION_ONNX_SHA256 = "b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf"
VISION_PT_SHA256 = "196ca7b151d84e0c4a8eac87128da9dd8f22c894984a991ef611536bb523e7c7"
TELEMETRY_XGB_SHA256 = "9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07"

PROVENANCE_IDENTITY_KEYS = ["vision_obs", "telemetry_obs", "vision_frame_id", "telemetry_seq",
                            "vision_identity_source", "telemetry_identity_source", "identity_source",
                            "vision_hash_repeat_audit"]
PROVENANCE_EXPIRY_KEYS = ["vision_expired", "vision_age_s", "telemetry_expired", "telemetry_age_s"]

FLAGGED_WINDOW = 3  # the window the E1 flag test sets through the UI


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shoot(page, name: str) -> None:
    """With ``DRA_E2E_EVIDENCE_DIR`` set, leave a screenshot of the open view for the evidence
    archive (part 2b). With it unset this writes nothing."""
    out = evidence_dir()
    if out is not None:
        (out / "screenshots").mkdir(exist_ok=True)
        page.screenshot(path=str(out / "screenshots" / f"{name}.png"), full_page=True)


# ======================================================================================
# ST-LIVE-E2E-01
# ======================================================================================
@pytest.fixture(scope="class")
def run(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, SLOW_FAKE_CAMERA_ARGS)
    live = LiveRun(chrome)
    try:
        live.collect()
        yield live
    finally:
        chrome.close()


class TestStLiveE2E01:
    """The tests share one paused run. ``test_07`` flags a window and unflags it again before it
    ends, so the others see the unflagged run in any order (a test_07 that fails half way can
    leave the flag set; the failure is then already reported)."""

    def test_01_the_run_completed_and_every_request_was_a_distinct_stored_window(self, run):
        assert run.error is None, run.error
        calls = run.calls
        assert len(calls) >= 10
        assert [c.response["window_id"] for c in calls] == list(range(1, len(calls) + 1))  # contiguous
        assert len({c.request_id for c in calls}) == len(calls)  # request ids unique
        assert all(c.response["provenance"]["request_id"] == c.request_id for c in calls)
        assert all(c.attempt == "1" for c in run.tap.infer if c.sid == run.sid)  # nothing was re-sent
        assert [c.outcome for c in run.tap.infer if c.outcome != "held"] == ["ok"] * len(calls)
        assert len(run.tap.held()) == 1  # the one request the harness held to quiesce the server
        assert len(run.tap.session_posts) == 1  # one session
        # Nothing is stranded: the database has exactly the windows the browser received.
        assert db_count(run.server, "SELECT COUNT(*) FROM inference_records WHERE session_id=?", run.sid) == len(calls)
        assert db_count(run.server, "SELECT COUNT(*) FROM fault_events WHERE session_id=?", run.sid) == 0

    def test_02_contract(self, run):
        assert run.error is None, run.error
        calls = run.calls
        for call in calls:
            record, prov = call.response, call.response["provenance"]
            assert set(record) == set(RISK_UPDATE_FIELDS), sorted(set(record) ^ set(RISK_UPDATE_FIELDS))
            assert record["operation_mode"] == "LIVE_MODEL_RUNTIME"
            assert prov["provider"] == "MobileNetV3ONNX+XGBoost"
            assert prov["vision_source"] == "camera_frame"
            assert prov["telemetry_source"] == "prepared_replay"
            assert len(record["visual_top_classes"]) == 10
            assert record["visual_top_classes"][0]["label"] == "safe_driving"
            assert [c["label"] for c in record["telemetry_behavior_classes"]] == ["Safe", "Aggressive", "Distracted"]
            assert sum(c["probability"] for c in record["visual_top_classes"]) == pytest.approx(1.0, abs=1e-4)
            assert sum(c["probability"] for c in record["telemetry_behavior_classes"]) == pytest.approx(1.0, abs=1e-4)
            # D01: the availability invariant.
            four = (record["RiskScore"], record["RiskLevel"], record["DominantEvidence"], record["AlertSeverity"])
            assert record["assessment_available"] == (record["RiskScore"] is not None) == (record["SystemHealth"] != "UNAVAILABLE")
            assert all(v is not None for v in four) if record["assessment_available"] else all(v is None for v in four)
            # The frozen models produced it.
            assert prov["vision_model_sha256"] == VISION_ONNX_SHA256
            assert prov["telemetry_model_sha256"] == TELEMETRY_XGB_SHA256
            # A healthy run: both branches carried usable evidence.
            assert record["modality_freshness"] == {"vision": "fresh", "telemetry": "fresh"}
            assert record["SystemHealth"] == "FULL"
            assert record["assessment_available"] is True
        # The runtime loads two of the three frozen files and records those two. The third (the
        # PyTorch checkpoint) is not loaded and has no provenance entry; its bytes on disk are
        # checked against the baseline instead. What the server says it loaded is checked too.
        assert sha256_of(MODEL_ROOT / "vision/mobilenetv3_large_vision.onnx") == VISION_ONNX_SHA256
        assert sha256_of(MODEL_ROOT / "vision/mobilenetv3_large_vision.pt") == VISION_PT_SHA256
        assert sha256_of(MODEL_ROOT / "telemetry/xgb_telemetry.json") == TELEMETRY_XGB_SHA256
        with api_client(run.server) as client:
            info = client.get("/api/models").json()
        assert info["vision"]["sha256"] == VISION_ONNX_SHA256
        assert info["telemetry"]["sha256"] == TELEMETRY_XGB_SHA256

    def test_03_r10_on_the_wire(self, run):
        assert run.error is None, run.error
        calls = run.calls
        bodies, records = [c.body for c in calls], [c.response for c in calls]
        probe = run.probe
        # Frame identity. A browser that supports requestVideoFrameCallback must have been asked
        # for callbacks by the product; whether they FIRE decides which path the wire shows.
        if run.rvfc_supported:
            assert probe["regs"], "the product never registered a requestVideoFrameCallback"
        explicit = bool(probe["callbacks"])
        if explicit:
            for body in bodies:
                assert body["vision_frame"]["epoch"] > 0 and body["vision_frame"]["index"] >= 0
                assert body["captured_at_source"] in ("capture_time", "callback")
            assert len({b["vision_frame"]["epoch"] for b in bodies}) == 1  # one camera start
            indexes = [b["vision_frame"]["index"] for b in bodies]
            assert indexes == sorted(indexes)
            first_seen: dict = {}
            for body in bodies:  # a re-sent frame is the same tuple: same bytes, same time
                key = frame_key(body)
                first_seen.setdefault(key, body)
                assert body["image_base64"] == first_seen[key]["image_base64"]
                assert body["captured_at"] == first_seen[key]["captured_at"]
        else:  # the fallback path: no identity, the page clock
            for body in bodies:
                assert "vision_frame" not in body and body["captured_at_source"] == "client_clock"
        # Telemetry: sequence 0, 1, 2, ... one step per 2 s of monitoring.
        seqs = [b["telemetry_seq"] for b in bodies]
        assert seqs[0] == 0 and seqs == sorted(seqs)
        assert sorted(set(seqs)) == list(range(0, max(seqs) + 1)), "a telemetry sequence number was skipped"
        stamps: dict[int, str] = {}
        for body in bodies:  # the same seq carries a byte-identical time in every request
            assert body["telemetry_timestamp"] == stamps.setdefault(body["telemetry_seq"], body["telemetry_timestamp"])
        for seq in range(1, max(seqs) + 1):  # and the time is arithmetic: exactly 2000 ms per step
            step = instant(stamps[seq]) - instant(stamps[seq - 1])
            assert step.total_seconds() == 2.0, (seq, step)
        sent_at: dict[int, float] = {}
        for call in calls:
            sent_at.setdefault(call.body["telemetry_seq"], call.at)
        spacing = (sent_at[max(seqs)] - sent_at[0]) / max(seqs)
        assert 1.8 <= spacing <= 2.3, f"a telemetry sample every {spacing:.2f} s of wall clock"
        # What the server made of it.
        for index, (body, record) in enumerate(zip(bodies, records)):
            prov = record["provenance"]
            previous = bodies[index - 1] if index else None
            new_telemetry = previous is None or body["telemetry_seq"] != previous["telemetry_seq"]
            new_vision = previous is None or frame_key(body) != frame_key(previous)
            assert prov["telemetry_obs"] == ("new" if new_telemetry else "repeat"), (index, prov["telemetry_obs"])
            assert prov["vision_obs"] == ("new" if new_vision else "repeat"), (index, prov["vision_obs"])
            for key in PROVENANCE_IDENTITY_KEYS + PROVENANCE_EXPIRY_KEYS:
                assert key in prov, key
            assert prov["telemetry_seq"] == body["telemetry_seq"]
            assert prov["telemetry_identity_source"] == "explicit"
            if explicit:
                assert prov["vision_frame_id"] == f"{body['vision_frame']['epoch']}:{body['vision_frame']['index']}"
                assert prov["vision_identity_source"] == prov["identity_source"] == "explicit"
            else:
                assert prov["vision_frame_id"] is None and prov["vision_identity_source"] == prov["identity_source"] == "fallback"
            # The canonical acquisition time: the one registered when the observation was first seen.
            assert instant(prov["telemetry_timestamp"]) == instant(stamps[body["telemetry_seq"]])
            first = next(b for b in bodies if frame_key(b) == frame_key(body))
            assert instant(prov["captured_at"]) == instant(first["captured_at"])
            assert prov["captured_at_source"] == body["captured_at_source"]
            assert prov["vision_expired"] is False and prov["telemetry_expired"] is False
            assert 0 <= prov["vision_age_s"] < 3 and 0 <= prov["telemetry_age_s"] < 3
            # A repeat is the observation it repeats, not a fresh inference of it.
            if previous is not None and not new_vision:
                assert record["P_distraction"] == records[index - 1]["P_distraction"]
                assert record["visual_top_classes"] == records[index - 1]["visual_top_classes"]
            if previous is not None and not new_telemetry:
                assert record["P_telemetry_anomaly"] == records[index - 1]["P_telemetry_anomaly"]
                assert record["telemetry_behavior_classes"] == records[index - 1]["telemetry_behavior_classes"]
        # Both verdicts occur on both branches.
        assert {r["provenance"]["telemetry_obs"] for r in records} == {"new", "repeat"}
        assert {r["provenance"]["vision_obs"] for r in records} == {"new", "repeat"}

    def test_04_five_homes_agree_on_every_field_of_every_window(self, run):
        """Five homes of each window: (1) the ``/infer`` body the browser received, (2) the database
        row, (3) ``GET /windows``, (4) the JSON export, (5) the CSV export. All 21 fields of the
        RiskUpdate contract, ``provenance`` included key by key, are compared; floats exactly.

        The CSV rule. Every contract field has a CSV column, so every field is compared: a
        scalar by the exporter's own encoding (None is an empty cell, a bool is ``true`` /
        ``false``, a number is its repr), the six structured fields (provenance,
        modality_freshness, visual_top_classes, telemetry_behavior_classes,
        telemetry_feature_contributions, telemetry_features) as the JSON document in the cell. Seven
        more columns the exporter lifts out of provenance (request_id, vision_source,
        telemetry_source, the two model hashes, P_distraction_raw, P_telemetry_raw) are compared
        with the provenance value. The two ``payload_unreadable*`` columns must be empty. Nothing
        is skipped, because nothing here cannot be compared."""
        assert run.error is None, run.error
        parties = Parties(run)
        count = len(run.calls)
        ids = list(range(1, count + 1))
        # The same windows everywhere.
        assert sorted(parties.infer) == sorted(parties.db) == sorted(parties.windows) == ids
        assert sorted(parties.export_json) == sorted(parties.export_csv) == ids
        assert parties.session["total_windows"] == count
        assert parties.export_json_top == {"session_id": run.sid}
        # Every field, every window, every home (CSV: all 21 fields + the seven provenance columns).
        diffs = parties_diffs(parties, parties.infer)
        assert not diffs, f"{len(diffs)} differences, first {diffs[:12]}"
        assert all(r["flagged"] is False for r in parties.infer.values())
        # GET /risk/latest is the last window, whole.
        assert parties.latest["window_id"] == count
        assert deep_diff(parties.latest, parties.infer[count]) == []
        # The provenance of every window really does carry what the exports are being checked for.
        for window_id, record in parties.export_json.items():
            for key in PROVENANCE_IDENTITY_KEYS + PROVENANCE_EXPIRY_KEYS:
                assert key in record["provenance"], (window_id, key)

    def test_05_the_latest_panel_shows_risk_latest(self, run):
        """IT-UI-01: what the Live Monitor displayed when the run went quiet, read from the DOM,
        against ``GET /risk/latest`` in the dashboard's display format."""
        assert run.error is None, run.error
        parties = Parties(run)
        latest = parties.latest
        assert latest["window_id"] == len(run.calls)
        expected = expected_latest_panel(latest, run.sid, parties.session["total_windows"])
        shown = dict(run.ui_latest)
        shown["strip"] = {k: v for k, v in shown["strip"].items() if k in expected["strip"]}
        diffs = deep_diff(shown, expected)
        assert not diffs, f"the Live Monitor does not show GET /risk/latest: {diffs}"

    def test_06_the_five_views_open_and_show_what_the_backend_recorded(self, run):
        assert run.error is None, run.error
        chrome, page = run.chrome, run.page
        records = {c.response["window_id"]: c.response for c in run.calls}
        count = len(records)
        wanted = records[FLAGGED_WINDOW]

        def open_view(name):
            page.get_by_role("button", name=name, exact=True).click()
            chrome.wait(300)

        shoot(page, "01-live-monitor")  # the view the run ended on

        # Signal Inspector
        open_view("Signal Inspector")
        buttons = page.locator(".window-list button")
        assert buttons.count() == count
        assert buttons.first.inner_text().strip() == f"Window {count}"
        page.get_by_role("button", name=f"Window {FLAGGED_WINDOW}", exact=True).click()
        chrome.wait(200)
        stats = page.evaluate(r"""() => Object.fromEntries([...document.querySelectorAll('.stat-list > div')]
            .map((d) => [d.querySelector('span')?.textContent.trim(), d.lastElementChild?.textContent.trim()]))""")
        assert stats["RiskScore"] == f"{fixed(wanted['RiskScore'], 1)} / 100"
        assert stats["RiskLevel"] == wanted["RiskLevel"]
        assert stats["Evidence Type"] == wanted["DominantEvidence"]
        assert stats["P_distraction"] == percent(wanted["P_distraction"])
        assert stats["Telemetry non-safe risk"] == percent(wanted["P_telemetry_anomaly"])
        assert stats["Vision freshness"] == stats["Telemetry freshness"] == "fresh"
        assert stats["Latency"] == f"{wanted['latency_ms']} ms"
        assert stats["Flag"] == "None"
        bars = page.evaluate(r"""() => [...document.querySelectorAll('.bar-row')].map((r) => [r.querySelector('span').textContent.trim(), r.querySelector('strong').textContent.trim()])""")
        assert bars == [[c["label"], fixed(c["probability"], 2)] for c in wanted["visual_top_classes"]]
        shoot(page, "02-signal-inspector")

        # Risk Trends: one row per window, newest first.
        open_view("Risk Trends")
        assert page.locator(".recharts-wrapper svg").count() >= 1
        rows = page.evaluate(r"""() => [...document.querySelectorAll('table tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent.trim()))""")
        assert len(rows) == count
        for row in rows:
            record = records[int(row[0])]
            assert row[2] == f"{fixed(record['RiskScore'], 1)} / 100"
            assert row[3] == record["RiskLevel"] and row[4] == record["AlertSeverity"]
            assert row[5] == record["DominantEvidence"] and row[6] == "None"
        assert [int(r[0]) for r in rows] == list(range(count, 0, -1))
        shoot(page, "03-risk-trends")

        # Explanation: the selected window's numbers.
        open_view("Explanation")
        summary = page.evaluate(r"""() => Object.fromEntries([...document.querySelectorAll('.summary-metric-grid > div')]
            .map((d) => [d.querySelector('span')?.textContent.trim(), d.lastElementChild?.textContent.trim()]))""")
        assert summary["RiskScore"] == f"{fixed(wanted['RiskScore'], 1)} / 100"
        assert summary["P_distraction"] == fixed(wanted["P_distraction"], 2)
        assert summary["Telemetry Non-Safe Risk"] == fixed(wanted["P_telemetry_anomaly"], 2)
        assert summary["RiskLevel"] == wanted["RiskLevel"]
        shoot(page, "04-explanation")

        # Configuration: both exports download, and are the server's exports of this session.
        open_view("Configuration")
        shoot(page, "05-configuration")
        with api_client(run.server) as client:
            served_json = client.get(f"/api/sessions/{run.sid}/export", params={"format": "json"}).content
            served_csv = client.get(f"/api/sessions/{run.sid}/export", params={"format": "csv"}).content
        for label, served in (("Export JSON", served_json), ("Export CSV", served_csv)):
            with page.expect_download() as download:
                page.get_by_role("button", name=label, exact=True).click()
            assert Path(download.value.path()).read_bytes() == served, label
        out = evidence_dir()
        if out is not None:  # the bytes the page downloaded (just proven equal to the server's export)
            (out / "session-export.json").write_bytes(served_json)
            (out / "session-export.csv").write_bytes(served_csv)

        # Live Monitor again.
        open_view("Live Monitor")
        assert page.locator(".session-strip").inner_text().count(run.sid) == 1
        assert chrome.console_errors == [] and chrome.page_errors == []

    def test_07_a_flag_set_in_the_ui_reaches_the_database_the_api_and_both_exports(self, run):
        assert run.error is None, run.error
        chrome, page = run.chrome, run.page
        before = {c.response["window_id"]: c.response for c in run.calls}
        page.get_by_role("button", name="Signal Inspector", exact=True).click()
        page.get_by_role("button", name=f"Window {FLAGGED_WINDOW}", exact=True).click()
        page.get_by_role("button", name="Flag", exact=True).click()
        chrome.wait_until(lambda: page.get_by_role("button", name="Unflag", exact=True).count() == 1,
                          "the Inspector to show window 3 as flagged", 10, tolerate_stop_panel=True)
        # The UI used the PATCH endpoint, on this session and window.
        assert ("PATCH", f"/api/sessions/{run.sid}/windows/{FLAGGED_WINDOW}/flag?flagged=true") in chrome.api_requests
        # Everywhere, the flagged window is flagged and nothing else about any window changed.
        expected = {w: {**r, "flagged": w == FLAGGED_WINDOW} for w, r in before.items()}
        parties = Parties(run)
        diffs = parties_diffs(parties, expected)
        assert not diffs, f"{len(diffs)} differences, first {diffs[:12]}"
        assert parties.export_json[FLAGGED_WINDOW]["flagged"] is True
        assert parties.export_csv[FLAGGED_WINDOW]["flagged"] == "true"
        assert sorted(w for w, r in parties.export_json.items() if r["flagged"]) == [FLAGGED_WINDOW]
        assert parties.latest["window_id"] == len(before) and parties.latest["flagged"] is False
        # The dashboard shows it, too.
        page.get_by_role("button", name="Risk Trends", exact=True).click()
        chrome.wait(300)
        flagged_rows = page.evaluate(r"""() => [...document.querySelectorAll('table tbody tr')]
            .filter((tr) => tr.children[6].textContent.trim() === 'flagged').map((tr) => tr.children[0].textContent.trim())""")
        assert flagged_rows == [str(FLAGGED_WINDOW)]

        # Unflag through the UI: every home follows, and the run is back to the unflagged state
        # test_04..06 read, so the class does not depend on test_07 running after them.
        page.get_by_role("button", name="Signal Inspector", exact=True).click()
        page.get_by_role("button", name=f"Window {FLAGGED_WINDOW}", exact=True).click()
        page.get_by_role("button", name="Unflag", exact=True).click()
        chrome.wait_until(lambda: page.get_by_role("button", name="Flag", exact=True).count() == 1,
                          "the Inspector to show window 3 as unflagged", 10, tolerate_stop_panel=True)
        assert ("PATCH", f"/api/sessions/{run.sid}/windows/{FLAGGED_WINDOW}/flag?flagged=false") in chrome.api_requests
        diffs = parties_diffs(Parties(run), before)
        assert not diffs, f"after Unflag, {len(diffs)} differences, first {diffs[:12]}"

    def test_08_no_console_errors_and_nothing_failed_on_the_server(self, run):
        assert run.error is None, run.error
        assert run.chrome.console_errors == [] and run.chrome.page_errors == []
        assert db_count(run.server, "SELECT COUNT(*) FROM fault_events WHERE session_id=?", run.sid) == 0


# ======================================================================================
# E2: the stop panel, by real clicks
# ======================================================================================
def test_e2_transport_faults_stop_the_loop_and_retry_resumes_the_same_session(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)
    try:
        sessions_before = session_ids(e2e_server)
        chrome.tap.abort_infer = 3  # the first logical request: three deliveries, all lost in transit
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: chrome.stop_panel().count() == 1, "the stop panel after 3 failed deliveries", 60,
                          tolerate_stop_panel=True)
        sid = chrome.tap.session_posts[0].response["id"]
        panel = chrome.stop_panel().inner_text()
        first = chrome.tap.infer[0]
        assert "Monitoring stopped: The backend cannot be reached" in panel
        assert "Category: transport" in panel
        assert f"Request id: {first.request_id}" in panel
        assert "Deliveries: 3 of 3" in panel
        assert "Retry re-sends this same request to the same session." in panel
        # Three deliveries of ONE request: numbered 1, 2, 3, byte-identical, none of them reached the server.
        assert [c.attempt for c in chrome.tap.infer] == ["1", "2", "3"]
        assert len({c.raw for c in chrome.tap.infer}) == 1
        assert [c.outcome for c in chrome.tap.infer] == ["aborted"] * 3
        assert db_count(e2e_server, "SELECT COUNT(*) FROM inference_records WHERE session_id=?", sid) == 0

        chrome.tap.abort_infer = 0  # the network is back
        chrome.stop_panel().get_by_role("button", name="Retry", exact=True).click()
        # The panel stays up while Retry is in flight ("Retrying..."), so it is not a failure to see it here.
        # A Retry that starts a NEW session ends the wait at once: this session would never get its windows.
        chrome.wait_until(lambda: len(chrome.tap.answered(sid)) >= 4 or len(chrome.tap.session_posts) > 1,
                          "the retried window and three more", 60, tolerate_stop_panel=True)
        assert len(chrome.tap.session_posts) == 1, "Retry created a new session instead of resuming this one"

        retried = chrome.tap.infer[3]
        assert retried.attempt == "4", "a manual retry continues the delivery count (1, 2, 3 automatic; 4 manual)"
        assert retried.raw == first.raw and retried.request_id == first.request_id  # the frozen request
        assert retried.status == 201 and retried.response["window_id"] == 1
        # Same session: no new one was created, and the request was stored exactly once.
        assert len(chrome.tap.session_posts) == 1
        assert session_ids(e2e_server) - sessions_before == {sid}
        assert db_count(e2e_server, "SELECT COUNT(*) FROM inference_records WHERE session_id=? AND request_id=?",
                        sid, first.request_id) == 1
        # The loop runs again: more windows in the same session, the panel is gone.
        later = chrome.tap.answered(sid)[1:]
        assert [c.response["window_id"] for c in chrome.tap.answered(sid)][:4] == [1, 2, 3, 4]
        assert all(c.attempt == "1" and c.request_id != first.request_id for c in later)
        assert chrome.stop_panel().count() == 0
        assert chrome.page.get_by_text("Monitoring active", exact=True).count() == 1
        assert chrome.page.locator(".session-strip").inner_text().count(sid) == 1
        assert db_count(e2e_server, "SELECT COUNT(*) FROM fault_events WHERE session_id=?", sid) == 0
    finally:
        chrome.close()


def test_e2_a_failed_new_session_makes_retry_create_a_new_session(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)
    try:
        sessions_before = session_ids(e2e_server)
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: len(chrome.tap.answered()) >= 3, "three windows of the first session", 60)
        first = chrome.tap.session_posts[0].response["id"]

        chrome.tap.abort_session_posts = {2}  # the next POST /api/sessions fails; the one after works
        chrome.top_button("New Session").click()
        chrome.wait_until(lambda: chrome.stop_panel().count() == 1, "the stop panel after a failed New Session", 30,
                          tolerate_stop_panel=True)
        panel = chrome.stop_panel().inner_text()
        assert "Failed during setup, before any request was sent" in panel
        assert "Retry repeats the setup: the model check, then a NEW session." in panel
        assert [c.outcome for c in chrome.tap.session_posts] == ["ok", "aborted"]
        chrome.wait(1000)  # the first session's last in-flight request, if any, has landed by now
        settled = db_count(e2e_server, "SELECT COUNT(*) FROM inference_records WHERE session_id=?", first)

        chrome.stop_panel().get_by_role("button", name="Retry", exact=True).click()
        chrome.wait_until(lambda: len(chrome.tap.session_posts) == 3 and chrome.tap.session_posts[2].outcome == "ok",
                          "the retry to create a session", 30, tolerate_stop_panel=True)
        second = chrome.tap.session_posts[2].response["id"]
        chrome.wait_until(lambda: len(chrome.tap.answered(second)) >= 3, "three windows of the new session", 60,
                          tolerate_stop_panel=True)

        assert second != first
        assert session_ids(e2e_server) - sessions_before == {first, second}
        assert [c.response["window_id"] for c in chrome.tap.answered(second)][:3] == [1, 2, 3]  # a fresh numbering
        assert chrome.stop_panel().count() == 0
        assert chrome.page.locator(".session-strip").inner_text().count(second) == 1
        # The abandoned session got nothing more after the failed New Session.
        assert db_count(e2e_server, "SELECT COUNT(*) FROM inference_records WHERE session_id=?", first) == settled
    finally:
        chrome.close()


def test_e2_an_unexpected_camera_loss_and_stop_camera_read_differently_and_neither_stops_the_loop(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)
    page = chrome.page

    def camera_line() -> str:
        return page.locator(".runtime-details span", has_text="Camera:").first.inner_text().strip()

    def imageless_answered(sid, after_number):
        return [c for c in chrome.tap.answered(sid) if c.number > after_number and c.body["image_base64"] is None]

    try:
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: len(chrome.tap.answered()) >= 5, "five windows with a picture", 60)
        sid = chrome.tap.session_posts[0].response["id"]
        assert all(c.body["image_base64"] for c in chrome.tap.answered(sid))
        first_epoch = (chrome.tap.infer[-1].body.get("vision_frame") or {}).get("epoch")  # None on the fallback path

        # (1) The device goes away: a synthetic `ended` on the capture track
        #     (MediaStreamTrack.stop() never fires `ended`, so the event is dispatched by hand).
        mark = chrome.tap.infer[-1].number
        page.evaluate("() => window.__e2e.streams.at(-1).getVideoTracks()[0].dispatchEvent(new Event('ended'))")
        chrome.wait_until(lambda: len(imageless_answered(sid, mark)) >= 5, "five windows after the camera was lost", 60)
        lost_line = camera_line()
        lost_notice = page.locator(".runtime-warning", has_text="No camera image is being sent").inner_text()
        assert re.fullmatch(r"Camera: error · disconnected at .+", lost_line), lost_line
        assert "(the camera was disconnected)" in lost_notice
        after_loss = imageless_answered(sid, mark)
        for call in after_loss:  # the loop carried on, with telemetry only (R5)
            assert call.body["telemetry_features"] is not None and "vision_frame" not in call.body
            assert call.response["modality_freshness"] == {"vision": "missing", "telemetry": "fresh"}
            assert call.response["provenance"]["vision_source"] == "missing"
        assert chrome.stop_panel().count() == 0

        # (2) The person starts the camera again (a new epoch), then presses Stop Camera.
        mark = chrome.tap.infer[-1].number
        page.get_by_role("button", name="Start Camera", exact=True).click()
        chrome.wait_until(lambda: any(c.number > mark and c.body["image_base64"] for c in chrome.tap.answered(sid)),
                          "pictures to flow again", 30)
        resumed = next(c for c in chrome.tap.answered(sid) if c.number > mark and c.body["image_base64"])
        if first_epoch is not None:
            assert resumed.body["vision_frame"]["epoch"] > first_epoch  # a restart is a new epoch
        assert resumed.response["modality_freshness"]["vision"] == "fresh"
        mark = chrome.tap.infer[-1].number
        page.get_by_role("button", name="Stop Camera", exact=True).click()
        chrome.wait_until(lambda: len(imageless_answered(sid, mark)) >= 5, "five windows after Stop Camera", 60)
        stopped_line = camera_line()
        stopped_notice = page.locator(".runtime-warning", has_text="No camera image is being sent").inner_text()
        assert re.fullmatch(r"Camera: idle · stopped by you at .+", stopped_line), stopped_line
        assert "(the camera was stopped)" in stopped_notice
        assert chrome.stop_panel().count() == 0

        # The two situations never read alike, in either place the camera is mentioned.
        assert re.sub(r" at .+", "", lost_line) != re.sub(r" at .+", "", stopped_line)
        assert lost_notice != stopped_notice
    finally:
        chrome.close()


# ======================================================================================
# E3: requestVideoFrameCallback on the fake camera - recorded, not judged
# ======================================================================================
def test_e3_rvfc_behaviour_on_the_fake_camera_is_recorded(pw, e2e_server, tmp_path):
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)
    try:
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: len(chrome.tap.answered()) >= 60, "60 windows", 120)
        sid = chrome.tap.session_posts[0].response["id"]
        probe = chrome.probe()
        timings = chrome.page.evaluate("() => window.__draLiveTimings")  # Task 10 part 1's read-only accessor
        supported = probe["supported"]
        calls = chrome.tap.answered(sid)
        bodies = [c.body for c in calls]

        callbacks = probe["callbacks"]
        at = [c["at"] for c in callbacks]
        span_s = (at[-1] - at[0]) / 1000 if len(at) > 1 else 0.0
        sent_age_ms = [(c.at - instant(c.body["captured_at"]).timestamp()) * 1000 for c in calls]
        measurement = {
            "chromium": chrome.version,
            "camera": "--use-fake-device-for-media-stream (default pattern generator)",
            "requests_answered": len(calls),
            "rvfc": {
                "supported": supported,
                "registrations": len(probe["regs"]),
                "registered_on_a_video_in_the_document": [r["connected"] for r in probe["regs"]][:3],
                "callbacks": len(callbacks),
                "callbacks_on_a_video_in_the_document": sum(1 for c in callbacks if c["connected"]),
                "span_s": round(span_s, 3),
                "rate_hz": round((len(at) - 1) / span_s, 2) if span_s else None,
                "presented_frames_first_last": [callbacks[0]["presentedFrames"], callbacks[-1]["presentedFrames"]] if callbacks else None,
                "captureTime_present": sum(1 for c in callbacks if c["hasCaptureTime"]),
                "captureTime_absent": sum(1 for c in callbacks if not c["hasCaptureTime"]),
                "capture_to_callback_lag_ms": summarise([c["lagMs"] for c in callbacks if c["lagMs"] is not None]),
            },
            "captured_at_source_in_requests": dict(Counter(b.get("captured_at_source") for b in bodies)),
            "requests_with_vision_frame": sum(1 for b in bodies if "vision_frame" in b),
            "vision_obs_in_responses": dict(Counter(c.response["provenance"]["vision_obs"] for c in calls)),
            "per_callback_ms": summarise([c["ms"] for c in callbacks]),
            "drawImage_ms": summarise(probe["draw"]),
            "toDataURL_ms": summarise(probe["encode"]),
            "image_base64_chars": summarise([float(len(b["image_base64"])) for b in bodies]),
            "frame_age_when_request_reached_the_tap_ms": summarise(sent_age_ms),
            "loop_timing_buffer_ms": {  # the loop's own per-window segments (ai/src/liveTiming.ts)
                "windows": len(timings),
                "capture_to_send": summarise([t["captureToSendMs"] for t in timings]),
                "network_including_server": summarise([t["networkMs"] for t in timings]),
                "render": summarise([t["renderMs"] for t in timings if t["renderMs"] is not None]),
            },
        }
        line = json.dumps(measurement, sort_keys=True)
        print("E3-MEASUREMENT " + line)
        (tmp_path / "rvfc-measurement.json").write_text(json.dumps(measurement, indent=2, sort_keys=True))
        out = os.environ.get("DRA_E2E_MEASUREMENTS_DIR")
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
            (Path(out) / "rvfc-measurement.json").write_text(json.dumps(measurement, indent=2, sort_keys=True))
        evidence = evidence_dir()
        if evidence is not None:  # the G-W4-A archive (part 2b)
            (evidence / "rvfc-measurement.json").write_text(json.dumps(measurement, indent=2, sort_keys=True))

        # Only structure is asserted, never a number: the run was healthy, the probe saw the
        # product ask for callbacks where the browser has them, and the wire shows the matching path.
        assert len(calls) >= 60
        if supported:
            assert probe["regs"], "the product never registered a requestVideoFrameCallback"
        if callbacks:
            assert all("vision_frame" in b for b in bodies)
        else:
            assert all("vision_frame" not in b and b["captured_at_source"] == "client_clock" for b in bodies)

        # Part 2b (carried over from 2a): the five-way reconciliation on the DEFAULT 20 fps camera,
        # where every vision observation is NEW (E1 reconciles on the 5 fps camera, where REPEATs
        # occur). Nothing above changed. First Pause with the server held quiet, so that the
        # database holds exactly what the browser received; then every window the run received is
        # reconciled across the five homes, GET /risk/latest is the last window, and the Live
        # Monitor shows it. The measurement above was taken before this and is not affected by it.
        live = LiveRun(chrome)
        live.sid = sid
        live.settle()
        parties = assert_reconciled(live)
        assert_ui_shows_latest(live, parties)
    finally:
        chrome.close()
