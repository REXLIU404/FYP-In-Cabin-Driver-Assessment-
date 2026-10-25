"""FIX-BACKEND-REACH, part D: "the backend is not running" is reported as exactly that.

The incident: only ``npm run dev`` was started (Vite, 5173), nothing listened on 8000. Vite's
``/api`` proxy cannot connect, so it answers by itself: HTTP 500, ``Content-Type: text/plain``,
empty body. The dashboard filed that under ``model_runtime`` and told the user about "a model or
storage error on the server ... while processing the frame". The earlier end-to-end tests could not
have seen it: they serve the page and the API from ONE uvicorn (the deployed shape), where a dead
backend means a page that never loads.

``test_e2_a_dev_proxy_answer_...``  the dev-proxy shape, by a Playwright route that returns exactly
    what Vite returns (measured with curl against a Vite whose proxy target was a closed port, see
    the task report): 500, ``text/plain``, no body, no ``X-DRA-Backend``.
``test_e2_a_real_backend_restart_...``  the real thing: a separate uvicorn is terminated mid-run and
    started again on the same database and the same port; Retry must pick the SAME session and the
    SAME frozen request up (delivery 4, stored once).

Both use the Playwright tap of ``e2e_support`` and the same stop-panel wording the part 2a tests
read. Expected values are literals.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

from e2e_support import (
    FAKE_CAMERA_ARGS,
    Chrome,
    api_client,
    db_count,
    db_records,
    session_ids,
    start_server,
)

MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml/outputs"
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)
pytestmark = [pytest.mark.e2e, requires_models]

# What the stop panel must NOT say when the backend simply is not there: the words of the two
# categories it used to be confused with, and a server message that no server wrote. (The setup
# Retry note legitimately says "the model check", so the bare word "model" is not forbidden.)
WRONG_WORDS = re.compile(r"Server message|model or storage|model_runtime|storage|processing the frame")


def test_the_deployed_backend_marks_its_page_and_every_kind_of_answer(e2e_server):
    """Over real HTTP, from the real uvicorn that serves the built ``dist/``: the page itself, a 200,
    a 404 and a validation 422 all carry the marker (the unit tests do the same in-process)."""
    with api_client(e2e_server) as client:
        for path, status in (("/", 200), ("/api/health", 200), ("/api/models", 200),
                             ("/api/sessions/no-such-session", 404), ("/api/faults?limit=0", 422)):
            response = client.get(path)
            assert response.status_code == status, (path, response.status_code)
            assert response.headers.get("x-dra-backend") == "1", (path, dict(response.headers))


# --------------------------------------------------------------------------------------
# 1. The dev-proxy shape
# --------------------------------------------------------------------------------------
def test_e2_a_dev_proxy_answer_without_the_backend_is_reported_as_backend_unreachable(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)
    state = {"down": True, "models_calls": 0}

    def vite_proxy_with_no_backend(route):
        """Vite's own answer when the proxy target refuses the connection (measured): HTTP 500,
        ``Vary: Origin``, ``Content-Type: text/plain``, empty body - and no ``X-DRA-Backend``."""
        if not state["down"]:
            route.fallback()  # on to the tap, which lets the request through to the real server
            return
        state["models_calls"] += 1
        route.fulfill(status=500, headers={"Content-Type": "text/plain", "Vary": "Origin"}, body="")

    # Registered after the tap's `**/api/**`, so it is consulted first.
    chrome.page.route("**/api/models", vite_proxy_with_no_backend)
    try:
        sessions_before = session_ids(e2e_server)
        chrome.open()
        # The fake answers exactly like the proxy: seen from the page, not from the route's arguments.
        shape = chrome.page.evaluate("""async () => {
            const r = await fetch('/api/models');
            return { status: r.status, type: r.headers.get('content-type'), marker: r.headers.get('x-dra-backend'),
                     body: await r.text() };
        }""")
        assert shape == {"status": 500, "type": "text/plain", "marker": None, "body": ""}
        state["models_calls"] = 0

        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: chrome.stop_panel().count() == 1, "the stop panel for a backend that is not there",
                          30, tolerate_stop_panel=True)
        panel = chrome.stop_panel().inner_text()

        assert "Monitoring stopped: The backend cannot be reached" in panel
        assert "Category: transport" in panel
        assert "Failed during setup, before any request was sent" in panel
        assert ("Details: the API proxy or a gateway answered HTTP 500 and the backend did not; "
                "is the backend running?") in panel
        assert "Retry repeats the setup: the model check, then the session." in panel
        assert not WRONG_WORDS.search(panel), panel
        assert "(HTTP 500)" not in panel  # the 500 was the proxy's, not the backend's
        # Setup stopped at the model check: no session, no request.
        assert state["models_calls"] >= 1
        assert chrome.tap.session_posts == [] and chrome.tap.infer == []
        assert session_ids(e2e_server) == sessions_before

        # The backend "comes back": Retry repeats the setup, creates ONE session, and the windows flow.
        state["down"] = False
        chrome.stop_panel().get_by_role("button", name="Retry", exact=True).click()
        chrome.wait_until(lambda: len(chrome.tap.answered()) >= 3 or len(chrome.tap.session_posts) > 1,
                          "three windows after Retry", 60, tolerate_stop_panel=True)
        assert len(chrome.tap.session_posts) == 1, "Retry created more than one session"
        sid = chrome.tap.session_posts[0].response["id"]
        assert session_ids(e2e_server) - sessions_before == {sid}
        assert [c.response["window_id"] for c in chrome.tap.answered(sid)][:3] == [1, 2, 3]
        assert chrome.stop_panel().count() == 0
        assert chrome.page.get_by_text("Monitoring active", exact=True).count() == 1
        assert db_count(e2e_server, "SELECT COUNT(*) FROM fault_events WHERE session_id=?", sid) == 0
    finally:
        chrome.close()


def test_the_backends_own_500_is_still_a_server_error_not_an_unreachable_backend(pw, e2e_server):
    """The opposite direction: an answer WITH the marker keeps its D02 category. A route that returns
    what the backend returns for a model failure (500, JSON detail, marker) must still read as
    'The server failed ...' with the server's own message."""
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)

    def backend_500(route):
        route.fulfill(status=500, headers={"Content-Type": "application/json", "X-DRA-Backend": "1"},
                      body='{"detail": "Vision model failed during inference"}')

    chrome.page.route("**/api/models", backend_500)
    try:
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: chrome.stop_panel().count() == 1, "the stop panel for the backend's own 500", 30,
                          tolerate_stop_panel=True)
        panel = chrome.stop_panel().inner_text()
        assert "Monitoring stopped: The server failed while starting the session" in panel
        assert "Category: model_runtime (HTTP 500)" in panel
        assert "Server message: Vision model failed during inference" in panel
        assert "processing the frame" not in panel
        assert "backend cannot be reached" not in panel
    finally:
        chrome.close()


