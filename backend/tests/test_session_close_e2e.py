"""The End Session button in a real browser: start -> end -> start again.

One monitoring run, driven by clicks on the dashboard served by the e2e uvicorn
(fake camera, throw-away database). The test checks the lifecycle the user sees:
the first session is closed, no window is added to it afterwards, and the next
Start Monitoring creates a different session that starts accepting windows.
"""
from pathlib import Path

import pytest

from e2e_support import FAKE_CAMERA_ARGS, Chrome, db_count

MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml/outputs"
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)
pytestmark = [pytest.mark.e2e, requires_models]

SESSION_STATUS = "SELECT status FROM sessions WHERE id=?"
SESSION_ROWS = "SELECT COUNT(*) FROM inference_records WHERE session_id=?"


def test_end_session_then_start_creates_a_new_session(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)
    try:
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: len(chrome.tap.answered()) >= 3,
                          "three windows of the first session", 90)
        first = chrome.tap.session_posts[0].response["id"]
        assert db_count(e2e_server, SESSION_STATUS, first) == "ACTIVE"

        chrome.top_button("End Session").click()
        chrome.wait_until(lambda: chrome.page.locator(".session-status").count() == 1,
                          "the Session ended label", 30)
        assert chrome.page.locator(".session-status").inner_text().strip() == "Session ended"
        chrome.wait_until(lambda: db_count(e2e_server, SESSION_STATUS, first) == "CLOSED",
                          "the first session to be CLOSED", 30)

        # Let any request that was already on the wire settle before the baseline.
        chrome.wait(1000)
        old_calls = len(chrome.tap.answered(first))
        old_rows = db_count(e2e_server, SESSION_ROWS, first)
        posts = len(chrome.tap.session_posts)

        def second_created() -> bool:
            return (len(chrome.tap.session_posts) == posts + 1
                    and chrome.tap.session_posts[-1].outcome == "ok")

        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(second_created, "the second session to be created", 60)
        second = chrome.tap.session_posts[-1].response["id"]
        assert second != first
        chrome.wait_until(lambda: len(chrome.tap.answered(second)) >= 2,
                          "two windows of the second session", 90)

        assert db_count(e2e_server, SESSION_STATUS, first) == "CLOSED"
        assert db_count(e2e_server, SESSION_STATUS, second) == "ACTIVE"
        assert len(chrome.tap.answered(first)) == old_calls, "the closed session got a new window"
        assert db_count(e2e_server, SESSION_ROWS, first) == old_rows
        assert chrome.console_errors == [] and chrome.page_errors == []
    finally:
        chrome.close()
