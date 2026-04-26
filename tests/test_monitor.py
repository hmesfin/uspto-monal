import json
import io
import zipfile
from datetime import date
from unittest.mock import MagicMock
from uspto.monitor import run_monitor, format_table, format_markdown, format_json
from uspto.storage import connect, create_schema, upsert_application


def _make_zip(xml_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("apa.xml", xml_bytes)
    return buf.getvalue()


def _existing_row(tmp_path):
    conn = connect(tmp_path / "x.db")
    create_schema(conn)
    upsert_application(conn, {
        "serial_number": "97000001",
        "mark_text": "EXISTING",
        "filing_date": date(2025, 1, 1),
        "registration_date": None,
        "status_code": "630", "status_description": "New",
        "owner_name": "X", "owner_state": "CA", "owner_country": "US",
        "description": "AI diagnostic", "matched_ai_terms": ["AI"],
        "matched_hc_terms": ["diagnostic"],
        "fetched_at": "2026-01-01", "raw_json": "{}",
    })
    conn.commit()
    return conn


def test_run_monitor_inserts_new_in_scope_rows(tmp_path):
    conn = _existing_row(tmp_path)
    client = MagicMock()
    client.list_files.return_value = [{"fileName": "apa20260420.zip"}]
    client.download_file.return_value = _make_zip(b"""<?xml version="1.0"?>
<trademark-applications-daily>
  <case-file>
    <serial-number>97000999</serial-number>
    <case-file-header>
      <mark-identification>NEWAI</mark-identification>
      <filing-date>20260420</filing-date>
      <status-code>630</status-code>
    </case-file-header>
    <case-file-statements>
      <case-file-statement>
        <type-code>GS0341</type-code>
        <text>machine learning clinical decision support</text>
      </case-file-statement>
    </case-file-statements>
    <classifications>
      <classification><international-code>042</international-code></classification>
    </classifications>
    <case-file-owners>
      <case-file-owner><party-name>Y Corp</party-name></case-file-owner>
    </case-file-owners>
  </case-file>
</trademark-applications-daily>
""")
    new_rows = run_monitor(client, conn, today=date(2026, 4, 26))
    assert [r["serial_number"] for r in new_rows] == ["97000999"]


def test_run_monitor_records_run(tmp_path):
    conn = _existing_row(tmp_path)
    client = MagicMock()
    client.list_files.return_value = []
    run_monitor(client, conn, today=date(2026, 4, 26))
    cursor = conn.execute("SELECT new_count FROM monitor_runs")
    assert cursor.fetchone()[0] == 0


def test_format_json_is_valid():
    rows = [{"serial_number": "1", "mark_text": "X", "filing_date": "2026-04-01"}]
    assert json.loads(format_json(rows)) == rows


def test_format_table_includes_serial():
    rows = [{"serial_number": "97000999", "mark_text": "NEWAI",
             "filing_date": "2026-04-20", "owner_name": "Y",
             "matched_ai_terms": ["ML"]}]
    assert "97000999" in format_table(rows)


def test_format_markdown_has_tsdr_link():
    rows = [{"serial_number": "97000999", "mark_text": "NEWAI",
             "filing_date": "2026-04-20", "owner_name": "Y",
             "matched_ai_terms": ["ML"]}]
    out = format_markdown(rows)
    assert "97000999" in out
    assert "tsdr.uspto.gov" in out
