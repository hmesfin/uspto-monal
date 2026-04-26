# USPTO Trademark CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI that pulls USPTO trademark filings filtered to healthcare+AI, monitors weekly, and renders 5-year trend reports.

**Architecture:** Single Python package with Typer CLI. Three commands (`backfill`, `monitor`, `report`). USPTO Open Data Portal trademark search API → SQLite → pandas/Plotly. Filter is hardcoded in v1: Nice classes {5,9,10,42,44} ∩ AI keywords ∩ healthcare keywords in goods/services description.

**Tech Stack:** Python 3.11+, uv, Typer, httpx, sqlite3 (stdlib), pandas, Plotly, Jinja2, python-dotenv, pytest, respx (HTTP mocking).

**Configuration:** 12-factor — config via environment variables, with `.env` loaded for local dev (`.env` is gitignored; `.env.example` is committed). This is a public OSS project on GitHub; never commit secrets.

**Reference:** See `docs/plans/2026-04-26-uspto-cli-design.md` for the approved design.

---

## Important note on the USPTO ODP API

I do not have a verified-current spec of the USPTO Open Data Portal trademark search API in this plan. Task 5 is a deliberate **spike** task: make one real API call, save the JSON response as a fixture, then build the typed client from observed shape. Do not skip this — guessing field names from training data is the #1 source of waste in this kind of work.

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

## Task 5: USPTO API client — SPIKE FIRST

This task is structured differently because the exact ODP API response shape needs to be verified, not guessed.

**Files:**
- Create: `tests/fixtures/api/search_sample.json` (captured live)
- Create: `src/uspto/client.py`
- Create: `tests/test_client.py`
- Create: `scripts/probe_api.py` (one-shot tool, will be committed for reproducibility)

**Step 1: Write the probe script**

`scripts/probe_api.py`:
```python
"""One-shot tool to capture an example USPTO ODP trademark search response.

Usage:
  USPTO_API_KEY=... python scripts/probe_api.py > tests/fixtures/api/search_sample.json
"""
import json
import os
import sys
import httpx

API_KEY = os.environ["USPTO_API_KEY"]
BASE = "https://api.uspto.gov"  # verify in ODP docs

# This URL/payload is a STARTING GUESS. Adjust based on the actual ODP
# trademark search endpoint. Consult https://data.uspto.gov/ for the
# current schema.
url = f"{BASE}/api/v1/trademarks/search"
params = {
    "q": "diagnostic AI",
    "limit": 5,
}
headers = {"X-API-KEY": API_KEY}

resp = httpx.get(url, params=params, headers=headers, timeout=30)
resp.raise_for_status()
print(json.dumps(resp.json(), indent=2))
sys.stderr.write(f"Status: {resp.status_code}\nFields top-level: {list(resp.json().keys())}\n")
```

**Step 2: Run the probe — capture real response shape**

```bash
mkdir -p tests/fixtures/api
# Loads .env automatically? No — bash doesn't. Either source it first or pass inline.
set -a && source .env && set +a
python scripts/probe_api.py > tests/fixtures/api/search_sample.json
```

If the URL/params guess is wrong, the script will 404 or 4xx. **STOP** and consult the ODP API documentation at https://data.uspto.gov/ before proceeding. Adjust the probe until you get a 200 with real data, then re-save the fixture.

Expected outcome: a `search_sample.json` containing real USPTO trademark records. Note the actual field names — they may differ from the design doc's assumed names (e.g., `serialNumber` vs `serial_number`, `markText` vs `mark_text`).

**Step 3: Document the observed schema**

Open the fixture, identify the fields needed for `applications` and `nice_classes` tables, and write a short table-mapping doc as a code comment at the top of `src/uspto/client.py`:

```python
"""USPTO Open Data Portal trademark search client.

API → DB field mapping (verified against tests/fixtures/api/search_sample.json):
  <api_field>            → <db_column>
  ...
"""
```

**Step 4: Implement client.py with retry**

