"""Test fixtures: a throw-away embedded PostgreSQL cluster per test run.

Set ``PFI_TEST_PG_BIN`` to the PostgreSQL ``bin`` folder (e.g.
``C:\\Program Files\\PostgreSQL\\18\\bin``) before running ``pytest``.
"""
import os
import shutil
import tempfile
from pathlib import Path

import pytest

PG_BIN = os.environ.get("PFI_TEST_PG_BIN")
if not PG_BIN:
    pytest.exit("Set PFI_TEST_PG_BIN to your PostgreSQL bin folder, e.g. "
                r"C:\Program Files\PostgreSQL\18\bin", returncode=2)
DATA = Path(tempfile.mkdtemp(prefix="pfi-test-"))
os.environ.update(PFI_PG_BIN=PG_BIN, PFI_DATA_DIR=str(DATA),
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
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables
                       if t.name != "schema_version")
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
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
