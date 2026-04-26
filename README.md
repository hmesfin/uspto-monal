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
uspto backfill              # fetch the last 60 months (one-time, can take a while)
uspto backfill --months 1   # quick test: just last month
uspto monitor               # print new filings since last run (default: table)
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

## How it works

USPTO publishes a daily ZIP of every new trademark application as the `TRTDXFAP` bulk dataset. `uspto backfill` and `uspto monitor` download those ZIPs, stream-parse the XML, run each record through the healthcare+AI filter, and store matches in a local SQLite DB. `uspto report` reads the DB and renders an interactive HTML trend report.

## Development

```
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

## Project layout

- `src/uspto/` — package
  - `cli.py` — Typer entry point
  - `client.py` — USPTO ODP datasets HTTP client
  - `extract.py` — XML case-file → DB row dict
  - `filter.py` — healthcare+AI classifier
  - `backfill.py` — month-by-month bulk ingest
  - `monitor.py` — delta + 3 output formats
  - `analyze.py` — pandas aggregations
  - `report.py` — Plotly + Jinja2 HTML report
  - `storage.py` — SQLite schema + UPSERT helpers
  - `config.py` — env-var config loader
  - `templates/trends.html.j2` — report template
- `scripts/probe_api.py` — reproducible API spike for re-capturing fixtures
- `tests/` — pytest suite (53 tests)
- `docs/plans/` — design + implementation docs