```python
import time
import random
import httpx
from typing import Iterator
from datetime import date

BASE_URL = "https://api.uspto.gov"  # confirm against probe


class USPTOClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL, timeout: float = 30.0):
        self._client = httpx.Client(
            base_url=base_url,
            headers={"X-API-KEY": api_key},
            timeout=timeout,
        )

    def search(
        self,
        *,
        date_from: date,
        date_to: date,
        offset: int = 0,
        limit: int = 100,
    ) -> dict:
        """Return one page of search results."""
        # Adjust path/params based on probe results
        return self._request(
            "GET",
            "/api/v1/trademarks/search",
            params={
                "filingDateFrom": date_from.isoformat(),
                "filingDateTo": date_to.isoformat(),
                "offset": offset,
                "limit": limit,
            },
        )

    def search_paginated(
        self, *, date_from: date, date_to: date, page_size: int = 100
    ) -> Iterator[dict]:
        """Yield one record at a time across all pages for the date window."""
        offset = 0
        while True:
            page = self.search(
                date_from=date_from, date_to=date_to,
                offset=offset, limit=page_size,
            )
            results = page.get("results", [])  # adjust key
            if not results:
                return
            for r in results:
                yield r
            if len(results) < page_size:
                return
            offset += page_size

    def _request(self, method: str, path: str, **kwargs) -> dict:
        for attempt in range(5):
            resp = self._client.request(method, path, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = (2 ** attempt) + random.random()
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    def close(self):
        self._client.close()
```

**Step 5: Write tests against the fixture**

`tests/test_client.py`:
```python
import json
from pathlib import Path
import respx
from httpx import Response
from datetime import date
from uspto.client import USPTOClient


FIXTURE = Path(__file__).parent / "fixtures" / "api" / "search_sample.json"


@respx.mock
def test_search_returns_results():
    payload = json.loads(FIXTURE.read_text())
    respx.get(url__regex=r".*/trademarks/search").mock(
        return_value=Response(200, json=payload)
    )
    client = USPTOClient(api_key="x")
    res = client.search(date_from=date(2025,1,1), date_to=date(2025,1,31))
    # confirm SOME field present — adjust based on actual fixture shape
    assert isinstance(res, dict)


@respx.mock
def test_429_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    payload = json.loads(FIXTURE.read_text())
    route = respx.get(url__regex=r".*/trademarks/search")
    route.side_effect = [
        Response(429),
        Response(200, json=payload),
    ]
    client = USPTOClient(api_key="x")
    res = client.search(date_from=date(2025,1,1), date_to=date(2025,1,31))
    assert isinstance(res, dict)


@respx.mock
def test_pagination_terminates_on_short_page():
    full = json.loads(FIXTURE.read_text())
    # build a 'short page' variant — only valid if 'results' key exists in fixture
    # ADAPT this test to the real response shape after spike
    short = {**full, "results": full.get("results", [])[:1]}
    respx.get(url__regex=r".*/trademarks/search").mock(
        return_value=Response(200, json=short)
    )
    client = USPTOClient(api_key="x")
    rows = list(client.search_paginated(
        date_from=date(2025,1,1), date_to=date(2025,1,31), page_size=100,
    ))
    assert len(rows) <= 1
```

**Step 6: Run tests**

```bash
pytest tests/test_client.py -v
```

Expected: 3 passed (after adjusting field names to match real fixture).

**Step 7: Commit**

```bash
git add src/uspto/client.py tests/test_client.py tests/fixtures/api/search_sample.json scripts/probe_api.py
git commit -m "feat: add USPTO ODP client with retry; capture API fixture"
```

---

## Task 6: Record extractor (translate API row → DB row)

**Files:**
- Create: `src/uspto/extract.py`
- Create: `tests/test_extract.py`

**Step 1: Write failing tests using the real fixture**

`tests/test_extract.py`:
```python
import json
from pathlib import Path
from uspto.extract import extract_application


FIXTURE = Path(__file__).parent / "fixtures" / "api" / "search_sample.json"


def _first_record():
    data = json.loads(FIXTURE.read_text())
    # ADJUST after probe — depends on fixture shape
    return data["results"][0]


def test_extract_application_returns_required_fields():
    raw = _first_record()
    row = extract_application(raw)
    required = {
        "serial_number", "mark_text", "filing_date", "owner_name",
        "description", "raw_json",
    }
    assert required.issubset(row.keys())
    assert row["serial_number"]  # not empty
```

**Step 2: Run, verify failure**

```bash
pytest tests/test_extract.py -v
```

Expected: ImportError.

**Step 3: Implement extract.py based on the fixture's actual field names**

