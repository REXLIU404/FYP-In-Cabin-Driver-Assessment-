"""Shared pytest configuration for the backend tests.

Two jobs:

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

The pre-existing ``api`` fixture in ``test_audit_regressions.py`` has the same
``(client, session_id)`` contract and, being module-level, takes precedence in
the modules that use it. New tests use only this one.
"""
import atexit
import os
import shutil
import tempfile

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
