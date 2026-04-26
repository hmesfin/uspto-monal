import pytest

from uspto.analyze import (
    ai_term_trends,
    filings_per_month,
    nice_class_distribution,
    recent_filings,
    status_distribution,
    summary_stats,
    top_applicants,
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
