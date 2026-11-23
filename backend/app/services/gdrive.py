"""Google Drive as a sync place, through the Drive web API.

Unlike OneDrive and Dropbox, Google Drive for desktop cannot share a
folder with the phone app (Google only lets an app see the files it
created itself). Personal Finance therefore keeps the sync files in the hidden
"app data" folder of the user's Drive, which both PFI on Windows and the
phone app reach with the ``drive.appdata`` permission. Nothing else in
the Drive is visible to Personal Finance.

File names in the app data folder are flat:
``pfi-sync.json`` and ``<device>-<00000001>.pfisync``.

Sign-in uses OAuth 2 for installed apps with PKCE and a loopback redirect
to the local PFI backend. The OAuth client of PFI on Windows comes from
``google-oauth.json`` (the file Google Cloud Console downloads for a
"Desktop app" client), placed next to the backend; it is not part of the
source code.
"""
import base64
import hashlib
import json
import logging
import re
import secrets
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from . import secret_store

log = logging.getLogger(__name__)

FOLDER = "gdrive:appdata"
LABEL = "Google Drive (PFI app data)"
SCOPE = "https://www.googleapis.com/auth/drive.appdata"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
TOKEN_FILE = "gdrive.token"
_NAME_RE = re.compile(r"^([0-9a-f]{16})-(\d{8})\.pfisync$")
_pending: dict[str, tuple[str, str, float]] = {}
_pending_lock = threading.Lock()


class DriveError(Exception):
    """Raised when Google Drive cannot be reached or refuses a request."""


def _client_file_candidates() -> list[Path]:
    here = Path(__file__).resolve().parent.parent.parent
    return [Path(sys.executable).resolve().parent / "google-oauth.json",
            here / "google-oauth.json"]


def client() -> tuple[str, str] | None:
    """Return the OAuth client id and secret of PFI on Windows, if set.

    The values come from ``PFI_GOOGLE_CLIENT_ID`` and
    ``PFI_GOOGLE_CLIENT_SECRET``, or from ``google-oauth.json`` next to
    the backend. Google treats the secret of an installed app as public.
    """
    from ..config import get_settings
    s = get_settings()
    if s.google_client_id:
        return s.google_client_id, s.google_client_secret
    for path in _client_file_candidates():
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                log.warning("%s cannot be read; Google Drive sync is off.",
                            path)
                return None
            info = data.get("installed") or data.get("web") or data
            if info.get("client_id"):
                return info["client_id"], info.get("client_secret", "")
    return None


def available() -> bool:
    """Return whether this build of PFI can sign in to Google Drive."""
    return client() is not None


def _token_path(data_dir: Path) -> Path:
    return Path(data_dir) / TOKEN_FILE


def signed_in(data_dir: Path) -> bool:
    """Return whether a Google refresh token is stored.

    Parameters
    ----------
    data_dir : Path
        The application data folder.
    """
    return secret_store.load(_token_path(data_dir)) is not None


def sign_out(data_dir: Path) -> None:
    """Forget the Google sign-in of this PC.

    Parameters
    ----------
    data_dir : Path
        The application data folder.
    """
    secret_store.save(_token_path(data_dir), None)


