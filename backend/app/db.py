"""SQLAlchemy engine, session factory, and declarative base (SQLite)."""
from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import settings

# check_same_thread=False is required for SQLite under a threaded ASGI server.
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 15}
    if settings.database_url.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()


def initialize_database():
    """Additive SQLite migration: preserve existing sessions and records."""
    Base.metadata.create_all(bind=engine)
    additions = {
        "sessions": {
            "next_window_id": "INTEGER NOT NULL DEFAULT 0",
            "operation_mode": "VARCHAR NOT NULL DEFAULT 'PREPARED_SESSION_RUNTIME'",
            "runtime_state": "JSON NOT NULL DEFAULT '{}'",
            "runtime_config": "JSON NOT NULL DEFAULT '{}'",
        },
        "inference_records": {
            "request_id": "VARCHAR",
            "request_hash": "VARCHAR",
            "assessment_available": "BOOLEAN NOT NULL DEFAULT 1",
        },
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {col["name"] for col in inspect(conn).get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        conn.execute(text("UPDATE sessions SET next_window_id = MAX(next_window_id, COALESCE((SELECT MAX(window_id) FROM inference_records WHERE session_id=sessions.id),0))"))
        duplicates = conn.execute(text("SELECT session_id, window_id FROM inference_records GROUP BY session_id, window_id HAVING COUNT(*)>1 LIMIT 1")).first()
        if duplicates:
            raise RuntimeError("Existing duplicate window IDs need manual reconciliation before migration; no records were deleted")
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_record_session_window ON inference_records(session_id, window_id)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_record_session_request ON inference_records(session_id, request_id)"))
        _backfill_assessment_available(conn)


# SQLite does not promise to evaluate AND terms left to right, and json_*() raises
# on malformed text, so every payload predicate sits behind this CASE. json_set()
# on a NULL / malformed payload yields NULL (or an error), which would erase the
# stored blob - hence the guard is mandatory, not defensive.
_PAYLOAD_IS_OBJECT = "CASE WHEN payload IS NOT NULL AND json_valid(payload) THEN json_type(payload) = 'object' ELSE 0 END"
_NO_FLAG_YET = "CASE WHEN payload IS NOT NULL AND json_valid(payload) THEN json_extract(payload, '$.assessment_available') IS NULL ELSE 0 END"
_UNAVAILABLE_ROW = "(system_health = 'UNAVAILABLE' OR CASE WHEN payload IS NOT NULL AND json_valid(payload) THEN json_extract(payload, '$.SystemHealth') = 'UNAVAILABLE' ELSE 0 END)"
_HAS_SCORE = "CASE WHEN payload IS NOT NULL AND json_valid(payload) THEN json_extract(payload, '$.RiskScore') IS NOT NULL ELSE 0 END"


def _backfill_assessment_available(conn) -> None:
    """Rewrite pre-existing rows to the nullable availability contract.

    Idempotent, and never deletes or NULLs a payload. ``json('true')`` /
    ``json('false')`` (not 1 / 0) keep the stored blob a real JSON boolean:
    export streams the blob as-is, so an integer would reach clients as
    ``"assessment_available": 1`` for migrated rows but ``true`` for new ones."""
    # 1. A no-evidence row was stored as a fabricated 0 / Low / NORMAL. Null the
    #    four values (columns and blob) and mark it unavailable. Must run first:
    #    step 2 would otherwise see its non-null RiskScore of 0.0 and call it assessed.
    conn.execute(text(
        "UPDATE inference_records SET payload = json_set(payload, "
        "'$.RiskScore', json('null'), '$.RiskLevel', json('null'), "
        "'$.DominantEvidence', json('null'), '$.AlertSeverity', json('null'), "
        "'$.assessment_available', json('false')) "
        f"WHERE {_PAYLOAD_IS_OBJECT} AND {_NO_FLAG_YET} AND {_UNAVAILABLE_ROW}"))
    conn.execute(text(
        "UPDATE inference_records SET assessment_available = 0, risk_score = NULL, "
        "risk_level = NULL, dominant_evidence = NULL, alert_severity = NULL "
        f"WHERE {_UNAVAILABLE_ROW}"))
    # 2. Everything else that is a recognisable assessment (has a score) is available.
    conn.execute(text(
        "UPDATE inference_records SET payload = json_set(payload, "
        "'$.assessment_available', json('true')) "
        f"WHERE {_PAYLOAD_IS_OBJECT} AND {_NO_FLAG_YET} AND {_HAS_SCORE}"))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
