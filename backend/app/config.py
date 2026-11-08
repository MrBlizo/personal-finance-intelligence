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
        The SQLAlchemy URL of an external PostgreSQL server. Ignored when
        ``pg_bin`` is set (embedded mode).
    pg_bin : Path or None
        The directory holding the bundled PostgreSQL binaries (``initdb``,
        ``pg_ctl``). When set, the backend runs its own private cluster.
    pg_port : int
        The preferred TCP port of the embedded PostgreSQL cluster.
    data_dir : Path
        The directory for the database cluster, archived imports and logs.
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

    database_url: str = "postgresql+psycopg://pfi:pfi@localhost:5432/pfi"
    pg_bin: Path | None = None
    pg_port: int = 54329
    data_dir: Path = _default_data_dir()
    frontend_dist: Path = PROJECT_DIR / "frontend" / "out"
    api_token: str = ""
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    base_currency_default: str = "CHF"
    background_tasks: bool = True

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
