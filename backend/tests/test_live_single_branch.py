"""Task 10 part 2b: the single-branch system tests ST-BRANCH-*.

A single-branch run is a degradation path the system has to support, not a new feature. The
browser drives the real dashboard exactly as in ``test_live_e2e.py`` (one uvicorn serving the API
and the freshly built ``dist/``, Chromium with a fake camera, everything recorded from the outside);
no product code is touched and nothing is deleted. What the tests control from the test harness
(not from the product): the camera permission, Stop / Start Camera clicks, the Vision Weight slider
and, for ST-BRANCH-V only, a Playwright route that rewrites the ``/infer`` request body.

    ST-BRANCH-T-SMOKE        camera running, then Stop Camera: telemetry only, score = 100 x frozen P_t
    ST-BRANCH-T-CONTINUITY   no camera from the very first request, one full replay lap and a wrap
    ST-BRANCH-V              vision only (telemetry removed in the route), 5 fps camera, Stop / Start Camera
    ST-BRANCH-ZERO           Vision Weight 1.00 (Telemetry 0.00), then Stop Camera: nothing may be scored

Common assertions (every test, over the single-branch and unavailable windows of its run):
  * ``DominantEvidence == ("Partial evidence" if assessment_available else None)`` - the current rule
    checks ``SystemHealth != FULL`` before the Low case (``fusion.determine_dominant_evidence``), so
    a low-risk single-branch window is still "Partial evidence";
  * an unavailable window has all four risk fields null, ``SystemHealth = UNAVAILABLE`` and the D01
    invariant holds; an available single-branch window is DEGRADED;
  * five-way reconciliation of EVERY window of the run (``e2e_support.assert_reconciled``):
    ``/infer`` answer = database = ``GET /windows`` = JSON export = CSV export, all 21 fields, floats
    exactly; ``GET /risk/latest`` is the last window; the Live Monitor shows it (the IT-UI-01 oracle).
    The server is made quiet first (the loop's next request is held), then everything is read;
  * a window's replay row (T-SMOKE, T-CONTINUITY, ZERO; V has no telemetry to look up) is found by
    looking its ``telemetry_features`` up in the frozen table (never by counting time) and must equal
    ``telemetry_seq % 25``;
  * no fault: ``fault_events`` is empty, the stop panel never showed, no console or page error.
The two-branch windows before a Stop Camera (T-SMOKE, ZERO) are outside the first two points; they
take part in the reconciliation only.

Expected values are literals in this file or in the frozen fixture ``fixtures/telemetry_pt_by_row.json``
(made by ``fixtures/make_telemetry_pt_fixture.py``, bound to the SHA-256 of ``xgb_telemetry.json``).
The tests never call a model, a simulator or a product function to compute an expectation; the only
thing computed is decimal half-up rounding, by the independent ``e2e_support.half_up``.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from e2e_support import (
    FAKE_CAMERA_ARGS,
    SLOW_FAKE_CAMERA_ARGS,
    Chrome,
    LiveRun,
    assert_reconciled,
    assert_ui_shows_latest,
    db_count,
    frame_key,
    half_up_float,
    instant,
)

MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml/outputs"
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)
pytestmark = [pytest.mark.e2e, requires_models]

FIXTURE = Path(__file__).parent / "fixtures" / "telemetry_pt_by_row.json"
REPLAY_CSV = Path(__file__).resolve().parents[2] / "ai/prototype-data/prepared_sessions/session_001/telemetry.csv"
# The frozen telemetry model (docs/evidence/2026-10-19/w3-gate/freeze_manifest.txt).
TELEMETRY_XGB_SHA256 = "9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07"
FEATURES = ("speed_kmph", "accel_x", "accel_y", "brake_pressure", "steering_angle", "throttle",
            "lane_deviation", "headway_distance")
REPLAY_ROWS = 25
ROWS_WITHOUT_TELEMETRY = (13, 16)  # CSV window_id 14 and 17: telemetry_available = 0
RISK_FIELDS = ("RiskScore", "RiskLevel", "DominantEvidence", "AlertSeverity")
MISSING_VISION = {"vision": "missing", "telemetry": "fresh"}


# --------------------------------------------------------------------------------------
# The frozen per-row table
# --------------------------------------------------------------------------------------
class Frozen:
    def __init__(self, table: dict):
        self.table = table
        self.rows = table["rows"]
        self._row_of = {tuple(float(r["telemetry_features"][k]) for k in FEATURES): r["row"]
                        for r in self.rows if r["telemetry_features"] is not None}

    def verify(self) -> "Frozen":
        """Fail - first, and by name - if this fixture does not belong to THIS model and THIS replay
        file. A test calls it before it compares anything with the table, so a mismatch is reported
        as a mismatch of fixture and model, not as 23 unexplained differences in probabilities."""
        table = self.table
        model = hashlib.sha256((MODEL_ROOT / "telemetry/xgb_telemetry.json").read_bytes()).hexdigest()
        assert table["telemetry_model_sha256"] == model, (
            f"the frozen fixture does not match the model: {FIXTURE.name} was made for xgb_telemetry.json "
            f"{table['telemetry_model_sha256'][:8]}, the file on disk is {model[:8]}. Regenerate it with "
            f"fixtures/make_telemetry_pt_fixture.py only as part of a deliberate model change.")
        assert model == TELEMETRY_XGB_SHA256, f"xgb_telemetry.json is {model[:8]}, the frozen baseline is {TELEMETRY_XGB_SHA256[:8]}"
        replay = hashlib.sha256(REPLAY_CSV.read_bytes()).hexdigest()
        assert table["replay_csv_sha256"] == replay, (
            "the frozen fixture does not match the replay CSV: the rows the front end sends changed")
        assert [r["row"] for r in self.rows] == list(range(REPLAY_ROWS))
        assert [r["row"] for r in self.rows if r["P_telemetry_anomaly"] is None] == list(ROWS_WITHOUT_TELEMETRY)
        return self

    def row_of(self, features: dict | None) -> int | None:
        """The replay row whose eight features these are, or None (no such row / no features)."""
        if features is None:
            return None
        return self._row_of.get(tuple(float(features[k]) for k in FEATURES))

    def pt(self, row: int) -> float:
        return self.rows[row]["P_telemetry_anomaly"]

    def classes(self, row: int) -> list[dict]:
        return [{"label": label, "probability": p} for label, p in self.rows[row]["behavior_classes"].items()]


@pytest.fixture(scope="module")
def frozen():
    """The frozen per-row table, loaded; ``Frozen.verify()`` checks it against the model."""
    return Frozen(json.loads(FIXTURE.read_text()))


# --------------------------------------------------------------------------------------
# Oracles (literals and independent rounding only)
# --------------------------------------------------------------------------------------
def score_of(probability: float) -> float:
    """``round_half_up(100 x P, 1)`` on the stored, unrounded probability."""
    return half_up_float(100 * probability, 1)


def level_of(score: float) -> str:
    return "Low" if score < 30 else ("Medium" if score < 60 else "High")


def common_problems(record: dict) -> list[str]:
    """The common assertions for ONE single-branch or unavailable window."""
    wid, available = record["window_id"], record["assessment_available"]
    health = record["SystemHealth"]
    out = []
    if record["DominantEvidence"] != ("Partial evidence" if available else None):
        out.append(f"window {wid}: DominantEvidence {record['DominantEvidence']!r} with assessment_available={available}")
    if available != (record["RiskScore"] is not None) or available != (health != "UNAVAILABLE"):
        out.append(f"window {wid}: D01 broken: assessment_available={available}, RiskScore={record['RiskScore']!r}, SystemHealth={health}")
    if available:
        if any(record[k] is None for k in RISK_FIELDS):
            out.append(f"window {wid}: an available window with a null risk field")
        if health != "DEGRADED":
            out.append(f"window {wid}: a single-branch window is {health}, not DEGRADED")
    else:
        if any(record[k] is not None for k in RISK_FIELDS):
            out.append(f"window {wid}: an unavailable window carries {[record[k] for k in RISK_FIELDS]}")
        if health != "UNAVAILABLE":
            out.append(f"window {wid}: an unavailable window is {health}")
    return out


def row_problems(frozen: Frozen, record: dict, seq: int) -> list[str]:
    """The window's replay row, looked up from its OWN ``telemetry_features``, against ``seq % 25``."""
    wid, expected_row = record["window_id"], seq % REPLAY_ROWS
    if expected_row in ROWS_WITHOUT_TELEMETRY:
        return [] if record["telemetry_features"] is None else [f"window {wid}: row {expected_row} has no telemetry but the record carries features"]
    row = frozen.row_of(record["telemetry_features"])
    if row is None:
        return [f"window {wid}: its telemetry_features are not any row of the frozen table"]
    if row != expected_row:
        return [f"window {wid}: its features are replay row {row}, but telemetry_seq {seq} is row {expected_row}"]
    return []


