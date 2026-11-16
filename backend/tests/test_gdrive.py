"""0.7.1: sync through Google Drive's app data folder (fake Drive API)."""
import json
import re
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.services import gdrive, sync
from tests.test_sync import Device, _add_account, _add_txn


class FakeDrive:
    """A tiny in-memory stand-in for the Drive v3 and OAuth endpoints."""

    def __init__(self):
        self.files: dict[str, tuple[str, bytes]] = {}
        self.tokens = 0

    def post(self, url, data=None, timeout=None):
        assert url == gdrive.TOKEN_URL
        self.tokens += 1
        body = {"access_token": f"at{self.tokens}", "expires_in": 3600}
        if data["grant_type"] == "authorization_code":
            assert data["code"] == "good-code" and data["code_verifier"]
            body["refresh_token"] = "rt-1"
        return httpx.Response(200, json=body)

    def request(self, method, url, headers=None, params=None, content=None,
                timeout=None):
        assert headers["Authorization"].startswith("Bearer at")
        params = params or {}
        if method == "GET" and url.endswith("/files"):
            assert params["spaces"] == "appDataFolder"
            return httpx.Response(200, json={"files": [
                {"id": fid, "name": name}
                for fid, (name, _) in self.files.items()]})
        if method == "GET":
            fid = url.rsplit("/", 1)[1]
            return httpx.Response(200, content=self.files[fid][1])
        if method == "POST" and url == gdrive.UPLOAD:
            boundary = re.search(r"boundary=(\S+)",
                                 headers["Content-Type"])[1].encode()
            parts = content.split(b"--" + boundary)
            meta = json.loads(parts[1].split(b"\r\n\r\n", 1)[1].strip())
            data = parts[2].split(b"\r\n\r\n", 1)[1][:-2]
            assert meta["parents"] == ["appDataFolder"]
            fid = f"f{len(self.files) + 1}"
            self.files[fid] = (meta["name"], data)
            return httpx.Response(200, json={"id": fid})
        raise AssertionError(f"unexpected {method} {url}")


@pytest.fixture()
def drive(monkeypatch):
    fake = FakeDrive()
    monkeypatch.setattr(gdrive.httpx, "post", fake.post)
    monkeypatch.setattr(gdrive.httpx, "request", fake.request)
    monkeypatch.setattr(gdrive, "client", lambda: ("cid", "csecret"))
    monkeypatch.setattr(sync, "PBKDF2_ITERATIONS", 1000)
    return fake


def _sign_in(dev):
    url = gdrive.start("http://127.0.0.1:9/oauth/google")
    q = parse_qs(urlparse(url).query)
    assert q["scope"] == [gdrive.SCOPE]
    assert q["code_challenge_method"] == ["S256"]
    gdrive.finish(dev.data, q["state"][0], "good-code")


def test_two_pcs_sync_through_google_drive(drive, tmp_path):
    a, b = Device(tmp_path, "pc"), Device(tmp_path, "laptop")
    try:
        with pytest.raises(sync.SyncError, match="Sign in"):
            a.setup(gdrive.FOLDER)
        _sign_in(a)
        _sign_in(b)
        assert gdrive.signed_in(a.data)
        assert b"rt-1" not in (a.data / gdrive.TOKEN_FILE).read_bytes()
        a.setup(gdrive.FOLDER)
        names = {n for n, _ in drive.files.values()}
        assert "pfi-sync.json" in names
        assert all(n == "pfi-sync.json" or gdrive._NAME_RE.match(n)
                   for n in names)
        b.setup(gdrive.FOLDER)
        acc = _add_account(a, "Drive account")
        _add_txn(a, acc, "-12.00", "Coop")
        assert a.run().sent > 0
        assert b.run().received > 0
        assert [t.description for t in b.txns()] == ["Coop"]
        assert sync.phone_can_find(gdrive.FOLDER)
        with pytest.raises(sync.SyncError, match="does not match"):
            sync.setup(b.db, b.data, gdrive.FOLDER, "wrong passphrase")
    finally:
        a.close()
        b.close()


def test_unknown_state_is_refused(drive, tmp_path):
    with pytest.raises(gdrive.DriveError, match="unknown or expired"):
        gdrive.finish(tmp_path, "made-up", "good-code")


def test_drive_errors_become_sync_errors(drive, tmp_path, monkeypatch):
    dev = Device(tmp_path, "pc")
    try:
        _sign_in(dev)
        dev.setup(gdrive.FOLDER)
        monkeypatch.setattr(gdrive.httpx, "request",
                            lambda *a, **k: httpx.Response(503))
        with pytest.raises(sync.SyncError, match="503"):
            dev.run()
    finally:
        dev.close()


def test_not_available_without_client(monkeypatch, tmp_path):
    monkeypatch.setattr(gdrive, "_client_file_candidates",
                        lambda: [tmp_path / "none.json"])
    assert gdrive.client() is None
    with pytest.raises(gdrive.DriveError, match="not available"):
        gdrive.start("http://127.0.0.1:9/oauth/google")
    (tmp_path / "none.json").write_text(json.dumps(
        {"installed": {"client_id": "x.apps.googleusercontent.com",
                       "client_secret": "s"}}))
    assert gdrive.client() == ("x.apps.googleusercontent.com", "s")


def test_callback_page(api, drive):
    r = api.get("/oauth/google", params={"error": "access_denied"})
    assert r.status_code == 200 and "cancelled" in r.text
    r = api.get("/oauth/google", params={"state": "nope", "code": "c"})
    assert r.status_code == 400
    r = api.post("/api/sync/google/start")
    assert r.status_code == 200
    state = parse_qs(urlparse(r.json()["url"]).query)["state"][0]
    r = api.get("/oauth/google", params={"state": state, "code": "good-code"})
    assert r.status_code == 200 and "connected" in r.text
    body = api.get("/api/sync").json()
    assert body["google_available"] and body["google_signed_in"]
