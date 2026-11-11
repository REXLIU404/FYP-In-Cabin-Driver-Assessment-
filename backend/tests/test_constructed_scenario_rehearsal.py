"""Constructed scenario rehearsal (plan Task 9): ``viva_v1`` played once, end to end, in the browser.

Marked ``long`` (deselected unless the run asks with ``-m long``, the same opt-in as ST-LONG-01):
viva_v1 is 136 s of playback at 5 frames/s (about 1,360 windows), so the run takes minutes. One
uvicorn serves the API and the freshly built ``dist/`` with ``DRA_SCENARIO_ROOT`` pointed at a
viva_v1 bundle the fixture generates into tmp.

Recorded, NOT judged: per segment it writes the window count, the distinct frame count, the
"truth vs model" agreement rate on each modality, the RiskLevel counts and the AlertSeverity
change sequence, and prints a one-line summary. These are engineering observations of a DEMO:
report results come from Live only (design doc D06), so no hit rate and no RiskLevel /
AlertSeverity value is asserted. Asserted structure only: the seven segments all appear in
order, the run stops itself at the end of the scenario, and no fault is recorded.

With ``DRA_E2E_EVIDENCE_DIR`` set the report is written there as ``viva_v1-rehearsal.json``.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from e2e_support import FAKE_CAMERA_ARGS, Chrome, api_client, db_count, evidence_dir

REPO = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO / "scripts" / "build_dataset_replay.py"
# The bundle generation is Task 3's script; the data root is resolved by the SAME rule the
# script and scripts/freeze_manifest.py share (never guessed in a test).
sys.path.insert(0, str(REPO / "scripts"))
from freeze_manifest import DataRootError, resolve_data_root  # noqa: E402

MODEL_ROOT = REPO / "ml" / "outputs"
# The exact reason text the conftest model accounting recognises (conftest.MODELS_SKIP_REASON).
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)
pytestmark = [pytest.mark.long, pytest.mark.e2e, requires_models]

SCENARIO_ID = "viva_v1"
SEGMENT_COUNT = 7  # viva_v1 has seven segments (demo/scenarios/viva_v1.json)


@pytest.fixture(scope="module")
def viva_server(e2e_dist, tmp_path_factory):
    """The viva_v1 bundle (generated into tmp by Task 3's script) and ONE uvicorn whose scenario
    root is that bundle directory. Never the developer's ``demo/bundles/`` and never the 8000
    port."""
    from e2e_support import start_server

    try:
        data_root, _ = resolve_data_root()
    except DataRootError:
        pytest.skip("State Farm data root not available")
    if data_root is None:
        pytest.skip("State Farm data root not available")
    bundles = tmp_path_factory.mktemp("scenario-bundles")
    done = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), SCENARIO_ID,
         "--out", str(bundles), "--data-root", str(data_root)],
        capture_output=True, text=True, timeout=600,
    )
    assert done.returncode == 0, (
        f"scripts/build_dataset_replay.py failed ({done.returncode}):\n"
        f"{done.stdout}\n{done.stderr}")
    manifest = json.loads((bundles / SCENARIO_ID / "manifest.json").read_text())
    server = start_server(tmp_path_factory.mktemp("constructed-rehearsal-server"),
                          extra_env={"DRA_SCENARIO_ROOT": str(bundles)})
    try:
        yield server, manifest
    finally:
        server.stop()


def text_of(page, selector: str) -> str:
    locator = page.locator(selector)
    return locator.inner_text() if locator.count() else ""


def select_scenario(chrome: Chrome, scenario_id: str) -> None:
    """The clicks a person makes to reach a loaded constructed scenario."""
    page = chrome.page
    page.select_option('select[aria-label="Data mode"]', value="CONSTRUCTED_SCENARIO_RUNTIME")
    chrome.wait_until(
        lambda: page.locator(f'select[aria-label="Scenario"] option[value="{scenario_id}"]').count() == 1,
        f"the Scenario dropdown to offer {scenario_id}", 30)
    page.select_option('select[aria-label="Scenario"]', value=scenario_id)
    chrome.wait_until(
        lambda: page.locator('.topbar-actions button.button--primary').is_enabled(),
        "Start Monitoring to be enabled (frames preloaded)", 300)


def alert_transitions(levels: list[tuple[int, str]]) -> list[list]:
    """The compressed change sequence of per-window alert severities: only the windows where the
    severity differs from the previous window's."""
    out = []
    for window_id, value in levels:
        if not out or out[-1][1] != value:
            out.append([window_id, value])
    return out


def top_label(classes: list[dict]) -> str | None:
    """The model's answer for one modality: the first (highest-probability) class, or None when
    the window carries none."""
    return classes[0]["label"] if classes else None


def agreement_rate(pairs: list[tuple]) -> dict:
    """Truth-vs-model agreement over one segment's windows: the share where the model's answer
    equals the dataset's own label. The truth lives on ``provenance.replay``, the model's answer
    in ``visual_top_classes`` / ``telemetry_behavior_classes``. Recorded, never asserted."""
    pairs = [(truth, model) for truth, model in pairs if truth is not None and model is not None]
    if not pairs:
        return {"windows": 0, "agreed": None, "rate": None}
    agreed = sum(1 for truth, model in pairs if model == truth)
    return {"windows": len(pairs), "agreed": agreed, "rate": round(agreed / len(pairs), 4)}


def test_task9_viva_v1_rehearsal(pw, viva_server):
    server, manifest = viva_server
    chrome = Chrome(pw, server, FAKE_CAMERA_ARGS)
    chrome.tap.drop_images = True  # about 1,360 windows: keep only the labels, not the pictures
    try:
        chrome.open()
        select_scenario(chrome, SCENARIO_ID)
        page = chrome.page
        option = page.locator(f'select[aria-label="Scenario"] option[value="{SCENARIO_ID}"]')
        assert option.inner_text() == "viva_v1 · 136 s · 7 segments"
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(
            lambda: text_of(page, ".scenario-badge") == "CONSTRUCTED SCENARIO",
            "the CONSTRUCTED SCENARIO badge", 30)
        # The displayed Truth follows the manifest; the first segment is c0 = safe_driving.
        chrome.wait_until(
            lambda: "Truth: safe_driving" in text_of(page, ".scenario-truth"),
            "the first segment's truth line (safe_driving)", 30)
        chrome.wait_until(
            lambda: "Scenario finished (136 s, 7 segments)" in text_of(page, ".scenario-caption"),
            "the scenario to finish", 200)
        sid = chrome.tap.session_posts[-1].response["id"]
        chrome.wait(500)  # let the last in-flight delivery settle one way or the other
        calls = chrome.tap.answered(sid)
        assert calls

        # Structure, and structure only (the plan's three assertions):
        # 1. all seven segments appear, in order, nothing else.
        segment_path = [c.response["provenance"]["replay"]["segment_index"] for c in calls]
        assert segment_path[0] == 0 and segment_path[-1] == SEGMENT_COUNT - 1
        assert sorted(set(segment_path)) == list(range(SEGMENT_COUNT))
        assert all(a <= b for a, b in zip(segment_path, segment_path[1:]))
        assert all(c.response["operation_mode"] == "CONSTRUCTED_SCENARIO_RUNTIME" for c in calls)
        assert all(c.response["provenance"]["vision_source"] == "dataset_replay" for c in calls)
        # 2. finished means stopped: the loop paused itself and sends nothing further.
        chrome.wait(1500)
        assert len(chrome.tap.answered(sid)) == len(calls), \
            "the loop kept sending after the scenario finished"
        assert page.locator('.topbar-actions button.button--primary').is_enabled(), \
            "Start Monitoring is not re-enabled after the run stopped itself"
        assert chrome.stop_panel_text() is None
        # 3. no fault, and the page never errored.
        assert db_count(server, "SELECT COUNT(*) FROM fault_events WHERE session_id=?", sid) == 0
        assert chrome.console_errors == [] and chrome.page_errors == []

        # Record, don't judge: the per-segment report. Everything below is computed from the
        # stored records and the bundle manifest; nothing is fabricated and nothing is asserted.
        per_segment = []
        for entry in manifest["segments"]:
            segment_calls = [c for c in calls
                             if c.response["provenance"]["replay"]["segment_index"] == entry["index"]]
            segment_calls.sort(key=lambda c: c.response["window_id"])
            per_segment.append({
                "index": entry["index"],
                "title": entry["title"],
                "driver_id": entry["driver_id"],
                "truth_vision": entry["vision_label"],
                "truth_telemetry": entry["telemetry_label"],
                "manifest_frames": entry["frame_count"],
                "manifest_telemetry_rows": entry["telemetry_count"],
                "windows": len(segment_calls),
                "distinct_frames": len({c.response["provenance"]["replay"]["frame_file"]
                                        for c in segment_calls}),
                "vision_agreement": agreement_rate([
                    (c.response["provenance"]["replay"].get("vision_label"),
                     top_label(c.response["visual_top_classes"])) for c in segment_calls]),
                "telemetry_agreement": agreement_rate([
                    (c.response["provenance"]["replay"].get("telemetry_label"),
                     top_label(c.response["telemetry_behavior_classes"])) for c in segment_calls]),
                "risk_levels": dict(Counter(c.response["RiskLevel"] for c in segment_calls)),
                "alert_severity_transitions": alert_transitions(
                    [(c.response["window_id"], c.response["AlertSeverity"]) for c in segment_calls]),
            })
        with api_client(server) as client:
            session = client.get(f"/api/sessions/{sid}").json()
        report = {
            "scenario_id": SCENARIO_ID,
            "session_id": sid,
            "duration_ms": manifest["duration_ms"],
            "frame_period_ms": manifest["frame_period_ms"],
            "telemetry_period_ms": manifest["telemetry_period_ms"],
            "windows_received": len(calls),
            "session_total_windows": session["total_windows"],
            "whole_run_risk_levels": dict(Counter(c.response["RiskLevel"] for c in calls)),
            "whole_run_alert_severity_transitions": alert_transitions(
                [(c.response["window_id"], c.response["AlertSeverity"]) for c in calls]),
            "segments": per_segment,
        }
        print("TASK9-REHEARSAL " + json.dumps({
            "scenario_id": SCENARIO_ID,
            "session_id": sid,
            "windows_received": len(calls),
            "session_total_windows": session["total_windows"],
            "segments": len(per_segment),
        }))
        out = evidence_dir()
        if out:
            (out / "viva_v1-rehearsal.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        chrome.close()
