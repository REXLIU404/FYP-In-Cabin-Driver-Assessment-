"""The additive SQLite upgrade must preserve legacy session evidence."""
import json

import pytest
from sqlalchemy import create_engine, text, inspect

LEGACY_RECORDS_DDL = (
    "CREATE TABLE inference_records(id INTEGER PRIMARY KEY, session_id VARCHAR, window_id INTEGER, "
    "timestamp VARCHAR, p_distraction FLOAT, p_telemetry_anomaly FLOAT, risk_score FLOAT, "
    "risk_level VARCHAR, dominant_evidence VARCHAR, alert_severity VARCHAR, system_health VARCHAR, "
    "latency_ms INTEGER, flagged BOOLEAN, payload JSON)"
)
FOUR = ("RiskScore", "RiskLevel", "DominantEvidence", "AlertSeverity")


def legacy_payload(window_id, available):
    """A RiskUpdate exactly as it was stored before assessment_available existed."""
    return {
        "session_id": "legacy", "window_id": window_id, "timestamp": "2026-09-28T00:00:00+00:00",
        "P_distraction": 0.8 if available else 0.0, "P_telemetry_anomaly": 0.2 if available else 0.0,
        "RiskScore": 50.0 if available else 0.0, "RiskLevel": "Medium" if available else "Low",
        "DominantEvidence": "Vision-dominant" if available else "Partial evidence",
        "AlertSeverity": "CAUTION" if available else "NORMAL",
        "SystemHealth": "FULL" if available else "UNAVAILABLE",
        "operation_mode": "PREPARED_SESSION_RUNTIME",
        "modality_freshness": {"vision": "fresh" if available else "missing",
                               "telemetry": "fresh" if available else "missing"},
        "latency_ms": 0, "visual_top_classes": [], "telemetry_behavior_classes": [],
        "telemetry_feature_contributions": [], "telemetry_features": None,
        "explanation": "", "flagged": False, "provenance": {"provider": "MockAIProvider"},
    }


def make_legacy_engine(tmp_path, *, with_records=True):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sessions(id VARCHAR PRIMARY KEY, created_at DATETIME, description VARCHAR)"))
        conn.execute(text(LEGACY_RECORDS_DDL))
        conn.execute(text("INSERT INTO sessions VALUES ('legacy', '2026-09-28T00:00:00', 'keep me')"))
        if with_records:
            conn.execute(text(
                "INSERT INTO inference_records(id,session_id,window_id,risk_score,risk_level,dominant_evidence,"
                "alert_severity,system_health,payload) VALUES (:id,'legacy',:w,:s,:l,:d,:a,:h,:p)"),
                [
                    # 1. an ordinary assessed row
                    {"id": 1, "w": 15, "s": 50.0, "l": "Medium", "d": "Vision-dominant", "a": "CAUTION",
                     "h": "FULL", "p": json.dumps(legacy_payload(15, True))},
                    # 2. the fabricated "safe" row an old no-evidence window was stored as
                    {"id": 2, "w": 16, "s": 0.0, "l": "Low", "d": "Partial evidence", "a": "NORMAL",
                     "h": "UNAVAILABLE", "p": json.dumps(legacy_payload(16, False))},
                    # 3. a payload that is valid JSON but not a RiskUpdate at all
                    {"id": 3, "w": 17, "s": None, "l": None, "d": None, "a": None, "h": None,
                     "p": json.dumps({"proof": "keep this"})},
                ])
    return engine


def payload_of(conn, row_id):
    raw = conn.execute(text("SELECT payload FROM inference_records WHERE id=:i"), {"i": row_id}).scalar()
    return None if raw is None else json.loads(raw)


def test_legacy_database_migration_preserves_rows_and_allocates_above_old_max(tmp_path, monkeypatch):
    from app import db
    engine = make_legacy_engine(tmp_path)
    monkeypatch.setattr(db, "engine", engine)
    db.initialize_database()
    db.initialize_database()  # repeatable migration
    with engine.connect() as conn:
        row = conn.execute(text("SELECT description,next_window_id,runtime_state FROM sessions WHERE id='legacy'")).one()
        assert row[0] == "keep me"
        assert row[1] == 17
        assert json.loads(row[2]) == {}
        assert payload_of(conn, 3) == {"proof": "keep this"}  # untouched, not erased
        assert conn.execute(text("SELECT COUNT(*) FROM inference_records")).scalar() == 3
        indexes = {index["name"] for index in inspect(conn).get_indexes("inference_records")}
        assert "uq_record_session_window" in indexes
        assert "uq_record_session_request" in indexes
    engine.dispose()


