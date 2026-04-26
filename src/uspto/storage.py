import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    serial_number       TEXT PRIMARY KEY,
    mark_text           TEXT,
    filing_date         DATE,
    registration_date   DATE,
    status_code         TEXT,
    status_description  TEXT,
    owner_name          TEXT,
    owner_state         TEXT,
    owner_country       TEXT,
    description         TEXT,
    matched_ai_terms    TEXT,
    matched_hc_terms    TEXT,
    fetched_at          TIMESTAMP,
    raw_json            TEXT
);

CREATE TABLE IF NOT EXISTS nice_classes (
    serial_number  TEXT,
    class_code     TEXT,
    PRIMARY KEY (serial_number, class_code)
);

CREATE TABLE IF NOT EXISTS monitor_runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at      TIMESTAMP,
    since_date  DATE,
    new_count   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_applications_filing_date
    ON applications(filing_date);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_application(conn: sqlite3.Connection, row: dict) -> None:
    # Caller is responsible for committing — keeps backfill loops fast.
    payload = {**row}
    payload["matched_ai_terms"] = json.dumps(payload.get("matched_ai_terms") or [])
    payload["matched_hc_terms"] = json.dumps(payload.get("matched_hc_terms") or [])
    conn.execute(
        """
        INSERT INTO applications (
            serial_number, mark_text, filing_date, registration_date,
            status_code, status_description, owner_name, owner_state,
            owner_country, description, matched_ai_terms, matched_hc_terms,
            fetched_at, raw_json
        ) VALUES (
            :serial_number, :mark_text, :filing_date, :registration_date,
            :status_code, :status_description, :owner_name, :owner_state,
            :owner_country, :description, :matched_ai_terms, :matched_hc_terms,
            :fetched_at, :raw_json
        )
        ON CONFLICT(serial_number) DO UPDATE SET
            mark_text=excluded.mark_text,
            filing_date=excluded.filing_date,
            registration_date=excluded.registration_date,
            status_code=excluded.status_code,
            status_description=excluded.status_description,
            owner_name=excluded.owner_name,
            owner_state=excluded.owner_state,
            owner_country=excluded.owner_country,
            description=excluded.description,
            matched_ai_terms=excluded.matched_ai_terms,
            matched_hc_terms=excluded.matched_hc_terms,
            fetched_at=excluded.fetched_at,
            raw_json=excluded.raw_json
        """,
        payload,
    )


def upsert_nice_classes(
    conn: sqlite3.Connection, serial_number: str, class_codes: Iterable[str]
) -> None:
    # Caller is responsible for committing.
    conn.executemany(
        "INSERT OR IGNORE INTO nice_classes(serial_number, class_code) VALUES (?, ?)",
        [(serial_number, code) for code in class_codes],
    )


def get_max_filing_date(conn: sqlite3.Connection) -> date | None:
    row = conn.execute("SELECT MAX(filing_date) FROM applications").fetchone()
    if row[0] is None:
        return None
    return date.fromisoformat(row[0])


def get_existing_serials(
    conn: sqlite3.Connection, serials: list[str]
) -> set[str]:
    if not serials:
        return set()
    placeholders = ",".join("?" * len(serials))
    cursor = conn.execute(
        f"SELECT serial_number FROM applications WHERE serial_number IN ({placeholders})",
        serials,
    )
    return {r[0] for r in cursor.fetchall()}
