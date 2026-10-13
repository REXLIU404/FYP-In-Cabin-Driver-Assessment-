"""Persistent fault events for ``POST /api/sessions/{id}/infer``.

Why this is its own module with its own table
---------------------------------------------
A failed attempt must be observable *and must outlive the session it failed in*
(D02). So ``fault_events``:

* has **no foreign key** on ``session_id``. ``sessions`` cascades deletes to its
  records and SQLite runs with ``foreign_keys=ON``; a FK would make the faults
  vanish with the session. The column is also nullable: a 404 "session not found"
  fault carries an id that never existed, and a schema-422 may carry none;
* is not an ORM model on ``Base``. ``ensure_schema`` below is the **only** place
  the table is described - ``initialize_database()`` and the ``api_factory``
  fixture both call it. A second description (``Base.metadata.create_all``) could
  create the same table with a different shape, depending on import order;
* is written through a session of its **own**, bound to the *request's* engine
  (``db.get_bind()``), never the module-level ``SessionLocal`` - that one points
  at the developer's real database while tests only override ``get_db``.

``record_fault`` and ``mark_recovered`` never raise. A fault logger that masks the
error it was reporting is worse than none. Every fault is also appended to an
independent JSON-lines file (``backend/logs/fault_events.log``), so the event
survives a database that cannot be written at all.
"""
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("app.faults")

# --- where a fault came from (C6) -------------------------------------------------
ORIGIN_REQUEST_VALIDATION = "request_validation"  # schema / frame / header rejected
ORIGIN_SESSION = "session"                        # unknown session, mode, request ledger, ordering
ORIGIN_VISION_MODEL = "vision_model"              # the image branch failed while running
ORIGIN_TELEMETRY_MODEL = "telemetry_model"        # the telemetry branch failed while running
ORIGIN_MODEL_LOAD = "model_load"                  # artifacts missing / dependency missing / metadata
ORIGIN_STORAGE = "storage"                        # the database could not commit
ORIGIN_UNKNOWN = "unknown"
ORIGINS = (ORIGIN_REQUEST_VALIDATION, ORIGIN_SESSION, ORIGIN_VISION_MODEL,
           ORIGIN_TELEMETRY_MODEL, ORIGIN_MODEL_LOAD, ORIGIN_STORAGE, ORIGIN_UNKNOWN)

# --- what kind of failure it was ---------------------------------------------------
CATEGORY_INPUT_VALIDATION = "input_validation"
CATEGORY_MODE_CONFLICT = "mode_conflict"
CATEGORY_NOT_FOUND = "not_found"
CATEGORY_IDEMPOTENCY_CONFLICT = "idempotency_conflict"      # same request_id, different input
# Added beyond the planned set: an out-of-order evidence timestamp is a 409 that the
# client must tell apart from a hash conflict (different UI text, D02), so it cannot
# share a category with it.
CATEGORY_OUT_OF_ORDER_EVIDENCE = "out_of_order_evidence"
CATEGORY_MODELS_UNAVAILABLE = "models_unavailable"          # 503, not retryable
CATEGORY_MODEL_RUNTIME = "model_runtime"                    # 500, retryable
CATEGORY_STORAGE = "storage"                                # 500, retryable
CATEGORY_TRANSPORT_TIMEOUT = "transport_timeout"            # client-side only; the server never writes it
CATEGORY_UNKNOWN = "unknown"
ERROR_CATEGORIES = (CATEGORY_INPUT_VALIDATION, CATEGORY_MODE_CONFLICT, CATEGORY_NOT_FOUND,
                    CATEGORY_IDEMPOTENCY_CONFLICT, CATEGORY_OUT_OF_ORDER_EVIDENCE,
                    CATEGORY_MODELS_UNAVAILABLE, CATEGORY_MODEL_RUNTIME, CATEGORY_STORAGE,
                    CATEGORY_TRANSPORT_TIMEOUT, CATEGORY_UNKNOWN)