def assert_clean_run(live: LiveRun) -> None:
    """No fault anywhere: the stop panel never showed, nothing in fault_events, no browser error."""
    assert live.error is None, live.error
    assert live.chrome.stop_panel().count() == 0
    assert db_count(live.server, "SELECT COUNT(*) FROM fault_events WHERE session_id=?", live.sid) == 0
    assert live.chrome.console_errors == [] and live.chrome.page_errors == []
    calls = [c for c in live.tap.infer if c.sid == live.sid]
    assert all(c.attempt == "1" for c in calls), "a request was delivered more than once"  # D02: nothing was re-sent
    assert [c.outcome for c in calls if c.outcome != "held"] == ["ok"] * len(live.calls)
    assert len(live.tap.held()) == 1  # the one request the harness held to make the server quiet
    assert len(live.tap.session_posts) == 1
    ids = [c.response["window_id"] for c in live.calls]
    assert ids == list(range(1, len(ids) + 1)), "window ids are not 1..N without gaps"
    assert len({c.request_id for c in live.calls}) == len(ids), "a request id was stored twice"


def imageless(calls):
    """The answered requests that, as the server received them, carried no camera picture."""
    return [c for c in calls if c.sent_body["image_base64"] is None]


def common_and_reconciliation(live: LiveRun, scope) -> None:
    """The tail every ST-BRANCH test shares: the common assertions over ``scope`` (calls), then the
    five-way reconciliation of every window, ``/risk/latest`` and the Live Monitor."""
    assert live.error is None, live.error
    problems = [p for call in scope for p in common_problems(call.response)]
    assert not problems, f"{len(problems)} problems, first {problems[:8]}"
    parties = assert_reconciled(live)
    assert_ui_shows_latest(live, parties)
    assert_clean_run(live)


def stop_camera(live: LiveRun) -> int:
    """Click Stop Camera; returns the number of the last request sent before the click."""
    mark = live.tap.infer[-1].number
    live.page.get_by_role("button", name="Stop Camera", exact=True).click()
    return mark


def start_camera(live: LiveRun) -> int:
    mark = live.tap.infer[-1].number
    live.page.get_by_role("button", name="Start Camera", exact=True).click()
    return mark


def cursor_positions(calls) -> list[int]:
    """The telemetry cursor position (``telemetry_seq``) of every request, in order. A request that
    carries telemetry says it. A request on a replay row with NO telemetry (13, 16) carries no
    ``telemetry_seq`` by contract (the front end omits it, or the server answers 422), so its
    position is derived: the first such request after a request with seq s is at s + 1 (the cursor
    stepped onto the empty row) and every further one stays there. ``test_02`` verifies the result:
    it must be exactly the positions whose ``seq % 25`` is an empty row."""
    out: list[int] = []
    last: int | None = None
    on_empty_row = False
    for call in calls:
        seq = call.sent_body.get("telemetry_seq")
        if seq is not None:
            last, on_empty_row = seq, False
        elif last is None:
            raise AssertionError("the first request carries no telemetry_seq")
        elif not on_empty_row:
            last, on_empty_row = last + 1, True
        out.append(last)
    return out


