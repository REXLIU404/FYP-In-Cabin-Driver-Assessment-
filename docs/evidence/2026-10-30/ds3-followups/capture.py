"""Screenshots and computed-style checks for the DS-3 review follow-ups (2026-10-30).

Throw-away server and SQLite on a free port, Chromium's fake camera; never port 8000, never
backend/driver_risk.db*. Live mode only, so no dataset image appears in any screenshot.

Run from the repository root: .venv/bin/python docs/evidence/2026-10-30/ds3-followups/capture.py <out dir>
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
server = start_server(Path(tempfile.mkdtemp(prefix="ds3-followups-")))
BRAND_DISPLAY = "() => getComputedStyle(document.querySelector('.brand-copy')).display"
try:
    with sync_playwright() as pw:
        chrome = Chrome(pw, server, FAKE_CAMERA_ARGS)
        page, tap = chrome.page, chrome.tap
        page.set_viewport_size({"width": 1440, "height": 900})

        def view(name):
            page.get_by_role("button", name=name, exact=True).click(); chrome.wait(500)

        chrome.open(); chrome.wait(1000)
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: len(tap.answered()) >= 8, "eight Live windows", 90)
        chrome.top_button("Pause").click(); chrome.wait(800)

        print("Live note:", page.locator(".runtime-panel > p").first.inner_text())
        labels = page.eval_on_selector_all(
            ".badge-field > span:first-child", "els => els.map(e => e.innerText)")
        print("badge labels as rendered:", labels)
        print("DominantEvidence tooltip:",
              page.locator(".badge-field", has_text="DominantEvidence").first.get_attribute("title"))
        page.screenshot(path=str(OUT / "01-live-monitor.png"))

        view("Signal Inspector")
        print("Signal Inspector has 'Evidence Type':", "Evidence Type" in page.inner_text("body"))
        page.screenshot(path=str(OUT / "02-signal-inspector.png"))
        view("Risk Trends")
        print("Risk Trends headers:", page.eval_on_selector_all("thead th", "els => els.map(e => e.innerText)"))
        page.screenshot(path=str(OUT / "03-risk-trends.png"))
        view("Live Monitor")

        # R29: collapse the sidebar at full width, then narrow to 800 px (the 681-900 px range).
        page.get_by_role("button", name="Collapse sidebar").click(); chrome.wait(300)
        for width in (800, 700):
            page.set_viewport_size({"width": width, "height": 900}); chrome.wait(400)
            print(f"collapsed sidebar at {width} px: .brand-copy display =", page.evaluate(BRAND_DISPLAY))
        page.set_viewport_size({"width": 800, "height": 900}); chrome.wait(400)
        page.screenshot(path=str(OUT / "04-collapsed-sidebar-800px.png"))
        page.set_viewport_size({"width": 1440, "height": 900}); chrome.wait(300)
        page.get_by_role("button", name="Expand sidebar").click(); chrome.wait(300)
        page.set_viewport_size({"width": 800, "height": 900}); chrome.wait(400)
        print("expanded sidebar at 800 px: .brand-copy display =", page.evaluate(BRAND_DISPLAY))
        print("console errors:", chrome.console_errors, "page errors:", chrome.page_errors)
        chrome.close()
finally:
    server.stop()
print("saved:", sorted(p.name for p in OUT.glob("*.png")))
