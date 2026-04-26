"""Backfill orchestrator: iterate date windows, download daily files, ingest."""
import sqlite3
import zipfile
import io
from datetime import date, timedelta
from typing import Iterator
from .client import USPTOClient
from .extract import iter_case_files, extract_application, extract_nice_classes
from .filter import classify
from .storage import upsert_application, upsert_nice_classes


def month_windows(today: date, months: int) -> Iterator[tuple[date, date]]:
    """Yield (start, end) date pairs for each of the past N months,
    most recent first."""
    end = today
    for _ in range(months):
        start = (end - timedelta(days=30)).replace(day=1)
        yield (start, end)
        end = start - timedelta(days=1)


def process_zip(zip_bytes: bytes, conn: sqlite3.Connection) -> int:
    """Parse one daily ZIP, classify, UPSERT in-scope rows. Returns count inserted."""
    inserted = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        xml_names = [n for n in z.namelist() if n.endswith(".xml")]
        if not xml_names:
            return 0
        xml_bytes = z.read(xml_names[0])
    for elem in iter_case_files(xml_bytes):
        row = extract_application(elem)
        if not row["serial_number"]:
            continue
        classes = extract_nice_classes(elem)
        cls = classify(row["description"], classes)
        if not cls.in_scope:
            continue
        row["matched_ai_terms"] = cls.ai_terms
        row["matched_hc_terms"] = cls.hc_terms
        upsert_application(conn, row)
        upsert_nice_classes(conn, row["serial_number"], classes)
        inserted += 1
    return inserted


def run_backfill(
    client: USPTOClient,
    conn: sqlite3.Connection,
    months: int = 60,
    today: date | None = None,
) -> int:
    """Iterate month windows, list files, download + process each.
    Returns total in-scope rows inserted/updated.
    """
    today = today or date.today()
    total = 0
    for start, end in month_windows(today, months):
        files = client.list_files(date_from=start, date_to=end)
        for f in files:
            zip_bytes = client.download_file(f["fileName"])
            total += process_zip(zip_bytes, conn)
        # Commit at end of each month so an interrupt only loses one window.
        conn.commit()
    return total
