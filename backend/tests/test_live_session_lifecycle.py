"""ST-SESSION-01 (sprint plan v3, W5 / G-W5-A): the session lifecycle in a real browser.

One monitoring run, driven by clicks on the dashboard served by the e2e uvicorn (fake camera,
throw-away database), walks the whole lifecycle; the tests then read what it recorded:

  A  Start Monitoring -> session A; the Signal Inspector opens on the newest window.
     Pause, wait 2.5 s, Start again -> RESUMED: still A, window ids continue, the telemetry
     cursor opens a new segment (its first sequence number is past every one A has sent).
  B  New Session -> session B, numbered from window 1; A gets nothing more.
     Refresh saved sessions, pick A -> A is shown read-only: no /infer is sent, and the
     Inspector and the Explanation open on A's newest window.
  C  Start Monitoring after loading A -> a NEW session C (a loaded session is never appended to);
     A and B get nothing more. Pinning a window in the Inspector keeps it while C runs on.

Every switch is made on a quiet server (``LiveRun.settle``: the loop's next request is held at the
network layer, then Pause), so each database holds exactly the windows the browser received and
the five-way reconciliation of part 2a holds for A, B and C separately.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from e2e_support import FAKE_CAMERA_ARGS, Chrome, LiveRun, assert_reconciled, db_count, fixed

MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml/outputs"
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)
pytestmark = [pytest.mark.e2e, requires_models]

ROWS_SQL = "SELECT COUNT(*) FROM inference_records WHERE session_id=?"
LIST_AND_SELECTED_JS = r"""() => {
  const buttons = [...document.querySelectorAll('.window-list button')];
  const number = (b) => { const m = b && b.textContent.match(/Window (\d+)/); return m ? Number(m[1]) : null; };
  return { first: number(buttons[0]), selected: number(document.querySelector('.window-list button.is-selected')),
           count: buttons.length };
}"""


class Lifecycle:
    def __init__(self, chrome: Chrome):
        self.chrome, self.page, self.tap, self.server = chrome, chrome.page, chrome.tap, chrome.server
        self.a, self.b, self.c = LiveRun(chrome), LiveRun(chrome), LiveRun(chrome)
        self.error: str | None = None
        self.obs: dict = {}

    def view(self, name: str) -> None:
        self.page.get_by_role("button", name=name, exact=True).click()
        self.chrome.wait(300)

    def quiet(self, run: LiveRun, sid: str) -> None:
        """Hold the loop's next request, wait for the dashboard to show the last stored window, Pause."""
        run.sid = sid
        self.view("Live Monitor")
        run.settle()

    def new_post(self, before: int, what: str) -> str:
        self.chrome.wait_until(lambda: len(self.tap.session_posts) == before + 1
                               and self.tap.session_posts[-1].outcome == "ok", what, 30)
        return self.tap.session_posts[-1].response["id"]

    def drive(self) -> None:
        ch, tap, page, obs = self.chrome, self.tap, self.page, self.obs
        rows = lambda sid: db_count(self.server, ROWS_SQL, sid)  # noqa: E731

        # A: start; the Inspector follows the newest window.
        ch.open()
        ch.top_button("Start Monitoring").click()
        ch.wait_until(lambda: len(tap.answered()) >= 6, "six windows of session A", 60)
        a = tap.session_posts[0].response["id"]
        self.view("Signal Inspector")
        ch.wait_until(lambda: (page.evaluate(LIST_AND_SELECTED_JS)["count"] or 0) >= 6, "the Inspector list", 10)
        obs["running_list"] = page.evaluate(LIST_AND_SELECTED_JS)
        page.get_by_role("button", name="Window 2", exact=True).click()  # pin a window of A
        obs["a_pinned"] = page.evaluate(LIST_AND_SELECTED_JS)

        # A: pause, wait, resume.
        self.quiet(self.a, a)
        obs["a_before_resume"] = len(tap.answered(a))
        obs["a_seq_before"] = max(c.sent_body["telemetry_seq"] for c in tap.answered(a) if "telemetry_seq" in c.sent_body)
        posts = len(tap.session_posts)
        ch.wait(2500)  # a cursor that did not freeze on Pause would have moved a sample on
        ch.top_button("Start Monitoring").click()
        ch.wait_until(lambda: len(tap.answered(a)) >= obs["a_before_resume"] + 5, "five more windows of A after resuming", 60)
        obs["posts_on_resume"] = len(tap.session_posts) - posts
        self.view("Signal Inspector")
        obs["a_pin_after_resume"] = page.evaluate(LIST_AND_SELECTED_JS)

        # B: New Session.
        self.quiet(self.a, a)
        obs["a_rows_before_b"] = rows(a)
        posts = len(tap.session_posts)
        ch.top_button("New Session").click()
        b = self.new_post(posts, "session B")
        ch.wait_until(lambda: len(tap.answered(b)) >= 5, "five windows of session B", 60)
        self.view("Signal Inspector")
        obs["b_list"] = page.evaluate(LIST_AND_SELECTED_JS)
        page.get_by_role("button", name="Window 2", exact=True).click()  # pin a window of B before loading A
        obs["b_pinned"] = page.evaluate(LIST_AND_SELECTED_JS)
        self.quiet(self.b, b)
        obs["a_rows_after_b"] = rows(a)

        # Load A from the saved list.
        page.get_by_role("button", name="Refresh saved sessions", exact=True).click()
        ch.wait_until(lambda: page.locator(f'select[aria-label="Saved live sessions"] option[value="{a}"]').count() == 1,
                      "session A in the saved list", 15)
        infer_before = len(tap.infer)
        page.get_by_label("Saved live sessions").select_option(a)
        ch.wait_until(lambda: page.locator(".session-strip").inner_text().count(a) == 1, "the dashboard to show session A", 15)
        ch.wait(2000)
        obs["infer_after_load"] = len(tap.infer) - infer_before
        obs["a_total"] = len(tap.answered(a))
        self.view("Signal Inspector")
        obs["loaded_list"] = page.evaluate(LIST_AND_SELECTED_JS)
        self.view("Explanation")
        obs["loaded_explanation"] = page.evaluate(r"""() => Object.fromEntries([...document.querySelectorAll('.summary-metric-grid > div')]
            .map((d) => [d.querySelector('span')?.textContent.trim(), d.lastElementChild?.textContent.trim()]))""")
        self.view("Live Monitor")

        # C: Start after loading A -> a new session; then pin a window while C runs.
        obs["rows_before_c"] = (rows(a), rows(b))
        posts = len(tap.session_posts)
        ch.top_button("Start Monitoring").click()
        c = self.new_post(posts, "session C")
        ch.wait_until(lambda: len(tap.answered(c)) >= 8, "eight windows of session C", 60)
        self.view("Signal Inspector")
        page.get_by_role("button", name="Window 2", exact=True).click()
        pinned_at = len(tap.answered(c))
        ch.wait_until(lambda: len(tap.answered(c)) >= pinned_at + 5, "five more windows of C after the pin", 60)
        obs["pinned_list"] = page.evaluate(LIST_AND_SELECTED_JS)
        self.quiet(self.c, c)
        obs["rows_after_c"] = (rows(a), rows(b))
        obs["sessions"] = (a, b, c)