# ======================================================================================
# ST-BRANCH-T-SMOKE
# ======================================================================================
@pytest.fixture(scope="class")
def smoke(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)  # the default 20 fps camera
    live = LiveRun(chrome)

    def drive():
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: len(live.tap.answered_with_image()) >= 3, "three windows that carry a picture", 60)
        live.stop_number = stop_camera(live)

        def after_stop():
            return [c for c in imageless(live.tap.answered()) if c.number > live.stop_number]

        def enough():
            seqs = {c.sent_body["telemetry_seq"] for c in after_stop()}
            return len(after_stop()) >= 5 and len(seqs) >= 4 and max(seqs) >= 3

        chrome.wait_until(enough, "five picture-less windows after Stop Camera, covering four telemetry samples", 90)
        live.settle()

    try:
        live.attempt(drive)
        yield live
    finally:
        chrome.close()


class TestStBranchTSmoke:
    """ST-BRANCH-T-SMOKE. The default camera runs, three full windows arrive, then Stop Camera: the
    loop carries on with telemetry only (R5). For every picture-less window the score is
    ``round_half_up(100 x P_telemetry_anomaly, 1)`` and that P equals the frozen value of its replay
    row. A single-branch score is the branch's own probability: the denominator is the EFFECTIVE
    weight (0.5 x 1 for telemetry, 0 for the missing vision), so (0.5 P) / 0.5 is exactly P."""

    def test_01_the_camera_was_stopped_and_the_loop_carried_on(self, smoke):
        assert smoke.error is None, smoke.error
        calls = smoke.calls
        imaged = [c for c in calls if c.sent_body["image_base64"] is not None]
        after = [c for c in imageless(calls) if c.number > smoke.stop_number]
        assert len(imaged) >= 3 and len(after) >= 5
        # Before the stop the windows were two-branch and FULL (they only take part in the reconciliation).
        for call in imaged:
            assert call.response["modality_freshness"] == {"vision": "fresh", "telemetry": "fresh"}, call.number
            assert call.response["SystemHealth"] == "FULL"
        assert smoke.page.locator(".runtime-details span", has_text="Camera:").first.inner_text().strip().startswith("Camera: idle · stopped by you at ")
        assert_clean_run(smoke)

    def test_02_telemetry_only_windows_score_the_frozen_probability(self, smoke, frozen):
        frozen.verify()
        assert smoke.error is None, smoke.error
        scope = imageless(smoke.calls)
        after = [c for c in scope if c.number > smoke.stop_number]
        assert len(after) >= 5
        problems, levels, rows = [], set(), set()
        for call in scope:
            record, prov = call.response, call.response["provenance"]
            wid = record["window_id"]
            if record["modality_freshness"] != MISSING_VISION:
                problems.append(f"window {wid}: modality_freshness {record['modality_freshness']}")
            if record["SystemHealth"] != "DEGRADED":
                problems.append(f"window {wid}: SystemHealth {record['SystemHealth']}")
            if (prov["vision_source"], prov["telemetry_source"]) != ("missing", "prepared_replay"):
                problems.append(f"window {wid}: provenance sources {prov['vision_source']}/{prov['telemetry_source']}")
            row = frozen.row_of(record["telemetry_features"])
            problems += row_problems(frozen, record, prov["telemetry_seq"])
            if row is None:
                continue
            rows.add(row)
            if record["P_telemetry_anomaly"] != frozen.pt(row):  # exact: the frozen model's number
                problems.append(f"window {wid}: P_telemetry_anomaly {record['P_telemetry_anomaly']!r} != frozen row {row} {frozen.pt(row)!r}")
            if record["telemetry_behavior_classes"] != frozen.classes(row):
                problems.append(f"window {wid}: the three class probabilities differ from frozen row {row}")
            if record["RiskScore"] != score_of(record["P_telemetry_anomaly"]):
                problems.append(f"window {wid}: RiskScore {record['RiskScore']!r} != round_half_up(100 x P_t, 1) = {score_of(record['P_telemetry_anomaly'])!r}")
            if record["RiskLevel"] != level_of(score_of(record["P_telemetry_anomaly"])):
                problems.append(f"window {wid}: RiskLevel {record['RiskLevel']} for score {record['RiskScore']}")
            levels.add(record["RiskLevel"])
            if record["P_distraction"] != 0.0 or record["visual_top_classes"] != []:
                problems.append(f"window {wid}: a missing vision branch carries P_distraction {record['P_distraction']!r}")
        assert not problems, f"{len(problems)} problems, first {problems[:8]}"
        # The windows cover at least one Low and one High replay row (0 / 3 against 1 / 2), so the
        # level mapping is exercised both ways and a wrong class or denominator cannot hide in 0.0.
        assert {"Low", "High"} <= levels, (sorted(levels), sorted(rows))
        assert any(frozen.pt(row) > 0.5 for row in rows)
        print("ST-BRANCH-T-SMOKE " + json.dumps({"picture_less_windows": len(scope), "after_stop": len(after),
                                                 "replay_rows": sorted(rows), "levels": sorted(levels)}))

    def test_03_common_assertions_and_five_way_reconciliation(self, smoke, frozen):
        frozen.verify()
        # The window of every replay row, two-branch or not, is the row its seq says.
        problems = [p for call in smoke.calls
                    for p in row_problems(frozen, call.response, call.response["provenance"]["telemetry_seq"])]
        assert not problems, problems[:8]
        common_and_reconciliation(smoke, imageless(smoke.calls))