```python
"""Translate USPTO API response rows into our DB row dicts.

Field mapping derived from tests/fixtures/api/search_sample.json.
If the API changes, update this file and the test fixture together.
"""
import json
from datetime import date, datetime


def extract_application(raw: dict) -> dict:
    """Map one API record → applications row dict.

    Note: do NOT set matched_ai_terms / matched_hc_terms here —
    the classifier in filter.py handles that, and backfill wires them in.
    """
    # ADJUST these paths based on the actual fixture
    return {
        "serial_number": raw.get("serialNumber") or raw.get("serial_number"),
        "mark_text": raw.get("markText") or raw.get("mark_text"),
        "filing_date": _parse_date(raw.get("filingDate")),
        "registration_date": _parse_date(raw.get("registrationDate")),
        "status_code": raw.get("statusCode"),
        "status_description": raw.get("statusDescription"),
        "owner_name": _first_owner(raw),
        "owner_state": _first_owner_field(raw, "state"),
        "owner_country": _first_owner_field(raw, "country"),
        "description": _first_desc(raw),
        "fetched_at": datetime.utcnow(),
        "raw_json": json.dumps(raw),
    }


def extract_nice_classes(raw: dict) -> list[str]:
    """Return list of class codes as strings."""
    classes = raw.get("niceClasses") or raw.get("internationalClassCodes") or []
    return [str(c) for c in classes]


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s[:10])


def _first_owner(raw: dict) -> str | None:
    owners = raw.get("owners") or []
    if not owners:
        return None
    return owners[0].get("name") or owners[0].get("ownerName")


def _first_owner_field(raw: dict, key: str) -> str | None:
    owners = raw.get("owners") or []
    if not owners:
        return None
    return owners[0].get(key)


def _first_desc(raw: dict) -> str:
    """Concatenate goods/services descriptions across all classes."""
    descs = raw.get("goodsAndServices") or raw.get("descriptionsOfGoodsAndServices") or []
    if isinstance(descs, str):
        return descs
    return " | ".join(d.get("description", "") for d in descs)
```

**Step 4: Run tests**

```bash
pytest tests/test_extract.py -v
```

Expected: 1 passed (after extractor is adapted to the real fixture shape).

**Step 5: Commit**

```bash
git add src/uspto/extract.py tests/test_extract.py
git commit -m "feat: add API → DB row extractor"
```

---

## Task 7: Backfill orchestrator (TDD)

**Files:**
- Create: `src/uspto/backfill.py`
- Create: `tests/test_backfill.py`

**Step 1: Write failing test**

`tests/test_backfill.py`:
```python
from datetime import date
from unittest.mock import MagicMock
from uspto.backfill import run_backfill, month_windows
from uspto.storage import connect, create_schema


def test_month_windows_yields_n_months():
    windows = list(month_windows(date(2026, 4, 26), months=3))
    assert len(windows) == 3
    # most recent first
    assert windows[0][0] <= date(2026, 4, 26) <= windows[0][1]


def test_run_backfill_inserts_in_scope_only(tmp_path):
    conn = connect(tmp_path / "x.db")
    create_schema(conn)
    fake_client = MagicMock()
    # one in-scope (AI + healthcare + class 42), one out-of-scope (no AI terms)
    fake_client.search_paginated.return_value = iter([
        {
            "serialNumber": "97000001",
            "markText": "MEDAI",
            "filingDate": "2025-03-15",
            "owners": [{"name": "Acme"}],
            "goodsAndServices": [{"description": "AI diagnostic software"}],
            "niceClasses": ["42"],
        },
        {
            "serialNumber": "97000002",
            "markText": "BOOTBARN",
            "filingDate": "2025-03-15",
            "owners": [{"name": "Boots Inc"}],
            "goodsAndServices": [{"description": "Cowboy boots"}],
            "niceClasses": ["25"],
        },
    ])
    run_backfill(fake_client, conn, months=1, today=date(2025, 3, 31))

    cursor = conn.execute("SELECT serial_number FROM applications")
    rows = [r[0] for r in cursor.fetchall()]
    assert rows == ["97000001"]
```

**Step 2: Run, verify failure**

```bash
pytest tests/test_backfill.py -v
```

Expected: ImportError.

**Step 3: Implement backfill.py**

```python
import json
from datetime import date, timedelta
from typing import Iterator
import sqlite3
from .client import USPTOClient
from .extract import extract_application, extract_nice_classes
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


def run_backfill(
    client: USPTOClient,
    conn: sqlite3.Connection,
    months: int = 60,
    today: date | None = None,
) -> int:
    """Returns count of in-scope rows inserted/updated."""
    today = today or date.today()
    inserted = 0
    for start, end in month_windows(today, months):
        for raw in client.search_paginated(date_from=start, date_to=end):
            row = extract_application(raw)
            if not row["serial_number"]:
                continue
            classes = extract_nice_classes(raw)
            cls = classify(row["description"] or "", classes)
            if not cls.in_scope:
                continue
            row["matched_ai_terms"] = cls.ai_terms
            row["matched_hc_terms"] = cls.hc_terms
            upsert_application(conn, row)
            upsert_nice_classes(conn, row["serial_number"], classes)
            inserted += 1
        # Commit at end of each month — keeps batches small enough to recover
        # from interruption without redoing too much work.
        conn.commit()
    return inserted
```

