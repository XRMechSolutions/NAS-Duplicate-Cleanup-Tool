from __future__ import annotations

from datetime import datetime


def test_datetime_roundtrip(test_db) -> None:
    with test_db.connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS dt_test (ts TIMESTAMP)")
        value = datetime(2024, 2, 3, 4, 5, 6)
        conn.execute("INSERT INTO dt_test (ts) VALUES (?)", (value,))
        row = conn.execute("SELECT ts FROM dt_test").fetchone()

    assert row["ts"] == value


def test_datetime_roundtrip_microseconds(test_db) -> None:
    with test_db.connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS dt_test_micro (ts TIMESTAMP)")
        value = datetime(2024, 2, 3, 4, 5, 6, 123456)
        conn.execute("INSERT INTO dt_test_micro (ts) VALUES (?)", (value,))
        row = conn.execute("SELECT ts FROM dt_test_micro").fetchone()

    assert row["ts"] == value
