"""Sync PFI between devices through a folder in the user's cloud drive.

See ``design/sync-protocol.md`` for the file format. In short: every device
writes numbered, encrypted change files into ``changes/<device-id>/`` of a
shared folder (OneDrive, Dropbox, Google Drive) and applies the files the
other devices wrote. Rows are identified by ``uid``; foreign keys travel as
the uid of the referenced row; the later ``updated_at`` wins; deletions are
sent as tombstones; rows created twice under the same natural key (an
account name, a category, a budget month) are merged.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import logging
import os
import re
import secrets
import socket
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..db import Base
from . import secret_store

log = logging.getLogger(__name__)

FORMAT = 1
MAGIC = b"PFS1"
MANIFEST = "pfi-sync.json"
KEY_FILE = "sync.key"
PBKDF2_ITERATIONS = 600_000
CHUNK = 2000
CHECK_TEXT = "PFI-SYNC"
#: Synced tables that are not exchanged in format 1 (receipt files).
EXCLUDED = frozenset({"attachments"})
_SEQ_RE = re.compile(r"^(\d{8})\.pfisync$")
_DEVICE_RE = re.compile(r"^[0-9a-f]{16}$")
_lock = threading.Lock()


class SyncError(Exception):
    """A sync problem the user can act on (folder, passphrase, setup)."""


class _Missing(Exception):
    """A foreign key points to a row this device does not have yet."""


# --- crypto -----------------------------------------------------------
def derive_key(passphrase: str, salt: bytes,
               iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """Derive the 32-byte sync key from the passphrase (PBKDF2-SHA256).

    Parameters
    ----------
    passphrase : str
        The sync passphrase, the same on every device.
    salt : bytes
        The random salt from the folder's manifest.
    iterations : int
        The PBKDF2 iteration count from the manifest.
    """
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt,
                               iterations, dklen=32)


def seal(key: bytes, aad: str, payload: dict) -> bytes:
    """Encrypt ``payload`` into the bytes of a change file.

    Parameters
    ----------
    key : bytes
        The 32-byte sync key.
    aad : str
        The file's ``<device-id>/<number>`` name, bound to the ciphertext.
    payload : dict
        The JSON document to encrypt.
    """
    raw = gzip.compress(json.dumps(payload, ensure_ascii=False,
                                   separators=(",", ":")).encode("utf-8"))
    nonce = secrets.token_bytes(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, raw, aad.encode())


def unseal(key: bytes, aad: str, data: bytes) -> dict:
    """Decrypt the bytes of a change file.

    Parameters
    ----------
    key : bytes
        The 32-byte sync key.
    aad : str
        The file's ``<device-id>/<number>`` name.
    data : bytes
        The file content.

    Raises
    ------
    SyncError
        If the file is not a PFI change file or the key does not match.
    """
    if data[:4] != MAGIC or len(data) < 4 + 12 + 16:
        raise SyncError(f"{aad} is not a PFI sync file.")
    try:
        raw = AESGCM(key).decrypt(data[4:16], data[16:], aad.encode())
    except InvalidTag:
        raise SyncError(
            f"{aad} could not be decrypted: it was written with another "
            "sync passphrase or is damaged. Set up sync again with the "
            "passphrase used on your other devices.") from None
    return json.loads(gzip.decompress(raw).decode("utf-8"))


# --- folder -----------------------------------------------------------
class FolderStore:
    """The shared sync folder on disk (inside a cloud-drive folder).

    Parameters
    ----------
    root : Path
        The sync folder, for example ``OneDrive/Apps/PFI Sync``.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def read_manifest(self) -> dict | None:
        """Return the folder's manifest, or ``None`` for a new folder."""
        path = self.root / MANIFEST
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SyncError(
                f"{path} cannot be read ({exc}). If your cloud drive is "
                "still downloading it, wait a moment and try again.") from exc

    def write_manifest(self, manifest: dict) -> None:
        """Create the manifest of a new sync folder.

        Parameters
        ----------
        manifest : dict
            The manifest document.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        self._atomic(self.root / MANIFEST,
                     json.dumps(manifest, indent=1).encode("utf-8"))

    def devices(self) -> list[str]:
        """Return the ids of the devices that wrote change files."""
        base = self.root / "changes"
        if not base.is_dir():
            return []
        return sorted(p.name for p in base.iterdir()
                      if p.is_dir() and _DEVICE_RE.match(p.name))

    def numbers(self, device: str) -> list[int]:
        """Return the file numbers a device wrote, in order.

        Parameters
        ----------
        device : str
            The device id.
        """
        folder = self.root / "changes" / device
        if not folder.is_dir():
            return []
        found = (_SEQ_RE.match(p.name) for p in folder.iterdir())
        return sorted(int(m[1]) for m in found if m)

    def read(self, device: str, number: int) -> bytes:
        """Return the bytes of one change file.

        Parameters
        ----------
        device : str
            The device id.
        number : int
            The file number.
        """
        return (self.root / "changes" / device
                / f"{number:08d}.pfisync").read_bytes()

    def write(self, device: str, number: int, data: bytes) -> None:
        """Write one change file (never overwrites an existing one).

        Parameters
        ----------
        device : str
            The device id of this device.
        number : int
            The next file number of this device.
        data : bytes
            The encrypted file content.
        """
        path = self.root / "changes" / device / f"{number:08d}.pfisync"
        if path.exists():
            raise SyncError(
                f"{path} already exists. Another installation uses the "
                "same device id; set up sync again on this device.")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic(path, data)

    @staticmethod
    def _atomic(path: Path, data: bytes) -> None:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)


# --- schema helpers ---------------------------------------------------
def _aad(device: str, number: int) -> str:
    return f"{device}/{number:08d}"


def sync_tables() -> list[str]:
    """Return the exchanged tables, parents before children."""
    synced = set(models.SYNCED_TABLES) - EXCLUDED
    return [t.name for t in Base.metadata.sorted_tables if t.name in synced]


def _fks(table: str) -> dict[str, tuple[str, str] | None]:
    """Map foreign-key columns to (table, column) or None if not synced."""
    synced = set(models.SYNCED_TABLES) - EXCLUDED
    out: dict[str, tuple[str, str] | None] = {}
    for fk in Base.metadata.tables[table].foreign_keys:
        ref = fk.column.table.name
        out[fk.parent.name] = (ref, fk.column.name) if ref in synced else None
    return out


def _has_id(table: str) -> bool:
    return [c.name for c in Base.metadata.tables[table].primary_key] == ["id"]


def _columns(conn: Connection, table: str) -> list[str]:
    have = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
    skip = {"uid", "updated_at"} | ({"id"} if _has_id(table) else set())
    return [c.name for c in Base.metadata.tables[table].columns
            if c.name in have and c.name not in skip]


def _unique_keys(table: str) -> list[tuple[str, ...]]:
    """Natural keys used to merge rows created on two devices."""
    from sqlalchemy import UniqueConstraint
    tbl = Base.metadata.tables[table]
    keys: list[tuple[str, ...]] = []
    for con in tbl.constraints:
        if isinstance(con, UniqueConstraint):
            keys.append(tuple(c.name for c in con.columns))
    keys += [(c.name,) for c in tbl.columns if c.unique]
    keys += [tuple(c.name for c in i.columns) for i in tbl.indexes
             if i.unique]
    if not _has_id(table):
        keys.append(tuple(c.name for c in tbl.primary_key))
    seen: list[tuple[str, ...]] = []
    for k in keys:
        if k and k not in seen and "uid" not in k:
            seen.append(k)
    return seen


def norm_time(value: str | None) -> str:
    """Return a sortable form of a stored time (fraction padded to 6).

    Parameters
    ----------
    value : str or None
        A ``YYYY-MM-DD HH:MM:SS[.ffffff]`` time as SQLite stores it.
    """
    if not value:
        return ""
    s = str(value).replace("T", " ")
    s = re.sub(r"(\+00:00|Z)$", "", s)
    head, _, frac = s.partition(".")
    return f"{head[:19]}.{(frac + '000000')[:6]}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# --- state ------------------------------------------------------------
def _get(conn: Connection, key: str, default: str | None = None
         ) -> str | None:
    v = conn.execute(text("SELECT value FROM sync_state WHERE key = :k"),
                     {"k": key}).scalar()
    return default if v is None else v


def _set(conn: Connection, key: str, value: str | None) -> None:
    if value is None:
        conn.execute(text("DELETE FROM sync_state WHERE key = :k"),
                     {"k": key})
        return
    conn.execute(text(
        "INSERT INTO sync_state (key, value) VALUES (:k, :v) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"),
        {"k": key, "v": value})


def _seen(conn: Connection, table: str, uid: str, u: str) -> None:
    conn.execute(text(
        "INSERT INTO sync_seen (table_name, uid, u) VALUES (:t, :id, :u) "
        "ON CONFLICT(table_name, uid) DO UPDATE SET u = excluded.u"),
        {"t": table, "id": uid, "u": u})


def _key_path(data_dir: Path) -> Path:
    return Path(data_dir) / KEY_FILE


def _load_key(data_dir: Path) -> bytes | None:
    raw = secret_store.load(_key_path(data_dir))
    return base64.b64decode(raw) if raw else None


@dataclass
class SyncStatus:
    """What the Settings page shows about sync."""

    enabled: bool
    folder: str | None = None
    device_id: str | None = None
    device_name: str | None = None
    last_sync: str | None = None
    last_error: str | None = None
    sent: int = 0
    received: int = 0
    pending: int = 0
    devices: list[dict] = field(default_factory=list)


def status(db: Session, data_dir: Path) -> SyncStatus:
    """Return the sync settings and the result of the last run.

    Parameters
    ----------
    db : Session
        The open database session.
    data_dir : Path
        The application data folder (holds the protected sync key).
    """
    conn = db.connection()
    enabled = _get(conn, "enabled") == "1" and _load_key(data_dir) is not None
    last = json.loads(_get(conn, "last_result", "{}") or "{}")
    me = _get(conn, "device_id")
    devices = []
    for row in conn.execute(text(
            "SELECT key, value FROM sync_state WHERE key LIKE 'device:%'")):
        info = json.loads(row.value)
        dev = row.key.split(":", 1)[1]
        if dev != me:
            devices.append({"id": dev, **info})
    pending = conn.execute(text("SELECT count(*) FROM sync_pending")).scalar()
    return SyncStatus(
        enabled=enabled, folder=_get(conn, "folder"), device_id=me,
        device_name=_get(conn, "device_name"),
        last_sync=last.get("at"), last_error=last.get("error"),
        sent=last.get("sent", 0), received=last.get("received", 0),
        pending=pending or 0,
        devices=sorted(devices, key=lambda d: d.get("seen", ""),
                       reverse=True))


def suggest_folders() -> list[dict]:
    """Return likely cloud-drive sync folders on this PC."""
    home = Path.home()
    found: list[dict] = []
    for env, label in (("OneDrive", "OneDrive"),
                       ("OneDriveConsumer", "OneDrive"),
                       ("OneDriveCommercial", "OneDrive (work)")):
        root = os.environ.get(env)
        if root and Path(root).is_dir():
            found.append({"provider": label, "path": str(
                Path(root) / "Apps" / "PFI Sync")})
    for root in (home / "Dropbox",):
        if root.is_dir():
            found.append({"provider": "Dropbox",
                          "path": str(root / "Apps" / "PFI Sync")})
    for root in (Path("G:/My Drive"), home / "Google Drive" / "My Drive"):
        if root.is_dir():
            found.append({"provider": "Google Drive",
                          "path": str(root / "PFI Sync")})
    unique: dict[str, dict] = {}
    for f in found:
        unique.setdefault(f["path"], f)
    return list(unique.values())


def folder_identity(manifest: dict) -> str:
    """Return what identifies one sync folder: its key-derivation salt.

    Parameters
    ----------
    manifest : dict
        The folder's manifest.
    """
    return str(manifest.get("kdf", {}).get("salt", ""))


def _forget_folder(conn: Connection) -> None:
    """Forget what was sent to and received from the previous folder."""
    for table in ("sync_seen", "sync_aliases", "sync_pending"):
        conn.execute(text(f"DELETE FROM {table}"))
    conn.execute(text(
        "DELETE FROM sync_state WHERE key LIKE 'applied:%' "
        "OR key LIKE 'device:%' OR key IN ('next_seq', 'device_id')"))


def _resend_all(conn: Connection) -> None:
    """Send everything again (this device's files left the folder)."""
    conn.execute(text("DELETE FROM sync_seen"))
    _set(conn, "next_seq", "1")


def phone_can_find(folder: str | None) -> bool:
    """Return whether the phone app looks in this folder.

    The phone reaches the cloud drive through its web API and always uses
    ``Apps/PFI Sync`` at the top of the drive.

    Parameters
    ----------
    folder : str or None
        The sync folder on this PC.
    """
    if not folder:
        return False
    parts = [x.lower() for x in re.split(r"[\\/]+", folder) if x]
    return len(parts) >= 3 and parts[-2:] == ["apps", "pfi sync"] and any(
        "onedrive" in x or "dropbox" in x for x in parts[:-2])


# --- setup ------------------------------------------------------------
def setup(db: Session, data_dir: Path, folder: str, passphrase: str,
          device_name: str | None = None) -> SyncStatus:
    """Start syncing with ``folder`` (create it or join it).

    A new folder gets a manifest protected by ``passphrase``; an existing
    one is joined when the passphrase matches. The derived key is kept in
    the data folder (protected with DPAPI on Windows).

    Parameters
    ----------
    db : Session
        The open database session.
    data_dir : Path
        The application data folder.
    folder : str
        The sync folder, inside a folder your cloud drive keeps in sync.
    passphrase : str
        The sync passphrase (at least 8 characters), the same everywhere.
    device_name : str, optional
        The name other devices show for this PC.

    Raises
    ------
    SyncError
        If the folder cannot be used or the passphrase does not match.
    """
    if len(passphrase or "") < 8:
        raise SyncError("Choose a sync passphrase of at least 8 characters.")
    root = Path(folder).expanduser()
    if not root.is_absolute():
        raise SyncError("Choose the full path of a folder, e.g. "
                        r"C:\Users\you\OneDrive\Apps\PFI Sync.")
    store = FolderStore(root)
    try:
        manifest = store.read_manifest()
        if manifest is None:
            salt = secrets.token_bytes(16)
            key = derive_key(passphrase, salt, PBKDF2_ITERATIONS)
            manifest = {
                "app": "PFI", "format": FORMAT,
                "kdf": {"alg": "pbkdf2-sha256",
                        "iterations": PBKDF2_ITERATIONS,
                        "salt": base64.b64encode(salt).decode()},
                "check": base64.b64encode(
                    seal(key, "check", {"check": CHECK_TEXT})).decode()}
            store.write_manifest(manifest)
        else:
            if manifest.get("app") != "PFI" or "kdf" not in manifest:
                raise SyncError(f"{root / MANIFEST} is not a PFI sync folder.")
            if int(manifest.get("format", 0)) > FORMAT:
                raise SyncError(
                    "This sync folder was created by a newer version of "
                    "PFI. Update PFI on this PC first.")
            kdf = manifest["kdf"]
            key = derive_key(passphrase, base64.b64decode(kdf["salt"]),
                             int(kdf["iterations"]))
            try:
                ok = unseal(key, "check", base64.b64decode(
                    manifest["check"])).get("check") == CHECK_TEXT
            except SyncError:
                ok = False
            if not ok:
                raise SyncError(
                    "The passphrase does not match the one used to create "
                    "this sync folder. Enter the passphrase from your "
                    "other device.")
    except OSError as exc:
        raise SyncError(
            f"{root} cannot be used ({exc.strerror or exc}). Choose a "
            "folder you can write to, inside your OneDrive, Dropbox or "
            "Google Drive folder.") from exc
    conn = db.connection()
    folder_id = folder_identity(manifest)
    if (_get(conn, "folder") != str(root)
            or _get(conn, "folder_id") != folder_id):
        _forget_folder(conn)
    _set(conn, "folder_id", folder_id)
    if not _get(conn, "device_id"):
        _set(conn, "device_id", secrets.token_hex(8))
    _set(conn, "device_name", (device_name or socket.gethostname())[:60])
    _set(conn, "folder", str(root))
    _set(conn, "enabled", "1")
    secret_store.save(_key_path(data_dir), base64.b64encode(key).decode())
    db.commit()
    return status(db, data_dir)


def disable(db: Session, data_dir: Path) -> SyncStatus:
    """Stop syncing on this device (the shared folder is left as it is).

    Parameters
    ----------
    db : Session
        The open database session.
    data_dir : Path
        The application data folder.
    """
    _set(db.connection(), "enabled", "0")
    secret_store.save(_key_path(data_dir), None)
    db.commit()
    return status(db, data_dir)


# --- export -----------------------------------------------------------
class _UidMap:
    """Translate local ids to uids and back, cached per run."""

    def __init__(self, conn: Connection):
        self.conn = conn
        self._to_uid: dict[tuple[str, str], dict] = {}

    def uid_of(self, table: str, col: str, value) -> str | None:
        if value is None:
            return None
        cache = self._to_uid.get((table, col))
        if cache is None:
            cache = dict(self.conn.execute(text(
                f"SELECT {col}, uid FROM {table}")).all())
            self._to_uid[(table, col)] = cache
        return cache.get(value)

    def local_of(self, table: str, col: str, uid: str):
        found = _resolve(self.conn, table, uid)
        if found is None:
            raise _Missing(f"{table}:{uid}")
        return self.conn.execute(text(
            f"SELECT {col} FROM {table} WHERE rowid = :r"),
            {"r": found[0]}).scalar()

    def forget(self, table: str) -> None:
        for k in [k for k in self._to_uid if k[0] == table]:
            del self._to_uid[k]


def collect_changes(conn: Connection) -> list[dict]:
    """Return the local changes the other devices have not received.

    Parameters
    ----------
    conn : Connection
        The open database connection.
    """
    ids = _UidMap(conn)
    out: list[dict] = []
    tables = sync_tables()
    for table in tables:
        cols = _columns(conn, table)
        fks = _fks(table)
        rows = conn.execute(text(
            f"SELECT t.* FROM {table} t LEFT JOIN sync_seen s "
            f"ON s.table_name = :t AND s.uid = t.uid "
            f"WHERE t.uid IS NOT NULL AND t.updated_at IS NOT NULL AND "
            f"(s.u IS NULL OR s.u <> CAST(t.updated_at AS TEXT)) "
            f"ORDER BY t.rowid"), {"t": table}).mappings().all()
        for r in rows:
            row = {}
            for c in cols:
                v = r[c]
                if c in fks:
                    ref = fks[c]
                    v = None if ref is None else ids.uid_of(*ref, v)
                if isinstance(v, bytes):
                    raise SyncError(f"{table}.{c} holds binary data, which "
                                    "sync format 1 cannot send.")
                row[c] = v
            out.append({"t": table, "uid": r["uid"],
                        "u": str(r["updated_at"]), "row": row})
    synced = set(tables)
    rows = conn.execute(text(
        "SELECT d.table_name, d.uid, max(d.deleted_at) AS deleted_at "
        "FROM sync_tombstones d LEFT JOIN sync_seen s "
        "ON s.table_name = d.table_name AND s.uid = d.uid "
        "GROUP BY d.table_name, d.uid "
        "HAVING max(s.u) IS NULL OR max(s.u) <> 'del:' || max(d.deleted_at)"
    )).all()
    order = {t: i for i, t in enumerate(tables)}
    dels = sorted((r for r in rows if r.table_name in synced),
                  key=lambda r: -order[r.table_name])
    out += [{"t": r.table_name, "uid": r.uid, "del": str(r.deleted_at)}
            for r in dels]
    return out


# --- import -----------------------------------------------------------
def _resolve(conn: Connection, table: str, uid: str
             ) -> tuple[int, str] | None:
    """Return (rowid, local uid) of the row known as ``uid`` here."""
    rid = conn.execute(text(f"SELECT rowid FROM {table} WHERE uid = :u"),
                       {"u": uid}).scalar()
    if rid is not None:
        return rid, uid
    alias = conn.execute(text(
        "SELECT uid FROM sync_aliases WHERE table_name = :t "
        "AND alias_uid = :u"), {"t": table, "u": uid}).scalar()
    if alias is None:
        return None
    rid = conn.execute(text(f"SELECT rowid FROM {table} WHERE uid = :u"),
                       {"u": alias}).scalar()
    return None if rid is None else (rid, alias)


def _translate(ids: _UidMap, table: str, row: dict,
               cols: list[str]) -> dict:
    fks = _fks(table)
    out = {}
    for c in cols:
        if c not in row:
            continue
        v = row[c]
        if c in fks:
            v = None if (v is None or fks[c] is None) else \
                ids.local_of(*fks[c], v)
        out[c] = v
    return out


def _apply_delete(conn: Connection, rec: dict) -> bool:
    table, when = rec["t"], rec["del"]
    found = _resolve(conn, table, rec["uid"])
    if found is None:
        conn.execute(text(
            "INSERT INTO sync_tombstones (table_name, uid, deleted_at) "
            "SELECT :t, :u, :d WHERE NOT EXISTS (SELECT 1 FROM "
            "sync_tombstones WHERE table_name = :t AND uid = :u)"),
            {"t": table, "u": rec["uid"], "d": when})
        _seen(conn, table, rec["uid"], "del:" + _last_del(
            conn, table, rec["uid"]))
        return False
    rid, local_uid = found
    local_u = conn.execute(text(
        f"SELECT CAST(updated_at AS TEXT) FROM {table} WHERE rowid = :r"),
        {"r": rid}).scalar()
    if norm_time(local_u) > norm_time(when):
        return False
    conn.execute(text(f"DELETE FROM {table} WHERE rowid = :r"), {"r": rid})
    conn.execute(text(
        "UPDATE sync_tombstones SET deleted_at = :d WHERE table_name = :t "
        "AND uid = :u"), {"t": table, "u": local_uid, "d": when})
    _seen(conn, table, local_uid, "del:" + when)
    return True


def _last_del(conn: Connection, table: str, uid: str) -> str:
    return str(conn.execute(text(
        "SELECT max(deleted_at) FROM sync_tombstones WHERE table_name = :t "
        "AND uid = :u"), {"t": table, "u": uid}).scalar())


def _update(conn: Connection, table: str, rid: int, local_uid: str,
            values: dict, u: str) -> bool:
    local_u = conn.execute(text(
        f"SELECT CAST(updated_at AS TEXT) FROM {table} WHERE rowid = :r"),
        {"r": rid}).scalar()
    if norm_time(u) <= norm_time(local_u):
        return False
    sets = ", ".join(f"{c} = :{c}" for c in values)
    conn.execute(text(
        f"UPDATE {table} SET {sets}{', ' if sets else ''}updated_at = :_u "
        f"WHERE rowid = :_r"), {**values, "_u": u, "_r": rid})
    _seen(conn, table, local_uid, u)
    return True


def _apply_upsert(conn: Connection, ids: _UidMap, rec: dict) -> bool:
    table, uid, u = rec["t"], rec["uid"], rec["u"]
    cols = _columns(conn, table)
    values = _translate(ids, table, rec.get("row") or {}, cols)
    found = _resolve(conn, table, uid)
    if found is not None:
        return _update(conn, table, found[0], found[1], values, u)
    deleted = conn.execute(text(
        "SELECT max(deleted_at) FROM sync_tombstones WHERE table_name = :t "
        "AND uid = :u"), {"t": table, "u": uid}).scalar()
    if deleted is not None and norm_time(deleted) >= norm_time(u):
        return False
    for key in _unique_keys(table):
        if any(values.get(c) is None for c in key):
            continue
        where = " AND ".join(f"{c} = :{c}" for c in key)
        hit = conn.execute(text(
            f"SELECT rowid AS rid, uid FROM {table} WHERE {where}"),
            {c: values[c] for c in key}).first()
        if hit is not None:
            conn.execute(text(
                "INSERT OR REPLACE INTO sync_aliases (table_name, alias_uid, "
                "uid) VALUES (:t, :a, :u)"),
                {"t": table, "a": uid, "u": hit.uid})
            return _update(conn, table, hit.rid, hit.uid, values, u)
    names = list(values) + ["uid", "updated_at"]
    conn.execute(text(
        f"INSERT INTO {table} ({', '.join(names)}) VALUES "
        f"({', '.join(':' + n for n in names)})"),
        {**values, "uid": uid, "updated_at": u})
    ids.forget(table)
    _seen(conn, table, uid, u)
    return True


def apply_changes(conn: Connection, records: list[dict]
                  ) -> tuple[int, list[dict], list[str]]:
    """Merge received changes into the local database.

    Parameters
    ----------
    conn : Connection
        The open database connection (the caller commits).
    records : list of dict
        The received change records.

    Returns
    -------
    tuple
        The number of rows changed, the records waiting for a parent row
        and the problems found (one line each).
    """
    order = {t: i for i, t in enumerate(sync_tables())}
    upserts = sorted((r for r in records if "del" not in r
                      and r.get("t") in order),
                     key=lambda r: order[r["t"]])
    deletes = sorted((r for r in records if "del" in r
                      and r.get("t") in order),
                     key=lambda r: -order[r["t"]])
    ids = _UidMap(conn)
    changed, problems = 0, []
    todo = upserts
    while todo:
        waiting = []
        for rec in todo:
            try:
                changed += _apply_upsert(conn, ids, rec)
            except _Missing:
                waiting.append(rec)
            except IntegrityError as exc:
                problems.append(f"{rec['t']} {rec['uid']}: {exc.orig}")
        if len(waiting) == len(todo):
            todo = waiting
            break
        todo = waiting
    for rec in deletes:
        changed += _apply_delete(conn, rec)
    conn.execute(text(
        "DELETE FROM sync_tombstones WHERE rowid NOT IN (SELECT max(rowid) "
        "FROM sync_tombstones GROUP BY table_name, uid)"))
    return changed, todo, problems


# --- run --------------------------------------------------------------
@dataclass
class SyncResult:
    """The outcome of one sync run."""

    sent: int
    received: int
    pending: int
    problems: list[str]


def run(db: Session, data_dir: Path) -> SyncResult:
    """Apply the other devices' new files, then write this device's changes.

    Parameters
    ----------
    db : Session
        The open database session.
    data_dir : Path
        The application data folder.

    Raises
    ------
    SyncError
        If sync is not set up or the folder cannot be read or written.
    """
    if not _lock.acquire(blocking=False):
        raise SyncError("A sync is already running; try again in a moment.")
    try:
        return _run(db, data_dir)
    except SyncError as exc:
        db.rollback()
        _record(db, {"at": _now(), "error": str(exc)})
        raise
    except OSError as exc:
        db.rollback()
        msg = (f"The sync folder cannot be used ({exc.strerror or exc}). "
               "Check that your cloud drive is running and the folder "
               "still exists.")
        _record(db, {"at": _now(), "error": msg})
        raise SyncError(msg) from exc
    finally:
        _lock.release()


def _record(db: Session, result: dict) -> None:
    _set(db.connection(), "last_result", json.dumps(result))
    db.commit()


def _run(db: Session, data_dir: Path) -> SyncResult:
    conn = db.connection()
    key = _load_key(data_dir)
    folder = _get(conn, "folder")
    me = _get(conn, "device_id")
    if _get(conn, "enabled") != "1" or key is None or not folder or not me:
        raise SyncError("Sync is not set up on this device. Choose a sync "
                        "folder and passphrase in Settings first.")
    store = FolderStore(Path(folder))
    manifest = store.read_manifest()
    if manifest is None:
        raise SyncError(
            f"{folder} no longer contains {MANIFEST}. If your cloud drive "
            "is still downloading the folder, try again later; otherwise "
            "set up sync again.")
    known = _get(conn, "folder_id")
    if known is not None and known != folder_identity(manifest):
        raise SyncError(
            "The sync folder was set up again (with a new passphrase) on "
            "another device. Set up sync again on this PC with that "
            "passphrase.")
    if known is None:
        _set(conn, "folder_id", folder_identity(manifest))
    if int(_get(conn, "next_seq", "1")) > 1 and not store.numbers(me):
        log.info("This device's sync files are no longer in the folder; "
                 "sending everything again.")
        _resend_all(conn)
    # 1. receive
    records: list[dict] = []
    for row in conn.execute(text("SELECT id, payload FROM sync_pending")):
        records.append(json.loads(row.payload))
    conn.execute(text("DELETE FROM sync_pending"))
    applied: dict[str, int] = {}
    for dev in store.devices():
        if dev == me:
            continue
        last = int(_get(conn, f"applied:{dev}", "0"))
        for number in store.numbers(dev):
            if number <= last:
                continue
            payload = unseal(key, _aad(dev, number), store.read(dev, number))
            if int(payload.get("format", 1)) > FORMAT:
                raise SyncError(
                    "Another device uses a newer version of PFI. Update "
                    "PFI on this PC to keep syncing.")
            records.extend(payload.get("changes", []))
            applied[dev] = number
            _set(conn, f"device:{dev}", json.dumps({
                "name": payload.get("name") or dev,
                "seen": payload.get("created")}))
    received, waiting, problems = apply_changes(conn, records)
    for rec in waiting:
        conn.execute(text("INSERT INTO sync_pending (payload, attempts) "
                          "VALUES (:p, 1)"), {"p": json.dumps(rec)})
    for dev, number in applied.items():
        _set(conn, f"applied:{dev}", str(number))
    db.commit()
    # 2. send
    conn = db.connection()
    changes = collect_changes(conn)
    number = int(_get(conn, "next_seq", "1"))
    name = _get(conn, "device_name") or socket.gethostname()
    for start in range(0, len(changes), CHUNK):
        part = changes[start:start + CHUNK]
        store.write(me, number, seal(key, _aad(me, number), {
            "format": FORMAT, "device": me, "name": name, "seq": number,
            "created": _now(), "changes": part}))
        for rec in part:
            _seen(conn, rec["t"], rec["uid"],
                  "del:" + rec["del"] if "del" in rec else rec["u"])
        number += 1
        _set(conn, "next_seq", str(number))
        db.commit()
        conn = db.connection()
    result = SyncResult(sent=len(changes), received=received,
                        pending=len(waiting), problems=problems)
    _record(db, {"at": _now(), "sent": result.sent,
                 "received": result.received,
                 "error": "; ".join(problems[:3]) or None})
    if problems:
        log.warning("Sync skipped %d changes: %s", len(problems),
                    "; ".join(problems[:5]))
    return result