# D02: only failures that can clear on their own are worth retrying.
RETRYABLE = {
    CATEGORY_INPUT_VALIDATION: False,
    CATEGORY_MODE_CONFLICT: False,
    CATEGORY_NOT_FOUND: False,
    CATEGORY_IDEMPOTENCY_CONFLICT: False,
    CATEGORY_OUT_OF_ORDER_EVIDENCE: False,
    CATEGORY_MODELS_UNAVAILABLE: False,   # a missing file does not appear by itself
    CATEGORY_MODEL_RUNTIME: True,
    CATEGORY_STORAGE: True,
    CATEGORY_TRANSPORT_TIMEOUT: True,
    CATEGORY_UNKNOWN: False,
}

RECOVERY_OPEN = "open"
RECOVERY_RECOVERED = "recovered"
RECOVERY_EXHAUSTED = "exhausted"  # reserved: the retry budget belongs to the client (Task 8)

DEFAULT_SINK_PATH = Path(__file__).resolve().parents[1] / "logs" / "fault_events.log"

# X-Attempt-Index is 1..MAX_ATTEMPT_INDEX. This is a sanity bound, not a retry budget
# (the budget belongs to the client, Task 8): an unbounded value reaches ``record_fault``
# as a Python int that an INTEGER column cannot hold, the INSERT overflows, and the
# attempt is left without its fault row. routers/windows.py declares the same number in
# ``Header(le=1000)``; the tests pin both.
MAX_ATTEMPT_INDEX = 1000

_DETAIL_LIMIT = 1000

FAULT_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS fault_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id VARCHAR,
    request_id VARCHAR,
    attempt_index INTEGER,
    origin VARCHAR NOT NULL,
    error_category VARCHAR NOT NULL,
    http_status INTEGER,
    retryable BOOLEAN NOT NULL,
    detail VARCHAR NOT NULL DEFAULT '',
    recovery_status VARCHAR NOT NULL DEFAULT 'open'
        CHECK (recovery_status IN ('open', 'recovered', 'exhausted')),
    recovered_by_request_id VARCHAR,
    occurred_at VARCHAR NOT NULL,
    recovered_at VARCHAR
)
"""
FAULT_EVENTS_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_fault_events_session_id ON fault_events(session_id)",
    # SQLite cannot ALTER TABLE ... ADD UNIQUE, so the constraint is an index. NULL
    # columns never collide in a SQLite unique index: a fault with no request id (or
    # an unparseable attempt header) is therefore always its own row.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_fault_session_request_attempt "
    "ON fault_events(session_id, request_id, attempt_index)",
)

_COLUMNS = ("id", "session_id", "request_id", "attempt_index", "origin", "error_category",
            "http_status", "retryable", "detail", "recovery_status",
            "recovered_by_request_id", "occurred_at", "recovered_at")


def ensure_schema(conn) -> None:
    """Create ``fault_events`` and its indexes. Idempotent; never touches other tables.

    The single description of this table: called by ``initialize_database()`` and
    by the test ``api_factory`` fixture (which only runs ``create_all``)."""
    conn.execute(text(FAULT_EVENTS_DDL))
    for statement in FAULT_EVENTS_INDEXES:
        conn.execute(text(statement))


class FaultHTTPException(HTTPException):
    """An ``HTTPException`` that says what it is, so classification never has to
    parse a message. The wire response is identical to a plain ``HTTPException``."""

    def __init__(self, status_code: int, detail: str, *, error_category: str, origin: str):
        super().__init__(status_code=status_code, detail=detail)
        self.error_category = error_category
        self.origin = origin


@dataclass(frozen=True)
class FaultClass:
    origin: str
    error_category: str
    http_status: int
    retryable: bool
    detail: str


def _clip(value: str, limit: int = _DETAIL_LIMIT) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _root_cause(exc: BaseException) -> BaseException:
    seen = 0
    while exc.__cause__ is not None and seen < 10:
        exc, seen = exc.__cause__, seen + 1
    return exc


def _cause_text(root: BaseException) -> str:
    # A SQLAlchemy error's str() carries the SQL and its parameters (a whole payload
    # blob); the driver's own message is the part that says what went wrong.
    root = getattr(root, "orig", None) or root
    return f"{type(root).__name__}: {root}"


def _response_status(exc: BaseException) -> int:
    """The status the client gets for ``exc``: an ``HTTPException`` carries its own,
    anything else escapes as the server's bare 500."""
    status = exc.status_code if isinstance(exc, HTTPException) else None
    return status if isinstance(status, int) else 500


