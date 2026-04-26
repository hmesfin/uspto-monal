# USPTO Trademark CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI that pulls USPTO trademark filings filtered to healthcare+AI, monitors weekly, and renders 5-year trend reports.

**Architecture:** Single Python package with Typer CLI. Three commands (`backfill`, `monitor`, `report`). USPTO Open Data Portal trademark search API → SQLite → pandas/Plotly. Filter is hardcoded in v1: Nice classes {5,9,10,42,44} ∩ AI keywords ∩ healthcare keywords in goods/services description.

**Tech Stack:** Python 3.11+, uv, Typer, httpx, sqlite3 (stdlib), pandas, Plotly, Jinja2, python-dotenv, pytest, respx (HTTP mocking).

**Configuration:** 12-factor — config via environment variables, with `.env` loaded for local dev (`.env` is gitignored; `.env.example` is committed). This is a public OSS project on GitHub; never commit secrets.

**Reference:** See `docs/plans/2026-04-26-uspto-cli-design.md` for the approved design.

---

## Important note on the USPTO data path

The USPTO Open Data Portal does NOT have a JSON search API for trademarks. (Verified during a Task 5 spike — only patent endpoints have `/search`.) The authoritative trademark data is the **`TRTDXFAP` bulk dataset** ("Trademark Full Text XML Data – Daily Applications") — a daily ZIP-of-XML file per filing date.

We will:
- **List files**: `GET https://api.uspto.gov/api/v1/datasets/products/TRTDXFAP?fileDataFromDate=YYYY-MM-DD&fileDataToDate=YYYY-MM-DD` returns `{"productFileBag": {"fileDataBag": [{"fileName", "fileDataFromDate", "fileDownloadURI", "fileSize"}, ...]}}`
- **Download**: `GET /api/v1/datasets/products/files/TRTDXFAP/{fileName}` returns a ZIP containing one XML file
- **Auth**: `X-API-KEY` header (verified working)
- **Parse**: `xml.etree.iterparse` for streaming (files can hit 200 MB)
- **Filter client-side** via the healthcare+AI classifier from Task 4

Sign up for an ODP API key at https://data.uspto.gov/ before starting Task 5.

---

## Task 0: Project scaffolding

> Git repo is already initialized. This task only creates the project files.

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `pyproject.toml`
- Create: `src/uspto/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create .gitignore and .env.example**

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
.pytest_cache/
*.egg-info/
dist/
build/
*.db
*.db-journal
.coverage
trends.html
tests/fixtures/api/*.json.local
.env
.env.local
```

`.env.example` (committed; users copy to `.env` and fill in):
```
# USPTO Open Data Portal API key — get one at https://data.uspto.gov/
USPTO_API_KEY=

# Where to keep the local SQLite DB (defaults to ~/.local/share/uspto/trademarks.db)
# USPTO_DB_PATH=
```

**Step 2: Create pyproject.toml**

```toml
[project]
name = "uspto"
version = "0.1.0"
description = "CLI for monitoring USPTO trademark filings (healthcare+AI focus)"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "httpx>=0.27",
    "pandas>=2.2",
    "plotly>=5.20",
    "jinja2>=3.1",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "respx>=0.21",
    "pytest-cov>=5.0",
]

[project.scripts]
uspto = "uspto.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/uspto"]
```

**Step 3: Create src/uspto/__init__.py and tests scaffolding**

`src/uspto/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: empty
`tests/conftest.py`:
```python
import pytest
```

**Step 4: Create venv, install, verify import**

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
python -c "import uspto; print(uspto.__version__)"
```

Expected output: `0.1.0`

**Step 5: Commit**

```bash
git add .gitignore .env.example pyproject.toml src/ tests/
git commit -m "chore: scaffold project"
```

---

## Task 1: Config loader (TDD)

Config comes from environment variables. `.env` is auto-loaded (via `python-dotenv`) for local dev convenience; in production/cron the user exports vars themselves.

**Files:**
- Create: `src/uspto/config.py`
- Create: `tests/test_config.py`

**Step 1: Write failing tests**

`tests/test_config.py`:
```python
import os
import pytest
from pathlib import Path
from uspto.config import Config, load_config, ConfigError


def test_load_config_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("USPTO_API_KEY", "abc123")
    monkeypatch.setenv("USPTO_DB_PATH", str(tmp_path / "x.db"))
    cfg = load_config()
    assert cfg.api_key == "abc123"
    assert cfg.db_path == (tmp_path / "x.db").resolve()


def test_load_config_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("USPTO_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="USPTO_API_KEY"):
        load_config()


def test_load_config_default_db_path(monkeypatch):
    monkeypatch.setenv("USPTO_API_KEY", "abc")
    monkeypatch.delenv("USPTO_DB_PATH", raising=False)
    cfg = load_config()
    assert cfg.db_path.is_absolute()
    assert str(cfg.db_path).endswith("uspto/trademarks.db")


def test_db_path_expands_user(monkeypatch):
    monkeypatch.setenv("USPTO_API_KEY", "abc")
    monkeypatch.setenv("USPTO_DB_PATH", "~/foo.db")
    cfg = load_config()
    assert "~" not in str(cfg.db_path)
    assert cfg.db_path.is_absolute()
```

**Step 2: Run tests to verify failure**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: uspto.config`.

**Step 3: Implement config.py**

```python
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


class ConfigError(Exception):
    pass


@dataclass
class Config:
    api_key: str
    db_path: Path


DEFAULT_DB_PATH = "~/.local/share/uspto/trademarks.db"


def load_config() -> Config:
    # Auto-load .env from CWD if present; safe in production (no-op if missing)
    load_dotenv()
    api_key = os.environ.get("USPTO_API_KEY")
    if not api_key:
        raise ConfigError(
            "USPTO_API_KEY is not set.\n"
            "  • Local dev: copy .env.example to .env and fill it in\n"
            "  • Otherwise: export USPTO_API_KEY=...\n"
            "Get a free key at https://data.uspto.gov/"
        )
    db_path = Path(
        os.environ.get("USPTO_DB_PATH") or DEFAULT_DB_PATH
    ).expanduser().resolve()
    return Config(api_key=api_key, db_path=db_path)
