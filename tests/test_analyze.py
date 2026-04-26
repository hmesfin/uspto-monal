import pytest

from uspto.analyze import (
    ai_term_trends,
    filings_per_month,
    nice_class_distribution,
    recent_filings,
    saas_share_over_time,
    status_distribution,
    summary_stats,
    top_applicants,
)
from uspto.status_codes import bucket
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


def test_status_distribution_buckets_codes(db):
    """Seed uses status_code='700' which should bucket to 'Registered'."""
    df = status_distribution(connect(db))
    assert df.iloc[0]["status"] == "Registered"


def test_status_bucket_function():
    assert bucket("700") == "Registered"
    assert bucket("630") == "Under examination"
    assert bucket("681") == "Suspended"
    assert bucket("819") == "Abandoned"
    assert bucket(None) == "Unknown"
    assert bucket("") == "Unknown"
    assert bucket("not-a-number") == "Unknown"


def test_recent_filings_limit(db):
    rows = recent_filings(connect(db), limit=3)
    assert len(rows) == 3


def test_summary_stats_keys(db):
    stats = summary_stats(connect(db))
    for k in [
        "total", "this_year", "last_year", "yoy_pct", "date_min", "date_max",
        "saas_total", "saas_share_pct", "saas_yoy_pct",
    ]:
        assert k in stats


def test_summary_stats_saas_count(db):
    """Seed: 3 of 5 marks have class 42 (97000001, 97000002, 97000003)."""
    stats = summary_stats(connect(db))
    assert stats["saas_total"] == 3
    assert 55 < stats["saas_share_pct"] < 65  # 3/5 = 60%


def test_saas_share_over_time(db):
    df = saas_share_over_time(connect(db))
    assert {"month", "saas_count", "total_count", "saas_share_pct"}.issubset(df.columns)
    assert df["total_count"].sum() == 5
    assert df["saas_count"].sum() == 3
