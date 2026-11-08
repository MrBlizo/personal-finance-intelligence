"""Database backups with the bundled pg_dump / pg_restore.

Backups are PostgreSQL custom-format dumps in ``<data_dir>/backups``:
``pfi-<kind>-<YYYYmmdd-HHMMSS>.dump`` with kind ``manual``, ``auto``
(weekly, the newest ``KEEP_AUTO`` are kept), ``pre-restore`` (taken
automatically before every restore) or ``uploaded``. Only automatic backups
are ever deleted by the app.
"""
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ..pg_embedded import NO_WINDOW, EmbeddedPostgres

log = logging.getLogger(__name__)
NAME_RE = re.compile(
    r"^pfi-(manual|auto|pre-restore|uploaded)-\d{8}-\d{6}(-\d+)?\.dump$")
KEEP_AUTO = 8
AUTO_EVERY = timedelta(days=7)


class BackupError(RuntimeError):
    """Raised when a backup or restore fails."""


@dataclass
class BackupInfo:
    name: str
    kind: str
    size: int
    created: datetime


def backup_dir(data_dir: Path) -> Path:
    """Return (and create) the folder that holds backups."""
    path = Path(data_dir) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_backups(data_dir: Path) -> list[BackupInfo]:
    """Return all backups, newest first.

    Parameters
    ----------
    data_dir : Path
        The application data directory.

    Returns
    -------
    list of BackupInfo
        The backups found in the backup folder.
    """
    out = []
    for f in backup_dir(data_dir).glob("pfi-*.dump"):
        if NAME_RE.match(f.name):
            st = f.stat()
            out.append(BackupInfo(f.name, f.name.split("-")[1]
                                  if not f.name.startswith("pfi-pre-restore")
                                  else "pre-restore", st.st_size,
                                  datetime.fromtimestamp(st.st_mtime)))
    return sorted(out, key=lambda b: b.created, reverse=True)


def resolve(data_dir: Path, name: str) -> Path:
    """Return the path of backup ``name`` after validating the name.

    Raises
    ------
    BackupError
        If the name is malformed or the file does not exist.
    """
    if not NAME_RE.match(name):
        raise BackupError(
            f"'{name}' is not a valid backup name. Choose a backup from the "
            "list in Settings.")
    path = backup_dir(data_dir) / name
    if not path.is_file():
        raise BackupError(f"Backup '{name}' no longer exists.")
    return path


def new_path(data_dir: Path, kind: str) -> Path:
    """Return a fresh, unused file name for a backup of ``kind``."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = backup_dir(data_dir) / f"pfi-{kind}-{stamp}.dump"
    n = 1
    while path.exists():
        path = backup_dir(data_dir) / f"pfi-{kind}-{stamp}-{n}.dump"
        n += 1
    return path


def _run(args: list[str], pg: EmbeddedPostgres, what: str) -> None:
    result = subprocess.run(args, env=pg.client_env(), capture_output=True,
                            text=True, creationflags=NO_WINDOW)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-800:]
        raise BackupError(
            f"{what} failed: {detail or 'no output'}. Make sure there is "
            "enough free disk space and that the file is a PFI backup.")


def create_backup(pg: EmbeddedPostgres, data_dir: Path,
                  kind: str = "manual") -> BackupInfo:
    """Write a full database dump and return its description.

    Parameters
    ----------
    pg : EmbeddedPostgres
        The running embedded cluster.
    data_dir : Path
        The application data directory.
    kind : str
        The backup kind: ``manual``, ``auto`` or ``pre-restore``.

    Returns
    -------
    BackupInfo
        The created backup.
    """
    path = new_path(data_dir, kind)
    _run([pg.tool("pg_dump"), "--format=custom", "--no-owner",
          f"--file={path}"], pg, "Backup")
    st = path.stat()
    log.info("Backup written: %s (%s bytes)", path, st.st_size)
    return BackupInfo(path.name, kind, st.st_size,
                      datetime.fromtimestamp(st.st_mtime))


def restore_backup(pg: EmbeddedPostgres, data_dir: Path, path: Path,
                   engine) -> BackupInfo:
    """Replace the database content with ``path``.

    A ``pre-restore`` backup of the current data is written first, so a
    restore can always be undone.

    Parameters
    ----------
    pg : EmbeddedPostgres
        The running embedded cluster.
    data_dir : Path
        The application data directory.
    path : Path
        The dump file to restore.
    engine : Engine
        The application engine; its pooled connections are closed first.

    Returns
    -------
    BackupInfo
        The safety backup taken before restoring.
    """
    safety = create_backup(pg, data_dir, "pre-restore")
    engine.dispose()
    _run([pg.tool("pg_restore"), "--clean", "--if-exists", "--no-owner",
          "--single-transaction", f"--dbname={pg.client_env()['PGDATABASE']}",
          str(path)], pg, "Restore")
    log.info("Restored %s (safety backup %s)", path.name, safety.name)
    return safety


def auto_backup_if_due(pg: EmbeddedPostgres, data_dir: Path,
                       now: datetime | None = None) -> BackupInfo | None:
    """Create a weekly automatic backup and prune old automatic ones.

    Parameters
    ----------
    pg : EmbeddedPostgres
        The running embedded cluster.
    data_dir : Path
        The application data directory.
    now : datetime, optional
        The reference time (defaults to now).

    Returns
    -------
    BackupInfo or None
        The new backup, or ``None`` if none was due.
    """
    now = now or datetime.now()
    autos = [b for b in list_backups(data_dir) if b.kind == "auto"]
    made = None
    if not autos or now - autos[0].created >= AUTO_EVERY:
        made = create_backup(pg, data_dir, "auto")
        autos.insert(0, made)
    for old in autos[KEEP_AUTO:]:
        (backup_dir(data_dir) / old.name).unlink(missing_ok=True)
    return made
