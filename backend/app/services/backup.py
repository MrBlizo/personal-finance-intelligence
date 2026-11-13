"""Backups of the SQLite database and the receipt attachments.

A backup is one file, ``pfi-<kind>-<YYYYmmdd-HHMMSS>.pfibak``: a ZIP archive
with ``manifest.json``, a consistent snapshot of ``pfi.sqlite`` and the
``attachments`` folder. With a backup password set, the whole archive is
encrypted (AES-256-GCM in 1 MiB chunks, key derived with scrypt), so a
copy in OneDrive or on a USB drive cannot be read without it.

Kinds: ``manual``, ``auto`` (weekly, the newest ``KEEP_AUTO`` are kept),
``pre-restore`` (written before every restore), ``move`` (for moving to
another PC) and ``uploaded``. Only automatic backups are ever deleted by
the app. Backups go to the folder chosen in Settings, or to
``<data_dir>/backups`` when none is chosen or it is unavailable.
``.dump`` files from PFI 0.3 are still listed, but since 0.5 they can only
be restored with PFI 0.4.0.
"""
import json
import logging
import os
import re
import shutil
import sqlite3
import struct
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .. import __version__
from . import secret_store

log = logging.getLogger(__name__)

KINDS = ("manual", "auto", "pre-restore", "uploaded", "move")
NAME_RE = re.compile(
    r"^pfi-(manual|auto|pre-restore|uploaded|move)-\d{8}-\d{6}(-\d+)?"
    r"\.(pfibak|dump)$")
KEEP_AUTO = 8
AUTO_EVERY = timedelta(days=7)
MAGIC = b"PFIENC1\0"
CHUNK = 1 << 20
SCRYPT_LOG_N = 15
MIN_PASSWORD = 8
CONFIG_FILE = "backup-settings.json"
SECRET_FILE = "backup-password"
DB_ENTRY = "pfi.sqlite"


class BackupError(RuntimeError):
    """Raised when a backup or restore fails."""


class PasswordError(BackupError):
    """Raised when an encrypted backup needs a (different) password."""


@dataclass
class BackupInfo:
    name: str
    kind: str
    size: int
    created: datetime
    folder: str
    encrypted: bool
    legacy: bool
    warning: str | None = None


@dataclass
class BackupConfig:
    folder: Path | None
    encrypt: bool
    has_password: bool


# --- settings ---------------------------------------------------------
def default_dir(data_dir: Path) -> Path:
    """Return (and create) the default backup folder in the data folder."""
    path = Path(data_dir) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _password(data_dir: Path) -> str | None:
    return secret_store.load(Path(data_dir) / SECRET_FILE)


def load_config(data_dir: Path) -> BackupConfig:
    """Return the backup folder and encryption settings.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    """
    path = Path(data_dir) / CONFIG_FILE
    raw = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("Ignoring unreadable %s", path)
    folder = raw.get("folder")
    has_pw = _password(data_dir) is not None
    return BackupConfig(Path(folder) if folder else None,
                        bool(raw.get("encrypt")) and has_pw, has_pw)


def _check_folder(folder: Path) -> str | None:
    """Return why ``folder`` cannot hold backups, or ``None`` if it can."""
    if not folder.is_dir():
        return f"The folder {folder} does not exist or is not connected."
    probe = folder / f".pfi-write-test-{os.getpid()}"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        return f"PFI cannot write to {folder} ({exc.strerror or exc})."
    return None


def save_config(data_dir: Path, folder: str | None, encrypt: bool,
                password: str | None = None,
                clear_password: bool = False) -> BackupConfig:
    """Store the backup folder and encryption choice.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    folder : str or None
        The folder for new backups; empty or ``None`` uses the default.
    encrypt : bool
        The flag to encrypt new backups with the saved password.
    password : str, optional
        The new backup password (at least ``MIN_PASSWORD`` characters).
    clear_password : bool
        The flag to forget the saved password (turns encryption off).

    Returns
    -------
    BackupConfig
        The settings now in effect.

    Raises
    ------
    BackupError
        If the folder is unusable or encryption lacks a password.
    """
    data_dir = Path(data_dir)
    target = Path(folder).expanduser() if folder and folder.strip() else None
    if target is not None:
        if not target.is_absolute():
            raise BackupError(
                f"'{folder}' is not a full folder path. Choose the folder "
                "with Browse, e.g. C:\\Users\\you\\OneDrive\\PFI backups.")
        problem = _check_folder(target)
        if problem:
            raise BackupError(problem + " Choose another folder or connect "
                              "the drive, then save again.")
    if password is not None:
        if len(password) < MIN_PASSWORD:
            raise BackupError(
                f"The backup password must have at least {MIN_PASSWORD} "
                "characters. Use a longer passphrase.")
        secret_store.save(data_dir / SECRET_FILE, password)
    if clear_password:
        secret_store.save(data_dir / SECRET_FILE, None)
        encrypt = False
    if encrypt and _password(data_dir) is None:
        raise BackupError(
            "Encryption needs a backup password. Enter one (at least "
            f"{MIN_PASSWORD} characters) and save again.")
    tmp = data_dir / (CONFIG_FILE + ".tmp")
    tmp.write_text(json.dumps({"folder": str(target) if target else None,
                               "encrypt": bool(encrypt)}), encoding="utf-8")
    os.replace(tmp, data_dir / CONFIG_FILE)
    return load_config(data_dir)


