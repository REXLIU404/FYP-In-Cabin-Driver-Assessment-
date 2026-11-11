"""Screenshots for the Live-only saved-session picker (throw-away server and database, fake camera).

Same environment as the end-to-end tests: one uvicorn on a free port and a temporary SQLite file
(never port 8000, never backend/driver_risk.db*). The scenario root is the developer's
demo/bundles (read only), so the scenario is viva_v1, as in the user's screenshot.

Run from the repository root: .venv/bin/python docs/evidence/2026-10-29/ui-scenario-sessions/capture.py <out dir>
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
server = start_server(Path(tempfile.mkdtemp(prefix="ui-scenario-sessions-")),
                      extra_env={"DRA_SCENARIO_ROOT": str(REPO / "demo" / "bundles")})
try:
    with sync_playwright() as pw:
        chrome = Chrome(pw, server, FAKE_CAMERA_ARGS)
        page = chrome.page
        page.set_viewport_size({"width": 1440, "height": 900})

        def shot(name):
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)

        def controls():
            return (page.get_by_role("button", name="Refresh saved sessions", exact=True).count(),
                    page.locator('select[aria-label="Saved live sessions"]').count())

        chrome.open(); chrome.wait(1500)
        print("Live controls (refresh, picker):", controls())
        shot("01-live-picker-shown")

        page.select_option('select[aria-label="Data mode"]', value="CONSTRUCTED_SCENARIO_RUNTIME")
        chrome.wait_until(
            lambda: page.locator('select[aria-label="Scenario"] option[value="viva_v1"]').count() == 1,
            "the Scenario dropdown to offer viva_v1", 30)
        page.select_option('select[aria-label="Scenario"]', value="viva_v1")
        chrome.wait_until(lambda: page.locator(".topbar-actions button.button--primary").is_enabled(),
                          "Start Monitoring to be enabled (frames preloaded)", 300)
        print("Scenario controls (refresh, picker):", controls())
        shot("02-scenario-picker-hidden")

        page.get_by_role("button", name="Signal Inspector", exact=True).click(); chrome.wait(500)
        print("Scenario empty hint:", page.locator(".empty-state p").first.inner_text())
        shot("03-scenario-empty-hint")

        page.get_by_role("button", name="Live Monitor", exact=True).click(); chrome.wait(300)
        page.select_option('select[aria-label="Data mode"]', value="LIVE_MODEL_RUNTIME"); chrome.wait(800)
        print("Back to Live, controls (refresh, picker):", controls())
        shot("04-back-to-live-picker-shown")
        print("console errors:", chrome.console_errors, "page errors:", chrome.page_errors)
        chrome.close()
finally:
    server.stop()
print("saved:", sorted(p.name for p in OUT.glob("*.png")))
