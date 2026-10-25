"""FIX-BACKEND-REACH, part A: every response the backend produces says so.

Why: with only ``npm run dev`` running (no backend on 8000) the Vite dev proxy answers every
``/api`` call with an HTTP 500 of its own - ``text/plain``, empty body. The front end could not tell
that from the backend's own 500 and reported "a model or storage error on the server". The backend
therefore stamps ``X-DRA-Backend: 1`` on everything it sends, and the front end treats an error
answer WITHOUT it as "the backend did not answer" (``frontend/src/api/client.ts``).

The header is checked on every kind of answer the backend gives: success, 404, 409, both 422s
(schema validation and an invalid frame), 503 ``models_unavailable``, the JSON 500
``model_runtime``, the plain-text 500 of an unhandled exception (which ServerErrorMiddleware sends
from OUTSIDE every user middleware, so the middleware cannot mark it), a CORS preflight, and a
static page. Expected values are literals: the header name and value are NOT imported from the
implementation.
"""
import pytest
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

# `live` is a fixture (a live session on a tmp database with fake-weights models); the other
# helpers build requests for it. Same pattern as test_server_timing.py.
from test_fault_events import bad_frame, infer, live, make_payload  # noqa: F401


def marker(response):
    """The marker header, looked up by its literal (lower-cased) name."""
    return response.headers.get("x-dra-backend")


def assert_marked(response, status):
    assert response.status_code == status, response.text
    assert marker(response) == "1", f"HTTP {status} without X-DRA-Backend; headers: {dict(response.headers)}"


# --- answers that come from the routes ---------------------------------------------------
def test_success_answers_are_marked(live):
    assert_marked(live.client.get("/api/health"), 200)
    assert_marked(live.client.get(f"/api/sessions/{live.sid}"), 200)
    assert_marked(live.client.get("/api/models"), 200)
    assert_marked(infer(live, make_payload("marker-ok-1")), 201)


def test_404_is_marked(live):
    assert_marked(live.client.get("/api/sessions/no-such-session"), 404)
    assert_marked(live.client.get("/api/this-route-does-not-exist"), 404)
    assert_marked(infer(live, make_payload("marker-404-1"), sid="no-such-session"), 404)


def test_409_is_marked(live):
    created = live.client.post("/api/sessions", json={"session_id": live.sid, "operation_mode": "LIVE_MODEL_RUNTIME"})
    assert_marked(created, 409)
    assert created.json() == {"detail": "session already exists"}


def test_both_kinds_of_422_are_marked(live):
    # Schema validation: FastAPI's RequestValidationError handler (installed by routers/faults.py).
    schema = live.client.post("/api/sessions", json={"operation_mode": "NO_SUCH_MODE"})
    assert_marked(schema, 422)
    assert isinstance(schema.json()["detail"], list)
    # An invalid frame: the route's own FaultHTTPException.
    frame = infer(live, bad_frame("marker-422-1"))
    assert_marked(frame, 422)
    assert isinstance(frame.json()["detail"], str)


def test_503_models_unavailable_is_marked(live, monkeypatch, tmp_path):
    from app.providers import trained

    empty = tmp_path / "no-model-files"
    empty.mkdir()
    monkeypatch.setattr(trained, "_provider", None)
    monkeypatch.setattr(trained.settings, "model_root", empty)
    assert_marked(infer(live, make_payload("marker-503-1")), 503)
    assert_marked(live.client.get("/api/models"), 503)  # the route the dashboard calls first


def test_500_model_runtime_json_is_marked(live):
    live.vision.fail = RuntimeError("onnxruntime: kernel crashed")
    response = infer(live, make_payload("marker-500-json-1"))
    assert_marked(response, 500)
    assert response.json() == {"detail": "Vision model failed during inference"}


def test_500_unhandled_exception_plain_text_is_marked(live, monkeypatch):
    """R-M1. This answer is built by ``routers/faults.on_unhandled_exception`` and sent by
    ServerErrorMiddleware, outside every user middleware: only the handler itself can mark it."""
    from app.routers import windows

    monkeypatch.setattr(windows, "_infer", lambda db, session_id, payload: {"not": "a RiskUpdate"})
    response = infer(live, make_payload("marker-500-text-1"))
    assert_marked(response, 500)
    assert response.text == "Internal Server Error"
    assert response.headers["content-type"].startswith("text/plain")


@pytest.fixture
def boom_route():
    """A throw-away route that raises, to prove the handler is global and not tied to /infer."""
    from fastapi.routing import APIRoute

    from app.main import app

    def boom():
        raise RuntimeError("anything")

    route = APIRoute("/api/_marker-boom", boom, methods=["GET"])
    app.router.routes.insert(0, route)
    try:
        yield
    finally:
        app.router.routes.remove(route)


def test_an_unhandled_exception_on_any_route_is_marked_too(live, boom_route):
    response = live.client.get("/api/_marker-boom")
    assert_marked(response, 500)
    assert response.text == "Internal Server Error"


# --- answers that do not come from a route ------------------------------------------------
def test_a_cors_preflight_is_marked_and_the_header_is_exposed_to_pages(live):
    """CORS answers a preflight itself, never reaching the routes; ``expose_headers`` is what
    lets a cross-origin page read the marker at all (a page sees only safelisted headers)."""
    origin = "http://127.0.0.1:5173"
    preflight = live.client.options(
        "/api/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert_marked(preflight, 200)
    cross_origin = live.client.get("/api/health", headers={"Origin": origin})
    assert_marked(cross_origin, 200)
    assert cross_origin.headers["access-control-allow-origin"] == origin
    # Server-Timing too: the page's latency buffer reads the server's stages from it.
    exposed = {h.strip() for h in cross_origin.headers["access-control-expose-headers"].split(",")}
    assert exposed == {"X-DRA-Backend", "Server-Timing"}


@pytest.fixture
def static_page(tmp_path):
    """A static mount like the one ``main.py`` adds for ``dist/``, but on a tmp directory and on a
    path of its own (the real mount at "/" only exists when ``dist/`` was built before import)."""
    from app.main import app

    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<!doctype html><title>stand-in for dist</title>")
    mount = Mount("/static-page-test", app=StaticFiles(directory=site, html=True), name="static-page-test")
    app.router.routes.insert(0, mount)
    try:
        yield "/static-page-test"
    finally:
        app.router.routes.remove(mount)


def test_a_static_page_and_a_missing_static_file_are_marked(live, static_page):
    page = live.client.get(static_page + "/")
    assert_marked(page, 200)
    assert "stand-in for dist" in page.text
    assert_marked(live.client.get(static_page + "/missing.js"), 404)


def test_the_marker_is_added_once_not_per_layer(live):
    """Two layers touch a response (the middleware, and the handler for the plain 500): never two values."""
    response = live.client.get("/api/health")
    assert response.headers.get_list("x-dra-backend") == ["1"]
