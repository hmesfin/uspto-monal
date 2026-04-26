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
