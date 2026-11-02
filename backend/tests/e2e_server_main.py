"""The one uvicorn process of the end-to-end tests (Task 10 part 2a).

Started by ``e2e_support.start_server`` as ``python e2e_server_main.py``. It serves the API AND
the built ``dist/`` (``app/main.py`` mounts it when it exists) on a single origin, so the browser
under test talks to exactly what ``uvicorn app.main:app`` serves. No vite dev server.

Two things a plain ``uvicorn app.main:app`` would get wrong for a test:

* the fault sink writes to ``backend/logs/fault_events.log`` and has no environment override, so
  the launcher points ``faults.DEFAULT_SINK_PATH`` at the test's directory first;
* ``lifespan`` runs ``initialize_database()`` on whatever ``DRA_DATABASE_URL`` names, so the
  launcher refuses to start unless that is the throw-away SQLite file the test created.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

expected_url = os.environ["DRA_E2E_DATABASE_URL"]
if os.environ.get("DRA_DATABASE_URL") != expected_url or "driver_risk.db" in expected_url:
    sys.exit(f"refusing to start: DRA_DATABASE_URL must be the throw-away database {expected_url!r}")

from app import faults  # noqa: E402

faults.DEFAULT_SINK_PATH = Path(os.environ["DRA_E2E_SINK"])

import uvicorn  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

assert settings.database_url == expected_url, settings.database_url

uvicorn.run(app, host="127.0.0.1", port=int(os.environ["DRA_E2E_PORT"]), log_level="warning")
