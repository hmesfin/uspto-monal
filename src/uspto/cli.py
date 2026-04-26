import webbrowser
from datetime import date
from pathlib import Path

import typer

from .backfill import run_backfill
from .client import USPTOClient
from .config import ConfigError, load_config
from .monitor import format_json, format_markdown, format_table, run_monitor
from .report import render_report
from .storage import connect, create_schema

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
    fmt: str = typer.Option("table", "--format", "-f", help="table | md | json"),
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