**Step 4: Run tests**

```bash
pytest tests/test_backfill.py -v
```

Expected: 2 passed.

**Step 5: Commit**

```bash
git add src/uspto/backfill.py tests/test_backfill.py
git commit -m "feat: add backfill orchestrator with month-by-month iteration"
```

---

## Task 8: Monitor command (TDD)

**Files:**
- Create: `src/uspto/monitor.py`
- Create: `tests/test_monitor.py`

**Step 1: Write failing tests**

`tests/test_monitor.py`:
```python
import json
from datetime import date
from unittest.mock import MagicMock
from uspto.monitor import run_monitor, format_table, format_markdown, format_json
from uspto.storage import connect, create_schema, upsert_application


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
    return conn


def test_run_monitor_returns_only_new_in_scope_rows(tmp_path):
    conn = _existing_row(tmp_path)
    client = MagicMock()
    client.search_paginated.return_value = iter([
        {  # already exists
            "serialNumber": "97000001", "markText": "EXISTING",
            "filingDate": "2025-01-01", "owners": [{"name": "X"}],
            "goodsAndServices": [{"description": "AI diagnostic"}],
            "niceClasses": ["42"],
        },
        {  # new + in-scope
            "serialNumber": "97000999", "markText": "NEWAI",
            "filingDate": "2026-04-20", "owners": [{"name": "Y"}],
            "goodsAndServices": [{"description": "ML clinical decision support"}],
            "niceClasses": ["42"],
        },
    ])
    new_rows = run_monitor(client, conn, today=date(2026, 4, 26))
    assert [r["serial_number"] for r in new_rows] == ["97000999"]


def test_format_json_is_valid():
    rows = [{"serial_number": "1", "mark_text": "X", "filing_date": "2026-04-01"}]
    out = format_json(rows)
    assert json.loads(out) == rows


def test_format_table_includes_serial(capsys):
    rows = [{"serial_number": "97000999", "mark_text": "NEWAI",
             "filing_date": "2026-04-20", "owner_name": "Y",
             "matched_ai_terms": ["ML"]}]
    out = format_table(rows)
    assert "97000999" in out


def test_format_markdown_has_links():
    rows = [{"serial_number": "97000999", "mark_text": "NEWAI",
             "filing_date": "2026-04-20", "owner_name": "Y",
             "matched_ai_terms": ["ML"]}]
    out = format_markdown(rows)
    assert "97000999" in out
    assert "tsdr.uspto.gov" in out  # link to TSDR record
```

**Step 2: Run, verify failure**

```bash
pytest tests/test_monitor.py -v
```

Expected: ImportError.

**Step 3: Implement monitor.py**

```python
import json
from datetime import date, datetime, timedelta
import sqlite3
from .client import USPTOClient
from .extract import extract_application, extract_nice_classes
from .filter import classify
from .storage import (
    upsert_application, upsert_nice_classes,
    get_max_filing_date, get_existing_serials,
)


TSDR_URL = "https://tsdr.uspto.gov/#caseNumber={sn}&caseType=SERIAL_NO&searchType=statusSearch"


def run_monitor(
    client: USPTOClient,
    conn: sqlite3.Connection,
    today: date | None = None,
    since: date | None = None,
) -> list[dict]:
    today = today or date.today()
    since = since or get_max_filing_date(conn) or (today - timedelta(days=7))
    new_rows = []
    candidates = []
    for raw in client.search_paginated(date_from=since, date_to=today):
        row = extract_application(raw)
        if not row["serial_number"]:
            continue
        classes = extract_nice_classes(raw)
        cls = classify(row["description"] or "", classes)
        if not cls.in_scope:
            continue
        row["matched_ai_terms"] = cls.ai_terms
        row["matched_hc_terms"] = cls.hc_terms
        candidates.append((row, classes))

    serials = [r["serial_number"] for r, _ in candidates]
    existing = get_existing_serials(conn, serials)
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

**Step 4: Run tests**

```bash
pytest tests/test_monitor.py -v
```

Expected: 4 passed.

**Step 5: Commit**

```bash
git add src/uspto/monitor.py tests/test_monitor.py
git commit -m "feat: add monitor command with delta + 3 output formats"
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
