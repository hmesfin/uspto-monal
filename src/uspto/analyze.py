import json
import sqlite3

import pandas as pd

from .status_codes import bucket as _status_bucket


def _read(conn: sqlite3.Connection, sql: str, params=()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def filings_per_month(conn: sqlite3.Connection) -> pd.DataFrame:
    df = _read(
        conn,
        "SELECT filing_date FROM applications WHERE filing_date IS NOT NULL",
    )
    df["month"] = pd.to_datetime(df["filing_date"]).dt.to_period("M").dt.to_timestamp()
    return df.groupby("month").size().reset_index(name="count").sort_values("month")


def top_applicants(conn: sqlite3.Connection, limit: int = 25) -> pd.DataFrame:
    return _read(
        conn,
        "SELECT owner_name, COUNT(*) AS count FROM applications "
        "WHERE owner_name IS NOT NULL "
        "GROUP BY owner_name ORDER BY count DESC, owner_name ASC LIMIT ?",
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
    """Bucket raw status codes into lifecycle stages (Registered, Examination,
    Abandoned, etc.) — descriptions aren't shipped in the XML feed, but the
    numeric codes are stable and bucket cleanly."""
    df = _read(conn, "SELECT status_code FROM applications")
    df["status"] = df["status_code"].apply(_status_bucket)
    return (
        df.groupby("status").size().reset_index(name="count")
        .sort_values("count", ascending=False)
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


SAAS_CLASS = "42"  # Nice class 42: scientific & tech services / SaaS


def summary_stats(conn: sqlite3.Connection) -> dict:
    df = _read(
        conn,
        "SELECT filing_date, serial_number FROM applications "
        "WHERE filing_date IS NOT NULL",
    )
    if df.empty:
        return {
            "total": 0,
            "this_year": 0, "last_year": 0, "yoy_pct": 0.0,
            "date_min": None, "date_max": None,
            "saas_total": 0, "saas_share_pct": 0.0, "saas_yoy_pct": 0.0,
        }
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    today = pd.Timestamp.today()
    this_year_mask = df["filing_date"].dt.year == today.year
    last_year_mask = df["filing_date"].dt.year == today.year - 1
    this_year = int(this_year_mask.sum())
    last_year = int(last_year_mask.sum())
    yoy = ((this_year - last_year) / last_year * 100) if last_year else 0.0

    # SaaS = any application with at least one Nice class 42 row.
    saas_serials = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT serial_number FROM nice_classes WHERE class_code = ?",
            (SAAS_CLASS,),
        )
    }
    df["is_saas"] = df["serial_number"].isin(saas_serials)
    saas_total = int(df["is_saas"].sum())
    saas_share = (saas_total / len(df) * 100) if len(df) else 0.0
    saas_this = int((df["is_saas"] & this_year_mask).sum())
    saas_last = int((df["is_saas"] & last_year_mask).sum())
    saas_yoy = ((saas_this - saas_last) / saas_last * 100) if saas_last else 0.0

    return {
        "total": len(df),
        "this_year": this_year, "last_year": last_year, "yoy_pct": float(yoy),
        "date_min": df["filing_date"].min().date(),
        "date_max": df["filing_date"].max().date(),
        "saas_total": saas_total,
        "saas_share_pct": float(saas_share),
        "saas_yoy_pct": float(saas_yoy),
    }


def saas_share_over_time(conn: sqlite3.Connection) -> pd.DataFrame:
    """Monthly: % of in-scope marks that are class 42 (SaaS-flavored).
    Returns columns: month, saas_count, total_count, saas_share_pct.
    Useful for testing the 'SaaS is dead' thesis against actual filings."""
    apps = _read(
        conn,
        "SELECT serial_number, filing_date FROM applications "
        "WHERE filing_date IS NOT NULL",
    )
    if apps.empty:
        return pd.DataFrame(
            columns=["month", "saas_count", "total_count", "saas_share_pct"]
        )
    saas_serials = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT serial_number FROM nice_classes WHERE class_code = ?",
            (SAAS_CLASS,),
        )
    }
    apps["month"] = (
        pd.to_datetime(apps["filing_date"]).dt.to_period("M").dt.to_timestamp()
    )
    apps["is_saas"] = apps["serial_number"].isin(saas_serials)
    grouped = apps.groupby("month").agg(
        saas_count=("is_saas", "sum"),
        total_count=("serial_number", "count"),
    ).reset_index()
    grouped["saas_share_pct"] = grouped["saas_count"] / grouped["total_count"] * 100
    return grouped.sort_values("month")