def target_dir(data_dir: Path) -> tuple[Path, str | None]:
    """Return the folder for a new backup and a warning if it fell back.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    """
    cfg = load_config(data_dir)
    if cfg.folder is not None:
        problem = _check_folder(cfg.folder)
        if problem is None:
            return cfg.folder, None
        return default_dir(data_dir), (
            f"{problem} The backup was saved in the app's own backup folder "
            "instead. Connect the drive or choose another folder in "
            "Settings.")
    return default_dir(data_dir), None


def _folders(data_dir: Path) -> list[Path]:
    out = [default_dir(data_dir)]
    cfg = load_config(data_dir)
    if cfg.folder is not None and cfg.folder.is_dir() \
            and cfg.folder.resolve() != out[0].resolve():
        out.append(cfg.folder)
    return out


# --- listing ---------------------------------------------------------
def is_encrypted(path: Path) -> bool:
    """Return whether ``path`` is an encrypted backup."""
    with open(path, "rb") as fh:
        return fh.read(len(MAGIC)) == MAGIC


def _info(path: Path, warning: str | None = None) -> BackupInfo:
    st = path.stat()
    kind = next(k for k in KINDS if path.name.startswith(f"pfi-{k}-"))
    legacy = path.suffix == ".dump"
    return BackupInfo(path.name, kind, st.st_size,
                      datetime.fromtimestamp(st.st_mtime), str(path.parent),
                      not legacy and is_encrypted(path), legacy, warning)


def list_backups(data_dir: Path) -> list[BackupInfo]:
    """Return all backups in the default and the chosen folder, newest first.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    """
    out = []
    for folder in _folders(data_dir):
        for f in folder.glob("pfi-*"):
            if NAME_RE.match(f.name) and f.is_file():
                out.append(_info(f))
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
    for folder in _folders(data_dir):
        if (folder / name).is_file():
            return folder / name
    raise BackupError(f"Backup '{name}' no longer exists.")


