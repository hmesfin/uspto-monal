import json
from datetime import date, datetime
from uspto.storage import (
    connect, create_schema, upsert_application,
    upsert_nice_classes, get_max_filing_date, get_existing_serials,
)


def _row():
    return {
        "serial_number": "97000001",
        "mark_text": "MEDAI",
        "filing_date": date(2025, 1, 15),
        "registration_date": None,
        "status_code": "630",
        "status_description": "New Application",
        "owner_name": "Acme Health Inc",
        "owner_state": "CA",
        "owner_country": "US",
        "description": "AI-powered diagnostic software for clinical use",
        "matched_ai_terms": ["AI"],
        "matched_hc_terms": ["diagnostic", "clinical"],
        "fetched_at": datetime(2026, 4, 26, 12, 0, 0),
        "raw_json": '{"foo": "bar"}',
    }


def test_upsert_application_inserts_then_updates(tmp_path):
    conn = connect(tmp_path / "x.db")
    create_schema(conn)
    row = _row()
    upsert_application(conn, row)
    upsert_application(conn, {**row, "mark_text": "MEDAI v2"})
    cursor = conn.execute("SELECT mark_text, COUNT(*) FROM applications GROUP BY serial_number")
    res = cursor.fetchone()
    assert res[0] == "MEDAI v2"
    assert res[1] == 1


def test_upsert_nice_classes_dedupes(tmp_path):
    conn = connect(tmp_path / "x.db")
    create_schema(conn)
    upsert_nice_classes(conn, "97000001", ["9", "42"])
    upsert_nice_classes(conn, "97000001", ["9", "10"])  # 9 already there
    cursor = conn.execute(
        "SELECT class_code FROM nice_classes WHERE serial_number=? ORDER BY class_code",
        ("97000001",),
    )
    codes = [r[0] for r in cursor.fetchall()]
    assert codes == ["10", "42", "9"]  # 9 is text-sorted last


def test_get_max_filing_date_empty_returns_none(tmp_path):
    conn = connect(tmp_path / "x.db")
    create_schema(conn)
    assert get_max_filing_date(conn) is None


def test_get_max_filing_date_returns_latest(tmp_path):
    conn = connect(tmp_path / "x.db")
    create_schema(conn)
    upsert_application(conn, _row())
    upsert_application(conn, {**_row(), "serial_number": "97000002", "filing_date": date(2025, 6, 1)})
    assert get_max_filing_date(conn) == date(2025, 6, 1)


def test_get_existing_serials(tmp_path):
    conn = connect(tmp_path / "x.db")
    create_schema(conn)
    upsert_application(conn, _row())
    serials = get_existing_serials(conn, ["97000001", "97000099"])
    assert serials == {"97000001"}
