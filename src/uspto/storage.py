import sqlite3
from pathlib import Path

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