```

**Step 4: Run tests, verify all pass**

```bash
pytest tests/test_config.py -v
```

Expected: 4 passed.

**Step 5: Commit**

```bash
git add src/uspto/config.py tests/test_config.py
git commit -m "feat: add config loader with fail-fast validation"
```

---

## Task 2: Storage schema (TDD)

**Files:**
- Create: `src/uspto/storage.py`
- Create: `tests/test_storage_schema.py`

**Step 1: Write failing tests**

`tests/test_storage_schema.py`:
```python
import sqlite3
from uspto.storage import create_schema, connect


def test_create_schema_creates_three_tables(tmp_path):
    db = tmp_path / "x.db"
    conn = connect(db)
    create_schema(conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = [r[0] for r in cursor.fetchall()]
    assert names == ["applications", "monitor_runs", "nice_classes"]


def test_create_schema_is_idempotent(tmp_path):
    db = tmp_path / "x.db"
    conn = connect(db)
    create_schema(conn)
    create_schema(conn)  # should not raise


def test_connect_creates_parent_directory(tmp_path):
    db = tmp_path / "nested" / "dir" / "x.db"
    conn = connect(db)
    assert db.parent.exists()
    conn.close()
```

**Step 2: Run, verify failure**

```bash
pytest tests/test_storage_schema.py -v
```

Expected: ImportError.

**Step 3: Implement storage.py (schema portion)**

```python
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
```

**Step 4: Run tests**

```bash
pytest tests/test_storage_schema.py -v
```

Expected: 3 passed.

**Step 5: Commit**

```bash
git add src/uspto/storage.py tests/test_storage_schema.py
git commit -m "feat: add SQLite schema and connection helper"
```

---

## Task 3: Storage UPSERTs (TDD)

**Files:**
- Modify: `src/uspto/storage.py`
- Create: `tests/test_storage_upsert.py`

**Step 1: Write failing tests**

`tests/test_storage_upsert.py`:
```python
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
```

**Step 2: Run, verify failure**

```bash
pytest tests/test_storage_upsert.py -v
```

Expected: ImportError on the new functions.

**Step 3: Implement (append to storage.py)**

```python
import json
from datetime import date
from typing import Iterable


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
```

**Step 4: Run tests**

```bash
pytest tests/test_storage_upsert.py -v
```

Expected: 5 passed.

**Step 5: Commit**

```bash
git add src/uspto/storage.py tests/test_storage_upsert.py
git commit -m "feat: add UPSERT and query helpers"
```

---

## Task 4: Filter logic (TDD)

**Files:**
- Create: `src/uspto/filter.py`
- Create: `tests/test_filter.py`

**Step 1: Write failing tests**

`tests/test_filter.py`:
```python
from uspto.filter import (
    AI_TERMS, HC_TERMS, NICE_CLASSES,
    match_ai_terms, match_hc_terms, classify,
)


def test_constants_present():
    assert "machine learning" in AI_TERMS
    assert "diagnostic" in HC_TERMS
    assert NICE_CLASSES == {"5", "9", "10", "42", "44"}


def test_match_ai_terms_case_insensitive():
    assert "machine learning" in match_ai_terms(
        "An MACHINE LEARNING based diagnostic tool"
    )


def test_match_ai_terms_word_boundary():
    # 'AI' should not match 'said' or 'paint'
    assert "AI" not in match_ai_terms("she said paint")


def test_match_ai_terms_AI_acronym_matches():
    assert "AI" in match_ai_terms("AI for cancer screening")


def test_classify_in_scope_returns_matched_terms():
    desc = "AI-powered diagnostic software for clinical decision support"
    classes = ["9", "42"]
    result = classify(desc, classes)
    assert result.in_scope is True
    assert "AI" in result.ai_terms
    assert "diagnostic" in result.hc_terms or "clinical" in result.hc_terms


def test_classify_out_of_scope_no_ai():
    result = classify("clinical diagnostic software", ["9"])
    assert result.in_scope is False


def test_classify_out_of_scope_no_healthcare():
    result = classify("AI software for ad targeting", ["9"])
    assert result.in_scope is False


def test_classify_out_of_scope_wrong_class():
    result = classify("AI diagnostic software", ["25"])  # clothing
    assert result.in_scope is False
```

**Step 2: Run, verify failure**

```bash
pytest tests/test_filter.py -v
```

Expected: ImportError.

**Step 3: Implement filter.py**

```python
import re
from dataclasses import dataclass


AI_TERMS = [
    "artificial intelligence",
    "machine learning",
    "neural network",
    "deep learning",
    "LLM",
    "large language model",
    "computer vision",
    "generative AI",
    "AI",
]

HC_TERMS = [
    "health",
    "medical",
    "clinical",
    "diagnostic",
    "patient",
    "therapeutic",
    "disease",
    "telemedicine",
    "pharmaceutical",
    "drug",
]

NICE_CLASSES = {"5", "9", "10", "42", "44"}


def _compile(terms: list[str]) -> list[tuple[str, re.Pattern]]:
    out = []
    for t in terms:
        # word-boundary, case-insensitive; preserve original term in result
        pat = re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)
        out.append((t, pat))
    return out


_AI = _compile(AI_TERMS)
_HC = _compile(HC_TERMS)


def match_ai_terms(text: str) -> list[str]:
    return [t for t, p in _AI if p.search(text)]


def match_hc_terms(text: str) -> list[str]:
    return [t for t, p in _HC if p.search(text)]


@dataclass
class Classification:
    in_scope: bool
    ai_terms: list[str]
    hc_terms: list[str]


def classify(description: str, nice_classes: list[str]) -> Classification:
    ai = match_ai_terms(description or "")
    hc = match_hc_terms(description or "")
    has_class = bool(NICE_CLASSES.intersection(nice_classes))
    in_scope = bool(ai) and bool(hc) and has_class
    return Classification(in_scope=in_scope, ai_terms=ai, hc_terms=hc)
