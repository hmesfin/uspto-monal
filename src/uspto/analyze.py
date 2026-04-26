import json
import sqlite3

import pandas as pd


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
    df = _read(
        conn,
        "SELECT filing_date FROM applications WHERE filing_date IS NOT NULL",
    )
    if df.empty:
        return {
            "total": 0,
            "this_year": 0,
            "last_year": 0,
            "yoy_pct": 0.0,
            "date_min": None,
            "date_max": None,
        }
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