def classify_exception(exc: BaseException) -> FaultClass:
    """Map whatever the ``/infer`` path raised onto a fault description. Does not
    alter or wrap the exception - the caller re-raises the original.

    Never raises. Classification prints the root cause (``str(...)``), and an
    exception whose own ``__str__`` fails would otherwise make the classifier's error
    take the original's place and leave the attempt without a fault row. If
    classification fails the attempt is recorded as ``unknown`` / not retryable, with
    the status of the response the client actually receives."""
    try:
        return _classify(exc)
    except Exception:
        logger.exception("could not classify a %s; recording the attempt as unknown", type(exc).__name__)
        return FaultClass(ORIGIN_UNKNOWN, CATEGORY_UNKNOWN, _response_status(exc), False,
                          _clip(f"Unclassifiable {type(exc).__name__}"))


def _classify(exc: BaseException) -> FaultClass:
    if isinstance(exc, FaultHTTPException):
        category, origin, status, message = exc.error_category, exc.origin, exc.status_code, str(exc.detail)
    elif isinstance(exc, HTTPException):  # raised by code that predates FaultHTTPException
        category = {404: CATEGORY_NOT_FOUND, 409: CATEGORY_MODE_CONFLICT, 422: CATEGORY_INPUT_VALIDATION,
                    503: CATEGORY_MODELS_UNAVAILABLE}.get(exc.status_code, CATEGORY_UNKNOWN)
        origin = ORIGIN_REQUEST_VALIDATION if category == CATEGORY_INPUT_VALIDATION else (
            ORIGIN_MODEL_LOAD if category == CATEGORY_MODELS_UNAVAILABLE else ORIGIN_SESSION)
        status, message = exc.status_code, str(exc.detail)
    elif isinstance(exc, SQLAlchemyError):
        category, origin, status, message = CATEGORY_STORAGE, ORIGIN_STORAGE, 500, "Database operation failed"
    else:
        # Includes a producer that contradicts its own RiskUpdate invariants
        # (pydantic.ValidationError): a deterministic bug, so not retryable.
        category, origin, status, message = CATEGORY_UNKNOWN, ORIGIN_UNKNOWN, 500, "Unexpected error"
    root = _root_cause(exc)
    if root is not exc or category in (CATEGORY_STORAGE, CATEGORY_UNKNOWN):
        message = f"{message}; cause: {_cause_text(root)}"
    return FaultClass(origin, category, status, RETRYABLE[category], _clip(message))


# --- sink ----------------------------------------------------------------------------
_SINK_LOCK = threading.Lock()


