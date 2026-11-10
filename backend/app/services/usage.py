"""Opt-in, anonymous count of how many people use PFI.

Nothing is sent unless the user says yes (first start or Settings). Then,
at most once a week, the app posts exactly three values to the counter:

* ``id``: a random identifier made on this PC when the user agreed. It is
  not derived from the computer, the Windows account or any data, and a
  new one is made if the user turns counting off and on again;
* ``version``: the app version, e.g. ``0.5.0``;
* ``lang``: the app language (``en``, ``fr`` or ``ar``).

No amounts, accounts, file names or other content ever leave the PC. The
counter (``usage-worker/`` in the repository) only counts distinct ids per
week.
"""
import json
import logging
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .. import __version__
from . import prefs

log = logging.getLogger(__name__)
#: The counter's address; empty means the feature is not offered at all.
USAGE_URL = ""
EVERY = timedelta(days=7)


def state(db: Session) -> str:
    """Return ``"ask"`` (not decided yet), ``"on"`` or ``"off"``."""
    value = prefs.get(db, "usage_ping")
    return {"1": "on", "0": "off"}.get(value, "ask")


def set_state(db: Session, on: bool) -> None:
    """Record the user's choice; turning it off forgets the random id.

    Parameters
    ----------
    db : Session
        The open database session; the caller commits.
    on : bool
        The flag the user chose.
    """
    prefs.put(db, "usage_ping", "1" if on else "0")
    if on and not prefs.get(db, "usage_id"):
        prefs.put(db, "usage_id", uuid.uuid4().hex)
    if not on:
        prefs.put(db, "usage_id", "")
        prefs.put(db, "usage_last_ping", "")


def payload(db: Session) -> dict:
    """Return exactly what is sent: the random id, version and language."""
    return {"id": prefs.get(db, "usage_id"), "version": __version__,
            "lang": prefs.get(db, "language")}


def due(db: Session, now: datetime | None = None,
        url: str | None = None) -> bool:
    """Return whether a weekly ping should be sent now.

    Parameters
    ----------
    db : Session
        The open database session.
    now : datetime, optional
        The reference time (defaults to now, UTC).
    url : str, optional
        The counter address (defaults to ``USAGE_URL``).
    """
    if not (USAGE_URL if url is None else url) or state(db) != "on" \
            or not prefs.get(db, "usage_id"):
        return False
    last = prefs.get(db, "usage_last_ping")
    if not last:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        return now - datetime.fromisoformat(last) >= EVERY
    except ValueError:
        return True


def send(db: Session, url: str | None = None,
         now: datetime | None = None) -> bool:
    """Send the ping if it is due and remember when; never raises.

    Parameters
    ----------
    db : Session
        The open database session; committed after a successful ping.
    url : str, optional
        The counter address (defaults to ``USAGE_URL``).
    now : datetime, optional
        The reference time (defaults to now, UTC).

    Returns
    -------
    bool
        ``True`` if the counter accepted the ping.
    """
    url = USAGE_URL if url is None else url
    now = now or datetime.now(timezone.utc)
    if not due(db, now, url):
        return False
    body = json.dumps(payload(db)).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "User-Agent": f"PFI/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = 200 <= resp.status < 300
    except Exception as exc:  # offline, blocked, counter down: try later
        log.info("Usage count not sent (%s); next try at the next start.",
                 exc)
        return False
    if ok:
        prefs.put(db, "usage_last_ping", now.isoformat(timespec="seconds"))
        db.commit()
    return ok