def start(redirect_uri: str) -> str:
    """Return the Google sign-in URL for a new sign-in.

    Parameters
    ----------
    redirect_uri : str
        The loopback callback of the local backend.

    Raises
    ------
    DriveError
        If this build has no Google OAuth client.
    """
    c = client()
    if c is None:
        raise DriveError(
            "Google Drive sync is not available in this build of Personal "
            "Finance. Use OneDrive, or a build that includes "
            "google-oauth.json.")
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(24)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    with _pending_lock:
        now = time.time()
        for k in [k for k, v in _pending.items() if now - v[2] > 900]:
            del _pending[k]
        _pending[state] = (verifier, redirect_uri, now)
    return AUTH_URL + "?" + urlencode({
        "client_id": c[0], "redirect_uri": redirect_uri,
        "response_type": "code", "scope": SCOPE, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent"})


def finish(data_dir: Path, state: str, code: str) -> None:
    """Exchange the sign-in code and keep the refresh token.

    Parameters
    ----------
    data_dir : Path
        The application data folder.
    state : str
        The state value Google sent back.
    code : str
        The authorization code.

    Raises
    ------
    DriveError
        If the sign-in is unknown, expired or refused by Google.
    """
    with _pending_lock:
        entry = _pending.pop(state, None)
    if entry is None:
        raise DriveError("This sign-in is unknown or expired. Start it "
                         "again from Settings › Sync in Personal Finance.")
    verifier, redirect_uri, _ = entry
    c = client()
    if c is None:
        raise DriveError("Google Drive sync is not available in this build.")
    data = _post_token({
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": redirect_uri, "code_verifier": verifier,
        "client_id": c[0], "client_secret": c[1]})
    refresh = data.get("refresh_token")
    if not refresh:
        raise DriveError("Google did not grant offline access. Sign in again "
                         "and allow Personal Finance to keep its sync files.")
    secret_store.save(_token_path(data_dir), refresh)


def _post_token(body: dict) -> dict:
    try:
        r = httpx.post(TOKEN_URL, data=body, timeout=30)
    except httpx.HTTPError as exc:
        raise DriveError(f"Google could not be reached ({exc}). Check the "
                         "internet connection and try again.") from exc
    if r.status_code != 200:
        raise DriveError(
            f"Google refused the sign-in ({r.status_code}). Sign in to "
            "Google Drive again in Settings › Sync.")
    return r.json()


class DriveStore:
    """Sync files in the app data folder of the user's Google Drive.

    Parameters
    ----------
    data_dir : Path
        The application data folder (holds the protected refresh token).
    """

    label = LABEL

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._access: str | None = None
        self._expires = 0.0
        self._files: dict[str, str] | None = None

    # --- http ---------------------------------------------------------
    def _token(self) -> str:
        if self._access and time.time() < self._expires:
            return self._access
        refresh = secret_store.load(_token_path(self.data_dir))
        c = client()
        if refresh is None or c is None:
            raise DriveError("Sign in to Google Drive in Settings › Sync.")
        data = _post_token({"grant_type": "refresh_token",
                            "refresh_token": refresh,
                            "client_id": c[0], "client_secret": c[1]})
        self._access = data["access_token"]
        self._expires = time.time() + int(data.get("expires_in", 3600)) - 60
        return self._access

    def _send(self, method: str, url: str, **kw) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token()}",
                   **kw.pop("headers", {})}
        try:
            r = httpx.request(method, url, headers=headers, timeout=60, **kw)
        except httpx.HTTPError as exc:
            raise DriveError(f"Google Drive could not be reached ({exc}). "
                             "Check the internet connection.") from exc
        if r.status_code == 401:
            self._access = None
            raise DriveError("Google Drive refused access. Sign in to "
                             "Google Drive again in Settings › Sync.")
        if r.status_code >= 300:
            raise DriveError(f"Google Drive answered {r.status_code}. Try "
                             "again in a moment.")
        return r

    def _list(self) -> dict[str, str]:
        if self._files is not None:
            return self._files
        files: dict[str, str] = {}
        token = None
        while True:
            params = {"spaces": "appDataFolder", "pageSize": 1000,
                      "fields": "nextPageToken, files(id, name)"}
            if token:
                params["pageToken"] = token
            j = self._send("GET", f"{API}/files", params=params).json()
            for f in j.get("files", []):
                files.setdefault(f["name"], f["id"])
            token = j.get("nextPageToken")
            if not token:
                break
        self._files = files
        return files

    def _download(self, name: str) -> bytes | None:
        fid = self._list().get(name)
        if fid is None:
            return None
        return self._send("GET", f"{API}/files/{fid}",
                          params={"alt": "media"}).content

    def _upload(self, name: str, data: bytes, mime: str) -> None:
        meta = {"name": name, "parents": ["appDataFolder"]}
        boundary = "pfi" + secrets.token_hex(8)
        body = (f"--{boundary}\r\nContent-Type: application/json; "
                f"charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
                f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() \
            + data + f"\r\n--{boundary}--".encode()
        kind = f"multipart/related; boundary={boundary}"
        r = self._send("POST", UPLOAD,
                       params={"uploadType": "multipart", "fields": "id"},
                       content=body, headers={"Content-Type": kind})
        self._list()[name] = r.json()["id"]

    # --- store interface (same as FolderStore) -------------------------
    def read_manifest(self) -> dict | None:
        """Return the manifest, or ``None`` when Drive has none yet."""
        raw = self._download("pfi-sync.json")
        return None if raw is None else json.loads(raw.decode("utf-8"))

    def write_manifest(self, manifest: dict) -> None:
        """Create the manifest.

        Parameters
        ----------
        manifest : dict
            The manifest document.
        """
        self._upload("pfi-sync.json",
                     json.dumps(manifest, indent=1).encode("utf-8"),
                     "application/json")

    def devices(self) -> list[str]:
        """Return the ids of the devices that wrote change files."""
        return sorted({m[1] for n in self._list()
                       if (m := _NAME_RE.match(n))})

    def numbers(self, device: str) -> list[int]:
        """Return the file numbers a device wrote, in order.

        Parameters
        ----------
        device : str
            The device id.
        """
        return sorted(int(m[2]) for n in self._list()
                      if (m := _NAME_RE.match(n)) and m[1] == device)

    def read(self, device: str, number: int) -> bytes:
        """Return the bytes of one change file.

        Parameters
        ----------
        device : str
            The device id.
        number : int
            The file number.
        """
        raw = self._download(f"{device}-{number:08d}.pfisync")
        if raw is None:
            raise DriveError(f"{device}-{number:08d}.pfisync is missing in "
                             "Google Drive. Try syncing again.")
        return raw

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
        name = f"{device}-{number:08d}.pfisync"
        if name in self._list():
            raise DriveError(
                f"{name} already exists in Google Drive. Another "
                "installation uses the same device id; set up sync again "
                "on this device.")
        self._upload(name, data, "application/octet-stream")