# ======================================================================================
# ST-BRANCH-T-CONTINUITY
# ======================================================================================
# The AlertSeverity of every window of each telemetry cursor position (seq), from the R10 rules
# (docs: plan R9 / R10; code: inference._step_alert_fsm_live / _advance_segment) applied to the
# single-branch scores of the replay rows: Low 0.0 at rows 0, 3, 21-24; High at 1, 2, 4-12, 14, 15,
# 17-20; rows 13 and 16 carry no telemetry. Seq 2 is the position where HIGH_ALERT is reached and
# is checked separately (None here). Positions 25+ are the second lap: seq 25 is row 0, seq 26 row 1.
ALERT_BY_SEQ = {
    0: "NORMAL",
    1: "CAUTION",
    2: None,
    3: "HIGH_ALERT", 4: "HIGH_ALERT", 5: "HIGH_ALERT", 6: "HIGH_ALERT", 7: "HIGH_ALERT", 8: "HIGH_ALERT",
    9: "HIGH_ALERT", 10: "HIGH_ALERT", 11: "HIGH_ALERT", 12: "HIGH_ALERT",
    13: "unavailable",
    14: "HIGH_ALERT", 15: "HIGH_ALERT",
    16: "unavailable",
    17: "HIGH_ALERT", 18: "HIGH_ALERT", 19: "HIGH_ALERT", 20: "HIGH_ALERT", 21: "HIGH_ALERT",
    22: "HIGH_ALERT", 23: "HIGH_ALERT", 24: "HIGH_ALERT", 25: "HIGH_ALERT", 26: "HIGH_ALERT",
    27: "HIGH_ALERT",
}
LAST_SEQ = 27  # the run stops at the first window of this position: 26 is complete, i.e. a lap and a wrap


@pytest.fixture(scope="class")
def continuity(pw, e2e_server):
    # No fake device and no camera permission: getUserMedia is refused, so the camera fails to
    # start on Start Monitoring. App.start() carries on regardless (R5) and the loop sends
    # telemetry only, from the very first request.
    chrome = Chrome(pw, e2e_server, [], permissions=())
    live = LiveRun(chrome)

    def drive():
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(
            lambda: max((c.sent_body.get("telemetry_seq", -1) for c in live.tap.answered()), default=-1) >= LAST_SEQ,
            f"telemetry_seq {LAST_SEQ} (about 56 s of monitoring)", 150)
        live.settle()

    try:
        live.attempt(drive)
        yield live
    finally:
        chrome.close()


