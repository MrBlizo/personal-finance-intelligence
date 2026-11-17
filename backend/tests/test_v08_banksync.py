"""0.8: bank sync through SimpleFIN and Enable Banking (fake servers)."""
import base64
import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.services import banksync
from conftest import make_account

ACCESS = "https://user:secret@bridge.example/simplefin"
CLAIM = "https://bridge.example/simplefin/claim/abc"
TOKEN = base64.b64encode(CLAIM.encode()).decode()


def _ts(days_ago: int) -> int:
    d = date.today() - timedelta(days=days_ago)
    return int(datetime(d.year, d.month, d.day, 12,
                        tzinfo=timezone.utc).timestamp())


SF_ACCOUNTS = {"errors": ["Chase needs a new sign-in"], "accounts": [{
    "org": {"name": "Chase"}, "id": "ACT-1", "name": "Chase Checking",
    "currency": "USD", "balance": "1520.10", "balance-date": _ts(0),
    "transactions": [
        {"id": "T1", "posted": _ts(3), "amount": "-12.50",
         "description": "STARBUCKS #123", "payee": "Starbucks"},
        {"id": "T2", "posted": _ts(2), "amount": "2100.00",
         "description": "ACME PAYROLL"},
        {"id": "T3", "posted": _ts(1), "amount": "-40.00",
         "description": "SHELL", "pending": True},
    ]}]}


class Fake:
    """A tiny stand-in for the providers' HTTP APIs."""

    def __init__(self):
        self.calls = []
        self.claimed = False

    def __call__(self, method, url, **kw):
        self.calls.append((method, url, kw))
        req = httpx.Request(method, url)
        if url == CLAIM:
            if self.claimed:
                return httpx.Response(403, request=req)
            self.claimed = True
            return httpx.Response(200, text=ACCESS, request=req)
        if url == "https://bridge.example/simplefin/accounts":
            assert kw["auth"] == ("user", "secret")
            data = json.loads(json.dumps(SF_ACCOUNTS))
            if kw["params"].get("balances-only"):
                for a in data["accounts"]:
                    a["transactions"] = []
            return httpx.Response(200, json=data, request=req)
        if url.startswith(banksync.EB_API):
            return self.eb(method, url[len(banksync.EB_API):], kw, req)
        return httpx.Response(404, request=req)

    def eb(self, method, path, kw, req):
        token = kw["headers"]["Authorization"].split()[1]
        head = json.loads(base64.urlsafe_b64decode(
            token.split(".")[0] + "=="))
        assert head == {"typ": "JWT", "alg": "RS256", "kid": "app-123"}
        if path == "/auth":
            assert kw["json"]["redirect_url"].startswith("https://")
            self.state = kw["json"]["state"]
            return httpx.Response(200, json={"url": "https://bank/consent"},
                                  request=req)
        if path == "/sessions":
            return httpx.Response(200, json={
                "session_id": "S1", "access": {"valid_until": "2027-05-01"},
                "accounts": [{"uid": "U1", "name": "Compte courant",
                              "currency": "EUR",
                              "account_id": {"iban": "FR76..."}}]},
                request=req)
        if path == "/sessions/S1":
            return httpx.Response(200, json={
                "accounts": ["U1"], "aspsp": {"name": "BNP Paribas"}},
                request=req)
        if path == "/accounts/U1/details":
            return httpx.Response(200, json={
                "name": "Compte courant", "currency": "EUR"}, request=req)
        if path == "/accounts/U1/transactions":
            page2 = kw["params"].get("continuation_key") == "k2"
            day = (date.today() - timedelta(days=2)).isoformat()
            txns = [{
                "entry_reference": "E2" if page2 else "E1",
                "transaction_amount": {"amount": "30.00", "currency": "EUR"},
                "credit_debit_indicator": "CRDT" if page2 else "DBIT",
                "status": "BOOK", "booking_date": day,
                "remittance_information": ["CARREFOUR PARIS"],
                "creditor": {"name": "Carrefour"},
                "debtor": {"name": "Employer SA"}},
                {"entry_reference": "E3", "status": "PDNG",
                 "transaction_amount": {"amount": "5", "currency": "EUR"},
                 "credit_debit_indicator": "DBIT", "booking_date": day}]
            return httpx.Response(200, json={
                "transactions": txns,
                "continuation_key": None if page2 else "k2"}, request=req)
        return httpx.Response(404, request=req)