@pytest.fixture(scope="class")
def life(pw, e2e_server):
    chrome = Chrome(pw, e2e_server, FAKE_CAMERA_ARGS)
    lifecycle = Lifecycle(chrome)
    try:
        try:
            lifecycle.drive()
        except Exception as exc:  # a failed wait or a Playwright timeout: the first test reports it
            lifecycle.error = str(exc) if isinstance(exc, AssertionError) else f"{type(exc).__name__}: {exc}"
        yield lifecycle
    finally:
        chrome.close()


class TestStSession01:
    def test_01_three_sessions_and_nothing_failed(self, life):
        assert life.error is None, life.error
        a, b, c = life.obs["sessions"]
        assert len({a, b, c}) == 3
        assert [p.outcome for p in life.tap.session_posts] == ["ok", "ok", "ok"]
        for sid in (a, b, c):
            assert db_count(life.server, "SELECT COUNT(*) FROM fault_events WHERE session_id=?", sid) == 0
        assert all(call.attempt == "1" for call in life.tap.infer)
        assert life.chrome.console_errors == [] and life.chrome.page_errors == []

    def test_02_a_running_session_shows_its_newest_window(self, life):
        assert life.error is None, life.error
        shown = life.obs["running_list"]
        assert shown["selected"] is not None and shown["selected"] == shown["first"], shown

    def test_03_pause_and_start_resume_the_same_session(self, life):
        assert life.error is None, life.error
        a = life.obs["sessions"][0]
        assert life.obs["posts_on_resume"] == 0, "Start after Pause created a new session"
        calls = life.tap.answered(a)
        assert [call.response["window_id"] for call in calls] == list(range(1, len(calls) + 1))
        # The cursor froze on Pause and opened a new segment on Start: the first sample after the
        # resume is past every sample sent before it (one past the frozen position, which is at
        # most one ahead of the last one sent), never a repeat of an old sequence number.
        resumed = calls[life.obs["a_before_resume"]:]
        first_seq = next(call.sent_body["telemetry_seq"] for call in resumed if "telemetry_seq" in call.sent_body)
        assert life.obs["a_seq_before"] < first_seq <= life.obs["a_seq_before"] + 2, (life.obs["a_seq_before"], first_seq)
        assert all(call.response["provenance"]["telemetry_obs"] == "new" for call in resumed[:1])

    def test_04_new_session_starts_at_window_1_and_leaves_the_old_one_alone(self, life):
        assert life.error is None, life.error
        a, b, _ = life.obs["sessions"]
        assert [call.response["window_id"] for call in life.tap.answered(b)][:5] == [1, 2, 3, 4, 5]
        assert life.obs["a_rows_after_b"] == life.obs["a_rows_before_b"]

    def test_05_a_loaded_session_is_read_only_and_opens_on_its_newest_window(self, life):
        assert life.error is None, life.error
        a = life.obs["sessions"][0]
        assert life.obs["infer_after_load"] == 0, "loading a saved session sent /infer requests"
        newest = life.obs["a_total"]
        shown = life.obs["loaded_list"]
        assert shown["selected"] == shown["first"] == newest, shown
        record = life.tap.answered(a)[newest - 1].response
        explanation = life.obs["loaded_explanation"]
        if record["assessment_available"]:
            assert explanation["RiskScore"] == f"{fixed(record['RiskScore'], 1)} / 100"

    def test_06_start_after_loading_creates_a_new_session(self, life):
        assert life.error is None, life.error
        _, _, c = life.obs["sessions"]
        assert [call.response["window_id"] for call in life.tap.answered(c)][:3] == [1, 2, 3]
        assert life.obs["rows_after_c"] == life.obs["rows_before_c"], "a loaded or earlier session got new windows"

    def test_07_a_pinned_window_stays_selected_while_new_windows_arrive(self, life):
        assert life.error is None, life.error
        shown = life.obs["pinned_list"]
        assert shown["selected"] == 2 and shown["first"] > 2, shown

    def test_08_each_session_reconciles_across_the_five_homes(self, life):
        assert life.error is None, life.error
        for run in (life.a, life.b, life.c):
            assert_reconciled(run)

    def test_09_a_pin_survives_pause_and_resume_but_not_a_session_switch(self, life):
        """Review Focus 3: a pinned window stays pinned within its session (Pause / Start resumes the
        same session), and every session switch - New Session, loading a saved session - drops the pin
        and opens on the newest window. Window 2 exists in A and in B, so a pin that survived a switch
        would still show 'Window 2' selected."""
        assert life.error is None, life.error
        assert life.obs["a_pinned"]["selected"] == 2, life.obs["a_pinned"]
        assert life.obs["a_pin_after_resume"]["selected"] == 2, life.obs["a_pin_after_resume"]
        after_new = life.obs["b_list"]
        assert after_new["selected"] == after_new["first"] and after_new["first"] >= 5, after_new
        assert life.obs["b_pinned"]["selected"] == 2, life.obs["b_pinned"]
        loaded = life.obs["loaded_list"]  # loading A happened while B was pinned to window 2
        assert loaded["selected"] == loaded["first"] == life.obs["a_total"], loaded

