"""Task 10 / R31: the export must survive stored rows whose payload cannot be read.

A history row can hold SQL NULL, text that is not JSON, or JSON that is not an object.
The export used to fail on such a row INSIDE the response generator - after the 200 and
the first bytes were already sent - so the client received half a JSON document or CSV
file and, depending on the server, either a reset connection or a truncated body that
looked like a download. The guard exports the row as a marked minimal record instead:
never dropped, never given invented risk values.

Expectations are literals. The two GOOD_* strings were captured from the export code as
it was BEFORE the guard (HEAD a0859bd) for the same stored payload, so they pin "a row
that was readable exports byte for byte as before"; they were not derived from the code
under test.
"""
import csv
import io
import json

import pytest
from sqlalchemy import text

from app import models

SID = "S1"

# A realistic readable payload (flagged False). Key order matters for the byte check.
GOOD_PAYLOAD = {
    "session_id": "S1", "window_id": 1, "timestamp": "2026-10-01T09:00:00+00:00",
    "P_distraction": 0.25, "P_telemetry_anomaly": 0.5, "RiskScore": 37.5, "RiskLevel": "Medium",
    "DominantEvidence": "Telemetry-dominant", "AlertSeverity": "CAUTION", "SystemHealth": "FULL",
    "assessment_available": True, "latency_ms": 12, "operation_mode": "LIVE_MODEL_RUNTIME",
    "modality_freshness": {"vision": "fresh", "telemetry": "fresh"},
    "visual_top_classes": [{"label": "safe_driving", "probability": 0.75}],
    "provenance": {"provider": "T", "vision_source": "camera_frame", "request_id": "=cmd",
                   "P_distraction_raw": 0.25},
    "explanation": "=starts with equals",
}
# Pre-guard export of GOOD_PAYLOAD, as one JSON array element and as one CSV record.
GOOD_JSON_ELEMENT = (
    '{"session_id": "S1", "window_id": 1, "timestamp": "2026-10-01T09:00:00+00:00", "P_distraction": 0.25, '
    '"P_telemetry_anomaly": 0.5, "RiskScore": 37.5, "RiskLevel": "Medium", "DominantEvidence": '
    '"Telemetry-dominant", "AlertSeverity": "CAUTION", "SystemHealth": "FULL", "assessment_available": true, '
    '"latency_ms": 12, "operation_mode": "LIVE_MODEL_RUNTIME", "modality_freshness": {"vision": "fresh", '
    '"telemetry": "fresh"}, "visual_top_classes": [{"label": "safe_driving", "probability": 0.75}], '
    '"provenance": {"provider": "T", "vision_source": "camera_frame", "request_id": "=cmd", '
    '"P_distraction_raw": 0.25}, "explanation": "=starts with equals", "flagged": false}'
)
# The pre-guard line ended "...,true,0.25,\r\n"; the two appended columns add ",," (both empty).
GOOD_CSV_RECORD = (
    "S1,1,2026-10-01T09:00:00+00:00,LIVE_MODEL_RUNTIME,0.25,0.5,37.5,Medium,Telemetry-dominant,CAUTION,FULL,12,"
    "false,camera_frame,,,,'=cmd,\"{\"\"provider\"\": \"\"T\"\", \"\"vision_source\"\": \"\"camera_frame\"\", "
    "\"\"request_id\"\": \"\"=cmd\"\", \"\"P_distraction_raw\"\": 0.25}\",\"{\"\"vision\"\": \"\"fresh\"\", "
    "\"\"telemetry\"\": \"\"fresh\"\"}\",\"[{\"\"label\"\": \"\"safe_driving\"\", \"\"probability\"\": 0.75}]\","
    "null,null,null,'=starts with equals,true,0.25,,,\r\n"
)
SMALL_PAYLOAD = {"window_id": 6, "RiskScore": 12.5}
SMALL_JSON_ELEMENT = '{"window_id": 6, "RiskScore": 12.5, "flagged": true}'

