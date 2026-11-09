"""Private PostgreSQL cluster bundled with the desktop app.

The cluster lives in ``<data_dir>/pgdata``, listens only on 127.0.0.1 and
uses a random password generated on first start (``<data_dir>/pg_secret``).

In the Microsoft Store package the binaries sit in the protected
``WindowsApps`` folder. ``initdb`` and ``pg_ctl`` relaunch themselves and
``postgres`` with a restricted token, and those child processes get "Access
is denied" there, so the binaries are first copied to
``<data_dir>/runtime/pgsql-<key>`` (once per app version).
"""
import hashlib
import logging
import os
import secrets
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import psycopg

log = logging.getLogger(__name__)
IS_WINDOWS = sys.platform == "win32"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
DB_USER = "pfi"
DB_NAME = "pfi"
SERVER_CONF = """
# --- Personal Finance Intelligence (desktop) ---
listen_addresses = '127.0.0.1'
unix_socket_directories = ''
max_connections = 20
shared_buffers = 64MB
"""


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def in_store_package(bin_dir: Path) -> bool:
    """Return whether the binaries are in the Microsoft Store install folder.

    Parameters
    ----------
    bin_dir : Path
        The directory containing the PostgreSQL programs.
    """
    path = str(bin_dir).replace("/", "\\").lower()
    return "\\windowsapps\\" in path


def relocate_binaries(bin_dir: Path, data_root: Path) -> Path:
    """Copy the PostgreSQL installation next to the data and return its bin.

    The ``bin``, ``lib`` and ``share`` folders next to ``bin_dir`` are copied
    to ``<data_root>/runtime/pgsql-<key>``, where the key is derived from the
    source path (it changes with every app version). An existing complete
    copy is reused; copies of other versions are removed.

    Parameters
    ----------
    bin_dir : Path
        The directory containing ``initdb``, ``pg_ctl`` and ``postgres``.
    data_root : Path
        The application data directory.

    Returns
    -------
    Path
        The ``bin`` directory of the copy.

    Raises
    ------
    RuntimeError
        If the copy cannot be made, e.g. because the disk is full.
    """
    source = Path(bin_dir).parent
    key = hashlib.sha1(str(source).lower().encode("utf-8")).hexdigest()[:12]
    runtime = Path(data_root) / "runtime"
    dest = runtime / f"pgsql-{key}"
    if not (dest / ".complete").is_file():
        log.info("Copying PostgreSQL from %s to %s", source, dest)
        tmp = runtime / f"pgsql-{key}.tmp"
        try:
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True)
            for part in ("bin", "lib", "share"):
                if (source / part).is_dir():
                    shutil.copytree(source / part, tmp / part)
            (tmp / ".complete").write_text(str(source), encoding="utf-8")
            shutil.rmtree(dest, ignore_errors=True)
            tmp.rename(dest)
        except OSError as exc:
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError(
                f"Could not copy the bundled PostgreSQL to {dest}: {exc}. "
                "The app runs the database from this copy because Windows "
                "blocks it inside the Store install folder. Free some disk "
                "space (about 160 MB are needed) and restart the app.") \
                from exc
    for old in runtime.glob("pgsql-*"):
        if old != dest:
            shutil.rmtree(old, ignore_errors=True)
    return dest / "bin"


