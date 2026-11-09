"""Typed application preferences stored as key/value rows in ``settings``."""
import json

from sqlalchemy.orm import Session

from ..models import ASSET_CLASSES, Setting
from ..seed import get_setting

LANGUAGES = ("en", "fr", "ar")
LOCK_MODES = ("off", "hello")

DEFAULTS: dict[str, str] = {
    "fx_auto_update": "1",
    "price_auto_update": "1",
    "language": "en",
    "app_lock": "off",
    "lock_after_minutes": "5",
    "auto_categorize": "1",
    "auto_categorize_threshold": "0.8",
    "allocation_targets": "{}",
    "stooq_api_key": "",
    "twelvedata_api_key": "",
    "alphavantage_api_key": "",
}
#: Personal API keys of price providers; never returned to the UI.
API_KEYS = ("stooq_api_key", "twelvedata_api_key", "alphavantage_api_key")


def get(db: Session, key: str) -> str:
    """Return a preference as stored text, falling back to its default."""
    return get_setting(db, key, DEFAULTS.get(key, ""))


def get_bool(db: Session, key: str) -> bool:
    """Return a boolean preference."""
    return get(db, key) == "1"


def get_float(db: Session, key: str) -> float:
    """Return a numeric preference, or its default if unparsable."""
    try:
        return float(get(db, key))
    except ValueError:
        return float(DEFAULTS[key])


def get_targets(db: Session) -> dict[str, float]:
    """Return the target allocation in percent per asset class."""
    try:
        raw = json.loads(get(db, "allocation_targets") or "{}")
    except json.JSONDecodeError:
        return {}
    return {k: float(v) for k, v in raw.items()
            if k in ASSET_CLASSES and float(v) > 0}


def put(db: Session, key: str, value: str) -> None:
    """Store a preference; the caller commits."""
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


def snapshot(db: Session) -> dict:
    """Return all user-facing preferences with proper types."""
    return {
        "fx_auto_update": get_bool(db, "fx_auto_update"),
        "fx_last_update": get(db, "fx_last_update") or None,
        "price_auto_update": get_bool(db, "price_auto_update"),
        "price_last_update": get(db, "price_last_update") or None,
        "language": get(db, "language"),
        "app_lock": get(db, "app_lock"),
        "lock_after_minutes": int(get_float(db, "lock_after_minutes")),
        "auto_categorize": get_bool(db, "auto_categorize"),
        "auto_categorize_threshold": get_float(db,
                                               "auto_categorize_threshold"),
        "allocation_targets": get_targets(db),
        # Keys themselves are never sent back to the UI: only whether one is
        # saved and its last four characters.
        **{f"{k}_set": bool(get(db, k)) for k in API_KEYS},
        **{f"{k}_hint": (get(db, k)[-4:] or None) for k in API_KEYS},
    }
