"""Tell users of the GitHub installer when a newer Personal Finance is out.

Store installs update themselves, so the check is skipped there. The only
request is an anonymous GET of the public "latest release" page of the PFI
repository on GitHub; nothing about the user or their data is sent. The
answer is cached for a day.
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .. import __version__
from . import prefs

LATEST_URL = ("https://api.github.com/repos/MrBlizo/"
              "personal-finance-intelligence/releases/latest")
RELEASES_PAGE = ("https://github.com/MrBlizo/personal-finance-intelligence/"
                 "releases/latest")
CACHE_HOURS = 24


def is_store_install() -> bool:
    """Return True when PFI runs from the Microsoft Store (MSIX) package."""
    if sys.platform != "win32":
        return False
    import ctypes
    length = ctypes.c_uint32(0)
    # APPMODEL_ERROR_NO_PACKAGE (15700) means "not packaged".
    rc = ctypes.windll.kernel32.GetCurrentPackageFullName(
        ctypes.byref(length), None)
    return rc != 15700


def parse_version(tag: str) -> tuple[int, ...]:
    """Turn ``v1.2.3`` (or ``1.2.3``) into ``(1, 2, 3)``.

    Parameters
    ----------
    tag : str
        The release tag or version text.

    Returns
    -------
    tuple of int
        The numeric parts; anything that is not a number counts as 0.
    """
    out = []
    for part in tag.strip().lstrip("vV").split("-")[0].split("."):
        out.append(int(part) if part.isdigit() else 0)
    return tuple(out)


def fetch_latest(timeout: float = 6.0) -> dict:
    """Ask GitHub for the latest release.

    Parameters
    ----------
    timeout : float
        The seconds to wait for GitHub.

    Returns
    -------
    dict
        ``version``, ``url`` and ``notes`` (the release text).
    """
    req = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"PFI/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    return {"version": str(data.get("tag_name", "")).lstrip("vV"),
            "url": data.get("html_url") or RELEASES_PAGE,
            "notes": (data.get("body") or "")[:4000]}


def status(db: Session, force: bool = False, fetch=fetch_latest) -> dict:
    """Return whether a newer version is available.

    Parameters
    ----------
    db : Session
        The open database session (the answer is cached in settings).
    force : bool
        The flag to ask GitHub even if the cached answer is recent.
    fetch : callable
        The function that returns the latest release (replaced in tests).

    Returns
    -------
    dict
        ``current``, ``latest`` (or None), ``newer`` (bool), ``url``,
        ``notes``, ``store`` (True for Store installs, which update
        themselves), ``enabled`` (the user's setting), ``checked_at`` and
        ``error`` (a readable message when GitHub could not be reached).
    """
    out = {"current": __version__, "latest": None, "newer": False,
           "url": RELEASES_PAGE, "notes": "", "store": is_store_install(),
           "enabled": prefs.get_bool(db, "update_check"),
           "checked_at": prefs.get(db, "update_checked_at") or None,
           "error": None}
    if out["store"] or not (out["enabled"] or force):
        return out
    cached = prefs.get(db, "update_latest")
    fresh = False
    if out["checked_at"] and cached and not force:
        try:
            when = datetime.fromisoformat(out["checked_at"])
            fresh = datetime.now(timezone.utc) - when < timedelta(
                hours=CACHE_HOURS)
        except ValueError:
            fresh = False
    if fresh:
        latest = json.loads(cached)
    else:
        try:
            latest = fetch()
        except Exception as exc:  # offline, rate-limited, GitHub down
            out["error"] = (
                f"Couldn't reach GitHub to check for updates ({exc}). "
                "Check your internet connection and try again later.")
            return out
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        prefs.put(db, "update_latest", json.dumps(latest))
        prefs.put(db, "update_checked_at", now)
        db.commit()
        out["checked_at"] = now
    out.update(latest=latest["version"], url=latest["url"],
               notes=latest["notes"])
    out["newer"] = parse_version(latest["version"]) > parse_version(
        __version__)
    return out
