from datetime import datetime
from pathlib import Path
import sqlite3

import plotly.express as px
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import analyze


_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _empty_fig(msg: str) -> str:
    return f"<p><em>{msg}</em></p>"


def render_report(conn: sqlite3.Connection, output: Path) -> None:
    output = Path(output)
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

    saas = analyze.saas_share_over_time(conn)
    fig_saas = (
        px.line(saas, x="month", y="saas_share_pct", title=None,
                labels={"saas_share_pct": "Class 42 share (%)"}).to_html(
            full_html=False, include_plotlyjs=False)
        if not saas.empty else _empty_fig("No SaaS data")
    )

    recent = analyze.recent_filings(conn, limit=50)
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(),
    )
    tpl = env.get_template("trends.html.j2")
    html = tpl.render(
        stats=stats,
        fig_filings=fig_filings, fig_ai_terms=fig_ai_terms,
        fig_top=fig_top, fig_classes=fig_classes, fig_status=fig_status,
        fig_saas=fig_saas,
        recent=recent,
        generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )
    output.write_text(html)
