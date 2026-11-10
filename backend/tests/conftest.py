"""Test fixtures: a throw-away SQLite database per test run.

The tests that move PostgreSQL data (``test_legacy.py``) also need
``PFI_TEST_PG_BIN``, the PostgreSQL ``bin`` folder (e.g.
``C:\\Program Files\\PostgreSQL\\18\\bin``); they are skipped without it.
"""
import os
import shutil
import tempfile
from pathlib import Path

import pytest

PG_BIN = os.environ.get("PFI_TEST_PG_BIN")
DATA = Path(tempfile.mkdtemp(prefix="pfi-test-"))
os.environ.pop("PFI_DATABASE_URL", None)
os.environ.update(PFI_PG_BIN=PG_BIN or "", PFI_DATA_DIR=str(DATA),
                  PFI_PG_PORT="54399", PFI_API_TOKEN="",
                  PFI_FRONTEND_DIST=str(DATA / "no-ui"),
                  PFI_BACKGROUND_TASKS="0")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_defaults  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
    shutil.rmtree(DATA, ignore_errors=True)


@pytest.fixture()
def api(client):
    """Client on an empty database with default categories."""
    with get_engine().begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name != "schema_version":
                conn.execute(table.delete())
        conn.execute(text("DELETE FROM sqlite_sequence")) \
            if conn.execute(text("SELECT 1 FROM sqlite_master WHERE "
                                 "name='sqlite_sequence'")).first() else None
    with SessionLocal() as db:
        seed_defaults(db, "CHF")
    return client


def cat_id(api, name, kind="expense"):
    return next(c["id"] for c in api.get("/api/categories").json()
                if c["name"] == name and c["kind"] == kind)


def make_account(api, name="Checking", currency="CHF", type_="checking",
                 opening="1000", opening_date="2026-01-01"):
    r = api.post("/api/accounts", json={
        "name": name, "type": type_, "currency": currency,
        "opening_balance": opening, "opening_date": opening_date})
    assert r.status_code == 201, r.text
    return r.json()["id"]
