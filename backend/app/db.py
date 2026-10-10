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
        "inference_records": {"request_id": "VARCHAR", "request_hash": "VARCHAR"},
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


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
