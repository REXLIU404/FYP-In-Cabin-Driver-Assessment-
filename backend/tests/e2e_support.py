"""Support code for ``test_live_e2e.py`` (Task 10 part 2a) and ``test_live_single_branch.py`` (part 2b):
the one-uvicorn server, a Chromium wrapper with a request tap, readers for the five places a window
lives, one monitoring run (``LiveRun``) with the five-way reconciliation (``Parties`` /
``assert_reconciled``), and the display-format oracle.

Nothing here touches product code. Everything the tests need that the product does not offer -
recording the ``/infer`` bodies, failing a request, holding one, dispatching a synthetic
``ended`` event, counting ``requestVideoFrameCallback`` callbacks - is done from the outside:
Playwright routes and an init script injected into the page.

This module does not import ``playwright`` or ``httpx`` at module level (``Chrome`` is handed a
started Playwright by the ``pw`` fixture of the test module), so importing it is free for a run
that has no end-to-end test in it.
"""
from __future__ import annotations

import atexit
import csv
import hashlib
import io
import json
import os
import re
import shutil
import socket
import sqlite3
import statistics
import subprocess
import sys
import time
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent

# The fake camera of every run. ``--use-fake-device-for-media-stream`` alone is a 20 fps pattern
# generator; ``=fps=5`` slows it to 5 fps (measured, see the Task 10 part 2a report), which makes
# the 10 Hz request loop outrun the camera so that a frame is sometimes sent twice (a REPEAT).
FAKE_CAMERA_ARGS = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
SLOW_FAKE_CAMERA_ARGS = ["--use-fake-device-for-media-stream=fps=5", "--use-fake-ui-for-media-stream"]


# --------------------------------------------------------------------------------------
# The server
# --------------------------------------------------------------------------------------
def build_dist() -> None:
    """``npm run build``. ``dist/`` is git-ignored and may be stale, so every end-to-end session
    builds the CURRENT frontend first; the tests then run against what this just produced."""
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm is not on PATH: the end-to-end tests need `npm run build`")
    done = subprocess.run([npm, "run", "build"], cwd=REPO, capture_output=True, text=True, timeout=600)
    if done.returncode != 0:
        raise RuntimeError(f"`npm run build` failed ({done.returncode}):\n{done.stdout[-3000:]}\n{done.stderr[-3000:]}")
    if not (REPO / "dist" / "index.html").is_file():
        raise RuntimeError("`npm run build` succeeded but dist/index.html does not exist")


def _free_port() -> int:
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Server:
    """One uvicorn process with a throw-away database and fault sink."""

    def __init__(self, base_url: str, db_path: Path, sink_path: Path, log_path: Path, process):
        self.base_url, self.db_path, self.sink_path, self.log_path = base_url, db_path, sink_path, log_path
        self.process = process

    def log_tail(self, lines: int = 40) -> str:
        try:
            return "\n".join(self.log_path.read_text(errors="replace").splitlines()[-lines:])
        except OSError:
            return "(no server log)"

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=15)


def start_server(workdir: Path, *, port: int | None = None, log_name: str = "uvicorn.log") -> Server:
    """Start one uvicorn on a throw-away database in ``workdir``.

    Called with just a directory it is what the shared ``e2e_server`` fixture always did: a free
    port, a new ``e2e.db``. A restart test (FIX-BACKEND-REACH) calls it a second time with the SAME
    ``workdir`` and ``port`` - and a different ``log_name``, so the first process's log survives -
    to bring the backend back on the very same database and address."""
    import httpx

    port = _free_port() if port is None else port
    db_path = workdir / "e2e.db"
    sink_path = workdir / "fault_events.log"
    log_path = workdir / log_name
    db_url = f"sqlite:///{db_path}"
    # Settings reads every DRA_* variable (env_prefix). A developer's shell must not change what
    # the tests run against (freshness tolerance, weights, thresholds, model root), so none of
    # theirs is passed on: the server runs on the defaults plus the four set here.
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("DRA_")},
        "DRA_DATABASE_URL": db_url,
        "DRA_E2E_DATABASE_URL": db_url,
        "DRA_E2E_SINK": str(sink_path),
        "DRA_E2E_PORT": str(port),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    # cwd = the throw-away directory: Settings reads ``.env`` relative to the working directory,
    # and a developer's backend/.env must not be able to redirect the database.
    with log_path.open("wb") as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("e2e_server_main.py"))],
                                   cwd=workdir, env=env, stdout=log, stderr=subprocess.STDOUT)
    server = Server(f"http://127.0.0.1:{port}", db_path, sink_path, log_path, process)
    atexit.register(server.stop)  # a pytest that is interrupted must not leave a uvicorn behind
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the e2e uvicorn exited with {process.returncode}:\n{server.log_tail()}")
        try:
            if httpx.get(server.base_url + "/api/health", timeout=1.0).status_code == 200:
                return server
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    server.stop()
    raise RuntimeError(f"the e2e uvicorn did not come up within 60 s:\n{server.log_tail()}")