NULL_RISK = {"RiskScore": None, "RiskLevel": None, "DominantEvidence": None, "AlertSeverity": None}
# (window_id, flagged, stored payload as SQL value, expected reason prefix)
BAD_ROWS = [
    (2, True, None, "payload is NULL"),
    (3, False, "{not json", "payload is not valid JSON: "),
    (4, True, "[1, 2]", "payload is a JSON array, not an object"),
    (5, False, '"just a string"', "payload is a JSON string, not an object"),
    (7, True, "null", "payload is a JSON null, not an object"),
    # SQLite is dynamically typed: "42" is stored as an INTEGER (the column has NUMERIC affinity)
    # and bytes as a BLOB. Both reach the exporter as non-str values.
    (8, False, "42", "payload is a JSON number, not an object"),
    (9, True, b"\xff\xfe", "payload is not valid JSON: the stored bytes are not UTF-8"),
]
# A BLOB that holds a valid JSON object is a readable row.
BLOB_PAYLOAD = b'{"window_id": 10, "RiskScore": 1.5}'
BLOB_JSON_ELEMENT = '{"window_id": 10, "RiskScore": 1.5, "flagged": false}'


def _insert_good(factory, window_id, payload, flagged):
    with factory() as db:
        db.add(models.InferenceRecord(session_id=SID, window_id=window_id, flagged=flagged, payload=payload))
        db.commit()


def _insert_raw(factory, window_id, flagged, raw):
    """Bypass the JSON type, as a legacy writer or a hand edit would have."""
    with factory() as db:
        db.execute(text("INSERT INTO inference_records(session_id, window_id, flagged, payload) "
                        "VALUES (:s, :w, :f, :p)"), {"s": SID, "w": window_id, "f": flagged, "p": raw})
        db.commit()


@pytest.fixture
def mixed(api, api_factory):
    """Session S1: windows 1, 6 and 10 readable, windows 2-5 and 7-9 unreadable (see BAD_ROWS)."""
    client, _ = api
    assert client.post("/api/sessions", json={"session_id": SID}).status_code == 201
    _insert_good(api_factory, 1, GOOD_PAYLOAD, False)
    _insert_good(api_factory, 6, SMALL_PAYLOAD, True)
    for window_id, flagged, raw, _ in BAD_ROWS:
        _insert_raw(api_factory, window_id, flagged, raw)
    _insert_raw(api_factory, 10, False, BLOB_PAYLOAD)
    return client


def test_the_malformed_fixtures_really_defeat_the_orm(api, api_factory):
    """Guards the guard: if the ORM could still read row 3, the tests below would pass
    without ever exercising the raw-text path."""
    client, _ = api
    assert client.post("/api/sessions", json={"session_id": SID}).status_code == 201
    _insert_raw(api_factory, 3, False, "{not json")
    with api_factory() as db, pytest.raises(ValueError):
        db.query(models.InferenceRecord).filter_by(session_id=SID, window_id=3).one().payload


def test_readable_rows_export_exactly_as_before(api, api_factory):
    client, _ = api
    assert client.post("/api/sessions", json={"session_id": SID}).status_code == 201
    _insert_good(api_factory, 1, GOOD_PAYLOAD, False)
    _insert_good(api_factory, 6, SMALL_PAYLOAD, True)

    response = client.get(f"/api/sessions/{SID}/export?format=json")
    assert response.status_code == 200
    assert response.text == '{"session_id":"S1","records":[' + GOOD_JSON_ELEMENT + "," + SMALL_JSON_ELEMENT + "]}"

    response = client.get(f"/api/sessions/{SID}/export?format=csv")
    assert response.status_code == 200
    lines = response.text.split("\r\n")
    assert lines[0].endswith(",P_distraction_raw,P_telemetry_raw,payload_unreadable,payload_unreadable_reason")
    assert len(lines[0].split(",")) == 30
    assert response.text.startswith(lines[0] + "\r\n" + GOOD_CSV_RECORD)


def test_json_export_marks_every_unreadable_row_and_stays_whole(mixed):
    response = mixed.get(f"/api/sessions/{SID}/export?format=json")
    assert response.status_code == 200
    body = response.json()  # the whole document parses: nothing was cut off
    assert body["session_id"] == SID
    records = body["records"]
    assert [r["window_id"] for r in records] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]  # none dropped, in order
    by_window = {r["window_id"]: r for r in records}

    for window_id, flagged, _, reason in BAD_ROWS:
        record = by_window[window_id]
        assert record["payload_unreadable"] is True
        assert record["payload_unreadable_reason"].startswith(reason), record
        assert record["flagged"] is flagged
        assert record["session_id"] == SID
        for name, value in NULL_RISK.items():
            assert record[name] is value, name  # present and null, never invented
        assert set(record) == {"session_id", "window_id", "flagged", "payload_unreadable",
                               "payload_unreadable_reason", *NULL_RISK}
    assert by_window[3]["payload_unreadable_reason"] != "payload is not valid JSON: "  # carries the cause

    # Readable rows are untouched, byte for byte, and carry no marker.
    assert GOOD_JSON_ELEMENT in response.text and SMALL_JSON_ELEMENT in response.text
    assert BLOB_JSON_ELEMENT in response.text  # a BLOB holding a JSON object is readable
    for readable in (1, 6, 10):
        assert "payload_unreadable" not in by_window[readable]


