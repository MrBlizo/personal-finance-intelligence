"""Application configuration loaded from environment variables or `.env`.

All variables use the ``PFI_`` prefix, e.g. ``PFI_DATABASE_URL``.
"""
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _default_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    root = Path(local) if local else Path.home() / ".local" / "share"
    return root / "PersonalFinanceIntelligence"


class Settings(BaseSettings):
    """Runtime settings for the Personal Finance Intelligence backend.

    Attributes
    ----------
    database_url : str
        The SQLAlchemy URL of a SQLite database. Empty (default) uses
        ``<data_dir>/pfi.sqlite``.
    data_dir : Path
        The directory for the database file, backups, receipts and logs.
    frontend_dist : Path
        The directory containing the static Next.js export.
    api_token : str
        The per-launch secret set by the desktop shell. Empty disables
        authentication (development mode).
    cors_origins : str
        The comma-separated origins allowed during frontend development.
    base_currency_default : str
        The reporting currency used when the database is first created.
    background_tasks : bool
        The flag for the weekly backup and daily rate update at start-up.
    """

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_prefix="PFI_", extra="ignore")

    database_url: str = ""
    data_dir: Path = _default_data_dir()
    frontend_dist: Path = PROJECT_DIR / "frontend" / "out"
    api_token: str = ""
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    base_currency_default: str = "CHF"
    background_tasks: bool = True

    @property
    def sqlite_path(self) -> Path:
        """Return the path of the application database file."""
        if self.database_url:
            if not self.database_url.startswith("sqlite:///"):
                raise ValueError(
                    f"PFI_DATABASE_URL must be a SQLite URL "
                    f"(sqlite:///C:/path/pfi.sqlite), not "
                    f"'{self.database_url.split(':')[0]}'. Since 0.4 PFI "
                    "stores its data in SQLite; remove the setting to use "
                    "the default file in the data folder.")
            return Path(self.database_url.removeprefix("sqlite:///"))
        return self.data_dir / "pfi.sqlite"

    def subdir(self, name: str) -> Path:
        """Return (and create) a subdirectory of the data directory.

        Parameters
        ----------
        name : str
            The name of the subdirectory, e.g. ``"imports"``.

        Returns
        -------
        Path
            The absolute path of the existing subdirectory.
        """
        path = self.data_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
