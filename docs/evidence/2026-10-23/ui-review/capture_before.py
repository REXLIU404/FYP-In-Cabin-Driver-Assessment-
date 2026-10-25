"""Screenshots of the real dashboard for the UI review (throw-away server and database, fake camera)."""
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, "/Users/liu/Desktop/FYP2-Live-System/backend/tests")
from e2e_support import FAKE_CAMERA_ARGS, Chrome, build_dist, start_server
from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1])
build_dist()
server = start_server(Path(tempfile.mkdtemp(prefix="ui-review-")))
VIEWS = ["Live Monitor", "Signal Inspector", "Risk Trends", "Explanation", "Configuration"]
try:
    with sync_playwright() as pw:
        chrome = Chrome(pw, server, FAKE_CAMERA_ARGS)
        page = chrome.page
        def shot(name, full=True):
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
        def view(name):
            page.get_by_role("button", name=name, exact=True).click(); chrome.wait(500)
        chrome.open(); chrome.wait(1500)
        shot("00-before-start")
        chrome.top_button("Start Monitoring").click()
        chrome.wait(12000)
        for i, v in enumerate(VIEWS, 1):
            view(v); shot(f"{i:02d}-{v.lower().replace(' ', '-')}")
        view("Live Monitor")
        page.get_by_role("button", name="Stop Camera", exact=True).click(); chrome.wait(4000)
        shot("06-camera-stopped")
        page.set_viewport_size({"width": 390, "height": 844}); chrome.wait(800)
        shot("07-mobile-live-monitor")
        view("Signal Inspector"); shot("08-mobile-inspector")
        page.set_viewport_size({"width": 1280, "height": 1000}); chrome.wait(500)
        view("Live Monitor")
        chrome.top_button("Pause").click(); chrome.wait(800)
        chrome.tap.abort_infer = 3
        chrome.top_button("Start Monitoring").click()
        chrome.wait_until(lambda: chrome.stop_panel().count() == 1, "stop panel", 40, tolerate_stop_panel=True)
        chrome.tap.abort_infer = 0
        shot("09-stop-panel")
        print("console errors:", chrome.console_errors, "page errors:", chrome.page_errors)
        chrome.close()
finally:
    server.stop()
print("saved:", sorted(p.name for p in OUT.glob("*.png")))
