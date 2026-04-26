import zipfile
import io
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock
from uspto.backfill import run_backfill, month_windows, process_zip
from uspto.storage import connect, create_schema


FIX = Path(__file__).parent / "fixtures" / "api"


def test_month_windows_yields_n_months():
    windows = list(month_windows(date(2026, 4, 26), months=3))
    assert len(windows) == 3
    assert windows[0][0] <= date(2026, 4, 26) <= windows[0][1]


def _make_zip(xml_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("apa.xml", xml_bytes)
    return buf.getvalue()


def test_process_zip_inserts_in_scope_only(tmp_path):
    conn = connect(tmp_path / "x.db")
    create_schema(conn)
    # Two records: one in-scope (AI + diagnostic + class 42), one out-of-scope
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<trademark-applications-daily>
  <case-file>
    <serial-number>97000001</serial-number>
    <case-file-header>
      <mark-identification>MEDAI</mark-identification>
      <filing-date>20250315</filing-date>
      <status-code>630</status-code>
    </case-file-header>
    <case-file-statements>
      <case-file-statement>
        <type-code>GS0341</type-code>
        <text>AI-powered diagnostic software for clinical use</text>
      </case-file-statement>
    </case-file-statements>
    <classifications>
      <classification><international-code>042</international-code></classification>
    </classifications>
    <case-file-owners>
      <case-file-owner><party-name>Acme Health</party-name></case-file-owner>
    </case-file-owners>
  </case-file>
  <case-file>
    <serial-number>97000002</serial-number>
    <case-file-header>
      <mark-identification>BOOTBARN</mark-identification>
      <filing-date>20250315</filing-date>
      <status-code>630</status-code>
    </case-file-header>
    <case-file-statements>
      <case-file-statement>
        <type-code>GS0341</type-code>
        <text>Cowboy boots and accessories</text>
      </case-file-statement>
    </case-file-statements>
    <classifications>
      <classification><international-code>025</international-code></classification>
    </classifications>
    <case-file-owners>
      <case-file-owner><party-name>Boots Inc</party-name></case-file-owner>
    </case-file-owners>
  </case-file>
</trademark-applications-daily>
"""
    n = process_zip(_make_zip(xml), conn)
    assert n == 1
    cursor = conn.execute("SELECT serial_number FROM applications")
    assert [r[0] for r in cursor.fetchall()] == ["97000001"]


def test_run_backfill_calls_client_per_window(tmp_path):
    conn = connect(tmp_path / "x.db")
    create_schema(conn)
    client = MagicMock()
    client.list_files.return_value = []  # no files → no work
    n = run_backfill(client, conn, months=2, today=date(2026, 4, 30))
    assert n == 0
    assert client.list_files.call_count == 2  # one per month
