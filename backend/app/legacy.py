"""What is left from the PostgreSQL era (0.1-0.3).

Up to 0.3 the app ran a private PostgreSQL cluster in ``<data_dir>/pgdata``
and wrote ``pg_dump`` backups (``.dump``). Version 0.4 moved that data into
SQLite on its first start and kept the old cluster as ``pgdata-0.3``.
Since 0.5 PostgreSQL is no longer bundled, so this module only

* detects a cluster that was never moved (``has_cluster``): the app then
  refuses to start with an empty database and points to PFI 0.4.0, which
  can still move it;
* lists and removes what 0.4 left behind (``leftovers`` and
  ``remove_leftovers``), when the user asks for it in Settings.
"""
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)
RETIRED = "pgdata-0.3"
CONVERTER_URL = ("https://github.com/MrBlizo/personal-finance-intelligence/"
                 "releases/tag/v0.4.0")
UNMOVED_MESSAGE = (
    "This PC still has data from PFI 0.3 that was never moved to the new "
    "format. PFI 0.5 can no longer read it. Install PFI 0.4.0 once "
    f"({CONVERTER_URL}), open it so it moves your data, then install the "
    "current version again. Your data has not been changed.")
DUMP_MESSAGE = (
    "This is a backup from PFI 0.3 (.dump). PFI 0.5 can no longer read it. "
    f"Install PFI 0.4.0 ({CONVERTER_URL}), restore the backup there, then "
    "update again.")


def has_cluster(data_dir: Path) -> bool:
    """Return whether ``data_dir`` holds a 0.3 cluster that was not moved.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    """
    return (Path(data_dir) / "pgdata" / "PG_VERSION").is_file()


@dataclass
class Leftovers:
    """The files 0.4 left after moving the data to SQLite.

    Attributes
    ----------
    paths : list of Path
        The folders and files that can be removed.
    size : int
        The total size in bytes.
    dumps : list of Path
        The old ``.dump`` backups, removed only on request.
    dump_size : int
        The total size of ``dumps`` in bytes.
    """

    paths: list[Path] = field(default_factory=list)
    size: int = 0
    dumps: list[Path] = field(default_factory=list)
    dump_size: int = 0


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def leftovers(data_dir: Path, backup_dirs: list[Path] = ()) -> Leftovers:
    """Find the 0.3 files that are no longer used.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    backup_dirs : list of Path, optional
        The backup folders searched for ``.dump`` files.

    Returns
    -------
    Leftovers
        The removable files. A cluster that was never moved (``pgdata``)
        is never included.
    """
    data_dir = Path(data_dir)
    found = Leftovers()
    for name in (RETIRED, "runtime", "pg_secret", "logs/postgres-server.log",
                 "logs/postgres-tools.log"):
        path = data_dir / name
        if path.exists():
            found.paths.append(path)
            found.size += _size(path)
    seen = set()
    for folder in backup_dirs:
        for dump in sorted(Path(folder).glob("pfi-*.dump")):
            if dump.resolve() not in seen:
                seen.add(dump.resolve())
                found.dumps.append(dump)
                found.dump_size += dump.stat().st_size
    return found


def remove_leftovers(data_dir: Path, backup_dirs: list[Path] = (),
                     dumps: bool = False) -> int:
    """Delete the unused 0.3 files and return the bytes freed.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    backup_dirs : list of Path, optional
        The backup folders searched for ``.dump`` files.
    dumps : bool, optional
        The flag to also delete old ``.dump`` backups (default ``False``).

    Returns
    -------
    int
        The number of bytes removed.

    Raises
    ------
    OSError
        If a file is locked; whatever was removed before stays removed and
        the call can simply be repeated.
    """
    found = leftovers(data_dir, backup_dirs)
    targets = found.paths + (found.dumps if dumps else [])
    freed = found.size + (found.dump_size if dumps else 0)
    for path in targets:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        log.info("Removed old 0.3 data: %s", path)
    return freed