class EmbeddedPostgres:
    """Start, reuse and stop a private PostgreSQL cluster.

    Parameters
    ----------
    bin_dir : Path
        The directory containing ``initdb``, ``pg_ctl`` and ``postgres``.
    data_root : Path
        The application data directory that will hold ``pgdata``.
    port : int
        The preferred TCP port; a free one is chosen if it is taken.
    relocate : bool or None
        The flag to run the binaries from a copy in ``data_root``; ``None``
        copies only when they are in the Store install folder.
    """

    def __init__(self, bin_dir: Path, data_root: Path, port: int,
                 relocate: bool | None = None) -> None:
        self.data_root = Path(data_root)
        self.bin_dir = Path(bin_dir)
        if relocate is None:
            relocate = in_store_package(self.bin_dir)
        if relocate:
            self.bin_dir = relocate_binaries(self.bin_dir, self.data_root)
        self.data_dir = self.data_root / "pgdata"
        self.secret_file = self.data_root / "pg_secret"
        self.log_file = self.data_root / "logs" / "postgres-tools.log"
        self.server_log = self.data_root / "logs" / "postgres-server.log"
        self.preferred_port = port
        self.port: int | None = None

    def _exe(self, name: str) -> str:
        path = self.bin_dir / (f"{name}.exe" if IS_WINDOWS else name)
        if not path.is_file():
            raise FileNotFoundError(
                f"PostgreSQL program '{path}' was not found. The bundled "
                "PostgreSQL folder is missing or incomplete. Reinstall the "
                "app, or set PFI_PG_BIN to a folder containing initdb and "
                "pg_ctl.")
        return str(path)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as fh:
            return subprocess.run(
                args, stdout=fh, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)

    def tool(self, name: str) -> str:
        """Return the full path of a PostgreSQL program (e.g. pg_dump)."""
        return self._exe(name)

    def client_env(self) -> dict[str, str]:
        """Return an environment that lets client tools log in."""
        return {**os.environ, "PGPASSWORD": self._password(),
                "PGHOST": "127.0.0.1", "PGPORT": str(self.port),
                "PGUSER": DB_USER, "PGDATABASE": DB_NAME}

    def _password(self) -> str:
        return self.secret_file.read_text(encoding="utf-8").strip()

    def ensure_initialized(self) -> None:
        """Create the cluster with ``initdb`` if it does not exist yet."""
        if (self.data_dir / "PG_VERSION").is_file():
            return
        self.data_root.mkdir(parents=True, exist_ok=True)
        password = secrets.token_urlsafe(24)
        self.secret_file.write_text(password, encoding="utf-8")
        os.chmod(self.secret_file, 0o600)
        pwfile = self.data_root / ".initdb_pw"
        pwfile.write_text(password, encoding="utf-8")
        try:
            log.info("Initialising PostgreSQL cluster in %s", self.data_dir)
            result = self._run([
                self._exe("initdb"), "-D", str(self.data_dir), "-U",
                DB_USER, f"--pwfile={pwfile}", "--auth=scram-sha-256",
                "-E", "UTF8", "--no-locale"])
        finally:
            pwfile.unlink(missing_ok=True)
        if result.returncode == 0:
            with (self.data_dir / "postgresql.conf").open(
                    "a", encoding="utf-8") as fh:
                fh.write(SERVER_CONF)
        else:
            raise RuntimeError(
                f"initdb failed (exit code {result.returncode}). See "
                f"{self.log_file} for details. Common causes: no write "
                "permission to the data folder, or running as an "
                "administrator/root account. Fix the cause and restart.")

    def running_port(self) -> int | None:
        """Return the port of an already running cluster, if any."""
        pid_file = self.data_dir / "postmaster.pid"
        if not pid_file.is_file():
            return None
        status = self._run([self._exe("pg_ctl"), "status", "-D",
                            str(self.data_dir)])
        if status.returncode != 0:
            return None
        lines = pid_file.read_text(encoding="utf-8").splitlines()
        return int(lines[3]) if len(lines) > 3 else None

    def start(self) -> str:
        """Start (or reuse) the cluster and return its SQLAlchemy URL.

        Returns
        -------
        str
            The ``postgresql+psycopg`` URL of the application database.
        """
        self.ensure_initialized()
        port = self.running_port()
        if port is None:
            port = (self.preferred_port if _port_free(self.preferred_port)
                    else _free_port())
            log.info("Starting PostgreSQL on 127.0.0.1:%s", port)
            result = self._run([
                self._exe("pg_ctl"), "start", "-w", "-t", "60", "-D",
                str(self.data_dir), "-l", str(self.server_log), "-o",
                f"-p {port}"])
            if result.returncode != 0:
                raise RuntimeError(
                    f"PostgreSQL did not start (exit code "
                    f"{result.returncode}). See {self.server_log}. If the "
                    "computer crashed, a stale postmaster.pid may remain "
                    "in the pgdata folder; close all app windows and retry.")
        self.port = port
        self._ensure_database()
        return (f"postgresql+psycopg://{DB_USER}:{self._password()}"
                f"@127.0.0.1:{port}/{DB_NAME}")

    def _ensure_database(self) -> None:
        with psycopg.connect(host="127.0.0.1", port=self.port,
                             user=DB_USER, password=self._password(),
                             dbname="postgres", autocommit=True) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (DB_NAME,)).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{DB_NAME}"')

    def stop(self) -> None:
        """Stop the cluster with a fast shutdown."""
        if not (self.data_dir / "postmaster.pid").is_file():
            return
        log.info("Stopping PostgreSQL")
        self._run([self._exe("pg_ctl"), "stop", "-D", str(self.data_dir),
                   "-m", "fast", "-w", "-t", "30"])