def test_migration_adds_flag_column_and_backfills_columns_and_payload(tmp_path, monkeypatch):
    from app import db
    from app.schemas import RiskUpdate
    engine = make_legacy_engine(tmp_path)
    monkeypatch.setattr(db, "engine", engine)
    db.initialize_database()
    with engine.connect() as conn:
        assert "assessment_available" in {c["name"] for c in inspect(conn).get_columns("inference_records")}
        columns = {r[0]: r[1:] for r in conn.execute(text(
            "SELECT id, assessment_available, risk_score, risk_level, dominant_evidence, alert_severity, "
            "system_health FROM inference_records"))}
        # 1. assessed row: untouched, flag defaults to true
        assert columns[1] == (1, 50.0, "Medium", "Vision-dominant", "CAUTION", "FULL")
        # 2. fabricated row: the four values are NULL, flag false, health stays UNAVAILABLE
        assert columns[2] == (0, None, None, None, None, "UNAVAILABLE")
        # 3. plain-payload row: not an assessment we can judge, left as it was
        assert columns[3][0] == 1

        assessed, fabricated = payload_of(conn, 1), payload_of(conn, 2)
        # JSON booleans (json.loads gives True/False), never the integers 1/0.
        assert assessed["assessment_available"] is True
        assert fabricated["assessment_available"] is False
        for name in FOUR:
            assert fabricated[name] is None
            assert assessed[name] == legacy_payload(15, True)[name]
        assert fabricated["SystemHealth"] == "UNAVAILABLE"
        # Values the migration has no business touching are byte-for-byte what they were.
        for key in ("session_id", "window_id", "provenance", "modality_freshness", "explanation"):
            assert fabricated[key] == legacy_payload(16, False)[key]
        # The migrated JSON is a valid canonical RiskUpdate on its own.
        assert RiskUpdate(**assessed).assessment_available is True
        assert RiskUpdate(**fabricated).assessment_available is False
        assert payload_of(conn, 3) == {"proof": "keep this"}
    engine.dispose()


def test_migration_is_idempotent_and_preserves_new_rows(tmp_path, monkeypatch):
    from app import db
    engine = make_legacy_engine(tmp_path)
    monkeypatch.setattr(db, "engine", engine)
    db.initialize_database()
    with engine.connect() as conn:
        once = conn.execute(text("SELECT id, assessment_available, risk_score, payload FROM inference_records ORDER BY id")).all()
    db.initialize_database()
    with engine.connect() as conn:
        twice = conn.execute(text("SELECT id, assessment_available, risk_score, payload FROM inference_records ORDER BY id")).all()
    assert once == twice
    engine.dispose()


@pytest.mark.parametrize("payload_sql", [
    "NULL",                                   # SQL NULL: json_set(NULL, ...) is NULL
    "'this is { not json'",                   # malformed text: json_set raises / returns NULL
    "'null'",                                 # JSON null: valid, but not an object
    "'[1, 2, 3]'",                            # JSON array
    "'17'",                                   # JSON number
], ids=["sql-null", "malformed", "json-null", "json-array", "json-number"])
@pytest.mark.parametrize("health", ["UNAVAILABLE", "FULL"], ids=["unavailable-row", "assessed-row"])
def test_migration_never_erases_a_row_whose_payload_is_unusable(tmp_path, monkeypatch, payload_sql, health):
    from app import db
    engine = make_legacy_engine(tmp_path, with_records=False)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO inference_records(id,session_id,window_id,risk_score,risk_level,alert_severity,"
            f"system_health,payload) VALUES (1,'legacy',3,0.0,'Low','NORMAL','{health}',{payload_sql})"))
        before = conn.execute(text("SELECT payload FROM inference_records WHERE id=1")).scalar()
    monkeypatch.setattr(db, "engine", engine)
    db.initialize_database()  # must not raise on malformed JSON
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM inference_records")).scalar() == 1
        after = conn.execute(text("SELECT payload FROM inference_records WHERE id=1")).scalar()
        assert after == before  # not NULLed, not rewritten
    engine.dispose()


def test_migrated_legacy_rows_export_as_json_booleans_and_nulls(tmp_path, monkeypatch):
    """End to end: the export streams the stored blob verbatim, so the migration must
    have written real JSON true/false/null - an integer would leak onto the wire."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app import db
    from app.db import get_db
    from app.main import app

    engine = make_legacy_engine(tmp_path)
    monkeypatch.setattr(db, "engine", engine)
    db.initialize_database()
    factory = sessionmaker(bind=engine)

    def migrated_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = migrated_db
    try:
        client = TestClient(app)
        response = client.get("/api/sessions/legacy/export?format=json")
        assert response.status_code == 200
        assessed, fabricated, plain = response.json()["records"]
        assert assessed["assessment_available"] is True
        assert fabricated["assessment_available"] is False
        assert all(fabricated[name] is None for name in FOUR)
        assert plain["proof"] == "keep this" and "assessment_available" not in plain
        assert '"assessment_available": 1' not in response.text
        assert '"assessment_available": 0' not in response.text
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
