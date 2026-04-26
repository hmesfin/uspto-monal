"""Populate a SQLite DB with a small, deterministic dataset for analysis tests."""
from datetime import date

from uspto.storage import (
    connect,
    create_schema,
    upsert_application,
    upsert_nice_classes,
)


def seed(db_path):
    conn = connect(db_path)
    create_schema(conn)
    rows = [
        ("97000001", "MEDAI",     date(2024, 1, 15), "Acme Health",  ["AI"],               ["diagnostic"],     ["9", "42"]),
        ("97000002", "DIAGNOSE",  date(2024, 6, 10), "Acme Health",  ["machine learning"], ["clinical"],       ["42"]),
        ("97000003", "CARELLM",   date(2025, 3, 1),  "Beta Bio",     ["LLM"],              ["patient"],        ["42"]),
        ("97000004", "VISIONMD",  date(2025, 9, 5),  "Beta Bio",     ["computer vision"],  ["medical"],        ["10"]),
        ("97000005", "GENPHARMA", date(2026, 2, 1),  "Gamma Pharma", ["generative AI"],    ["pharmaceutical"], ["5"]),
    ]
    for sn, mark, fdate, owner, ai, hc, classes in rows:
        upsert_application(conn, {
            "serial_number": sn,
            "mark_text": mark,
            "filing_date": fdate,
            "registration_date": None,
            "status_code": "700",
            "status_description": "Registered",
            "owner_name": owner,
            "owner_state": "CA",
            "owner_country": "US",
            "description": f"{', '.join(ai)} for {', '.join(hc)} use",
            "matched_ai_terms": ai,
            "matched_hc_terms": hc,
            "fetched_at": "2026-04-26",
            "raw_json": "{}",
        })
        upsert_nice_classes(conn, sn, classes)
    conn.commit()
    conn.close()
    return db_path
