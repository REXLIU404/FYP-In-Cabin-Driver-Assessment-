"""Shared pytest configuration for the backend tests.

Five jobs:

1. Guarantee that *importing the app never touches a real database*. ``Settings``
   is instantiated once, the first time ``app.config`` is imported, and its
   default ``sqlite:///./driver_risk.db`` is a path relative to the working
   directory. ``test_api.py`` redirects the URL at import time, but any test
   module that imports ``app.config`` first would silently fall back to that
   default (or to a developer's ``.env``). The environment variable is therefore
   forced here, before any test module is collected, to a throw-away directory.

2. Provide an isolated ``api`` fixture for new tests: its own SQLite file under
   ``tmp_path``, ``get_db`` overridden, the lifespan skipped (it would initialise
   the *global* engine) and the module-global output cache cleared on teardown.

3. Keep fault events out of the real ``backend/logs/``. A failed ``/infer`` appends a
   line to the fault sink file, and a module-level fixture such as the one in
   ``test_audit_regressions.py`` overrides only ``get_db``. The autouse fixture
   below therefore redirects the sink's default path for EVERY test.

4. Make "needs the trained models" skips impossible to miss. ``ml/outputs/*`` is
   git-ignored, so a clean checkout skips the heaviest live tests and pytest still
   exits 0: a green that proved nothing about them. ``pytest_terminal_summary`` prints
   the count and the names of those skips in a banner, and ``DRA_REQUIRE_MODELS=1``
   (the pre-release gate) turns each of them into a failure instead.

5. Provide the end-to-end environment of ``test_live_e2e.py``: the ``e2e`` marker, a session-scoped
   ``npm run build`` and the ONE uvicorn that serves the API and the freshly built ``dist/`` on a
   throw-away database (``e2e_dist`` / ``e2e_server``). Both import their helpers lazily, so a run
   that selects no end-to-end test never builds or starts anything.

The pre-existing ``api`` fixture in ``test_audit_regressions.py`` has the same
``(client, session_id)`` contract and, being module-level, takes precedence in
the modules that use it. New tests use only this one.
"""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Forced (not setdefault): a test run must never reach a real development DB,
# whatever the shell environment or a ``.env`` file says. No ``app`` import here.
_SCRATCH_DIR = tempfile.mkdtemp(prefix="dra-pytest-")
os.environ["DRA_DATABASE_URL"] = "sqlite:///" + os.path.join(_SCRATCH_DIR, "import-time.db")
atexit.register(shutil.rmtree, _SCRATCH_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _fault_sink_in_tmp(tmp_path, monkeypatch):
    """No test may append to the real ``backend/logs/fault_events.log``."""
    from app import faults

    monkeypatch.setattr(faults, "DEFAULT_SINK_PATH", tmp_path / "default-sink" / "fault_events.log")


@pytest.fixture
def api_factory(tmp_path):
    """A ``sessionmaker`` bound to a fresh, tmp_path-scoped database with the
    current schema, and the app's ``get_db`` dependency pointed at it. The fault
    sink is pointed at ``tmp_path / 'fault_events.log'``."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from app.db import Base, get_db
    from app.faults import FaultSink, ensure_schema, get_fault_sink
    from app.main import app

    engine = create_engine(
        f"sqlite:///{tmp_path / 'api.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(connection, _):  # same pragmas the production engine applies
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

    factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    # create_all does not know fault_events (it is deliberately not on Base); the same
    # function initialize_database() uses builds it, so there is one description.
    with engine.begin() as conn:
        ensure_schema(conn)

    def isolated_db():
        with factory() as db:
            yield db

    def isolated_sink():
        return FaultSink(tmp_path / "fault_events.log")

    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = isolated_db
    app.dependency_overrides[get_fault_sink] = isolated_sink
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)
        engine.dispose()


@pytest.fixture
def api(api_factory, tmp_path):
    """``(client, session_id)`` where ``session_id`` is a replay-mode session that
    already exists. No lifespan context: it would initialise the global engine."""
    from fastapi.testclient import TestClient

    from app import cache
    from app.main import app

    client = TestClient(app)
    sid = f"api-{tmp_path.name}"
    assert client.post("/api/sessions", json={"session_id": sid}).status_code == 201
    try:
        yield client, sid
    finally:
        client.close()
        cache._latest.clear()  # module-global: would leak between tests otherwise


# --------------------------------------------------------------------------------------
# End-to-end environment (Task 10 part 2a): ONE uvicorn serving the API and the built dist/.
# --------------------------------------------------------------------------------------
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "e2e: drives Chromium against one real uvicorn that serves the API and the freshly built dist/ "
        "(slow; part of the full run, select with -m e2e)",
    )


@pytest.fixture(scope="session")
def e2e_dist():
    """``npm run build`` once per pytest session. ``dist/`` is git-ignored and can be stale; the
    end-to-end tests must exercise the CURRENT frontend, so they never trust an existing one."""
    from e2e_support import build_dist

    build_dist()


@pytest.fixture(scope="session")
def e2e_server(e2e_dist, tmp_path_factory):
    """The single uvicorn of the end-to-end tests: a throw-away SQLite file, the fault sink in the
    same directory, a free port, the API and ``dist/`` on one origin. Never the development database."""
    from e2e_support import start_server

    server = start_server(tmp_path_factory.mktemp("e2e-server"))
    try:
        yield server
    finally:
        server.stop()


# --------------------------------------------------------------------------------------
# "Needs the trained models" skips: counted, printed, and optionally fatal.
# --------------------------------------------------------------------------------------
# The reason string of every ``requires_models`` skipif in this directory
# (test_live_inference.py, test_unavailable_contract.py, test_live_e2e.py). It is how a skip is
# recognised, so a test that spells it differently would escape the accounting;
# test_model_gate.py pins that every ``requires_models`` marker uses this exact text.
MODELS_SKIP_REASON = "local trained artifacts not installed"
REQUIRE_MODELS_ENV = "DRA_REQUIRE_MODELS"
_MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml" / "outputs"
_STABLE_MODEL_FILES = (
    "vision/mobilenetv3_large_vision.onnx",
    "vision/mobilenetv3_large_vision.pt",
    "telemetry/xgb_telemetry.json",
)
_model_skips: list[str] = []


def _require_models() -> bool:
    return os.environ.get(REQUIRE_MODELS_ENV) == "1"


def _is_models_skip(report) -> bool:
    """A skip raised by ``skipif(..., reason=MODELS_SKIP_REASON)``. For a mark-based
    skip pytest stores ``(path, lineno, reason)`` in ``longrepr``; a ``pytest.skip()``
    call stores ``"Skipped: reason"`` there. Both contain the reason text."""
    return bool(report.skipped) and MODELS_SKIP_REASON in str(report.longrepr)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "setup" or not _is_models_skip(report):
        return
    _model_skips.append(report.nodeid)
    if _require_models():
        # Not a skip any more: the session ends non-zero and the test is listed red.
        report.outcome = "failed"
        report.longrepr = (
            f"{REQUIRE_MODELS_ENV}=1 but the trained model artifacts are missing, so this test "
            f"cannot run ({MODELS_SKIP_REASON}).\nExpected under {_MODEL_ROOT}: "
            + ", ".join(_STABLE_MODEL_FILES)
        )


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not _model_skips:
        if _require_models():
            terminalreporter.write_line(f"{REQUIRE_MODELS_ENV}=1: no model-dependent test was skipped.")
        return
    missing = [name for name in _STABLE_MODEL_FILES if not (_MODEL_ROOT / name).exists()]
    terminalreporter.section(
        f"{len(_model_skips)} MODEL-DEPENDENT TEST(S) NOT RUN (models missing)",
        sep="!", red=True, bold=True,
    )
    terminalreporter.write_line(
        "These tests were skipped, not passed: a green result says nothing about them.", red=True, bold=True)
    terminalreporter.write_line(f"Model root: {_MODEL_ROOT}")
    terminalreporter.write_line("Missing: " + (", ".join(missing) if missing else "(all stable files exist; check the skip condition)"))
    for nodeid in _model_skips:
        terminalreporter.write_line(f"  SKIPPED  {nodeid}")
    if _require_models():
        terminalreporter.write_line(
            f"{REQUIRE_MODELS_ENV}=1: each of the above was reported as a FAILURE.", red=True, bold=True)
    else:
        terminalreporter.write_line(
            f"Set {REQUIRE_MODELS_ENV}=1 (pre-release gate) to make a missing model fail the run.")