class TestStBranchTContinuity:
    """ST-BRANCH-T-CONTINUITY: no picture from the first request on, one full replay lap (25 rows,
    50 s) and the wrap into the second lap (about 56 s in all).

    Why the camera fails instead of being intercepted: ``App.start()`` calls ``camera.start()`` first
    and then starts the loop whatever the camera did, so a refused ``getUserMedia`` (no permission,
    no device) is the product's own telemetry-only path, with no request rewriting at all. A person
    who denies the camera prompt gets exactly this. The status line says "failed to start" (after
    the word ``denied`` or ``error``, whichever refusal the browser raises).

    The AlertSeverity sequence is the R10 rule, and it holds under ARITHMETIC acquisition time:
    ``test_02`` asserts that the telemetry timestamps of neighbouring positions differ by exactly
    2000 ms. HIGH_ALERT needs the server clock AND the source time of NEW supporting samples to
    have each covered 2000 ms, so the first High sample (seq 1) opens the span and the second
    (seq 2) closes it. If the source timestamps jittered (a real sensor), the span could be a few
    milliseconds short and the alert would come one sample later (known limitation K2); this test
    is only valid under the arithmetic times and does not claim otherwise. Seq 2 is therefore
    some ``CAUTION`` windows (possibly none) followed by ``HIGH_ALERT`` windows, at least one of them:
    the switch happens where the server clock completes 2000 ms since the first window of seq 1, which
    is the first window of seq 2 or a later one of the same seq (a REPEAT can finish the wall-clock
    condition, never the source one). Seq 1 is ``CAUTION`` in EVERY window; a rule of "two consecutive
    High windows" would make its second window ``HIGH_ALERT``.

    The expected sequence below was derived by hand from ``inference._advance_segment`` /
    ``_step_alert_fsm_live`` and the frozen scores, before any run: seq 0 Low (NORMAL); seq 1 opens the
    High segment (CAUTION); seq 2 closes its source span at exactly 2000 ms; seq 3 and the Low rows
    21-25 cannot release the latch (recovery needs a Low span of 10000 ms; 21..25 is 8000 ms and seq 26
    is High again); seq 13 and 16 carry no input at all, so their windows emit no severity but the
    latch stays."""

    def test_01_the_loop_never_stopped_and_no_picture_was_ever_sent(self, continuity):
        assert continuity.error is None, continuity.error
        calls = continuity.calls
        assert len(calls) >= 200 and max(c.sent_body["telemetry_seq"] for c in calls if "telemetry_seq" in c.sent_body) >= LAST_SEQ
        for call in calls:
            body = call.sent_body
            assert body["image_base64"] is None and body["captured_at"] is None
            assert "vision_frame" not in body and "captured_at_source" not in body
        line = continuity.page.locator(".runtime-details span", has_text="Camera:").first.inner_text().strip()
        # The status word is the hook's: "denied" for a NotAllowedError, "error" for any other refusal
        # (no device). Which one the browser raises is not what this test is about; "failed to start" is.
        assert re.fullmatch(r"Camera: (error|denied) · failed to start at .+", line), line
        assert_clean_run(continuity)  # includes: window ids 1..N without a gap, every X-Attempt-Index 1, no fault, no stop panel

    def test_02_every_cursor_position_appears_and_maps_to_its_replay_row(self, continuity, frozen):
        frozen.verify()
        assert continuity.error is None, continuity.error
        calls = continuity.calls
        seqs = cursor_positions(calls)
        assert seqs == sorted(seqs), "the cursor went backwards"
        assert sorted(set(seqs)) == list(range(0, max(seqs) + 1)), "a telemetry cursor position was skipped"
        # Exactly the empty rows (13, 16 and their second-lap twins) send no telemetry and no seq.
        for call, seq in zip(calls, seqs):
            body = call.sent_body
            empty = seq % REPLAY_ROWS in ROWS_WITHOUT_TELEMETRY
            assert (body["telemetry_features"] is None) == empty, (call.number, seq)
            assert ("telemetry_seq" in body) == (not empty), (call.number, seq)
            assert body["telemetry_source"] == ("missing" if empty else "prepared_replay")
            if empty:
                assert body["telemetry_timestamp"] is None
        # The row of every window, from its own features, equals seq % 25 (this is also the wrap).
        problems = [p for call, seq in zip(calls, seqs) for p in row_problems(frozen, call.response, seq)]
        problems += [f"window {c.response['window_id']}: provenance.telemetry_seq {c.response['provenance']['telemetry_seq']} != {s}"
                     for c, s in zip(calls, seqs) if s % REPLAY_ROWS not in ROWS_WITHOUT_TELEMETRY
                     and c.response["provenance"]["telemetry_seq"] != s]
        assert not problems, f"{len(problems)} problems, first {problems[:8]}"
        # The premise of the alert sequence: arithmetic acquisition time, byte-identical per seq,
        # exactly 2000 ms per step (4000 ms across an empty row).
        stamps: dict[int, str] = {}
        for call in calls:
            body = call.sent_body
            if "telemetry_seq" in body:
                assert body["telemetry_timestamp"] == stamps.setdefault(body["telemetry_seq"], body["telemetry_timestamp"])
        present = sorted(stamps)
        for before, after in zip(present, present[1:]):
            assert (instant(stamps[after]) - instant(stamps[before])).total_seconds() == 2.0 * (after - before), (before, after)
        assert len(present) == len(set(seqs)) - len([s for s in set(seqs) if s % REPLAY_ROWS in ROWS_WITHOUT_TELEMETRY])
        # The server counts the same observations: a new telemetry sample per cursor position.
        news = [c.response["provenance"]["telemetry_seq"] for c in calls if c.response["provenance"]["telemetry_obs"] == "new"]
        assert news == [s for s in present]

    def test_03_branch_values_and_the_unavailable_windows(self, continuity, frozen):
        frozen.verify()
        assert continuity.error is None, continuity.error
        calls = continuity.calls
        seqs = cursor_positions(calls)
        problems, unavailable_seqs, available_after_gap = [], set(), []
        for call, seq in zip(calls, seqs):
            record, prov = call.response, call.response["provenance"]
            wid = record["window_id"]
            if seq % REPLAY_ROWS in ROWS_WITHOUT_TELEMETRY:  # no input on either branch: nothing to score
                unavailable_seqs.add(seq)
                if record["modality_freshness"] != {"vision": "missing", "telemetry": "missing"}:
                    problems.append(f"window {wid} (seq {seq}): modality_freshness {record['modality_freshness']}")
                if record["assessment_available"] or record["SystemHealth"] != "UNAVAILABLE" or any(record[k] is not None for k in RISK_FIELDS):
                    problems.append(f"window {wid} (seq {seq}): not an unavailable window")
                if (prov["vision_source"], prov["telemetry_source"]) != ("missing", "missing"):
                    problems.append(f"window {wid} (seq {seq}): provenance sources {prov['vision_source']}/{prov['telemetry_source']}")
                continue
            row = seq % REPLAY_ROWS
            if record["modality_freshness"] != MISSING_VISION or record["SystemHealth"] != "DEGRADED":
                problems.append(f"window {wid} (seq {seq}): {record['modality_freshness']} / {record['SystemHealth']}")
            if (prov["vision_source"], prov["telemetry_source"]) != ("missing", "prepared_replay"):
                problems.append(f"window {wid} (seq {seq}): provenance sources {prov['vision_source']}/{prov['telemetry_source']}")
            if record["P_telemetry_anomaly"] != frozen.pt(row):
                problems.append(f"window {wid} (seq {seq}): P_telemetry_anomaly {record['P_telemetry_anomaly']!r} != frozen row {row} {frozen.pt(row)!r}")
            if record["telemetry_behavior_classes"] != frozen.classes(row):
                problems.append(f"window {wid} (seq {seq}): class probabilities differ from frozen row {row}")
            if record["RiskScore"] != score_of(frozen.pt(row)) or record["RiskLevel"] != level_of(score_of(frozen.pt(row))):
                problems.append(f"window {wid} (seq {seq}): {record['RiskScore']!r} {record['RiskLevel']} for frozen row {row}")
            if seq - 1 in unavailable_seqs or seq - 2 in unavailable_seqs:
                available_after_gap.append(seq)
        assert not problems, f"{len(problems)} problems, first {problems[:8]}"
        # Both empty rows were met, and the window after each recovered to DEGRADED (checked above for 14 and 17).
        assert unavailable_seqs == {13, 16}, unavailable_seqs
        assert {14, 17} <= set(available_after_gap)

    def test_04_alert_severity_follows_the_r10_rule(self, continuity):
        assert continuity.error is None, continuity.error
        calls = continuity.calls
        seqs = cursor_positions(calls)
        groups: dict[int, list] = {}
        for call, seq in zip(calls, seqs):
            groups.setdefault(seq, []).append(call.response["AlertSeverity"])
        assert sorted(groups) == list(range(0, LAST_SEQ + 1))
        # Enough windows per position that "all CAUTION in seq 1" really excludes a 2-window rule.
        assert all(len(groups[seq]) >= 3 for seq in range(0, LAST_SEQ)), {s: len(g) for s, g in groups.items()}
        problems = []
        for seq, alerts in groups.items():
            want = ALERT_BY_SEQ[seq]
            if seq == 2:
                first_alert = next((i for i, a in enumerate(alerts) if a == "HIGH_ALERT"), None)
                if first_alert is None:
                    problems.append("seq 2 never reached HIGH_ALERT")
                elif alerts[:first_alert] != ["CAUTION"] * first_alert or alerts[first_alert:] != ["HIGH_ALERT"] * (len(alerts) - first_alert):
                    problems.append(f"seq 2 is not CAUTION... then HIGH_ALERT...: {alerts}")
            elif want == "unavailable":
                if alerts != [None] * len(alerts):
                    problems.append(f"seq {seq} (no telemetry): AlertSeverity should be null in every window, got {sorted(set(map(str, alerts)))}")
            elif alerts != [want] * len(alerts):
                problems.append(f"seq {seq}: expected every window {want}, got {sorted(set(map(str, alerts)))} ({len(alerts)} windows)")
        assert not problems, problems
        two = groups[2]
        print("ST-BRANCH-T-CONTINUITY " + json.dumps({
            "windows": len(calls), "windows_per_seq_min_median_max": [min(map(len, groups.values())),
                                                                      sorted(map(len, groups.values()))[len(groups) // 2],
                                                                      max(map(len, groups.values()))],
            "seq2_windows": len(two), "seq2_cautions_before_high_alert": two.index("HIGH_ALERT")}))
        # Never before seq 2, and the latch is never lost afterwards (neither by a Low run nor by an unavailable window).
        flat = [a for seq in sorted(groups) for a in groups[seq]]
        first_high = flat.index("HIGH_ALERT")
        assert all(a == "HIGH_ALERT" or a is None for a in flat[first_high:]), "the HIGH_ALERT latch was released"

    def test_05_common_assertions_and_five_way_reconciliation(self, continuity):
        common_and_reconciliation(continuity, continuity.calls)


# ======================================================================================
# ST-BRANCH-V
# ======================================================================================
def vision_only(body: dict) -> dict:
    """The route's rewrite of ST-BRANCH-V: no telemetry of any kind. ``telemetry_seq`` is removed
    TOGETHER with the features, because the server answers 422 to a seq without telemetry and the
    front end stops on a 422. A pure function of the request body, so a re-sent request is
    rewritten to the very same bytes."""
    rewritten = {key: value for key, value in body.items() if key != "telemetry_seq"}
    rewritten.update(telemetry_features=None, telemetry_timestamp=None, telemetry_source="missing")
    return rewritten


@pytest.fixture(scope="class")
def vision(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, SLOW_FAKE_CAMERA_ARGS)  # 5 fps: the loop outruns it, so REPEATs occur
    chrome.tap.rewrite_infer = vision_only  # in place before the page is opened: no request escapes it
    live = LiveRun(chrome)

    def both_kinds(calls, each=6):
        kinds = [c.response["provenance"]["vision_obs"] for c in calls]
        return kinds.count("new") >= each and kinds.count("repeat") >= each

    def drive():
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: both_kinds(live.tap.answered_with_image()),
                          "six NEW and six REPEAT windows with a picture", 60)
        live.stop_number = stop_camera(live)
        chrome.wait_until(lambda: len([c for c in imageless(live.tap.answered()) if c.number > live.stop_number]) >= 6,
                          "six picture-less windows after Stop Camera", 60)
        live.restart_number = start_camera(live)

        def after_restart():
            return [c for c in live.tap.answered_with_image() if c.number > live.restart_number]

        chrome.wait_until(lambda: both_kinds(after_restart()),
                          "six NEW and six REPEAT windows with a picture after Start Camera", 60)
        live.settle()

    try:
        live.attempt(drive)
        yield live
    finally:
        chrome.close()


