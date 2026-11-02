"""Screenshots for e26e32a: a Data mode change leaves the session; no "not live" wording.

Throw-away server and SQLite on a free port, Chromium's fake camera, the developer's demo/bundles
(read only; viva_v1). Never port 8000, never backend/driver_risk.db*.

Run from the repository root: .venv/bin/python docs/evidence/2026-10-29/ui-mode-switch/capture.py <out dir>
"""
import sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend" / "tests"))
from e2e_support import FAKE_CAMERA_ARGS, Chrome, build_dist, start_server
from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
build_dist()
server = start_server(Path(tempfile.mkdtemp(prefix="ui-mode-switch-")),
                      extra_env={"DRA_SCENARIO_ROOT": str(REPO / "demo" / "bundles")})
try:
    with sync_playwright() as pw:
        chrome = Chrome(pw, server, FAKE_CAMERA_ARGS)
        page, tap = chrome.page, chrome.tap
        page.set_viewport_size({"width": 1440, "height": 900})

        def shot(name, locator=None):
            target = page.locator(locator) if locator else page
            target.screenshot(path=str(OUT / f"{name}.png"))

        def body() -> str:
            return page.inner_text("body")

        def run_windows(n: int) -> str:
            posts = len(tap.session_posts)
            chrome.top_button("Start Monitoring").click()
            chrome.wait_until(lambda: len(tap.session_posts) > posts
                              and tap.session_posts[-1].response is not None, "a session", 60)
            sid = tap.session_posts[-1].response["id"]
            chrome.wait_until(lambda: len(tap.answered(sid)) >= n, f"{n} windows", 120)
            return sid

        chrome.open(); chrome.wait(1000)
        # 1. Live: a few windows, the Vehicle Signals panel has no disclaimer sentence.
        live_sid = run_windows(5)
        chrome.top_button("Pause").click(); chrome.wait(800)
        signals = page.locator("section.panel", has_text="Vehicle Signals")
        print("Live Vehicle Signals text:", signals.inner_text().splitlines()[:3])
        shot("01-live-vehicle-signals", "section.panel:has-text('Vehicle Signals')")

        # 2. Switch to the scenario: the Live session leaves the screen.
        page.select_option('select[aria-label="Data mode"]', value="CONSTRUCTED_SCENARIO_RUNTIME")
        chrome.wait(800)
        print("after Live -> scenario: live sid on screen?", live_sid in body(),
              "| session strip:", page.locator(".session-strip").count())
        page.select_option('select[aria-label="Scenario"]', value="viva_v1")
        chrome.wait_until(lambda: page.locator(".topbar-actions button.button--primary").is_enabled(),
                          "frames preloaded", 300)
        shot("02-after-switch-to-scenario")

        # 3. The scenario running: badge text, no "not live" anywhere.
        scenario_sid = run_windows(15)
        print("badge:", page.locator(".scenario-badge").inner_text(),
              "| 'not live' on page:", "not live" in body().lower())
        shot("03-scenario-running")
        shot("04-scenario-vehicle-signals", "section.panel:has-text('Vehicle Signals')")
        chrome.top_button("Pause").click(); chrome.wait(800)

        # 4. Back to Live: the scenario run leaves the screen.
        page.select_option('select[aria-label="Data mode"]', value="LIVE_MODEL_RUNTIME"); chrome.wait(800)
        print("after scenario -> Live: scenario sid on screen?", scenario_sid in body(),
              "| topbar badge:", page.locator(".topbar-mode").count(),
              "| session strip:", page.locator(".session-strip").count())
        shot("05-after-switch-to-live")
        print("console errors:", chrome.console_errors, "page errors:", chrome.page_errors)
        chrome.close()
finally:
    server.stop()
print("saved:", sorted(p.name for p in OUT.glob("*.png")))
