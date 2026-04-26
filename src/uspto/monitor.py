"""Monitor: download + process daily files since last seen, surface new rows."""
import json
import sqlite3
import zipfile
import io
from datetime import date, datetime, timedelta
from .client import USPTOClient
from .extract import iter_case_files, extract_application, extract_nice_classes
from .filter import classify
from .storage import (
    get_existing_serials, get_max_filing_date,
    upsert_application, upsert_nice_classes,
)


TSDR_URL = "https://tsdr.uspto.gov/#caseNumber={sn}&caseType=SERIAL_NO&searchType=statusSearch"


def run_monitor(
    client: USPTOClient,
    conn: sqlite3.Connection,
    today: date | None = None,
    since: date | None = None,
) -> list[dict]:
    """Download daily files since `since` (default: max filing date in DB),
    classify, UPSERT in-scope rows, return the newly-inserted ones."""
    today = today or date.today()
    since = since or get_max_filing_date(conn) or (today - timedelta(days=7))

    candidates: list[tuple[dict, list[str]]] = []
    files = client.list_files(date_from=since, date_to=today)
    for f in files:
        zip_bytes = client.download_file(f["fileName"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            xml_names = [n for n in z.namelist() if n.endswith(".xml")]
            if not xml_names:
                continue
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
            candidates.append((row, classes))

    serials = [r["serial_number"] for r, _ in candidates]
    existing = get_existing_serials(conn, serials)
    new_rows: list[dict] = []
    for row, classes in candidates:
        if row["serial_number"] in existing:
            continue
        upsert_application(conn, row)
        upsert_nice_classes(conn, row["serial_number"], classes)
        new_rows.append(row)

    conn.execute(
        "INSERT INTO monitor_runs (run_at, since_date, new_count) VALUES (?, ?, ?)",
        (datetime.utcnow(), since, len(new_rows)),
    )
    conn.commit()
    return new_rows


def format_table(rows: list[dict]) -> str:
    if not rows:
        return "(no new filings)\n"
    lines = ["SERIAL      FILED       OWNER                      MARK"]
    for r in rows:
        lines.append(
            f"{r['serial_number']:<11} {str(r['filing_date']):<11} "
            f"{(r.get('owner_name') or '')[:25]:<26} {r.get('mark_text', '')}"
        )
    return "\n".join(lines) + "\n"


def format_markdown(rows: list[dict]) -> str:
    if not rows:
        return "_No new filings._\n"
    out = ["| Serial | Filed | Owner | Mark | AI terms |", "|---|---|---|---|---|"]
    for r in rows:
        url = TSDR_URL.format(sn=r["serial_number"])
        ai = ", ".join(r.get("matched_ai_terms", []) or [])
        out.append(
            f"| [{r['serial_number']}]({url}) | {r['filing_date']} | "
            f"{r.get('owner_name', '')} | {r.get('mark_text', '')} | {ai} |"
        )
    return "\n".join(out) + "\n"


def format_json(rows: list[dict]) -> str:
    def default(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return str(o)
    return json.dumps(rows, default=default, indent=2)