def new_path(folder: Path, kind: str, ext: str = "pfibak") -> Path:
    """Return a fresh, unused file name for a backup of ``kind``."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = Path(folder) / f"pfi-{kind}-{stamp}.{ext}"
    n = 1
    while path.exists():
        path = Path(folder) / f"pfi-{kind}-{stamp}-{n}.{ext}"
        n += 1
    return path


# --- encryption ---------------------------------------------------------
def _key(password: str, salt: bytes, log_n: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=1 << log_n, r=8, p=1).derive(
        password.encode("utf-8"))


def encrypt_file(src: Path, dst: Path, password: str) -> None:
    """Encrypt ``src`` into ``dst`` in authenticated 1 MiB chunks.

    Parameters
    ----------
    src : Path
        The plain file.
    dst : Path
        The encrypted file to write.
    password : str
        The backup password.
    """
    salt, prefix = os.urandom(16), os.urandom(8)
    aead = AESGCM(_key(password, salt, SCRYPT_LOG_N))
    size = Path(src).stat().st_size
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(MAGIC + salt + bytes([SCRYPT_LOG_N]) + prefix)
        index, done = 0, 0
        while True:
            chunk = fin.read(CHUNK)
            done += len(chunk)
            final = done >= size
            aad = MAGIC + struct.pack(">QB", index, final)
            ct = aead.encrypt(prefix + struct.pack(">I", index), chunk, aad)
            fout.write(struct.pack(">I", len(ct)) + ct)
            index += 1
            if final:
                break


def decrypt_file(src: Path, dst: Path, password: str) -> None:
    """Decrypt a file written by ``encrypt_file``.

    Raises
    ------
    PasswordError
        If the password is wrong or the file was altered or cut short.
    """
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        head = fin.read(len(MAGIC) + 16 + 1 + 8)
        if len(head) < len(MAGIC) + 25 or not head.startswith(MAGIC):
            raise BackupError("This is not an encrypted PFI backup.")
        salt = head[8:24]
        log_n, prefix = head[24], head[25:33]
        aead = AESGCM(_key(password, salt, log_n))
        index = 0
        while True:
            raw_len = fin.read(4)
            if len(raw_len) < 4:
                raise PasswordError(
                    "The backup file is incomplete (cut off). Copy it again "
                    "from where it was saved.")
            ct = fin.read(struct.unpack(">I", raw_len)[0])
            final = fin.peek(1)[:1] == b"" if hasattr(fin, "peek") \
                else not fin.read(0)
            aad = MAGIC + struct.pack(">QB", index, final)
            try:
                fout.write(aead.decrypt(prefix + struct.pack(">I", index),
                                        ct, aad))
            except InvalidTag as exc:
                raise PasswordError(
                    "The backup password is wrong, or the file was damaged. "
                    "Enter the password used when this backup was made."
                ) from exc
            index += 1
            if final:
                return


# --- writing ---------------------------------------------------------
def _snapshot(db_path: Path, out: Path) -> None:
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(out)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def write_archive(db_path: Path, attachments: Path, out: Path,
                  password: str | None) -> None:
    """Write a backup of the database and attachments to ``out``.

    Parameters
    ----------
    db_path : Path
        The live SQLite database.
    attachments : Path
        The attachments folder (may not exist).
    out : Path
        The backup file to create.
    password : str or None
        The password to encrypt with; ``None`` writes a plain ZIP.
    """
    with tempfile.TemporaryDirectory(prefix="pfi-bak-") as tmp:
        snap = Path(tmp) / DB_ENTRY
        _snapshot(db_path, snap)
        archive = Path(tmp) / "backup.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({
                "app": "Personal Finance Intelligence", "format": 1,
                "version": __version__,
                "created": datetime.now().isoformat(timespec="seconds")}))
            zf.write(snap, DB_ENTRY)
            if attachments.is_dir():
                for f in sorted(attachments.rglob("*")):
                    if f.is_file():
                        zf.write(f, "attachments/" + f.relative_to(
                            attachments).as_posix())
        part = out.with_name(out.name + ".part")
        if password:
            encrypt_file(archive, part, password)
        else:
            shutil.copyfile(archive, part)
        os.replace(part, out)


def create_backup(data_dir: Path, db_path: Path, kind: str = "manual",
                  folder: Path | None = None) -> BackupInfo:
    """Back up the database and attachments and describe the result.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    db_path : Path
        The live SQLite database.
    kind : str
        The backup kind, one of ``KINDS``.
    folder : Path, optional
        The folder to write to; by default the chosen backup folder.

    Returns
    -------
    BackupInfo
        The new backup; ``warning`` is set if the chosen folder was
        unavailable and the default folder was used.

    Raises
    ------
    BackupError
        If the file cannot be written.
    """
    warning = None
    if folder is None:
        folder, warning = target_dir(data_dir)
    cfg = load_config(data_dir)
    path = new_path(folder, kind)
    try:
        write_archive(db_path, Path(data_dir) / "attachments", path,
                      _password(data_dir) if cfg.encrypt else None)
    except (OSError, sqlite3.Error) as exc:
        raise BackupError(
            f"The backup could not be written to {folder}: {exc}. Make sure "
            "there is enough free disk space.") from exc
    log.info("Backup written: %s", path)
    return _info(path, warning)


# --- restoring ---------------------------------------------------------
def _extract(path: Path, work: Path, password: str | None,
             data_dir: Path) -> tuple[Path, Path]:
    """Unpack a ``.pfibak`` into ``work`` and check it; return db + files."""
    archive = path
    if is_encrypted(path):
        candidates = [p for p in (password, _password(data_dir)) if p]
        if not candidates:
            raise PasswordError(
                "This backup is protected with a password. Enter the "
                "password used when it was made.")
        archive = work / "backup.zip"
        for i, pw in enumerate(candidates):
            try:
                decrypt_file(path, archive, pw)
                break
            except PasswordError:
                if i == len(candidates) - 1:
                    raise
    try:
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            if DB_ENTRY not in names or "manifest.json" not in names:
                raise BackupError(
                    "This file is not a PFI backup (no database inside). "
                    "Choose a file made with 'Back up now'.")
            for name in names:
                target = (work / "out" / name).resolve()
                if not str(target).startswith(str((work / "out").resolve())):
                    raise BackupError("The backup contains unsafe paths.")
            zf.extractall(work / "out")
    except zipfile.BadZipFile as exc:
        raise BackupError(
            "This file is not a PFI backup or it is damaged. Choose a file "
            "made with 'Back up now'.") from exc
    db = work / "out" / DB_ENTRY
    _check_sqlite(db)
    return db, work / "out" / "attachments"


def _check_sqlite(db: Path) -> None:
    try:
        con = sqlite3.connect(db)
        try:
            ok = con.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise BackupError(f"The database in the backup is damaged: {exc}."
                          ) from exc
    if ok != "ok" or "transactions" not in tables:
        raise BackupError(
            "The database in the backup is damaged or not from PFI. Choose "
            "another backup.")


def install_database(new_db: Path, new_files: Path | None, db_path: Path,
                     data_dir: Path, engine=None) -> None:
    """Replace the live database (and attachments) with restored copies.

    Parameters
    ----------
    new_db : Path
        The checked SQLite file to put in place.
    new_files : Path or None
        The restored attachments folder.
    db_path : Path
        The live database file.
    data_dir : Path
        The application data directory.
    engine : Engine, optional
        The application engine; its connections are closed first.
    """
    if engine is not None:
        engine.dispose()
    staged = db_path.with_name(db_path.name + ".restore")
    try:
        shutil.copyfile(new_db, staged)
        for extra in (Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
            extra.unlink(missing_ok=True)
        os.replace(staged, db_path)
    except OSError as exc:
        staged.unlink(missing_ok=True)
        raise BackupError(
            f"The database file could not be replaced ({exc}). Your data "
            "was not changed. Close other programs that may use the PFI "
            "folder (e.g. a virus scan), restart PFI and try again.") from exc
    live = Path(data_dir) / "attachments"
    old = Path(data_dir) / "attachments.old"
    shutil.rmtree(old, ignore_errors=True)
    try:
        if live.exists():
            live.rename(old)
        if new_files is not None and new_files.is_dir():
            shutil.copytree(new_files, live)
    except OSError as exc:
        shutil.rmtree(live, ignore_errors=True)
        if old.exists():
            old.rename(live)
        raise BackupError(
            f"The data was restored, but the receipts could not be copied "
            f"({exc}). The previous receipts were kept. Restore again after "
            "restarting PFI.") from exc
    shutil.rmtree(old, ignore_errors=True)


def restore_backup(data_dir: Path, db_path: Path, path: Path, engine,
                   password: str | None = None) -> BackupInfo:
    """Replace the data with backup ``path``; a safety backup comes first.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    db_path : Path
        The live SQLite database.
    path : Path
        The ``.pfibak`` file to restore.
    engine : Engine
        The application engine; its pooled connections are closed.
    password : str, optional
        The password of an encrypted backup.

    Returns
    -------
    BackupInfo
        The safety backup taken before restoring.

    Raises
    ------
    BackupError
        If the backup is unreadable, damaged, needs a password or is a 0.3
        ``.dump`` file; nothing is changed in that case.
    """
    from ..legacy import DUMP_MESSAGE
    if path.suffix == ".dump":
        raise BackupError(DUMP_MESSAGE)
    data_dir = Path(data_dir)
    with tempfile.TemporaryDirectory(prefix="pfi-restore-",
                                     dir=data_dir) as tmp:
        work = Path(tmp)
        new_db, files = _extract(path, work, password, data_dir)
        safety = create_backup(data_dir, db_path, "pre-restore",
                               default_dir(data_dir))
        install_database(new_db, files, db_path, data_dir, engine)
    log.info("Restored %s (safety backup %s)", path.name, safety.name)
    return safety


def auto_backup_if_due(data_dir: Path, db_path: Path,
                       now: datetime | None = None) -> BackupInfo | None:
    """Create a weekly automatic backup and prune old automatic ones.

    Parameters
    ----------
    data_dir : Path
        The application data directory.
    db_path : Path
        The live SQLite database.
    now : datetime, optional
        The reference time (defaults to now).

    Returns
    -------
    BackupInfo or None
        The new backup, or ``None`` if none was due.
    """
    now = now or datetime.now()
    autos = [b for b in list_backups(data_dir)
             if b.kind == "auto" and not b.legacy]
    made = None
    if not autos or now - autos[0].created >= AUTO_EVERY:
        made = create_backup(data_dir, db_path, "auto")
        autos.insert(0, made)
    for old in autos[KEEP_AUTO:]:
        (Path(old.folder) / old.name).unlink(missing_ok=True)
    return made