def ema_problems(pairs) -> tuple[list[str], dict]:
    """The expected NEW-only EMA chain (R10), walked over ``(call, record)`` pairs in order.

    The rules, as read from ``inference.run_inference`` (LIVE_MODEL_RUNTIME):
      * a NEW observation is SEEDED when no chain exists: ``P_distraction == P_distraction_raw``
        (full precision); otherwise ``P_distraction == round_half_up(alpha x raw + (1 - alpha) x
        previous NEW P_distraction, 3)``; the chain then holds that value;
      * a REPEAT shows what its observation was registered with - its ``P_distraction`` and its
        ``P_distraction_raw`` both - and neither reads nor extends the chain, nor re-links a
        broken one;
      * the chain is BROKEN (the next NEW seeds again) after any window whose vision branch is not
        fresh (missing or expired) or that carries no assessment, and after a processing gap
        longer than ``freshness_tolerance_s`` between two windows."""
    problems: list[str] = []
    stats = {"new": 0, "repeat": 0, "seeds": [], "gap_resets": 0, "order": []}
    chain, registered, registered_key, previous_time = None, {}, None, None
    for call, record in pairs:
        prov, wid = record["provenance"], record["window_id"]
        config = prov["fusion_config"]
        alpha, tolerance = config["ema_alpha"], config["freshness_tolerance_s"]
        moment = instant(record["timestamp"])
        if previous_time is not None and (moment - previous_time).total_seconds() > tolerance:
            chain, stats["gap_resets"] = None, stats["gap_resets"] + 1
        previous_time = moment
        if call.sent_body["image_base64"] is None or record["modality_freshness"]["vision"] != "fresh" or not record["assessment_available"]:
            chain = None
            stats["order"].append((wid, "break"))
            continue
        key = frame_key(call.sent_body)
        expected_obs = "repeat" if key == registered_key else "new"
        if prov["vision_obs"] != expected_obs:
            problems.append(f"window {wid}: vision_obs {prov['vision_obs']!r}, the frame identity says {expected_obs!r}")
        if expected_obs == "new":
            raw = prov["P_distraction_raw"]
            if chain is None:
                want = raw
                stats["seeds"].append(wid)
            else:
                want = half_up_float(alpha * raw + (1 - alpha) * chain, 3)
            if record["P_distraction"] != want:
                problems.append(f"window {wid}: NEW P_distraction {record['P_distraction']!r}, expected {want!r} "
                                f"({'seed = raw' if chain is None else 'EMA of raw ' + repr(raw) + ' and ' + repr(chain)})")
            chain, registered[key], registered_key = want, (want, raw), key
            stats["new"] += 1
            stats["order"].append((wid, "new"))
        else:
            stats["repeat"] += 1
            stats["order"].append((wid, "repeat"))
            kept = registered.get(key)
            if kept is None:
                problems.append(f"window {wid}: a REPEAT of a frame that was never registered")
            elif record["P_distraction"] != kept[0] or prov["P_distraction_raw"] != kept[1]:
                problems.append(f"window {wid}: REPEAT shows P {record['P_distraction']!r} / raw {prov['P_distraction_raw']!r}, "
                                f"its observation was registered with {kept[0]!r} / {kept[1]!r}")
    return problems, stats