# --------------------------------------------------------------------------------------
# 2. A real stop and restart of the backend process
# --------------------------------------------------------------------------------------
def test_e2_a_real_backend_restart_on_the_same_database_and_port_is_resumed_by_retry(pw, e2e_dist, tmp_path):
    workdir = tmp_path / "restart-server"
    workdir.mkdir()
    server = start_server(workdir)  # a server of its own: never the shared e2e_server
    port = urlparse(server.base_url).port
    servers = [server]
    chrome = Chrome(pw, server, FAKE_CAMERA_ARGS)
    try:
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: len(chrome.tap.answered()) >= 4, "four windows before the backend is stopped", 60)
        sid = chrome.tap.session_posts[0].response["id"]

        # --- the backend process is terminated ------------------------------------------
        server.stop()
        assert server.process.poll() is not None, "the uvicorn process is still alive"
        chrome.wait_until(lambda: chrome.stop_panel().count() == 1,
                          "the stop panel after three deliveries to a dead backend", 90, tolerate_stop_panel=True)
        panel = chrome.stop_panel().inner_text()

        frozen_calls = [c for c in chrome.tap.infer if c.outcome == "unreachable"]
        assert len(frozen_calls) == 3, [(c.number, c.attempt, c.outcome) for c in chrome.tap.infer]
        frozen = frozen_calls[0]
        assert [c.attempt for c in frozen_calls] == ["1", "2", "3"]
        assert len({c.request_id for c in frozen_calls}) == 1 and len({c.raw for c in frozen_calls}) == 1
        assert "Monitoring stopped: The backend cannot be reached" in panel
        assert "Category: transport" in panel
        assert f"Request id: {frozen.request_id}" in panel
        assert "Deliveries: 3 of 3" in panel
        assert "Retry re-sends this same request to the same session." in panel
        assert not WRONG_WORDS.search(panel), panel

        # What the database holds while the backend is down: the windows that were stored, and none
        # of the frozen request (no process was there to store it).
        stored_before = db_records(server, sid)
        stored = len(stored_before)
        assert stored >= 4
        assert [r["window_id"] for r in stored_before] == list(range(1, stored + 1))
        assert all(r["request_id"] != frozen.request_id for r in stored_before)
        assert session_ids(server) == {sid}

        # --- the same database, the same port ---------------------------------------------
        restarted = start_server(workdir, port=port, log_name="uvicorn-restarted.log")
        servers.append(restarted)
        chrome.server = restarted
        assert restarted.base_url == server.base_url and restarted.db_path == server.db_path
        assert session_ids(restarted) == {sid}, "the session did not survive the restart"
        with api_client(restarted) as client:
            meta = client.get(f"/api/sessions/{sid}").json()
        assert meta["total_windows"] == stored

        # --- Retry ----------------------------------------------------------------------
        answered_before = len(chrome.tap.answered(sid))
        chrome.stop_panel().get_by_role("button", name="Retry", exact=True).click()
        chrome.wait_until(lambda: len(chrome.tap.answered(sid)) >= answered_before + 4 or len(chrome.tap.session_posts) > 1,
                          "the retried window and three more", 60, tolerate_stop_panel=True)

        # The same session: Retry did not start a new one.
        assert len(chrome.tap.session_posts) == 1, "Retry created a new session instead of resuming this one"
        assert session_ids(restarted) == {sid}
        # The same frozen request, delivery number 4, byte for byte.
        deliveries = [c for c in chrome.tap.infer if c.request_id == frozen.request_id]
        assert [c.attempt for c in deliveries] == ["1", "2", "3", "4"]
        assert [c.outcome for c in deliveries] == ["unreachable", "unreachable", "unreachable", "ok"]
        retried = deliveries[3]
        assert retried.raw == frozen.raw
        assert retried.status == 201 and retried.response["window_id"] == stored + 1
        # Stored exactly once, and the window ids are still 1..N with no repeat.
        assert db_count(restarted, "SELECT COUNT(*) FROM inference_records WHERE session_id=? AND request_id=?",
                        sid, frozen.request_id) == 1
        after = db_records(restarted, sid)
        assert [r["window_id"] for r in after] == list(range(1, len(after) + 1))
        assert len({r["request_id"] for r in after}) == len(after)
        assert after[:stored] == stored_before, "a window written before the restart changed"
        assert after[stored]["request_id"] == frozen.request_id
        # The loop runs again: new requests of their own, each on its first delivery, same session.
        later = [c for c in chrome.tap.answered(sid) if c.number > retried.number]
        assert len(later) >= 3
        assert all(c.attempt == "1" and c.request_id != frozen.request_id for c in later)
        assert chrome.stop_panel().count() == 0
        assert chrome.page.get_by_text("Monitoring active", exact=True).count() == 1
        assert chrome.page.locator(".session-strip").inner_text().count(sid) == 1
        # The dead backend recorded nothing about the failed deliveries; the restarted one saw only successes.
        assert db_count(restarted, "SELECT COUNT(*) FROM fault_events WHERE session_id=?", sid) == 0
    finally:
        chrome.close()
        for each in servers:
            each.stop()
