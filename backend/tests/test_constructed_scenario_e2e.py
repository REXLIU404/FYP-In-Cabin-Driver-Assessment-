"""Constructed scenario end to end (plan Task 8): the demo mode through the real stack.

One uvicorn serves the API and the freshly built ``dist/`` with ``DRA_SCENARIO_ROOT`` pointed
at a bundle the fixture generates into tmp (``scripts/build_dataset_replay.py``, ``e2e_short``:
3 segments x 4 s = 60 frames / 6 telemetry rows). Chromium drives the dashboard exactly as a
person would - the data mode is switched, the bundle is selected and loaded, a run is played
to its end - and everything is recorded from the outside (Playwright routes + the same tap the
Live end-to-end tests use).

This is an ENGINEERING CHECK, never an evaluation (design doc D06): no hit rate and no
RiskLevel / AlertSeverity value is asserted here. Report results come from Live only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from e2e_support import (
    FAKE_CAMERA_ARGS,
    Chrome,
    LiveRun,
    Parties,
    parties_diffs,
    read_latest_panel,
)

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
pytestmark = [pytest.mark.e2e, requires_models]


@pytest.fixture(scope="module")
def scenario_server(e2e_dist, tmp_path_factory):
    """The bundle (generated into tmp by Task 3's script) and ONE uvicorn whose scenario root
    is that bundle directory. Never the developer's ``demo/bundles/`` and never the 8000 port."""
    from e2e_support import start_server

    try:
        data_root, _ = resolve_data_root()
    except DataRootError:
        pytest.skip("State Farm data root not available")
    if data_root is None:
        pytest.skip("State Farm data root not available")
    bundles = tmp_path_factory.mktemp("scenario-bundles")
    done = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), "e2e_short",
         "--out", str(bundles), "--data-root", str(data_root)],
        capture_output=True, text=True, timeout=600,
    )
    assert done.returncode == 0, (
        f"scripts/build_dataset_replay.py failed ({done.returncode}):\n"
        f"{done.stdout}\n{done.stderr}")
    server = start_server(tmp_path_factory.mktemp("constructed-e2e-server"),
                          extra_env={"DRA_SCENARIO_ROOT": str(bundles)})
    try:
        yield server
    finally:
        server.stop()


def text_of(page, selector: str) -> str:
    locator = page.locator(selector)
    return locator.inner_text() if locator.count() else ""


def select_constructed_scenario(chrome: Chrome) -> None:
    """The clicks a person makes to reach a loaded constructed scenario (plan Task 8 Step 1)."""
    page = chrome.page
    page.select_option('select[aria-label="Data mode"]', value="CONSTRUCTED_SCENARIO_RUNTIME")
    chrome.wait_until(
        lambda: page.locator('select[aria-label="Scenario"] option[value="e2e_short"]').count() == 1,
        "the Scenario dropdown to offer e2e_short", 30)
    page.select_option('select[aria-label="Scenario"]', value="e2e_short")
    chrome.wait_until(
        lambda: page.locator('.topbar-actions button.button--primary').is_enabled(),
        "Start Monitoring to be enabled (frames preloaded)", 120)


def test_the_mode_is_offered_and_the_scenario_loads(pw, scenario_server):
    chrome = Chrome(pw, scenario_server, FAKE_CAMERA_ARGS)
    try:
        chrome.open()
        page = chrome.page
        labels = page.locator('select[aria-label="Data mode"] option').all_text_contents()
        assert labels == ["Live camera (trained models)", "Constructed scenario"]
        select_constructed_scenario(chrome)
        option = page.locator('select[aria-label="Scenario"] option[value="e2e_short"]')
        assert page.locator('select[aria-label="Scenario"]').input_value() == "e2e_short"
        assert option.inner_text() == "e2e_short · 12 s · 3 segments"
        # The constructed scenario shows no note sentence: the player's banner says "not live".
        assert page.locator(".runtime-panel > p").count() == 0
    finally:
        chrome.close()