def api_client(server: Server):
    import httpx

    return httpx.Client(base_url=server.base_url, timeout=30.0)


def db_connection(server: Server) -> sqlite3.Connection:
    conn = sqlite3.connect(server.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def session_ids(server: Server) -> set[str]:
    with closing(db_connection(server)) as conn:
        return {row["id"] for row in conn.execute("SELECT id FROM sessions")}


def db_records(server: Server, sid: str) -> list[dict]:
    """The ``inference_records`` rows of one session, oldest first: the typed columns as stored
    plus the decoded ``payload``."""
    with closing(db_connection(server)) as conn:
        rows = conn.execute("SELECT * FROM inference_records WHERE session_id=? ORDER BY window_id", (sid,)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        out.append(item)
    return out


def db_count(server: Server, sql: str, *params) -> int:
    with closing(db_connection(server)) as conn:
        return conn.execute(sql, params).fetchone()[0]


# --------------------------------------------------------------------------------------
# The browser, and what it is made to do
# --------------------------------------------------------------------------------------
# Injected before any page script runs. Test tooling only: it observes the browser, it does not
# change what the product does.
PROBE_JS = r"""
(() => {
  const state = { regs: [], callbacks: [], draw: [], encode: [], streams: [] };
  window.__e2e = state;
  const supported = typeof HTMLVideoElement.prototype.requestVideoFrameCallback === 'function';
  state.supported = supported;
  if (supported) {
    const original = HTMLVideoElement.prototype.requestVideoFrameCallback;
    HTMLVideoElement.prototype.requestVideoFrameCallback = function (callback) {
      const video = this;
      state.regs.push({ at: performance.now(), connected: video.isConnected,
                        hidden: video.getAttribute('aria-hidden') === 'true' });
      const wrapped = (now, meta) => {
        const entered = performance.now();
        try { return callback(now, meta); }
        finally {
          const left = performance.now();
          const hasCaptureTime = typeof meta.captureTime === 'number';
          state.callbacks.push({ at: entered, ms: left - entered, presentedFrames: meta.presentedFrames,
                                 hasCaptureTime, lagMs: hasCaptureTime ? entered - meta.captureTime : null,
                                 connected: video.isConnected });
        }
      };
      return original.call(this, wrapped);
    };
  }
  const draw = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (...args) {
    const at = performance.now();
    try { return draw.apply(this, args); } finally { state.draw.push(performance.now() - at); }
  };
  const encode = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function (...args) {
    const at = performance.now();
    try { return encode.apply(this, args); } finally { state.encode.push(performance.now() - at); }
  };
  const media = navigator.mediaDevices;
  if (media && media.getUserMedia) {
    const original = media.getUserMedia.bind(media);
    media.getUserMedia = async (constraints) => {
      const stream = await original(constraints);
      state.streams.push(stream);
      return stream;
    };
  }
})();
"""

INFER_PATH = re.compile(r"^/api/sessions/([^/]+)/infer$")


@dataclass
class InferCall:
    """One ``POST /api/sessions/{sid}/infer`` the page made, as the tap saw it."""

    number: int
    at: float  # time.time() when the tap saw it
    sid: str
    raw: str  # the request body, byte for byte
    body: dict
    attempt: str | None  # the X-Attempt-Index header, as sent
    outcome: str = "pending"  # ok | aborted | held | unreachable
    status: int | None = None
    response: dict | None = None
    response_text: str | None = None
    route: object | None = field(default=None, repr=False)  # kept for a held call, so it can be released
    sent_raw: str | None = None  # what the SERVER received; None = the browser's body, unchanged (no rewrite)

    @property
    def request_id(self) -> str:
        return self.body["request_id"]

    @property
    def sent_body(self) -> dict:
        """The body that reached the server. ``raw`` / ``body`` stay what the browser sent; the two
        differ only when the tap was told to rewrite (``ApiTap.rewrite_infer``)."""
        return self.body if self.sent_raw is None else json.loads(self.sent_raw)


@dataclass
class SessionCall:
    number: int
    at: float
    outcome: str = "pending"  # ok | aborted | unreachable
    status: int | None = None
    response: dict | None = None


class ApiTap:
    """The page's ``/api`` traffic. ``/infer`` and ``POST /api/sessions`` go through
    ``route.fetch`` so that both the request and the response body are recorded and the browser
    still receives the real answer; every other request passes through untouched.

    The knobs are plain attributes the test sets while it drives the page:
    ``abort_infer``  fail the next N infer requests at the network layer (they never reach the server);
    ``hold_infer``   do not answer infer requests at all (the server never sees them);
    ``abort_session_posts``  the 1-based numbers of the ``POST /api/sessions`` calls to fail;
    ``rewrite_infer``  a PURE function from the decoded request body to the body the server gets
                       (Task 10 part 2b, ST-BRANCH-V). Pure, so a re-sent request is rewritten to the
                       very same bytes. ``InferCall.raw`` / ``.body`` stay the browser's own.

    When the server is not there (a test that stops the backend) ``route.fetch`` raises; the tap then
    answers the page with a refused connection, as the browser would have seen without a tap, and
    records the call as ``unreachable``. Every other test has a live server, so this never runs for them.
    """

    def __init__(self):
        self.infer: list[InferCall] = []
        self.session_posts: list[SessionCall] = []
        self.abort_infer = 0
        self.hold_infer = False
        self.abort_session_posts: set[int] = set()
        self.rewrite_infer = None

    def answered_with_image(self, sid: str | None = None) -> list[InferCall]:
        """Answered infer calls whose request, as the SERVER received it, carried a camera image."""
        return [c for c in self.answered(sid) if c.sent_body["image_base64"] is not None]

    def answered(self, sid: str | None = None) -> list[InferCall]:
        """The infer calls the server answered with a stored window (201), in the order sent."""
        return [c for c in self.infer if c.outcome == "ok" and c.status == 201 and (sid is None or c.sid == sid)]

    def held(self) -> list[InferCall]:
        return [c for c in self.infer if c.outcome == "held"]

    def release_held(self) -> None:
        """Fail the requests that were held. The page has normally cancelled them already (a Pause
        aborts its fetch), in which case there is nothing left to fail and the error is ignored."""
        for call in self.held():
            try:
                call.route.abort("failed")
            except Exception:
                pass

    def handle(self, route) -> None:
        request = route.request
        path = urlparse(request.url).path
        if request.method == "POST" and path == "/api/sessions":
            return self._sessions(route)
        match = INFER_PATH.match(path)
        if request.method == "POST" and match:
            return self._infer(route, match.group(1))
        route.continue_()

    def _sessions(self, route) -> None:
        call = SessionCall(number=len(self.session_posts) + 1, at=time.time())
        self.session_posts.append(call)
        if call.number in self.abort_session_posts:
            call.outcome = "aborted"
            route.abort("failed")
            return
        try:
            response = route.fetch()
        except Exception:  # the server is down: the page must see a refused connection
            call.outcome = "unreachable"
            route.abort("connectionrefused")
            return
        call.status = response.status
        call.response = response.json() if response.ok else None
        call.outcome = "ok"
        route.fulfill(response=response)

    def _infer(self, route, sid: str) -> None:
        request = route.request
        raw = request.post_data or ""
        call = InferCall(number=len(self.infer) + 1, at=time.time(), sid=sid, raw=raw, body=json.loads(raw),
                         attempt=request.headers.get("x-attempt-index"))
        self.infer.append(call)
        if self.hold_infer:
            call.outcome = "held"  # never answered: the route is simply left pending
            call.route = route
            return
        if self.abort_infer > 0:
            self.abort_infer -= 1
            call.outcome = "aborted"
            route.abort("failed")
            return
        if self.rewrite_infer is not None:
            call.sent_raw = json.dumps(self.rewrite_infer(json.loads(raw)), separators=(",", ":"))
        try:
            response = route.fetch() if call.sent_raw is None else route.fetch(post_data=call.sent_raw)
        except Exception:  # the server is down: the page must see a refused connection
            call.outcome = "unreachable"
            route.abort("connectionrefused")
            return
        call.status = response.status
        try:
            call.response = response.json()
        except Exception:  # a non-JSON error body
            call.response_text = response.text()
        call.outcome = "ok"
        route.fulfill(response=response)


class Chrome:
    """One Chromium with a fake camera, one context (camera permission granted), one page, the tap
    and a record of every console error / uncaught page error / failed non-infer request."""

    def __init__(self, pw, server: Server, args: list[str], permissions: tuple[str, ...] = ("camera",)):
        self.server = server
        self.browser = pw.chromium.launch(args=args)
        self.version = self.browser.version
        self.context = self.browser.new_context(permissions=list(permissions), viewport={"width": 1280, "height": 1000})
        self.page = self.context.new_page()
        self.tap = ApiTap()
        self.console_errors: list[str] = []
        self.page_errors: list[str] = []
        self.api_requests: list[tuple[str, str]] = []
        self.page.add_init_script(PROBE_JS)
        self.page.on("console", lambda m: self.console_errors.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.page_errors.append(str(e)))
        self.page.on("request", self._log_request)
        self.page.route("**/api/**", self.tap.handle)

    def _log_request(self, request) -> None:
        parts = urlparse(request.url)
        if parts.path.startswith("/api/") and not INFER_PATH.match(parts.path):
            self.api_requests.append((request.method, parts.path + (f"?{parts.query}" if parts.query else "")))

    def open(self) -> None:
        self.page.goto(self.server.base_url + "/")

    def top_button(self, name: str):
        return self.page.locator(".topbar-actions").get_by_role("button", name=name, exact=True)

    def stop_panel(self):
        return self.page.get_by_role("alert", name="Monitoring stopped")

    def stop_panel_text(self) -> str | None:
        panel = self.stop_panel()
        return panel.inner_text() if panel.count() else None

    def probe(self) -> dict:
        return self.page.evaluate("() => JSON.parse(JSON.stringify(window.__e2e))")

    def wait(self, ms: int) -> None:
        self.page.wait_for_timeout(ms)

    def wait_until(self, predicate, what: str, timeout_s: float = 60.0, *, tolerate_stop_panel: bool = False) -> None:
        """Poll ``predicate`` while the Playwright loop runs (the route handlers only run inside
        Playwright calls, so this never sleeps with ``time.sleep``). Fails fast, with the panel's
        text, when the app shows its stop panel and the test did not expect one."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if predicate():
                return
            if not tolerate_stop_panel:
                panel = self.stop_panel_text()
                if panel is not None:
                    raise AssertionError(f"while waiting for {what}: the app stopped monitoring:\n{panel}")
            self.wait(100)
        raise AssertionError(f"timed out after {timeout_s:.0f} s waiting for {what} "
                             f"(infer calls so far: {len(self.tap.infer)}, answered: {len(self.tap.answered())})")

    def close(self) -> None:
        try:
            # Stop the routes first: a handler still waiting on the network (or a request the test
            # held on purpose) would otherwise be cancelled noisily when the context goes away.
            self.tap.release_held()
            self.page.unroute_all(behavior="ignoreErrors")
            self.context.close()
        finally:
            self.browser.close()


# --------------------------------------------------------------------------------------
# Reading the five places a window lives
# --------------------------------------------------------------------------------------
# Every field of the RiskUpdate contract. A literal on purpose: a field added to (or dropped from)
# the contract must be noticed here, by hand.
RISK_UPDATE_FIELDS = [
    "session_id", "window_id", "timestamp", "assessment_available", "P_distraction", "P_telemetry_anomaly",
    "RiskScore", "RiskLevel", "DominantEvidence", "AlertSeverity", "SystemHealth", "operation_mode",
    "modality_freshness", "latency_ms", "visual_top_classes", "telemetry_behavior_classes",
    "telemetry_feature_contributions", "telemetry_features", "explanation", "flagged", "provenance",
]

# CSV: the columns that hold a JSON document, and the columns the exporter takes from provenance.
CSV_JSON_COLUMNS = ("provenance", "modality_freshness", "visual_top_classes", "telemetry_behavior_classes",
                    "telemetry_feature_contributions", "telemetry_features")
CSV_FROM_PROVENANCE = ("request_id", "vision_source", "telemetry_source", "vision_model_sha256",
                       "telemetry_model_sha256", "P_distraction_raw", "P_telemetry_raw")


def deep_diff(left, right, path: str = "") -> list[str]:
    """Every difference between two decoded JSON values, with its path. ``True`` is not ``1``."""
    if isinstance(left, dict) and isinstance(right, dict):
        out: list[str] = []
        for key in sorted(set(left) | set(right)):
            here = f"{path}.{key}" if path else key
            if key not in left:
                out.append(f"{here}: absent on the left, right has {right[key]!r}")
            elif key not in right:
                out.append(f"{here}: left has {left[key]!r}, absent on the right")
            else:
                out += deep_diff(left[key], right[key], here)
        return out
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return [f"{path}: list of {len(left)} items against {len(right)}"]
        out = []
        for index, (a, b) in enumerate(zip(left, right)):
            out += deep_diff(a, b, f"{path}[{index}]")
        return out
    same = left == right and isinstance(left, bool) == isinstance(right, bool)
    return [] if same else [f"{path}: {left!r} != {right!r}"]


def parse_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def _csv_cell_diff(column: str, cell: str, value) -> str | None:
    """The CSV encoding is the exporter's own explicit one: None is an empty cell, a bool is
    ``true`` / ``false``, a number is its ``repr``, a JSON column is a JSON document, a string is
    itself (a leading ``= + - @`` would be quoted with ``'``; none of these values has one)."""
    if value is None:
        expected_ok = cell == ""
    elif isinstance(value, bool):
        expected_ok = cell == ("true" if value else "false")
    elif isinstance(value, int):
        expected_ok = cell.lstrip("-").isdigit() and int(cell) == value
    elif isinstance(value, float):
        try:
            expected_ok = float(cell) == value
        except ValueError:
            expected_ok = False
    else:
        expected_ok = cell == value
    return None if expected_ok else f"csv {column}: cell {cell!r} for value {value!r}"


def csv_row_diffs(row: dict, record: dict) -> list[str]:
    """CSV against one RiskUpdate. The comparable columns are ALL 21 contract fields (the six
    structured ones as JSON documents) plus the seven provenance-derived columns; the two
    ``payload_unreadable*`` columns must be empty on a readable row."""
    diffs: list[str] = []
    expected = [*RISK_UPDATE_FIELDS, *CSV_FROM_PROVENANCE, "payload_unreadable", "payload_unreadable_reason"]
    missing = [column for column in expected if column not in row]
    if missing:  # a dropped column is a reconciliation difference, not a KeyError
        return [f"csv: column {column!r} is missing from the export" for column in missing]
    for column in RISK_UPDATE_FIELDS:
        if column in CSV_JSON_COLUMNS:
            try:
                decoded = json.loads(row[column])
            except ValueError:
                diffs.append(f"csv {column}: not JSON: {row[column][:80]!r}")
                continue
            diffs += [f"csv {column}: {d}" for d in deep_diff(decoded, record[column])]
        else:
            diff = _csv_cell_diff(column, row[column], record[column])
            if diff:
                diffs.append(diff)
    for column in CSV_FROM_PROVENANCE:
        diff = _csv_cell_diff(column, row[column], record["provenance"][column])
        if diff:
            diffs.append(diff)
    for column in ("payload_unreadable", "payload_unreadable_reason"):
        if row[column] != "":
            diffs.append(f"csv {column}: {row[column]!r}, expected empty on a readable row")
    return diffs


def record_diffs(row: dict, record: dict) -> list[str]:
    """The typed columns of a database row against the RiskUpdate they were written from."""
    pairs = {
        "window_id": record["window_id"], "timestamp": record["timestamp"],
        "p_distraction": record["P_distraction"], "p_telemetry_anomaly": record["P_telemetry_anomaly"],
        "risk_score": record["RiskScore"], "risk_level": record["RiskLevel"],
        "dominant_evidence": record["DominantEvidence"], "alert_severity": record["AlertSeverity"],
        "system_health": record["SystemHealth"], "latency_ms": record["latency_ms"],
        "request_id": record["provenance"]["request_id"],
    }
    out = [f"db column {name}: {row[name]!r} != {expected!r}" for name, expected in pairs.items()
           if row[name] != expected]
    for name, expected in (("assessment_available", record["assessment_available"]), ("flagged", record["flagged"])):
        if bool(row[name]) != expected:
            out.append(f"db column {name}: {row[name]!r} != {expected!r}")
    return out


# --------------------------------------------------------------------------------------
# What the dashboard says, and what it should say
# --------------------------------------------------------------------------------------
def half_up(value: float, places: int) -> Decimal:
    """Round half UP on the decimal digits of the shortest repr - the rule the dashboard's
    ``formatFixed`` and the backend's ``round_half_up`` follow (84.25 -> 84.3, never banker's)."""
    return Decimal(repr(float(value))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def fixed(value: float, places: int) -> str:
    return format(half_up(value, places), "f")


def percent(value: float) -> str:
    """The dashboard's ``asPercent``: round to 2 places, scale, round half up to an integer."""
    return f"{(half_up(value, 2) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)}%"


def _branch(record: dict, branch: str, shown: str) -> str:
    """A branch with no usable input shows words, not its 0.0 (ruling A: 'Expired' when it had evidence)."""
    if record["modality_freshness"][branch] != "missing":
        return shown
    return "Expired" if record["provenance"].get(f"{branch}_expired") else "No input"


LATEST_PANEL_JS = r"""
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const strip = {};
  document.querySelectorAll('.session-strip > div').forEach((d) => {
    const label = d.querySelector('span'), value = d.querySelector('strong');
    if (label && value) strip[clean(label.textContent)] = clean(value.textContent);
  });
  const banner = document.querySelector('section.alert-banner');
  const gauge = document.querySelector('.risk-gauge');
  return {
    strip,
    bannerTitle: banner ? clean(banner.querySelector('div > strong')?.textContent) : null,
    bannerText: banner ? clean(banner.querySelector('div > span')?.textContent) : null,
    bannerPills: banner ? [...banner.querySelectorAll('.banner-pills .pill')].map((p) => clean(p.textContent)) : [],
    gaugeLabel: gauge ? gauge.getAttribute('aria-label') : null,
    gaugeValue: gauge ? clean(gauge.querySelector('.risk-gauge__value span')?.textContent) : null,
    badges: [...document.querySelectorAll('.risk-badges .pill')].map((p) => clean(p.textContent)),
    cards: [...document.querySelectorAll('.modality-card')].map((c) => ({
      title: clean(c.querySelector(':scope > span')?.textContent),
      percent: clean(c.querySelector(':scope > strong')?.textContent),
      freshness: clean(c.querySelector('.pill')?.textContent),
      probability: clean(c.querySelector('small')?.textContent),
    })),
  };
}
"""


def read_latest_panel(page) -> dict:
    return page.evaluate(LATEST_PANEL_JS)


def expected_latest_panel(record: dict, session_id: str, total_windows: int) -> dict:
    """What the Live Monitor's latest panel must show for ``record``, written out from the display
    rules (1 decimal for the score, 2 for a probability, integer percent). ``record`` may be a window
    with no assessment (part 2b); the panel then says so instead of showing a score."""
    pd, pt = record["P_distraction"], record["P_telemetry_anomaly"]
    fresh = record["modality_freshness"]
    strip = {"Session": session_id, "Window": str(record["window_id"]), "Stored records": str(total_windows)}
    cards = [
        {"title": "Visual Distraction", "percent": "—" if fresh["vision"] == "missing" else percent(pd),
         "freshness": fresh["vision"], "probability": _branch(record, "vision", fixed(pd, 2))},
        {"title": "Telemetry Non-Safe", "percent": "—" if fresh["telemetry"] == "missing" else percent(pt),
         "freshness": fresh["telemetry"], "probability": _branch(record, "telemetry", fixed(pt, 2))},
    ]
    if not record["assessment_available"]:
        # Part 2b: a window with no assessment (AlertBanner / LiveMonitor "unavailable" state): the
        # banner says so in fixed words and shows only the SystemHealth pill, there is no gauge and no
        # RiskLevel / evidence / alert badge, and the two branch cards still show their own state.
        return {
            "strip": strip,
            "bannerTitle": "No assessment for the latest window",
            "bannerText": "Neither input branch contributed usable evidence, so no RiskScore, RiskLevel or alert is reported for it.",
            "bannerPills": [record["SystemHealth"]],
            "gaugeLabel": None,
            "gaugeValue": None,
            "badges": [],
            "cards": cards,
        }
    score = fixed(record["RiskScore"], 1)
    vision_percent = _branch(record, "vision", percent(pd))
    telemetry_percent = _branch(record, "telemetry", percent(pt))
    return {
        "strip": strip,
        "bannerTitle": "Current Monitoring Status",
        "bannerText": f"RiskScore: {score} / 100 | Visual distraction: {vision_percent} | Telemetry non-safe: {telemetry_percent}",
        "bannerPills": [record["AlertSeverity"], record["SystemHealth"]],
        "gaugeLabel": f"RiskScore: {score} / 100",
        "gaugeValue": score,
        "badges": [record["RiskLevel"], record["DominantEvidence"], record["AlertSeverity"]],
        "cards": cards,
    }


# --------------------------------------------------------------------------------------
# Small things
# --------------------------------------------------------------------------------------
def instant(stamp: str) -> datetime:
    """An ISO-8601 time as an instant: the server normalises ``...Z`` to ``+00:00``."""
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def summarise(values: list[float]) -> dict:
    """Count / min / median / p95 / max, for the measurements that are only recorded."""
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {"n": len(ordered), "min": round(ordered[0], 3), "median": round(statistics.median(ordered), 3),
            "p95": round(p95, 3), "max": round(ordered[-1], 3)}


# --------------------------------------------------------------------------------------
# One monitoring run and the five homes of its windows
# (LiveRun / Parties / parties_diffs / frame_key moved here from test_live_e2e.py in part 2b, so that
# ``test_live_single_branch.py`` and the E3 test reuse them; their behaviour is unchanged)
# --------------------------------------------------------------------------------------
EVIDENCE_ENV = "DRA_E2E_EVIDENCE_DIR"


def evidence_dir() -> Path | None:
    """Where a test may leave its artifacts (screenshots, exports, measurements) for the evidence
    archive: the directory named by ``DRA_E2E_EVIDENCE_DIR``. With the variable unset a test writes
    nothing outside its own tmp directory, so a plain test run never touches the repository."""
    value = os.environ.get(EVIDENCE_ENV)
    if not value:
        return None
    path = Path(value)
    path.mkdir(parents=True, exist_ok=True)
    return path


class LiveRun:
    """The state one monitoring run leaves behind: the paused page, what the tap recorded, and
    what the Live Monitor showed at the moment the server went quiet."""

    def __init__(self, chrome: Chrome):
        self.chrome = chrome
        self.server = chrome.server
        self.tap = chrome.tap
        self.page = chrome.page
        self.sid: str | None = None
        self.error: str | None = None  # why the run did not complete; the first test reports it
        self.ui_latest: dict | None = None
        self.probe: dict | None = None
        self.rvfc_supported: bool | None = None

    @property
    def calls(self):
        """The answered ``/infer`` calls of the run, in the order sent; window ids 1..N."""
        return self.tap.answered(self.sid)

    def attempt(self, steps) -> None:
        """Run the driving steps of a test; a failed wait is kept in ``error`` (the first test of
        the run reports it), so a broken run is a FAILED test with its cause, not a fixture error."""
        try:
            steps()
        except Exception as exc:  # AssertionError from a wait; anything else (a Playwright timeout) too
            self.error = str(exc) if isinstance(exc, AssertionError) else f"{type(exc).__name__}: {exc}"

    def collect(self) -> None:
        chrome = self.chrome
        chrome.open()
        chrome.top_button("Start Monitoring").click()
        self.attempt(lambda: (
            chrome.wait_until(lambda: self._enough(), "10 windows spanning 4 telemetry samples (seq 0..3)", 90),
            self.settle()))

    def settle(self) -> None:
        """Make the server quiet and read what the dashboard shows. From now on the loop's next
        request is held at the network layer and never reaches the server. The request before it
        has been answered (the loop sends one at a time), so the database holds exactly the windows
        the browser received - and the dashboard shows the newest of them. The Live Monitor must be
        the open view. Then Pause: the page cancels the held request itself."""
        chrome = self.chrome
        self.sid = self.sid or self.tap.session_posts[0].response["id"]
        self.tap.hold_infer = True
        chrome.wait_until(lambda: self.tap.held(), "the loop's next request to be held", 20)
        last = str(self.calls[-1].response["window_id"])
        chrome.wait_until(lambda: read_latest_panel(self.page)["strip"].get("Window") == last,
                          f"the dashboard to show window {last}", 10)
        self.ui_latest = read_latest_panel(self.page)
        self.rvfc_supported = self.page.evaluate("() => typeof HTMLVideoElement.prototype.requestVideoFrameCallback === 'function'")
        self.probe = chrome.probe()
        chrome.top_button("Pause").click()
        chrome.wait(500)
        self.tap.hold_infer = False

    def _enough(self) -> bool:
        answered = self.tap.answered()
        return len(answered) >= 10 and max(c.body.get("telemetry_seq", -1) for c in answered) >= 3


class Parties:
    """One window's five homes, fetched together: the browser's ``/infer`` bodies, the database,
    ``GET /windows``, the JSON export and the CSV export, plus ``GET /risk/latest``."""

    def __init__(self, run: LiveRun):
        sid = run.sid
        with api_client(run.server) as client:
            windows = client.get(f"/api/sessions/{sid}/windows", params={"after": 0, "limit": 1000})
            export_json = client.get(f"/api/sessions/{sid}/export", params={"format": "json"})
            export_csv = client.get(f"/api/sessions/{sid}/export", params={"format": "csv"})
            latest = client.get(f"/api/sessions/{sid}/risk/latest")
            self.session = client.get(f"/api/sessions/{sid}").json()
        assert windows.status_code == export_json.status_code == export_csv.status_code == latest.status_code == 200
        self.infer = {c.response["window_id"]: c.response for c in run.calls}
        self.db = {row["window_id"]: row for row in db_records(run.server, sid)}
        self.windows = {w["window_id"]: w for w in windows.json()}
        self.export_json = {r["window_id"]: r for r in export_json.json()["records"]}
        self.export_json_top = {k: v for k, v in export_json.json().items() if k != "records"}
        self.export_csv = {int(r["window_id"]): r for r in parse_csv(export_csv.text)}
        self.latest = latest.json()
        self.export_json_bytes, self.export_csv_bytes = export_json.content, export_csv.content


def parties_diffs(parties: Parties, expected: dict[int, dict]) -> list[str]:
    """Every difference between each home of every window and ``expected`` (the /infer bodies,
    with any deliberate change applied), field by field."""
    out: list[str] = []
    for window_id, want in expected.items():
        for name, home in (("database payload", {k: v["payload"] for k, v in parties.db.items()}),
                           ("GET /windows", parties.windows), ("export JSON", parties.export_json)):
            if window_id not in home:
                out.append(f"window {window_id}: missing from {name}")
                continue
            out += [f"window {window_id} {name}: {d}" for d in deep_diff(want, home[window_id])]
        if window_id in parties.db:
            out += [f"window {window_id}: {d}" for d in record_diffs(parties.db[window_id], want)]
        if window_id in parties.export_csv:
            out += [f"window {window_id}: {d}" for d in csv_row_diffs(parties.export_csv[window_id], want)]
        else:
            out.append(f"window {window_id}: missing from export CSV")
    return out


def frame_key(body: dict):
    """The identity a request gives its camera frame: (epoch, index), or the bytes when it sent none."""
    frame = body.get("vision_frame")
    return (frame["epoch"], frame["index"]) if frame else ("bytes", hashlib.sha256(body["image_base64"].encode()).hexdigest())


def assert_reconciled(run: LiveRun) -> Parties:
    """The part 2b reconciliation, for a run whose server is quiet (``LiveRun.settle``).

    For EVERY window the run received - single-branch, unavailable and two-branch alike - the five
    homes agree on all 21 contract fields, ``provenance`` key by key, floats exactly: (1) the
    ``/infer`` answer the browser received, (2) the database row (payload and typed columns),
    (3) ``GET /windows``, (4) the JSON export, (5) the CSV export (the rule is the one written in
    ``TestStLiveE2E01.test_04``: every contract field is compared, a scalar by the exporter's own
    encoding, the six structured fields as JSON documents, the seven provenance-derived columns
    against provenance). The same window ids 1..N exist everywhere, ``total_windows`` is N, and
    ``GET /risk/latest`` is the last window, whole."""
    parties = Parties(run)
    count = len(run.calls)
    ids = list(range(1, count + 1))
    assert sorted(parties.infer) == sorted(parties.db) == sorted(parties.windows) == ids
    assert sorted(parties.export_json) == sorted(parties.export_csv) == ids
    assert parties.session["total_windows"] == count
    assert parties.export_json_top == {"session_id": run.sid}
    diffs = parties_diffs(parties, parties.infer)
    assert not diffs, f"{len(diffs)} differences, first {diffs[:12]}"
    assert parties.latest["window_id"] == count
    diffs = deep_diff(parties.latest, parties.infer[count])
    assert not diffs, f"GET /risk/latest is not the last window: {diffs[:12]}"
    return parties


def assert_ui_shows_latest(run: LiveRun, parties: Parties) -> None:
    """IT-UI-01: what the Live Monitor displayed when the run went quiet (read from the DOM by
    ``LiveRun.settle``) against ``GET /risk/latest`` in the dashboard's display format."""
    expected = expected_latest_panel(parties.latest, run.sid, parties.session["total_windows"])
    shown = dict(run.ui_latest)
    shown["strip"] = {k: v for k, v in shown["strip"].items() if k in expected["strip"]}
    diffs = deep_diff(shown, expected)
    assert not diffs, f"the Live Monitor does not show GET /risk/latest: {diffs}"


def half_up_float(value: float, places: int) -> float:
    """``half_up`` as the float a record stores (an independent implementation: Decimal on the repr)."""
    return float(half_up(value, places))