@pytest.fixture()
def fake(monkeypatch, api):
    f = Fake()
    monkeypatch.setattr(banksync, "_http", f)
    yield f
    for p in ("simplefin", "enablebanking"):
        api.delete(f"/api/banksync/{p}")


def _txns(api, acc):
    rows = api.get("/api/transactions", params={"account_id": acc}).json()
    return sorted((t["description"], float(t["amount"]))
                  for t in rows["items"])


def test_simplefin_connect_link_and_sync(api, fake):
    acc = make_account(api, currency="USD", opening_date="2020-01-01")
    r = api.post("/api/banksync/simplefin", json={"token": TOKEN})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simplefin"] is True
    assert body["warnings"] == ["Chase needs a new sign-in"]
    [link] = body["links"]
    assert link["name"] == "Chase Checking" and link["balance"] == 1520.10
    assert "secret" not in r.text
    api.put(f"/api/banksync/links/{link['id']}", json={"account_id": acc})
    res = api.post("/api/banksync/run").json()["result"]
    assert res["imported"] == 2 and res["accounts"] == 1
    assert _txns(api, acc) == [("ACME PAYROLL", 2100.0),
                               ("STARBUCKS #123", -12.5)]
    again = api.post("/api/banksync/run").json()["result"]
    assert again["imported"] == 0 and again["duplicates"] == 2


def test_simplefin_used_token_and_garbage(api, fake):
    assert api.post("/api/banksync/simplefin",
                    json={"token": TOKEN}).status_code == 200
    r = api.post("/api/banksync/simplefin", json={"token": TOKEN})
    assert r.status_code == 422 and "already used" in r.json()["detail"]
    r = api.post("/api/banksync/simplefin", json={"token": "not a token!!"})
    assert r.status_code == 422


def _pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return key, pem


def test_enable_banking_jwt_is_valid_rs256():
    key, pem = _pem()
    token = banksync.eb_jwt("app-123", pem, now=1_800_000_000)
    head, body, sig = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=="))
    assert claims == {"iss": "enablebanking.com",
                      "aud": "api.enablebanking.com",
                      "iat": 1_800_000_000, "exp": 1_800_003_600}
    key.public_key().verify(base64.urlsafe_b64decode(sig + "=="),
                            f"{head}.{body}".encode(), padding.PKCS1v15(),
                            hashes.SHA256())


def test_enable_banking_consent_and_sync(api, fake):
    _, pem = _pem()
    acc = make_account(api, currency="EUR", opening_date="2020-01-01")
    r = api.post("/api/banksync/enablebanking",
                 json={"app_id": "app-123", "private_key": pem})
    assert r.status_code == 200, r.text
    assert "PRIVATE KEY" not in r.text
    r = api.post("/api/banksync/enablebanking/connect",
                 json={"bank": "BNP Paribas", "country": "fr"})
    assert r.json()["url"] == "https://bank/consent"
    port, _ = fake.state.split(".", 1)
    assert port.isdigit()
    page = api.get("/oauth/enablebanking",
                   params={"code": "c0de", "state": "wrong"})
    assert page.status_code == 400
    page = api.get("/oauth/enablebanking",
                   params={"code": "c0de", "state": fake.state})
    assert page.status_code == 200 and "connected" in page.text
    [link] = api.get("/api/banksync").json()["links"]
    assert link["institution"] == "BNP Paribas"
    api.put(f"/api/banksync/links/{link['id']}", json={"account_id": acc})
    res = api.post("/api/banksync/run").json()["result"]
    assert res["imported"] == 2, res
    assert _txns(api, acc) == [("CARREFOUR PARIS", -30.0),
                               ("CARREFOUR PARIS", 30.0)]


def test_bad_private_key_is_refused(api, fake):
    r = api.post("/api/banksync/enablebanking",
                 json={"app_id": "app-123", "private_key": "x" * 120})
    assert r.status_code == 422 and "PEM" in r.json()["detail"]


def test_due_only_with_linked_accounts(api, fake):
    from app.db import SessionLocal
    with SessionLocal() as db:
        assert banksync.due(db) is False
    acc = make_account(api, currency="USD")
    link = api.post("/api/banksync/simplefin",
                    json={"token": TOKEN}).json()["links"][0]
    api.put(f"/api/banksync/links/{link['id']}", json={"account_id": acc})
    with SessionLocal() as db:
        assert banksync.due(db) is True
    api.post("/api/banksync/run")
    with SessionLocal() as db:
        assert banksync.due(db) is False
