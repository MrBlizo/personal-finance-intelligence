"""0.5: the opt-in anonymous user count sends nothing unless asked."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import __version__
from app.db import SessionLocal
from app.routers import core
from app.services import usage


class FakeResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def sent(monkeypatch):
    calls = []

    def fake(req, timeout=10):
        calls.append((req.full_url, json.loads(req.data)))
        return FakeResponse()
    monkeypatch.setattr(usage.urllib.request, "urlopen", fake)
    monkeypatch.setattr(usage, "USAGE_URL", "https://counter.test/ping")
    monkeypatch.setattr(core, "_ping_now", lambda: None)
    return calls


def test_nothing_without_consent(api, sent):
    s = api.get("/api/settings").json()
    assert s["usage_ping"] == "ask" and s["usage_available"]
    assert s["usage_sent"] is None
    with SessionLocal() as db:
        assert not usage.send(db)
    assert sent == []


def test_opt_in_sends_three_values_weekly(api, sent):
    s = api.put("/api/settings", json={"usage_ping": "on"}).json()
    assert s["usage_ping"] == "on"
    rid = s["usage_sent"]["id"]
    assert len(rid) == 32 and int(rid, 16) >= 0
    assert s["usage_sent"] == {"id": rid, "version": __version__,
                               "lang": "en"}
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    with SessionLocal() as db:
        assert usage.send(db, now=now)
        assert not usage.send(db, now=now + timedelta(days=6))
        assert usage.send(db, now=now + timedelta(days=7))
    bodies = [b for _, b in sent]
    assert all(b == {"id": rid, "version": __version__, "lang": "en"}
               for b in bodies)
    assert all(url == "https://counter.test/ping" for url, _ in sent)


def test_opt_out_forgets_the_id(api, sent):
    first = api.put("/api/settings", json={"usage_ping": "on"}).json()
    off = api.put("/api/settings", json={"usage_ping": "off"}).json()
    assert off["usage_ping"] == "off" and off["usage_sent"] is None
    with SessionLocal() as db:
        assert usage.payload(db)["id"] == ""
        assert not usage.due(db)
    again = api.put("/api/settings", json={"usage_ping": "on"}).json()
    assert again["usage_sent"]["id"] != first["usage_sent"]["id"]


def test_not_offered_without_counter(api, monkeypatch):
    monkeypatch.setattr(usage, "USAGE_URL", "")
    assert api.get("/api/settings").json()["usage_available"] is False


def test_offline_is_quiet(api, monkeypatch):
    def down(req, timeout=10):
        raise OSError("no network")
    monkeypatch.setattr(usage.urllib.request, "urlopen", down)
    with SessionLocal() as db:
        usage.set_state(db, True)
        db.commit()
        assert usage.send(db, url="https://counter.test/ping") is False
        assert usage.due(db, url="https://counter.test/ping")
