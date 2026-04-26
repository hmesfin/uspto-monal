import sqlite3
from uspto.storage import create_schema, connect


def test_create_schema_creates_three_tables(tmp_path):
    db = tmp_path / "x.db"
    conn = connect(db)
    create_schema(conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    names = [r[0] for r in cursor.fetchall()]
    assert names == ["applications", "monitor_runs", "nice_classes"]


def test_create_schema_is_idempotent(tmp_path):
    db = tmp_path / "x.db"
    conn = connect(db)
    create_schema(conn)
    create_schema(conn)  # should not raise


def test_connect_creates_parent_directory(tmp_path):
    db = tmp_path / "nested" / "dir" / "x.db"
    conn = connect(db)
    assert db.parent.exists()
    conn.close()