class FaultSink:
    """Append-only JSON-lines file, independent of the database. ``write`` never raises."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def write(self, event: dict[str, Any]) -> None:
        try:
            with _SINK_LOCK:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
        except Exception:  # a broken log must not hide the fault it was meant to keep
            logger.exception("fault sink write failed (%s)", self.path)


def get_fault_sink() -> FaultSink:
    """FastAPI dependency; tests override it (and ``DEFAULT_SINK_PATH``) to ``tmp_path``."""
    return FaultSink(DEFAULT_SINK_PATH)


# --- write side -----------------------------------------------------------------------
# ON CONFLICT DO NOTHING (not INSERT OR IGNORE): only a uniqueness conflict - the same
# attempt delivered twice - is skipped. A NOT NULL or CHECK violation still raises, so
# a malformed fault is not silently dropped.
_INSERT = text(
    "INSERT INTO fault_events (session_id, request_id, attempt_index, origin, "
    "error_category, http_status, retryable, detail, recovery_status, occurred_at) "
    "VALUES (:session_id, :request_id, :attempt_index, :origin, :error_category, "
    ":http_status, :retryable, :detail, 'open', :occurred_at) ON CONFLICT DO NOTHING")


def record_fault(db, *, session_id: Optional[str], request_id: Optional[str],
                 attempt_index: Optional[int], origin: str, error_category: str,
                 http_status: Optional[int], retryable: bool, detail: str,
                 sink: Optional[FaultSink] = None) -> None:
    """Persist one failed attempt. Never raises, never touches ``db``'s own transaction.

    The caller MUST have rolled ``db`` back first: SQLite has one writer, and a failed
    request that still holds the write lock would make this insert wait out
    ``busy_timeout`` (15 s) and then fail with "database is locked".

    A repeat of the same (session, request, attempt) is ignored by the unique index -
    it is the same attempt delivered twice, not a new failure."""
    event = {
        "session_id": session_id, "request_id": request_id, "attempt_index": attempt_index,
        "origin": origin, "error_category": error_category, "http_status": http_status,
        "retryable": bool(retryable), "detail": _clip(detail or ""),
        "occurred_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
    }
    stored = False
    try:
        with sessionmaker(bind=db.get_bind())() as fault_db:
            fault_db.execute(_INSERT, event)
            fault_db.commit()
        stored = True
    except Exception:
        logger.exception("could not store fault event in the database; the sink keeps it")
    try:
        (sink if sink is not None else get_fault_sink()).write({**event, "db_written": stored})
    except Exception:
        logger.exception("fault sink unavailable")


def mark_recovered(db, session_id: str, request_id: str) -> None:
    """After a NEW record was committed in ``session_id``: every ``open`` fault of that
    session becomes ``recovered``. An idempotent replay is not a recovery and must not
    call this. Never raises - the success it follows is already committed."""
    try:
        with sessionmaker(bind=db.get_bind())() as fault_db:
            fault_db.execute(
                text("UPDATE fault_events SET recovery_status = 'recovered', "
                     "recovered_by_request_id = :request_id, recovered_at = :recovered_at "
                     "WHERE session_id = :session_id AND recovery_status = 'open'"),
                {"request_id": request_id, "session_id": session_id,
                 "recovered_at": datetime.now(timezone.utc).isoformat(timespec="microseconds")})
            fault_db.commit()
    except Exception:
        logger.exception("could not mark faults recovered for session %s", session_id)


# --- read side ---------------------------------------------------------------------------
def open_fault_count(db, session_id: str) -> int:
    """Open faults of one session. Counts rows of a deleted session too - they outlive it."""
    try:
        return db.execute(
            text("SELECT COUNT(*) FROM fault_events WHERE session_id = :session_id "
                 "AND recovery_status = 'open'"), {"session_id": session_id}).scalar() or 0
    except OperationalError as exc:
        # A database that never ran ensure_schema has no fault table, hence no faults.
        if "no such table" in str(exc).lower():
            return 0
        raise


def list_fault_events(db, *, session_id: Optional[str] = None, limit: int = 500) -> list[dict]:
    where = "WHERE session_id = :session_id " if session_id is not None else ""
    rows = db.execute(
        text(f"SELECT {', '.join(_COLUMNS)} FROM fault_events {where}"
             "ORDER BY occurred_at, id LIMIT :limit"),
        {"limit": limit, **({"session_id": session_id} if session_id is not None else {})}).mappings().all()
    return [{**row, "retryable": bool(row["retryable"])} for row in rows]


# --- request parsing helpers shared by the route and the global handlers -------------
def parse_attempt_header(raw: Optional[str]) -> Optional[int]:
    """``X-Attempt-Index``: absent = 1; an integer in 1..MAX_ATTEMPT_INDEX = itself;
    anything else (not a number, below 1, above the bound) = None."""
    if raw is None:
        return 1
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    return value if 1 <= value <= MAX_ATTEMPT_INDEX else None


def request_id_from_body(body: Any) -> Optional[str]:
    """Best-effort ``request_id`` from a body that failed validation (``exc.body``)."""
    if isinstance(body, dict) and isinstance(body.get("request_id"), str):
        return body["request_id"][:100]
    return None


def describe_validation_errors(errors) -> str:
    """Field paths and messages only. Pydantic's ``input`` is deliberately dropped:
    it can hold a multi-megabyte base64 frame."""
    parts = [f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg', 'invalid')}" for err in errors]
    return _clip("; ".join(parts) or "request validation failed", 500)
