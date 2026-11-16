"""The phone app's copy of the schema must match the models."""
import json
import sqlite3
from pathlib import Path

from app.services import mobile_schema

ASSETS = Path(__file__).resolve().parents[2] / "mobile" / "assets" / "db"


def test_phone_schema_is_up_to_date():
    assert (ASSETS / "schema.sql").read_text(encoding="utf-8") == \
        mobile_schema.build_sql(), (
        "Run: python -m app.services.mobile_schema ../mobile/assets/db")
    assert json.loads((ASSETS / "schema.json").read_text(
        encoding="utf-8")) == json.loads(json.dumps(
            mobile_schema.build_meta()))


def test_phone_schema_creates_a_working_database():
    conn = sqlite3.connect(":memory:")
    conn.executescript(mobile_schema.build_sql())
    conn.execute(
        "INSERT INTO accounts (name, type, currency, opening_balance, "
        "opening_date, is_archived, is_demo) VALUES "
        "('Cash', 'cash', 'CHF', 0, '2026-01-01', 0, 0)")
    uid, updated = conn.execute(
        "SELECT uid, updated_at FROM accounts").fetchone()
    assert len(uid) == 32 and updated
    conn.execute("DELETE FROM accounts")
    assert conn.execute("SELECT table_name, uid FROM sync_tombstones"
                        ).fetchone() == ("accounts", uid)