class TestStBranchV:
    """ST-BRANCH-V: vision only. A Playwright route rewrites every ``/infer`` body so the server
    sees no telemetry (``vision_only``: features, timestamp and ``telemetry_seq`` removed, source
    ``missing``); the browser still sends telemetry and the route is the only thing between. The camera
    is the 5 fps fake device, so the 10 Hz loop outruns it and a frame is sometimes sent twice (a
    REPEAT), which checks the NEW-only EMA end to end. Stop Camera, then Start Camera, breaks the
    chain mid-run: the picture-less windows in between have no evidence at all (UNAVAILABLE), and
    the first NEW frame after Start Camera must be a seed.

    No score value is asserted: the fake camera draws a different picture every frame."""

    def test_01_the_server_saw_vision_only_and_the_rewrite_is_deterministic(self, vision):
        assert vision.error is None, vision.error
        calls = vision.calls
        assert len(calls) >= 30
        for call in calls:
            body = call.sent_body
            assert body["telemetry_features"] is None and body["telemetry_timestamp"] is None
            assert body["telemetry_source"] == "missing" and "telemetry_seq" not in body
            assert call.sent_raw == json.dumps(vision_only(json.loads(call.raw)), separators=(",", ":"))  # same input, same bytes
        assert any("telemetry_seq" in c.body and c.body["telemetry_features"] is not None for c in calls), \
            "the browser sent no telemetry, so the rewrite proved nothing"
        # The rewrite is a pure function of the browser's body: the same request, re-sent, gets the
        # same bytes, and the body it was given is left as the browser built it.
        sample = next(c.body for c in calls if "telemetry_seq" in c.body)
        before = json.dumps(sample, sort_keys=True)
        assert json.dumps(vision_only(sample), separators=(",", ":")) == json.dumps(vision_only(sample), separators=(",", ":"))
        assert json.dumps(sample, sort_keys=True) == before and "telemetry_seq" in sample
        assert_clean_run(vision)

    def test_02_vision_only_windows_score_the_distraction_probability(self, vision):
        assert vision.error is None, vision.error
        problems, with_picture = [], [c for c in vision.calls if c.sent_body["image_base64"] is not None]
        assert len(with_picture) >= 24
        for call in with_picture:
            record, prov = call.response, call.response["provenance"]
            wid = record["window_id"]
            if record["modality_freshness"] != {"vision": "fresh", "telemetry": "missing"} or record["SystemHealth"] != "DEGRADED":
                problems.append(f"window {wid}: {record['modality_freshness']} / {record['SystemHealth']}")
            if (prov["vision_source"], prov["telemetry_source"]) != ("camera_frame", "missing"):
                problems.append(f"window {wid}: provenance sources {prov['vision_source']}/{prov['telemetry_source']}")
            if record["RiskScore"] != score_of(record["P_distraction"]) or record["RiskLevel"] != level_of(score_of(record["P_distraction"])):
                problems.append(f"window {wid}: RiskScore {record['RiskScore']!r} / {record['RiskLevel']} for P_distraction {record['P_distraction']!r}")
            if record["P_telemetry_anomaly"] != 0.0 or record["telemetry_features"] is not None or record["telemetry_behavior_classes"] != []:
                problems.append(f"window {wid}: a missing telemetry branch carries data")
        assert not problems, f"{len(problems)} problems, first {problems[:8]}"

    def test_03_the_ema_chain_is_new_only_and_reseeds_after_unavailable_windows(self, vision):
        """The reseed conditions, from ``inference.run_inference``: see ``ema_problems``."""
        assert vision.error is None, vision.error
        pairs = [(c, c.response) for c in vision.calls]
        problems, stats = ema_problems(pairs)
        assert not problems, f"{len(problems)} problems, first {problems[:6]}"
        print("ST-BRANCH-V " + json.dumps({k: v for k, v in stats.items() if k != "order"} | {"windows": len(pairs)}))
        assert stats["new"] >= 12 and stats["repeat"] >= 12, stats  # both regimes occurred, in both stretches
        assert len(stats["seeds"]) >= 2, stats["seeds"]  # the first frame and the first one after Start Camera
        # The first NEW frame after Start Camera is a seed, i.e. P_distraction == raw, to the bit.
        first = next(c for c in vision.tap.answered_with_image() if c.number > vision.restart_number)
        assert first.response["window_id"] in stats["seeds"]
        assert first.response["provenance"]["vision_obs"] == "new"
        assert first.response["P_distraction"] == first.response["provenance"]["P_distraction_raw"]
        # ...and the chain really was broken in between: windows without a picture came first.
        broken = [c for c in imageless(vision.calls) if vision.stop_number < c.number < first.number]
        assert len(broken) >= 6
        # Once running again the chain is smoothed: not every NEW frame is its own raw value.
        later = [c for c in vision.tap.answered_with_image() if c.number > first.number and c.response["provenance"]["vision_obs"] == "new"]
        assert any(c.response["P_distraction"] != c.response["provenance"]["P_distraction_raw"] for c in later)

    def test_04_picture_less_windows_are_unavailable(self, vision):
        assert vision.error is None, vision.error
        gap = imageless(vision.calls)
        assert len([c for c in gap if c.number > vision.stop_number]) >= 6  # the Stop Camera stretch
        for call in gap:
            record = call.response
            assert record["assessment_available"] is False and record["SystemHealth"] == "UNAVAILABLE", call.number
            assert all(record[k] is None for k in RISK_FIELDS)
            assert record["modality_freshness"] == {"vision": "missing", "telemetry": "missing"}
            assert record["provenance"]["vision_source"] == "missing"
            assert record["provenance"]["telemetry_source"] == "missing"

    def test_05_common_assertions_and_five_way_reconciliation(self, vision):
        common_and_reconciliation(vision, vision.calls)