def test_a_full_run(pw, scenario_server):
    chrome = Chrome(pw, scenario_server, FAKE_CAMERA_ARGS)
    run = LiveRun(chrome)  # reuse its plumbing for assert_reconciled (never collect/settle)
    try:
        chrome.open()
        select_constructed_scenario(chrome)
        page = chrome.page
        assert text_of(page, ".topbar-mode") == "CONSTRUCTED SCENARIO"
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(
            lambda: "CONSTRUCTED SCENARIO · not live" in text_of(page, ".scenario-badge"),
            "the not-live badge", 30)
        # The displayed Truth follows the manifest's segments (e2e_short: safe_driving ->
        # texting_right -> talking_phone_left), each for its 4 s.
        chrome.wait_until(
            lambda: "Truth: safe_driving" in text_of(page, ".scenario-truth"),
            "the first segment's truth line (safe_driving)", 30)
        chrome.wait_until(
            lambda: "Truth: texting_right" in text_of(page, ".scenario-truth"),
            "the second segment's truth line (texting_right)", 30)
        chrome.wait_until(
            lambda: "Scenario finished (12 s, 3 segments)" in text_of(page, ".scenario-caption"),
            "the scenario to finish", 120)
        # Finished means stopped: the loop pauses itself and sends nothing further.
        run.sid = chrome.tap.session_posts[-1].response["id"]
        chrome.wait(500)  # let the last in-flight delivery settle one way or the other
        calls = run.calls
        assert calls
        # The five homes of every window agree, over the windows the BROWSER received.
        # The loop's self-stop pauses at the finish: a response that crosses that pause
        # boundary is discarded by the loop (the same race a manual Pause has), so the
        # dashboard may show the window BEFORE the last answered one - it never shows a
        # window it did not process. The strip's "Stored records" mirrors its own Window
        # (the loop's total), and both stop one window earlier in that case. Like a Live
        # pause, the stopped session's last window also goes stale three seconds after it
        # was committed, and the stale panel replaces the latest-window panel; the strip
        # itself stays, so it is still readable then.
        last = str(len(calls))
        before_last = str(len(calls) - 1)
        chrome.wait_until(
            lambda: read_latest_panel(page)["strip"].get("Window") in (last, before_last),
            f"the dashboard to show window {last} (or {before_last})", 10)
        run.ui_latest = read_latest_panel(page)
        parties = Parties(run)
        received = {c.response["window_id"]: c.response for c in calls}
        server_ids = sorted(parties.db)
        assert all(i in server_ids for i in received)
        extra = [i for i in server_ids if i not in received]
        assert extra == [] or extra == [len(calls) + 1], f"unexpected server-only windows {extra}"
        diffs = parties_diffs(parties, received)
        assert not diffs, f"{len(diffs)} differences, first {diffs[:12]}"
        assert parties.export_json_top == {"session_id": run.sid}
        assert parties.latest["window_id"] == (len(calls) + 1 if extra else len(calls))
        # The dashboard shows the newest window the loop processed, which is the newest
        # the browser received, or the one before it when the self-stop discarded the last
        # response (the loop never shows a window it did not process). The strip's
        # "Stored records" mirrors its Window.
        shown = run.ui_latest["strip"]["Window"]
        assert shown in (last, before_last)
        assert run.ui_latest["strip"]["Stored records"] == shown
        chrome.wait(1500)
        assert len(run.calls) == len(calls), "the loop kept sending after the scenario finished"
        assert page.locator('.topbar-actions button.button--primary').is_enabled(), \
            "Start Monitoring is not re-enabled after the run stopped itself"
        # e2e_short's last segment is c4 = talking_phone_left (demo/scenarios/e2e_short.json).
        assert "Truth: talking_phone_left" in text_of(page, ".scenario-truth")
        assert chrome.stop_panel_text() is None
        # Every window is a constructed-scenario window whose images came from the dataset replay.
        assert [c.response["window_id"] for c in calls] == list(range(1, len(calls) + 1))
        assert all(c.response["operation_mode"] == "CONSTRUCTED_SCENARIO_RUNTIME" for c in calls)
        assert all(c.sent_body["image_base64"] is not None for c in calls)
        assert all(c.response["provenance"]["vision_source"] == "dataset_replay" for c in calls)
        # The ground-truth segment index passes through 0, 1, 2 in order.
        segment_path = [c.response["provenance"]["replay"]["segment_index"] for c in calls]
        assert segment_path[0] == 0 and segment_path[-1] == 2
        assert segment_path.count(1) > 0
        assert all(a <= b for a, b in zip(segment_path, segment_path[1:]))
    finally:
        chrome.close()


def test_a_long_pause_does_not_expire_the_evidence(pw, scenario_server):
    chrome = Chrome(pw, scenario_server, FAKE_CAMERA_ARGS)
    try:
        chrome.open()
        select_constructed_scenario(chrome)
        page = chrome.page
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: len(chrome.tap.answered()) >= 2, "two windows", 60)
        sid = chrome.tap.session_posts[0].response["id"]
        chrome.top_button("Pause").click()
        chrome.wait_until(
            lambda: page.locator('.topbar-actions button.button--primary').is_enabled(),
            "Start Monitoring to be re-enabled after Pause", 20)
        before = len(chrome.tap.answered(sid))
        chrome.wait(4000)  # a REAL pause, longer than the 3 s freshness tolerance
        assert len(chrome.tap.answered(sid)) == before, "a paused run must send nothing"
        chrome.top_button("Start Monitoring").click()  # resume the same session
        chrome.wait_until(lambda: len(chrome.tap.answered(sid)) > before,
                          "the first window after resume", 60)
        first = chrome.tap.answered(sid)[before]
        # The playback clock froze over the pause (rule: only Stop and Pause freeze it), so the
        # first window after resume is fresh on both branches despite the 4 s gap.
        assert first.response["modality_freshness"] == {"vision": "fresh", "telemetry": "fresh"}
        chrome.top_button("Pause").click()
    finally:
        chrome.close()


def test_live_is_still_the_default_on_reload(pw, scenario_server):
    chrome = Chrome(pw, scenario_server, FAKE_CAMERA_ARGS)
    try:
        chrome.open()
        mode = chrome.page.locator('select[aria-label="Data mode"]')
        assert mode.input_value() == "LIVE_MODEL_RUNTIME"
        select_constructed_scenario(chrome)
        assert mode.input_value() == "CONSTRUCTED_SCENARIO_RUNTIME"
        chrome.page.reload()
        chrome.wait_until(
            lambda: chrome.page.locator('select[aria-label="Data mode"]').input_value()
            == "LIVE_MODEL_RUNTIME",
            "Live to be the default after a reload", 20)
    finally:
        chrome.close()
