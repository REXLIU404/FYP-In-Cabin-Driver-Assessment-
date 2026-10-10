"""The additive SQLite upgrade must preserve legacy session evidence."""
import json

from sqlalchemy import create_engine, text, inspect


def test_legacy_database_migration_preserves_rows_and_allocates_above_old_max(tmp_path, monkeypatch):
    from app import db
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sessions(id VARCHAR PRIMARY KEY, created_at DATETIME, description VARCHAR)"))
        conn.execute(text("CREATE TABLE inference_records(id INTEGER PRIMARY KEY, session_id VARCHAR, window_id INTEGER, timestamp VARCHAR, p_distraction FLOAT, p_telemetry_anomaly FLOAT, risk_score FLOAT, risk_level VARCHAR, dominant_evidence VARCHAR, alert_severity VARCHAR, system_health VARCHAR, latency_ms INTEGER, flagged BOOLEAN, payload JSON)"))
        conn.execute(text("INSERT INTO sessions VALUES ('legacy', '2026-09-28T00:00:00', 'keep me')"))
        conn.execute(text("INSERT INTO inference_records(id,session_id,window_id,payload) VALUES (1,'legacy',17,:payload)"), {"payload": json.dumps({"proof": "keep this"})})
    monkeypatch.setattr(db, "engine", engine)
    db.initialize_database()
    db.initialize_database()  # repeatable migration
    with engine.connect() as conn:
        row = conn.execute(text("SELECT description,next_window_id,runtime_state FROM sessions WHERE id='legacy'")).one()
        assert row[0] == "keep me"
        assert row[1] == 17
        assert json.loads(row[2]) == {}
        assert json.loads(conn.execute(text("SELECT payload FROM inference_records")).scalar()) == {"proof": "keep this"}
        indexes = {index["name"] for index in inspect(conn).get_indexes("inference_records")}
        assert "uq_record_session_window" in indexes
        assert "uq_record_session_request" in indexes
    engine.dispose()