# ======================================================================================
# ST-BRANCH-ZERO
# ======================================================================================
@pytest.fixture(scope="class")
def zero(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)
    live = LiveRun(chrome)

    def drive():
        page = chrome.page
        chrome.open()
        page.get_by_role("button", name="Configuration", exact=True).click()
        page.get_by_label("Vision Weight").fill("1")  # the slider at its maximum; Telemetry follows to 0
        chrome.wait_until(lambda: page.get_by_text("Vision Weight: 1.00", exact=True).count() == 1
                          and page.get_by_text("Telemetry Weight: 0.00", exact=True).count() == 1,
                          "the sliders to read Vision 1.00 / Telemetry 0.00", 10)
        page.get_by_role("button", name="Live Monitor", exact=True).click()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: len(live.tap.answered_with_image()) >= 3, "three windows that carry a picture", 60)
        live.stop_number = stop_camera(live)

        def after_stop():
            return [c for c in imageless(live.tap.answered()) if c.number > live.stop_number]

        def enough():
            seqs = {c.sent_body["telemetry_seq"] for c in after_stop()}
            return len(after_stop()) >= 5 and len(seqs) >= 4 and max(seqs) >= 3

        chrome.wait_until(enough, "five picture-less windows after Stop Camera, covering four telemetry samples", 90)
        live.settle()

    try:
        live.attempt(drive)
        yield live
    finally:
        chrome.close()


class TestStBranchZero:
    """ST-BRANCH-ZERO (the reverse case): Vision Weight 1.00, Telemetry Weight 0.00, set through the
    Configuration view. While the camera runs, vision alone decides. After Stop Camera the only
    branch with evidence is telemetry, and it has no weight: the window must be UNAVAILABLE, never
    the telemetry-only score ``100 x P_t`` (the zero-effective-weight boundary fixed in Tasks 2-4:
    the denominator is the EFFECTIVE weight, ``w_t x freshness = 0``, so there is nothing to divide by).

    Before the stop the windows are two-branch (both branches fresh) and outside the common
    single-branch assertions. By the code they are ``FULL`` - ``fusion.map_system_health`` looks only
    at freshness, "never at the weights" - and ``RiskScore = (1.0 x P_d + 0.0 x P_t) / 1.0``, i.e. the
    smoothed ``P_distraction``, which is what is asserted. Their DominantEvidence is not asserted:
    the decision tree compares the two probabilities whatever the weights, so it can say
    "Telemetry-dominant" for a branch that has no weight (an observation recorded in the report)."""

    def test_01_the_weights_were_applied_and_the_loop_carried_on(self, zero):
        assert zero.error is None, zero.error
        calls = zero.calls
        assert len([c for c in calls if c.sent_body["image_base64"] is not None]) >= 3
        assert len([c for c in imageless(calls) if c.number > zero.stop_number]) >= 5
        for call in calls:
            config = call.response["provenance"]["fusion_config"]
            assert (config["weight_vision"], config["weight_telemetry"]) == (1, 0), config
        assert_clean_run(zero)

    def test_02_after_stop_camera_every_window_is_unavailable_and_nothing_leaks(self, zero, frozen):
        frozen.verify()
        assert zero.error is None, zero.error
        after = [c for c in imageless(zero.calls) if c.number > zero.stop_number]
        assert len(after) >= 5
        leaked, magnitudes = [], []
        for call in after:
            record = call.response
            wid = record["window_id"]
            if record["assessment_available"] is not False or record["SystemHealth"] != "UNAVAILABLE":
                leaked.append(f"window {wid}: assessment_available={record['assessment_available']} SystemHealth={record['SystemHealth']}")
            if any(record[k] is not None for k in RISK_FIELDS):
                leaked.append(f"window {wid}: a risk field is set: {[record[k] for k in RISK_FIELDS]}")
            if record["RiskScore"] == score_of(record["P_telemetry_anomaly"]):
                leaked.append(f"window {wid}: RiskScore equals round_half_up(100 x P_t, 1) = {score_of(record['P_telemetry_anomaly'])!r}")
            # The telemetry branch itself is intact: it is fresh, and carries the frozen model's number.
            if record["modality_freshness"] != MISSING_VISION:
                leaked.append(f"window {wid}: modality_freshness {record['modality_freshness']}")
            row = frozen.row_of(record["telemetry_features"])
            if row is None or record["P_telemetry_anomaly"] != frozen.pt(row):
                leaked.append(f"window {wid}: P_telemetry_anomaly {record['P_telemetry_anomaly']!r} is not the frozen value of its row")
            else:
                magnitudes.append(score_of(frozen.pt(row)))
        assert not leaked, f"{len(leaked)} problems, first {leaked[:6]}"
        # A leaked 100 x P_t would have been visible: at least one of these windows would have scored high.
        assert max(magnitudes) >= 60, magnitudes

    def test_03_before_the_stop_vision_alone_decides(self, zero):
        assert zero.error is None, zero.error
        before = [c for c in zero.calls if c.sent_body["image_base64"] is not None]
        problems = []
        for call in before:
            record = call.response
            wid = record["window_id"]
            if record["modality_freshness"] != {"vision": "fresh", "telemetry": "fresh"} or record["SystemHealth"] != "FULL":
                problems.append(f"window {wid}: {record['modality_freshness']} / {record['SystemHealth']}")
            if not record["assessment_available"] or record["RiskScore"] != score_of(record["P_distraction"]):
                problems.append(f"window {wid}: RiskScore {record['RiskScore']!r} is not round_half_up(100 x P_distraction, 1) = {score_of(record['P_distraction'])!r}")
            elif record["RiskLevel"] != level_of(record["RiskScore"]):
                problems.append(f"window {wid}: RiskLevel {record['RiskLevel']} for score {record['RiskScore']}")
        assert not problems, f"{len(problems)} problems, first {problems[:6]}"
        print("ST-BRANCH-ZERO " + json.dumps({"two_branch_windows_before_stop": len(before),
                                              "their_DominantEvidence": sorted({c.response["DominantEvidence"] for c in before}),
                                              "their_P_t_rows_and_scores": sorted({(c.response["provenance"]["telemetry_seq"] % REPLAY_ROWS,
                                                                                    c.response["RiskScore"]) for c in before})[:6]}))

    def test_04_common_assertions_and_five_way_reconciliation(self, zero, frozen):
        frozen.verify()
        problems = [p for call in zero.calls
                    for p in row_problems(frozen, call.response, call.response["provenance"]["telemetry_seq"])]
        assert not problems, problems[:8]
        common_and_reconciliation(zero, [c for c in imageless(zero.calls) if c.number > zero.stop_number])
