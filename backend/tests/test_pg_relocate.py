"""Running the bundled PostgreSQL from a copy (Microsoft Store install)."""
from pathlib import Path

import pytest

from app import pg_embedded
from app.pg_embedded import (EmbeddedPostgres, in_store_package,
                             relocate_binaries)


def fake_pgsql(root: Path, marker: str = "v1") -> Path:
    """Create a minimal PostgreSQL folder layout and return its bin dir.

    Parameters
    ----------
    root : Path
        The folder that will contain ``bin``, ``lib`` and ``share``.
    marker : str
        The text written into every fake program, to tell copies apart.
    """
    for part, name in (("bin", "initdb.exe"), ("bin", "pg_ctl.exe"),
                       ("bin", "initdb"), ("bin", "pg_ctl"),
                       ("lib", "plpgsql.dll"),
                       ("share", "postgres.bki")):
        (root / part).mkdir(parents=True, exist_ok=True)
        (root / part / name).write_text(marker, encoding="utf-8")
    (root / "server_license.txt").write_text("license", encoding="utf-8")
    return root / "bin"


@pytest.mark.parametrize("path, expected", [
    (r"C:\Program Files\WindowsApps\Ibrahim.PFI_0.3.1.0_x64__ynbh\pgsql\bin",
     True),
    ("C:/Program Files/WindowsApps/Ibrahim.PFI_0.3.1.0_x64__ynbh/pgsql/bin",
     True),
    (r"C:\Users\me\AppData\Local\Programs\PFI\pgsql\bin", False),
    (r"C:\Users\me\Desktop\New folder\dist\PFI\pgsql\bin", False),
    ("/usr/lib/postgresql/16/bin", False),
])
def test_store_folder_is_detected(path, expected):
    assert in_store_package(Path(path)) is expected


def test_copy_is_made_once_and_reused(tmp_path):
    src_bin = fake_pgsql(tmp_path / "pkg-0.3.1" / "pgsql")
    data = tmp_path / "data"
    first = relocate_binaries(src_bin, data)
    assert first.parent.parent == data / "runtime"
    assert (first / "initdb.exe").read_text(encoding="utf-8") == "v1"
    assert (first.parent / "lib" / "plpgsql.dll").is_file()
    assert (first.parent / "share" / "postgres.bki").is_file()
    assert not (first.parent / "server_license.txt").exists()
    (first / "initdb.exe").write_text("touched", encoding="utf-8")
    assert relocate_binaries(src_bin, data) == first
    assert (first / "initdb.exe").read_text(encoding="utf-8") == "touched"


def test_new_app_version_replaces_the_old_copy(tmp_path):
    data = tmp_path / "data"
    old = relocate_binaries(fake_pgsql(tmp_path / "pkg-0.3.1" / "pgsql"),
                            data)
    new = relocate_binaries(
        fake_pgsql(tmp_path / "pkg-0.3.2" / "pgsql", "v2"), data)
    assert new != old and not old.parent.exists()
    assert (new / "initdb.exe").read_text(encoding="utf-8") == "v2"
    assert [p.name for p in (data / "runtime").iterdir()] == [new.parent.name]


def test_interrupted_copy_is_redone(tmp_path):
    src_bin = fake_pgsql(tmp_path / "pkg" / "pgsql")
    data = tmp_path / "data"
    dest = relocate_binaries(src_bin, data)
    (dest.parent / ".complete").unlink()
    (dest / "initdb.exe").unlink()
    again = relocate_binaries(src_bin, data)
    assert (again / "initdb.exe").is_file()
    assert (again.parent / ".complete").is_file()


def test_failed_copy_gives_a_clear_error(tmp_path, monkeypatch):
    src_bin = fake_pgsql(tmp_path / "pkg" / "pgsql")

    def no_space(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(pg_embedded.shutil, "copytree", no_space)
    with pytest.raises(RuntimeError, match="disk space"):
        relocate_binaries(src_bin, tmp_path / "data")
    assert not list((tmp_path / "data" / "runtime").glob("*.tmp"))


def test_embedded_postgres_uses_the_copy(tmp_path):
    src_bin = fake_pgsql(tmp_path / "pkg" / "pgsql")
    data = tmp_path / "data"
    plain = EmbeddedPostgres(src_bin, data, 5432)
    assert plain.bin_dir == src_bin
    moved = EmbeddedPostgres(src_bin, data, 5432, relocate=True)
    assert moved.bin_dir.is_relative_to(data / "runtime")
    assert Path(moved.tool("initdb")).parent == moved.bin_dir