def test_csv_export_marks_every_unreadable_row_and_stays_whole(mixed):
    response = mixed.get(f"/api/sessions/{SID}/export?format=csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert [row["window_id"] for row in rows] == [str(n) for n in range(1, 11)]  # none dropped
    by_window = {int(row["window_id"]): row for row in rows}

    for window_id, flagged, _, reason in BAD_ROWS:
        row = by_window[window_id]
        assert row["payload_unreadable"] == "true"
        assert row["payload_unreadable_reason"].startswith(reason), row
        assert row["flagged"] == ("true" if flagged else "false")
        assert row["session_id"] == SID
        for name in NULL_RISK:
            assert row[name] == "", name  # the CSV encoding of null
        for name in ("P_distraction", "P_telemetry_anomaly", "SystemHealth", "assessment_available",
                     "timestamp", "provenance"):
            assert row[name] == "", name  # nothing else is invented either

    assert GOOD_CSV_RECORD in response.text  # the readable row is byte for byte what it was
    for window_id in (1, 6, 10):
        assert by_window[window_id]["payload_unreadable"] == ""
        assert by_window[window_id]["payload_unreadable_reason"] == ""
    assert by_window[6]["RiskScore"] == "12.5" and by_window[6]["flagged"] == "true"
    assert by_window[10]["RiskScore"] == "1.5"  # the BLOB row


@pytest.mark.parametrize("fmt", ["json", "csv"])
def test_a_session_of_only_unreadable_rows_still_exports_every_row(api, api_factory, fmt):
    client, _ = api
    assert client.post("/api/sessions", json={"session_id": SID}).status_code == 201
    _insert_raw(api_factory, 1, False, None)
    _insert_raw(api_factory, 2, False, "[]")
    response = client.get(f"/api/sessions/{SID}/export?format={fmt}")
    assert response.status_code == 200
    if fmt == "json":
        assert [r["window_id"] for r in response.json()["records"]] == [1, 2]
    else:
        assert [r["window_id"] for r in csv.DictReader(io.StringIO(response.text))] == ["1", "2"]


# Controller follow-up (Task 10 part 1 review, Important): a READABLE payload whose
# provenance is not an object. The CSV row builder used to read keys out of it inside the
# generator: a number or a list raised after the 200 (truncated CSV), a string turned
# ``k in provenance`` into a substring test. JSON already exported these verbatim.
ODD_PROVENANCE = [
    (2, 5, "5"),
    (3, ["request_id"], '["request_id"]'),
    (4, "has request_id inside", '"has request_id inside"'),
]


def test_csv_export_survives_a_provenance_that_is_not_an_object(api, api_factory):
    client, _ = api
    assert client.post("/api/sessions", json={"session_id": SID}).status_code == 201
    _insert_good(api_factory, 1, GOOD_PAYLOAD, False)
    for window_id, provenance, _ in ODD_PROVENANCE:
        _insert_good(api_factory, window_id, {"window_id": window_id, "RiskScore": 40.0, "provenance": provenance}, False)
    _insert_good(api_factory, 5, {"window_id": 5, "RiskScore": 41.0, "provenance": {"request_id": "r5"}}, False)

    response = client.get(f"/api/sessions/{SID}/export?format=csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert [row["window_id"] for row in rows] == ["1", "2", "3", "4", "5"]
    assert response.text.splitlines(keepends=True)[1] == GOOD_CSV_RECORD  # a normal row is untouched
    for window_id, _, cell in ODD_PROVENANCE:
        row = rows[window_id - 1]
        assert row["provenance"] == cell        # verbatim
        assert row["request_id"] == ""          # nothing read out of a non-object
        assert row["RiskScore"] == "40.0"       # the readable payload still exports
        assert row["payload_unreadable"] == ""  # the payload itself was readable
    assert rows[4]["request_id"] == "r5"       # an object provenance still feeds its column

    json_response = client.get(f"/api/sessions/{SID}/export?format=json")
    assert json_response.status_code == 200
    assert [r.get("provenance") for r in json_response.json()["records"][1:4]] == [5, ["request_id"], "has request_id inside"]