```

**Step 4: Run tests**

```bash
pytest tests/test_filter.py -v
```

Expected: 8 passed.

**Step 5: Commit**

```bash
git add src/uspto/filter.py tests/test_filter.py
git commit -m "feat: add healthcare+AI classifier"
```

---

## Task 5: USPTO ODP datasets client — spike-verified

The Task 5 spike confirmed: trademark data lives in the `TRTDXFAP` daily bulk dataset. The client downloads files; it does not search. Two methods only.

**Files:**
- Create: `scripts/probe_api.py` (committed; reproducible)
- Create: `tests/fixtures/api/files_listing_sample.json` (captured live)
- Create: `tests/fixtures/api/sample_day.zip` OR `tests/fixtures/api/sample_day.xml` (captured live; choose smallest reasonable)
- Create: `src/uspto/client.py`
- Create: `tests/test_client.py`

### Step 1: Probe script

`scripts/probe_api.py`:
```python
"""Probe the USPTO ODP datasets API for the TRTDXFAP trademark bulk product.

Usage:
  USPTO_API_KEY=... python scripts/probe_api.py
Writes:
  tests/fixtures/api/files_listing_sample.json   (file listing for a 1-week window)
  tests/fixtures/api/sample_day.zip              (one daily ZIP)

The captured ZIP is committed to the repo so tests don't need network access.
Expected ZIP size: 5–50 MB. If a single day is too large, narrow the listing
window or pick the smallest file in the listing before downloading.
"""
import json
import os
import sys
from pathlib import Path
import httpx

BASE = "https://api.uspto.gov"
PRODUCT = "TRTDXFAP"
HEADERS = {"X-API-KEY": os.environ["USPTO_API_KEY"]}
FIX = Path("tests/fixtures/api")
FIX.mkdir(parents=True, exist_ok=True)

# 1) List files in a recent week (USPTO publishes Tue–Fri typically; pick a
#    range that's likely to contain at least one file).
listing = httpx.get(
    f"{BASE}/api/v1/datasets/products/{PRODUCT}",
    params={"fileDataFromDate": "2026-04-15", "fileDataToDate": "2026-04-22"},
    headers=HEADERS, timeout=30,
)
listing.raise_for_status()
data = listing.json()
(FIX / "files_listing_sample.json").write_text(json.dumps(data, indent=2))

# 2) Download the smallest file in the listing.
files = data["productFileBag"]["fileDataBag"]
if not files:
    sys.exit("No files in listing — widen the date window")
smallest = min(files, key=lambda f: f.get("fileSize", 1 << 62))
print(f"Downloading {smallest['fileName']} ({smallest.get('fileSize')} bytes)", file=sys.stderr)
zip_resp = httpx.get(
    f"{BASE}/api/v1/datasets/products/files/{PRODUCT}/{smallest['fileName']}",
    headers=HEADERS, timeout=120, follow_redirects=True,
)
zip_resp.raise_for_status()
(FIX / "sample_day.zip").write_bytes(zip_resp.content)
print(f"Saved sample_day.zip ({len(zip_resp.content)} bytes)", file=sys.stderr)
```

### Step 2: Run the probe

```bash
cd /home/hamel/projects/cli-tools/uspto
set -a && source .env && set +a
python scripts/probe_api.py
```

Expected: writes `tests/fixtures/api/files_listing_sample.json` (~few KB) and `tests/fixtures/api/sample_day.zip` (~5–50 MB).

If the ZIP is over 50 MB, look at the smallest file's contents (USPTO's daily Sundays/holidays might have been reissued with larger size). Pick another date or accept the size — but flag if it's >100 MB.

### Step 3: Implement client.py

```python
"""USPTO ODP datasets client for the TRTDXFAP trademark bulk product.

Verified via spike (see scripts/probe_api.py and tests/fixtures/api/):
  Base: https://api.uspto.gov
  Auth: X-API-KEY header
  List: GET /api/v1/datasets/products/TRTDXFAP?fileDataFromDate=&fileDataToDate=
        → {"productFileBag": {"fileDataBag": [{"fileName", "fileDataFromDate",
            "fileDownloadURI", "fileSize"}, ...]}}
  Get:  GET /api/v1/datasets/products/files/TRTDXFAP/{fileName} → ZIP bytes

This module ONLY handles HTTP. XML parsing lives in extract.py (Task 6).
"""
import random
import time
from datetime import date
from typing import Iterator
import httpx


BASE_URL = "https://api.uspto.gov"
PRODUCT = "TRTDXFAP"


class USPTOClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL, timeout: float = 60.0):
        self._client = httpx.Client(
            base_url=base_url,
            headers={"X-API-KEY": api_key},
            timeout=timeout,
            follow_redirects=True,
        )

    def list_files(self, *, date_from: date, date_to: date) -> list[dict]:
        """Return list of file metadata dicts in the date range.

        Each dict contains at least: fileName, fileDataFromDate, fileSize.
        Empty list if no files.
        """
        data = self._request(
            "GET",
            f"/api/v1/datasets/products/{PRODUCT}",
            params={
                "fileDataFromDate": date_from.isoformat(),
                "fileDataToDate": date_to.isoformat(),
            },
        )
        return (
            data.get("productFileBag", {}).get("fileDataBag", [])
            or []
        )

    def download_file(self, file_name: str) -> bytes:
        """Return the raw ZIP bytes for one daily file."""
        resp = self._request_raw(
            "GET",
            f"/api/v1/datasets/products/files/{PRODUCT}/{file_name}",
        )
        return resp.content

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self._request_raw(method, path, **kwargs)
        return resp.json()

    def _request_raw(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Retry 429 and 5xx with exponential backoff + jitter, max 5 attempts."""
        last_resp = None
        for attempt in range(5):
            resp = self._client.request(method, path, **kwargs)
            last_resp = resp
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = (2 ** attempt) + random.random()
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        last_resp.raise_for_status()
        return last_resp

    def close(self) -> None:
        self._client.close()
```

### Step 4: Tests with respx

`tests/test_client.py`:
```python
import json
from pathlib import Path
from datetime import date
import respx
from httpx import Response
from uspto.client import USPTOClient


FIX = Path(__file__).parent / "fixtures" / "api"
LISTING = FIX / "files_listing_sample.json"
ZIP_FIX = FIX / "sample_day.zip"


@respx.mock
def test_list_files_returns_metadata_list():
    respx.get(url__regex=r".*/datasets/products/TRTDXFAP$|.*/datasets/products/TRTDXFAP\?.*").mock(
        return_value=Response(200, json=json.loads(LISTING.read_text()))
    )
    client = USPTOClient(api_key="x")
    files = client.list_files(date_from=date(2026, 4, 15), date_to=date(2026, 4, 22))
    assert isinstance(files, list)
    assert all("fileName" in f for f in files)


@respx.mock
def test_list_files_empty_listing():
    respx.get(url__regex=r".*/datasets/products/TRTDXFAP.*").mock(
        return_value=Response(200, json={"productFileBag": {"fileDataBag": []}})
    )
    client = USPTOClient(api_key="x")
    assert client.list_files(date_from=date(2026, 1, 1), date_to=date(2026, 1, 7)) == []


@respx.mock
def test_download_file_returns_bytes():
    body = ZIP_FIX.read_bytes()
    respx.get(url__regex=r".*/datasets/products/files/TRTDXFAP/.*").mock(
        return_value=Response(200, content=body)
    )
    client = USPTOClient(api_key="x")
    out = client.download_file("apa.zip")
    assert out == body
    assert out[:2] == b"PK"  # ZIP magic


@respx.mock
def test_429_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    route = respx.get(url__regex=r".*/datasets/products/TRTDXFAP.*")
    route.side_effect = [
        Response(429),
        Response(200, json=json.loads(LISTING.read_text())),
    ]
    client = USPTOClient(api_key="x")
    files = client.list_files(date_from=date(2026, 4, 15), date_to=date(2026, 4, 22))
    assert isinstance(files, list)
```

### Step 5: Run + commit

```bash
source .venv/bin/activate
pytest tests/test_client.py -v
```

Expected: 4 passed.

```bash
git add src/uspto/client.py tests/test_client.py \
        tests/fixtures/api/files_listing_sample.json \
        tests/fixtures/api/sample_day.zip \
        scripts/probe_api.py
git commit -m "feat: add USPTO ODP datasets client + bulk XML fixture"
```

**Note on the ZIP fixture (important for OSS hygiene):**
Don't commit the raw 5–50 MB daily ZIP — it bloats git history. Instead:

1. The probe downloads the real ZIP to `.local/sample_day.full.zip` (gitignored — see `.gitignore` patterns: `*.full.zip` or use `tests/fixtures/api/*.local.*`).
2. Open it, inspect the structure once.
3. Hand-curate a small `sample_day.zip` containing just 2–3 representative `<case-file>` elements (one in-scope healthcare+AI, one out-of-scope) wrapped in the same root element. Aim for under 50 KB.
4. Commit only the small curated ZIP.

The smaller fixture is enough to verify: client downloads → extractor parses → backfill ingests. Real-data scale testing happens via the live API on first `uspto backfill` run.

Add to `.gitignore` if not already there:
```
tests/fixtures/api/*.full.zip
.local/
```

---

## Task 6: XML extractor (case-file → DB row dict)

The downloaded ZIP contains one XML file per daily release. The XML follows the U.S. Trademark Applications DTD (v2.3 as of 2026). Each `<case-file>` element is one trademark application.

**Goals:**
- Stream-parse the XML (don't load all into memory — files can be 200 MB)
- Convert each `<case-file>` element to the same dict shape `upsert_application` already expects (so storage/filter/backfill code is unchanged)
- Extract Nice classes as `list[str]`

**Files:**
- Create: `src/uspto/extract.py`
- Create: `tests/test_extract.py`

### Step 1: Verify the XML structure

Before writing extractor code, the implementer should:
1. Unzip `tests/fixtures/api/sample_day.zip` once and identify the XML's element structure.
2. Note the exact element names — the DTD uses lowercase-hyphenated names (e.g., `<case-file>`, `<serial-number>`, `<mark-identification>`, `<filing-date>`).
3. Document the observed structure in a comment at the top of `extract.py`.

Common elements to target (verify against the actual file):
- `<serial-number>` — the 8-digit ID, our PK
- `<case-file-header>` containing:
  - `<filing-date>` (YYYYMMDD or YYYY-MM-DD)
  - `<registration-date>` (nullable)
  - `<status-code>`
  - `<mark-identification>` — the human-readable mark text
- `<case-file-statements>` containing one or more `<case-file-statement>` elements; the goods/services description has `type-code` starting `GS` (e.g. `GS0341`)
- `<classifications>` containing one or more `<classification>` elements with `<international-code>` (the Nice class)
- `<case-file-owners>` containing one or more `<case-file-owner>` with `<party-name>`, `<address-1>`, `<state>`, `<country>`

### Step 2: Write a failing test against the real fixture

`tests/test_extract.py`:
```python
import zipfile
from pathlib import Path
from uspto.extract import iter_case_files, extract_application, extract_nice_classes


FIX = Path(__file__).parent / "fixtures" / "api"
ZIP_FIX = FIX / "sample_day.zip"


def _open_xml():
    """Open the inner XML from the sample ZIP as a binary stream."""
    with zipfile.ZipFile(ZIP_FIX) as z:
        # The ZIP contains one .xml file
        names = [n for n in z.namelist() if n.endswith(".xml")]
        assert len(names) == 1, f"Expected 1 xml, got {names}"
        return z.read(names[0])


def test_iter_case_files_yields_elements():
    xml_bytes = _open_xml()
    elems = list(iter_case_files(xml_bytes))
    assert len(elems) > 0


def test_extract_application_returns_required_fields():
    xml_bytes = _open_xml()
    elem = next(iter_case_files(xml_bytes))
    row = extract_application(elem)
    required = {"serial_number", "mark_text", "filing_date", "description",
                "owner_name", "fetched_at", "raw_json"}
    assert required.issubset(row.keys())
    assert row["serial_number"]
    # date parsed properly
    if row["filing_date"]:
        assert hasattr(row["filing_date"], "year")  # is a date


def test_extract_nice_classes_returns_strings():
    xml_bytes = _open_xml()
    elem = next(iter_case_files(xml_bytes))
    classes = extract_nice_classes(elem)
    assert isinstance(classes, list)
    for c in classes:
        assert isinstance(c, str)
```

### Step 3: Run, verify failure

```bash
pytest tests/test_extract.py -v
```

Expected: ImportError on `uspto.extract`.

### Step 4: Implement extract.py

```python
"""Translate USPTO trademark XML <case-file> elements into DB row dicts.

XML element mapping (verified against tests/fixtures/api/sample_day.zip):
  <serial-number>                              → applications.serial_number
  <case-file-header>/<mark-identification>     → applications.mark_text
  <case-file-header>/<filing-date>             → applications.filing_date
  <case-file-header>/<registration-date>       → applications.registration_date
  <case-file-header>/<status-code>             → applications.status_code
  <case-file-statements>/<case-file-statement>
       where type-code starts "GS"             → applications.description
  <classifications>/<classification>/<international-code>  → nice_classes.class_code
  <case-file-owners>/<case-file-owner>[0]/<party-name>     → applications.owner_name

If the DTD changes, update this file and re-capture the fixture.
"""
import json
from datetime import date, datetime
from typing import Iterator
from xml.etree import ElementTree as ET


def iter_case_files(xml_bytes: bytes) -> Iterator[ET.Element]:
    """Stream-yield <case-file> elements from a USPTO trademark daily XML.

    Memory-bounded: clears each element after yielding so the parser doesn't
    accumulate the entire document in memory.
    """
    import io
    parser = ET.iterparse(io.BytesIO(xml_bytes), events=("end",))
    for event, elem in parser:
        if elem.tag == "case-file":
            yield elem
            elem.clear()


def extract_application(elem: ET.Element) -> dict:
    """Map one <case-file> element → applications row dict (no matched_*_terms)."""
    header = elem.find("case-file-header")
    return {
        "serial_number": _text(elem, "serial-number"),
        "mark_text": _text(header, "mark-identification") if header is not None else None,
        "filing_date": _parse_date(_text(header, "filing-date") if header is not None else None),
        "registration_date": _parse_date(_text(header, "registration-date") if header is not None else None),
        "status_code": _text(header, "status-code") if header is not None else None,
        "status_description": None,  # not in feed; could derive from status_code lookup later
        "owner_name": _first_owner_field(elem, "party-name"),
        "owner_state": _first_owner_field(elem, "owner-address-state-or-country"),
        "owner_country": _first_owner_field(elem, "owner-address-country"),
        "description": _goods_services_description(elem),
        "fetched_at": datetime.utcnow(),
        "raw_json": json.dumps(_xml_to_dict(elem)),  # lossy but searchable
    }


def extract_nice_classes(elem: ET.Element) -> list[str]:
    """Return list of Nice class codes as strings."""
    out: list[str] = []
    for cls in elem.iterfind(".//classification"):
        code = _text(cls, "international-code")
        if code:
            out.append(code.lstrip("0") or "0")
    return out


# --- helpers ---

def _text(parent: ET.Element | None, tag: str) -> str | None:
    if parent is None:
        return None
    found = parent.find(tag)
    return found.text if found is not None and found.text else None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    # USPTO uses YYYYMMDD with no separators in this feed
    if len(s) == 8 and s.isdigit():
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _first_owner_field(elem: ET.Element, tag: str) -> str | None:
    """Return the first owner's value for `tag`, searched anywhere in case-file-owners."""
    owners = elem.find("case-file-owners")
    if owners is None:
        return None
    first_owner = owners.find("case-file-owner")
    if first_owner is None:
        return None
    return _text(first_owner, tag)


def _goods_services_description(elem: ET.Element) -> str:
    """Concatenate all goods/services statements (type-code starting with 'GS')."""
    parts: list[str] = []
    statements = elem.find("case-file-statements")
    if statements is None:
        return ""
    for stmt in statements.iterfind("case-file-statement"):
        type_code = _text(stmt, "type-code") or ""
        text = _text(stmt, "text") or ""
        if type_code.startswith("GS") and text:
            parts.append(text)
    return " | ".join(parts)


def _xml_to_dict(elem: ET.Element) -> dict:
    """Lossy XML → dict for `raw_json` storage. Keys are tag names; nested children
    become nested dicts; repeated tags become lists. Attributes prefixed with @."""
    result: dict = {}
    for k, v in elem.attrib.items():
        result[f"@{k}"] = v
    for child in elem:
        child_value = _xml_to_dict(child) if len(child) or child.attrib else (child.text or "")
        if child.tag in result:
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(child_value)
        else:
            result[child.tag] = child_value
    if not result and elem.text:
        return elem.text
    if elem.text and elem.text.strip():
        result["#text"] = elem.text.strip()
    return result
```

**Important:** the DTD element names above are educated estimates from public USPTO documentation. The implementer **must verify** them against the real fixture. If `<filing-date>` is actually `<filed-date>`, change it. If the goods/services type-codes don't match `GS*`, find the right ones empirically. The test cases will catch surface-level errors; visual inspection of the XML catches subtler ones.

### Step 5: Run tests + iterate

```bash
source .venv/bin/activate
pytest tests/test_extract.py -v
```

Expected: 3 passed (after element name verification).

If tests fail because the real DTD uses different names: open the XML, fix the names in `extract.py`, re-run. Don't change the tests — the tests verify the contract (right keys present, types correct), not the specific element names.

### Step 6: Commit

```bash
git add src/uspto/extract.py tests/test_extract.py
git commit -m "feat: add XML case-file extractor with streaming parse"
```

---

## Task 7: Backfill orchestrator (TDD)

Iterates over the date range, lists files via the client, downloads each ZIP, stream-parses, classifies, and UPSERTs in-scope records.

**Files:**
- Create: `src/uspto/backfill.py`
- Create: `tests/test_backfill.py`

### Step 1: Write failing tests

`tests/test_backfill.py`:
```python
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
```

### Step 2: Run, verify failure

```bash
pytest tests/test_backfill.py -v
```

Expected: ImportError.

### Step 3: Implement backfill.py

```python
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
```

### Step 4: Run tests + commit

```bash
source .venv/bin/activate
pytest tests/test_backfill.py -v
```

Expected: 3 passed.

```bash
git add src/uspto/backfill.py tests/test_backfill.py
git commit -m "feat: add backfill orchestrator (per-month bulk-XML ingest)"
```

---

## Task 8: Monitor command (TDD)

Lists files since the last seen filing date, downloads + processes each via the same `process_zip` from Task 7. Returns a list of newly-inserted rows, formatted via one of three formatters.

**Files:**
- Create: `src/uspto/monitor.py`
- Create: `tests/test_monitor.py`

### Step 1: Write failing tests

`tests/test_monitor.py`:
```python
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
        <text>ML clinical decision support</text>
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
```

### Step 2: Run, verify failure

```bash
pytest tests/test_monitor.py -v
```

Expected: ImportError.

### Step 3: Implement monitor.py

```python
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
```

### Step 4: Run + commit

```bash
source .venv/bin/activate
pytest tests/test_monitor.py -v
```

Expected: 5 passed.

```bash
git add src/uspto/monitor.py tests/test_monitor.py
git commit -m "feat: add monitor command with bulk-XML delta and 3 output formats"
```

---

## Task 9: Analyze module (TDD)

**Files:**
- Create: `src/uspto/analyze.py`
- Create: `tests/test_analyze.py`
- Create: `tests/fixtures/seed.py` (helper to populate fixture DB)

**Step 1: Write failing tests**

`tests/fixtures/seed.py`:
```python
"""Populate a SQLite DB with a small, deterministic dataset for analysis tests."""
from datetime import date
from uspto.storage import connect, create_schema, upsert_application, upsert_nice_classes


def seed(db_path):
    conn = connect(db_path)
    create_schema(conn)
    rows = [
        ("97000001", "MEDAI",     date(2024, 1, 15), "Acme Health",  ["AI"],     ["diagnostic"], ["9", "42"]),
        ("97000002", "DIAGNOSE",  date(2024, 6, 10), "Acme Health",  ["machine learning"], ["clinical"], ["42"]),
        ("97000003", "CARELLM",   date(2025, 3, 1),  "Beta Bio",     ["LLM"],    ["patient"],    ["42"]),
        ("97000004", "VISIONMD",  date(2025, 9, 5),  "Beta Bio",     ["computer vision"], ["medical"], ["10"]),
        ("97000005", "GENPHARMA", date(2026, 2, 1),  "Gamma Pharma", ["generative AI"], ["pharmaceutical"], ["5"]),
    ]
    for sn, mark, fdate, owner, ai, hc, classes in rows:
        upsert_application(conn, {
            "serial_number": sn, "mark_text": mark, "filing_date": fdate,
            "registration_date": None, "status_code": "700",
            "status_description": "Registered", "owner_name": owner,
            "owner_state": "CA", "owner_country": "US",
            "description": f"{', '.join(ai)} for {', '.join(hc)} use",
            "matched_ai_terms": ai, "matched_hc_terms": hc,
            "fetched_at": "2026-04-26", "raw_json": "{}",
        })
        upsert_nice_classes(conn, sn, classes)
    conn.close()
    return db_path
```

`tests/test_analyze.py`:
```python
import pytest
from uspto.analyze import (
    filings_per_month, top_applicants, ai_term_trends,
    nice_class_distribution, status_distribution, recent_filings,
    summary_stats,
)
from uspto.storage import connect
from tests.fixtures.seed import seed


@pytest.fixture
def db(tmp_path):
    return seed(tmp_path / "test.db")


def test_filings_per_month_returns_dataframe(db):
    df = filings_per_month(connect(db))
    assert "month" in df.columns
    assert "count" in df.columns
    assert df["count"].sum() == 5


def test_top_applicants_orders_by_count_desc(db):
    df = top_applicants(connect(db), limit=10)
    assert df.iloc[0]["owner_name"] == "Acme Health"
    assert df.iloc[0]["count"] == 2


def test_ai_term_trends_one_row_per_term_per_month(db):
    df = ai_term_trends(connect(db))
    assert {"month", "term", "count"}.issubset(df.columns)
    assert df["count"].sum() == 5  # each row has 1 AI term


def test_nice_class_distribution(db):
    df = nice_class_distribution(connect(db))
    assert df["count"].sum() == 6  # one mark has 2 classes


def test_status_distribution(db):
    df = status_distribution(connect(db))
    assert df.iloc[0]["count"] == 5


def test_recent_filings_limit(db):
    rows = recent_filings(connect(db), limit=3)
    assert len(rows) == 3


def test_summary_stats_keys(db):
    stats = summary_stats(connect(db))
    for k in ["total", "this_year", "last_year", "yoy_pct", "date_min", "date_max"]:
        assert k in stats
```

**Step 2: Run, verify failure**

```bash
pytest tests/test_analyze.py -v
```

Expected: ImportError.

**Step 3: Implement analyze.py**

```python
import json
import sqlite3
import pandas as pd
from datetime import date


def _read(conn: sqlite3.Connection, sql: str, params=()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def filings_per_month(conn: sqlite3.Connection) -> pd.DataFrame:
    df = _read(conn, "SELECT filing_date FROM applications WHERE filing_date IS NOT NULL")
    df["month"] = pd.to_datetime(df["filing_date"]).dt.to_period("M").dt.to_timestamp()
    return df.groupby("month").size().reset_index(name="count").sort_values("month")


def top_applicants(conn: sqlite3.Connection, limit: int = 25) -> pd.DataFrame:
    return _read(
        conn,
        "SELECT owner_name, COUNT(*) AS count FROM applications "
        "WHERE owner_name IS NOT NULL "
        "GROUP BY owner_name ORDER BY count DESC LIMIT ?",
        (limit,),
    )


def ai_term_trends(conn: sqlite3.Connection) -> pd.DataFrame:
    df = _read(conn, "SELECT filing_date, matched_ai_terms FROM applications")
    df["month"] = pd.to_datetime(df["filing_date"]).dt.to_period("M").dt.to_timestamp()
    df["terms"] = df["matched_ai_terms"].apply(lambda s: json.loads(s) if s else [])
    df = df.explode("terms").dropna(subset=["terms"])
    df = df.rename(columns={"terms": "term"})
    return df.groupby(["month", "term"]).size().reset_index(name="count")


def nice_class_distribution(conn: sqlite3.Connection) -> pd.DataFrame:
    return _read(
        conn,
        "SELECT class_code, COUNT(*) AS count FROM nice_classes "
        "GROUP BY class_code ORDER BY count DESC",
    )


def status_distribution(conn: sqlite3.Connection) -> pd.DataFrame:
    return _read(
        conn,
        "SELECT COALESCE(status_description, 'Unknown') AS status, "
        "COUNT(*) AS count FROM applications "
        "GROUP BY status_description ORDER BY count DESC",
    )


def recent_filings(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    df = _read(
        conn,
        "SELECT serial_number, mark_text, filing_date, owner_name, "
        "status_description, matched_ai_terms FROM applications "
        "ORDER BY filing_date DESC LIMIT ?",
        (limit,),
    )
    return df.to_dict("records")


def summary_stats(conn: sqlite3.Connection) -> dict:
    df = _read(conn, "SELECT filing_date FROM applications WHERE filing_date IS NOT NULL")
    if df.empty:
        return {"total": 0, "this_year": 0, "last_year": 0, "yoy_pct": 0.0,
                "date_min": None, "date_max": None}
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    today = pd.Timestamp.today()
    this_year = (df["filing_date"].dt.year == today.year).sum()
    last_year = (df["filing_date"].dt.year == today.year - 1).sum()
    yoy = ((this_year - last_year) / last_year * 100) if last_year else 0.0
    return {
        "total": len(df),
        "this_year": int(this_year),
        "last_year": int(last_year),
        "yoy_pct": float(yoy),
        "date_min": df["filing_date"].min().date(),
        "date_max": df["filing_date"].max().date(),
    }
```

**Step 4: Run tests**

```bash
pytest tests/test_analyze.py -v
```

Expected: 7 passed.

**Step 5: Commit**

```bash
git add src/uspto/analyze.py tests/test_analyze.py tests/fixtures/seed.py
git commit -m "feat: add analyze module with 7 aggregations"
```

---

## Task 10: Report rendering (Plotly + Jinja2)

**Files:**
- Create: `src/uspto/report.py`
- Create: `src/uspto/templates/trends.html.j2`
- Create: `tests/test_report.py`

**Step 1: Write failing test**

`tests/test_report.py`:
```python
from uspto.report import render_report
from uspto.storage import connect
from tests.fixtures.seed import seed


def test_render_report_writes_non_empty_html(tmp_path):
    db = seed(tmp_path / "test.db")
    out = tmp_path / "trends.html"
    render_report(connect(db), out)
    assert out.exists()
    html = out.read_text()
    assert len(html) > 1000
    # Plotly's bundle adds a <script> with 'plotly' in the source
    assert "plotly" in html.lower()
    # Contains at least one applicant name from the seed
    assert "Acme Health" in html


def test_render_report_handles_empty_db(tmp_path):
    from uspto.storage import connect, create_schema
    db = tmp_path / "empty.db"
    conn = connect(db)
    create_schema(conn)
    out = tmp_path / "trends.html"
    render_report(connect(db), out)
    assert out.exists()
```

**Step 2: Run, verify failure**

```bash
pytest tests/test_report.py -v
```

Expected: ImportError.

**Step 3: Create the Jinja2 template**

`src/uspto/templates/trends.html.j2`:
```html
<!doctype html>
<html><head>
<meta charset="utf-8">
<title>USPTO Healthcare+AI Trademark Trends</title>
<style>
body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 1100px; }
h1, h2 { border-bottom: 1px solid #ddd; padding-bottom: 0.3rem; }
.summary { display: flex; gap: 2rem; margin: 1rem 0; }
.card { background: #f5f5f5; padding: 1rem 1.5rem; border-radius: 8px; }
.card .num { font-size: 2rem; font-weight: bold; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid #eee; }
.delta-up { color: #2a7; } .delta-dn { color: #c33; }
</style>
</head><body>
<h1>USPTO Healthcare + AI Trademark Trends</h1>
<p><em>Generated {{ generated_at }} · Date range: {{ stats.date_min }} → {{ stats.date_max }}</em></p>

<div class="summary">
  <div class="card"><div>Total marks</div><div class="num">{{ stats.total }}</div></div>
  <div class="card"><div>This year</div><div class="num">{{ stats.this_year }}</div></div>
  <div class="card"><div>YoY change</div>
    <div class="num {% if stats.yoy_pct >= 0 %}delta-up{% else %}delta-dn{% endif %}">
      {{ "%+.1f"|format(stats.yoy_pct) }}%
    </div></div>
</div>

<h2>Filings per month</h2>
{{ fig_filings | safe }}

<h2>AI keyword trends</h2>
{{ fig_ai_terms | safe }}

<h2>Top 25 applicants</h2>
{{ fig_top | safe }}

<h2>Nice class distribution</h2>
{{ fig_classes | safe }}

<h2>Status breakdown</h2>
{{ fig_status | safe }}

<h2>Recent filings</h2>
<table>
  <tr><th>Serial</th><th>Filed</th><th>Owner</th><th>Mark</th><th>Status</th></tr>
  {% for r in recent %}
  <tr>
    <td><a href="https://tsdr.uspto.gov/#caseNumber={{ r.serial_number }}&caseType=SERIAL_NO&searchType=statusSearch">{{ r.serial_number }}</a></td>
    <td>{{ r.filing_date }}</td>
    <td>{{ r.owner_name or "" }}</td>
    <td>{{ r.mark_text or "" }}</td>
    <td>{{ r.status_description or "" }}</td>
  </tr>
  {% endfor %}
</table>
</body></html>
```

**Step 4: Implement report.py**

```python
from datetime import datetime
from pathlib import Path
import sqlite3
import plotly.express as px
from jinja2 import Environment, PackageLoader, select_autoescape
from . import analyze


def _empty_fig(msg: str) -> str:
    return f"<p><em>{msg}</em></p>"


def render_report(conn: sqlite3.Connection, output: Path) -> None:
    stats = analyze.summary_stats(conn)
    if stats["total"] == 0:
        output.write_text("<html><body><p>No data yet.</p></body></html>")
        return

    fpm = analyze.filings_per_month(conn)
    fig_filings = (
        px.line(fpm, x="month", y="count", title=None).to_html(
            full_html=False, include_plotlyjs="inline")
        if not fpm.empty else _empty_fig("No filings data")
    )

    ai = analyze.ai_term_trends(conn)
    fig_ai_terms = (
        px.area(ai, x="month", y="count", color="term", title=None).to_html(
            full_html=False, include_plotlyjs=False)
        if not ai.empty else _empty_fig("No AI term data")
    )

    top = analyze.top_applicants(conn, limit=25)
    fig_top = (
        px.bar(top, x="count", y="owner_name", orientation="h", title=None).to_html(
            full_html=False, include_plotlyjs=False)
        if not top.empty else _empty_fig("No applicants")
    )

    cls = analyze.nice_class_distribution(conn)
    fig_classes = (
        px.pie(cls, values="count", names="class_code", hole=0.5, title=None).to_html(
            full_html=False, include_plotlyjs=False)
        if not cls.empty else _empty_fig("No class data")
    )

    sts = analyze.status_distribution(conn)
    fig_status = (
        px.pie(sts, values="count", names="status", hole=0.5, title=None).to_html(
            full_html=False, include_plotlyjs=False)
        if not sts.empty else _empty_fig("No status data")
    )

    recent = analyze.recent_filings(conn, limit=50)
    env = Environment(
        loader=PackageLoader("uspto", "templates"),
        autoescape=select_autoescape(),
    )
    tpl = env.get_template("trends.html.j2")
    html = tpl.render(
        stats=stats,
        fig_filings=fig_filings, fig_ai_terms=fig_ai_terms,
        fig_top=fig_top, fig_classes=fig_classes, fig_status=fig_status,
        recent=recent,
        generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )
    output.write_text(html)
```

**Step 5: Run tests**

```bash
pytest tests/test_report.py -v
```

Expected: 2 passed.

**Step 6: Commit**

```bash
git add src/uspto/report.py src/uspto/templates/trends.html.j2 tests/test_report.py
git commit -m "feat: render Plotly+Jinja2 trend report"
```

---

### Note for Task 11 (CLI)

The `_load()` helper in `cli.py` should call `load_config()` (no path argument) — `load_config` reads from environment variables and auto-loads `.env`. Keep error handling identical to the plan: catch `ConfigError`, print red, exit 1.

---

## Task 11: CLI wiring (Typer)

**Files:**
- Create: `src/uspto/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write failing tests**

`tests/test_cli.py`:
```python
from typer.testing import CliRunner
from uspto.cli import app


runner = CliRunner()


def test_help_works():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "backfill" in result.stdout
    assert "monitor" in result.stdout
    assert "report" in result.stdout


def test_monitor_help_lists_format_flag():
    result = runner.invoke(app, ["monitor", "--help"])
    assert result.exit_code == 0
    assert "--format" in result.stdout
```

**Step 2: Run, verify failure**

```bash
pytest tests/test_cli.py -v
```

Expected: ImportError or empty CLI.

**Step 3: Implement cli.py**

```python
import sys
import webbrowser
from datetime import date
from pathlib import Path
import typer
from .config import load_config, ConfigError
from .client import USPTOClient
from .storage import connect, create_schema
from .backfill import run_backfill
from .monitor import run_monitor, format_table, format_markdown, format_json
from .report import render_report

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _load() -> tuple:
    try:
        cfg = load_config()
    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    conn = connect(cfg.db_path)
    create_schema(conn)
    return cfg, conn


@app.command()
def backfill(months: int = 60):
    """Fetch the last N months of matching marks (default 60)."""
    cfg, conn = _load()
    client = USPTOClient(api_key=cfg.api_key)
    typer.echo(f"Backfilling {months} months...")
    n = run_backfill(client, conn, months=months)
    typer.echo(f"Done. {n} in-scope rows inserted/updated.")


@app.command()
def monitor(
    fmt: str = typer.Option("table", "--format", "-f",
                            help="table | md | json"),
    since: str | None = typer.Option(None, help="ISO date override"),
):
    """Print new in-scope filings since the last run."""
    cfg, conn = _load()
    client = USPTOClient(api_key=cfg.api_key)
    since_date = date.fromisoformat(since) if since else None
    rows = run_monitor(client, conn, since=since_date)
    if fmt == "table":
        typer.echo(format_table(rows))
    elif fmt == "md":
        typer.echo(format_markdown(rows))
    elif fmt == "json":
        typer.echo(format_json(rows))
    else:
        typer.secho(f"Unknown format: {fmt}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)


@app.command()
def report(
    output: Path = typer.Option(Path("trends.html"), "--output", "-o"),
    open_browser: bool = typer.Option(False, "--open", help="Auto-open in browser"),
):
    """Render the HTML trend report."""
    _, conn = _load()
    render_report(conn, output)
    typer.echo(f"Wrote {output}")
    if open_browser:
        webbrowser.open(f"file://{output.resolve()}")


if __name__ == "__main__":
    app()
```

**Step 4: Run tests + smoke test the binary**

```bash
pytest tests/test_cli.py -v
uspto --help
```

Expected: 2 passed; `uspto --help` shows the three commands.

**Step 5: Commit**

```bash
git add src/uspto/cli.py tests/test_cli.py
git commit -m "feat: wire Typer CLI for backfill/monitor/report"
```

---

## Task 12: README & one full end-to-end run

**Files:**
- Create: `README.md`

**Step 1: Write README.md**

```markdown
# uspto

CLI for monitoring USPTO trademark filings in the healthcare + AI intersection.

## Setup

1. Get a free USPTO Open Data Portal API key at https://data.uspto.gov/
2. Configure environment:
   ```
   cp .env.example .env
   # edit .env, set USPTO_API_KEY
   ```
3. Install:
   ```
   uv tool install .
   ```
   For cron / non-shell contexts, export `USPTO_API_KEY` directly instead of relying on `.env`.

## Usage

```
uspto backfill              # fetch the last 60 months (one-time)
uspto monitor               # print new filings since last run
uspto monitor -f md         # markdown output (good for piping to a file)
uspto monitor -f json       # JSON for scripting
uspto report --open         # render trends.html and open in browser
```

## Weekly cron

```
0 9 * * 1 /home/you/.local/bin/uspto monitor -f md > ~/uspto-weekly.md
```

## What's in scope

A trademark application is included if it satisfies all three:
- **Nice class** in {5, 9, 10, 42, 44}
- **AI keyword** in goods/services description (e.g., "machine learning", "LLM")
- **Healthcare keyword** in goods/services description (e.g., "diagnostic", "clinical")

The full term lists live in `src/uspto/filter.py`.

## Development

```
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```
```

**Step 2: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

**Step 3: Manual end-to-end smoke (requires real API key)**

```bash
uspto backfill --months 1     # fetch one month only, to keep it fast
uspto monitor -f table
uspto report --open
```

Expected: backfill completes without error; report opens in browser showing real data.

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and usage"
```

**Step 5: Tag v0.1.0**

```bash
git tag v0.1.0
```

---

## Acceptance criteria (definition of done)

- [ ] `pytest` is green
- [ ] `uspto --help` lists three commands
- [ ] `uspto backfill --months 1` against the live API populates SQLite without error
- [ ] `uspto monitor -f md` produces valid markdown
- [ ] `uspto report` writes a `trends.html` ≥ 1 MB with all 7 sections rendered
- [ ] README's quickstart works for a new user from a clean checkout
