# USPTO Trademark CLI — Design

**Date:** 2026-04-26
**Status:** Approved, ready for implementation plan

## Purpose

A Python CLI tool that pulls USPTO trademark filings, filters to the healthcare-tech + AI intersection, and surfaces two views:

1. **Monitoring** — what's new in the last week (digest output)
2. **Trends** — where the wind is blowing (5-year HTML report with charts)

## Scope

- **Domain:** trademarks only (patents are a future extension)
- **Filter:** healthcare + AI intersection, hardcoded in v1
- **Backfill:** 5 years of history
- **Cadence:** weekly monitoring (user wires their own cron)

## Approach

API-first using the USPTO Open Data Portal (ODP) trademark search API. Local SQLite for storage. Plotly + Jinja2 for the trend report.

Bulk XML downloads were considered and rejected — the filter is narrow enough that the search API can handle backfill in reasonable time, and bulk parsing adds complexity that doesn't pay off until we need higher fidelity than the API provides.

## CLI Surface

Three commands:

```
uspto backfill              # one-shot: fetch last 5yr of matching marks → SQLite
uspto monitor               # fetch new filings since last run, print digest
                            #   --format table|md|json  (default: table)
                            #   --since 2026-04-01      (override last-run date)
uspto report                # read SQLite → render trends.html in cwd
                            #   --open                  (auto-open in browser)
```

Config at `~/.config/uspto/config.toml`:

```toml
api_key = "..."             # USPTO ODP API key
db_path = "~/.local/share/uspto/trademarks.db"
```

## Filter Definition (v1, hardcoded)

A trademark application is **in scope** if and only if all three conditions hold:

1. At least one Nice class in `{5, 9, 10, 42, 44}`
   - 5 = pharmaceuticals
   - 9 = software / electronics
   - 10 = medical apparatus
   - 42 = SaaS / scientific & tech services
   - 44 = medical services
2. Goods/services description contains at least one **AI term**:
   `artificial intelligence | machine learning | neural network | deep learning | LLM | large language model | computer vision | generative AI`
3. Goods/services description contains at least one **healthcare term**:
   `health | medical | clinical | diagnostic | patient | therapeutic | disease | telemedicine | pharmaceutical | drug`

Matched terms are recorded per row so the report can show "which AI keywords are surging."

## Storage Schema (SQLite)

```sql
applications (
    serial_number      TEXT PRIMARY KEY,   -- USPTO unique ID
    mark_text          TEXT,
    filing_date        DATE,
    registration_date  DATE,                -- nullable
    status_code        TEXT,
    status_description TEXT,
    owner_name         TEXT,
    owner_state        TEXT,
    owner_country      TEXT,
    description        TEXT,                -- goods/services description
    matched_ai_terms   TEXT,                -- JSON array
    matched_hc_terms   TEXT,                -- JSON array
    fetched_at         TIMESTAMP,
    raw_json           TEXT                 -- full API response
)

nice_classes (
    serial_number  TEXT,
    class_code     TEXT,
    PRIMARY KEY (serial_number, class_code)
)

monitor_runs (
    run_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at     TIMESTAMP,
    since_date DATE,
    new_count  INTEGER
)
```

`raw_json` future-proofs analyses — new fields can be extracted later without re-fetching.

## Data Flow

**Backfill** (one-shot):
- Iterate month-by-month over the last 60 months
- For each month: query API with filter, paginate, UPSERT into `applications` + `nice_classes`
- Idempotent — re-running resumes safely (at most one redundant month re-fetched)

**Monitor** (weekly):
- `since_date = max(filing_date) from applications`, fallback to 7 days ago
- Query API for filings ≥ `since_date`
- Diff against existing `serial_number`s
- Format new rows per `--format`
- Insert one row into `monitor_runs`

**Report** (on demand):
- pandas reads `applications` + `nice_classes`
- Compute aggregations
- Plotly figures embedded inline (no CDN) into Jinja2 template
- Write `trends.html` in current directory

## Trend Report Contents (`trends.html`)

Single self-contained HTML file. Sections, top to bottom:

1. **Header / summary card** — totals, date range, YoY % change
2. **Filing volume over time** — monthly line chart, last 60 months
3. **AI keyword trends** — stacked area, one band per AI term
4. **Top applicants** — horizontal bar, top 25
5. **Nice class distribution** — donut across {5, 9, 10, 42, 44}
6. **Status breakdown** — donut across registered/pending/abandoned/etc.
7. **Recent filings table** — last 50 marks with TSDR links

Estimated size: 2–4 MB (Plotly JS bundle dominates).

## Error Handling

| Condition | Behavior |
|---|---|
| 429 rate limit | Exponential backoff with jitter, max 5 retries |
| 5xx / network blip | Same backoff |
| 401 (bad key) | Fail fast, point at config file |
| Missing config | Print one-shot setup hint with ODP signup URL |
| Backfill interrupted | Safe re-run (UPSERT + month-at-a-time) |

## Testing

- **Unit:** filter logic, keyword matching, schema round-trips
- **Integration:** mocked API responses → backfill → SQLite → report renders non-empty HTML
- **Smoke:** `uspto report` against a fixture DB
- **No live API calls in CI**

## Packaging & Ops

- `pyproject.toml`, installed with `uv tool install .` → `uspto` on PATH
- Python 3.11+, dev in a `uv venv`
- Weekly cron is the user's responsibility; README ships a sample line:
  `0 9 * * 1 /home/hamel/.local/bin/uspto monitor --format md > ~/uspto-weekly.md`
- No Docker in v1

## Repository Layout

```
uspto/
├── pyproject.toml
├── README.md
├── docs/plans/2026-04-26-uspto-cli-design.md
├── src/uspto/
│   ├── __init__.py
│   ├── cli.py          # Typer app
│   ├── client.py       # ODP API wrapper
│   ├── filter.py       # healthcare+AI query + keyword lists
│   ├── storage.py      # SQLite schema + UPSERT helpers
│   ├── monitor.py      # delta logic + formatters
│   ├── analyze.py      # pandas aggregations
│   ├── report.py       # plotly + jinja2 → HTML
│   └── templates/
│       └── trends.html.j2
└── tests/
    ├── fixtures/
    └── test_*.py
```

## Out of Scope (v1)

- Patents (separate domain, slot in later)
- Generic/configurable filter engine (filter is hardcoded)
- Embedded scheduler (cron handles it)
- Docker (single-user CLI doesn't need it)
- Notifications (email/Slack) — `monitor` writes stdout/files, user pipes elsewhere

## Future Extensions

- Patent support (mirror the trademark module structure)
- Promote filter to config (track other slices: e.g., fintech+AI)
- Diff reports (this week vs last week summaries)
- Export to other formats (CSV for spreadsheet jockeys)
