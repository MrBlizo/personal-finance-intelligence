"""0.5: no PostgreSQL; leftovers from 0.3 can be removed on request."""
from fastapi.testclient import TestClient

from app import legacy
from app.config import get_settings
from app.main import create_app


def _fill(data_dir):
    (data_dir / "pgdata-0.3" / "base").mkdir(parents=True)
    (data_dir / "pgdata-0.3" / "base" / "1").write_bytes(b"x" * 100)
    (data_dir / "runtime" / "pgsql-abc").mkdir(parents=True)
    (data_dir / "pg_secret").write_text("secret")
    (data_dir / "logs").mkdir(exist_ok=True)
    (data_dir / "logs" / "postgres-server.log").write_text("log")
    (data_dir / "logs" / "api.log").write_text("keep")
    (data_dir / "backups").mkdir(exist_ok=True)
    (data_dir / "backups" / "pfi-auto-20261110-001815.dump").write_bytes(
        b"PGDMP" + b"0" * 50)


def test_leftovers_and_removal(tmp_path):
    _fill(tmp_path)
    (tmp_path / "pfi.sqlite").write_bytes(b"db")
    found = legacy.leftovers(tmp_path, [tmp_path / "backups"])
    assert sorted(p.name for p in found.paths) == [
        "pg_secret", "pgdata-0.3", "postgres-server.log", "runtime"]
    assert found.size == 100 + 6 + 3
    assert len(found.dumps) == 1 and found.dump_size == 55
    freed = legacy.remove_leftovers(tmp_path, [tmp_path / "backups"])
    assert freed == 109
    assert not (tmp_path / "pgdata-0.3").exists()
    assert (tmp_path / "logs" / "api.log").exists()
    assert (tmp_path / "pfi.sqlite").exists()
    assert (tmp_path / "backups" / "pfi-auto-20261110-001815.dump").exists()
    assert legacy.remove_leftovers(tmp_path, [tmp_path / "backups"],
                                   dumps=True) == 55
    assert not list((tmp_path / "backups").glob("*.dump"))


def test_unmoved_cluster_is_never_a_leftover(tmp_path):
    (tmp_path / "pgdata").mkdir()
    (tmp_path / "pgdata" / "PG_VERSION").write_text("16")
    assert legacy.has_cluster(tmp_path)
    assert legacy.leftovers(tmp_path).paths == []


def test_cleanup_endpoints(api):
    data_dir = get_settings().data_dir
    _fill(data_dir)
    info = api.get("/api/legacy-data").json()
    assert info["size"] == 109 and info["dumps"] == 1
    assert "pgdata-0.3" in info["items"]
    rows = {b["name"]: b for b in api.get("/api/backups").json()["backups"]}
    assert rows["pfi-auto-20261110-001815.dump"]["legacy"]
    r = api.post("/api/backups/pfi-auto-20261110-001815.dump/restore")
    assert r.status_code == 422 and "0.4.0" in r.json()["detail"]
    out = api.post("/api/legacy-data/delete", json={}).json()
    assert out["freed"] == 109 and out["size"] == 0 and out["dumps"] == 1
    out = api.post("/api/legacy-data/delete", json={"dumps": True}).json()
    assert out["freed"] == 55 and out["dumps"] == 0


def test_dump_upload_points_to_04(api):
    r = api.post("/api/backups/upload", files={
        "file": ("old.dump", b"PGDMP" + b"0" * 20,
                 "application/octet-stream")})
    assert r.status_code == 422 and "0.4.0" in r.json()["detail"]


def test_unmoved_cluster_blocks_start(tmp_path, monkeypatch):
    (tmp_path / "pgdata").mkdir()
    (tmp_path / "pgdata" / "PG_VERSION").write_text("16")
    settings = get_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    app = create_app()
    with TestClient(app) as c:
        health = c.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "blocked"
        assert c.get("/api/accounts").status_code == 503
        page = c.get("/")
        assert page.status_code == 503 and "PFI 0.4.0" in page.text
    assert not (tmp_path / "pfi.sqlite").exists()
    assert (tmp_path / "pgdata" / "PG_VERSION").exists()
