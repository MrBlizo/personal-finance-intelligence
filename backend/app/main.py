"""FastAPI application: startup (database, migrations), routers, UI."""
import logging
import mimetypes
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import get_settings
from . import legacy
from .db import SessionLocal, init_engine, sqlite_url
from .migrations import run_migrations
from .routers import analytics, automation, core, extras, investments
from .routers import planning, system
from .routers import reports
from .routers import transactions
from .security import TokenMiddleware
from .seed import seed_defaults
from .services.automation import post_due
from .services.backup import auto_backup_if_due
from .services.prices import prices_due, update_prices
from .services.fx import FxRateMissing
from .services.fx_fetch import auto_update_due, update_rates
from .services.ledger import base_currency

log = logging.getLogger("pfi")

# On Windows, Python reads MIME types from the registry, where ".js" is often
# mapped to "text/plain"; WebView2 then refuses to run the UI scripts and the
# window stays blank. Register the correct types explicitly.
for _ext, _type in ((".js", "text/javascript"), (".mjs", "text/javascript"),
                    (".css", "text/css"), (".json", "application/json"),
                    (".svg", "image/svg+xml"), (".txt", "text/plain"),
                    (".woff2", "font/woff2"), (".html", "text/html")):
    mimetypes.add_type(_type, _ext)


def background_tasks(data_dir: Path, db_path: Path) -> None:
    """Weekly backup, recurring auto-posting, daily rate and price update.

    Runs in a daemon thread after start-up; failures are logged only, so a
    missing internet connection never blocks the app.
    """
    try:
        made = auto_backup_if_due(data_dir, db_path)
        if made:
            log.info("Automatic backup created: %s", made.name)
            if made.warning:
                log.warning(made.warning)
    except Exception:
        log.exception("Automatic backup failed")
    try:
        with SessionLocal() as db:
            removed = extras.sweep_orphans(db, data_dir / "attachments")
            if removed:
                log.info("Removed %d unused attachment files", removed)
    except Exception:
        log.exception("Attachment clean-up failed")
    try:
        with SessionLocal() as db:
            posted = post_due(db)
            db.commit()
            if posted:
                log.info("Posted %d recurring transactions", len(posted))
    except Exception:
        log.exception("Recurring auto-posting failed")
    try:
        with SessionLocal() as db:
            if auto_update_due(db):
                result = update_rates(db, base_currency(db), backfill=True)
                log.info("Exchange rates updated: %s", result)
    except Exception as exc:
        log.warning("Automatic exchange-rate update skipped: %s", exc)
    try:
        with SessionLocal() as db:
            if prices_due(db):
                log.info("Prices updated: %s", update_prices(db))
    except Exception as exc:
        log.warning("Automatic price update skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db_path = settings.sqlite_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists() and legacy.has_cluster(settings.data_dir):
        counts = legacy.migrate_cluster(settings.pg_bin, settings.data_dir,
                                        db_path, settings.pg_port,
                                        settings.pg_relocate)
        log.info("Moved the 0.3 database to SQLite: %d transactions",
                 counts.get("transactions", 0))
    engine = init_engine(sqlite_url(db_path))
    version = run_migrations(engine)
    with SessionLocal() as db:
        seed_defaults(db, settings.base_currency_default)
    log.info("Database ready: %s (schema v%s)", db_path, version)
    if settings.background_tasks:
        threading.Thread(target=background_tasks,
                         args=(settings.data_dir, db_path),
                         daemon=True).start()
    try:
        yield
    finally:
        engine.dispose()


def create_app() -> FastAPI:
    """Build the FastAPI application with all routers and the static UI."""
    settings = get_settings()
    app = FastAPI(title="Personal Finance Intelligence API",
                  version=__version__, lifespan=lifespan)
    app.add_middleware(TokenMiddleware, token=settings.api_token)
    if not settings.api_token:
        app.add_middleware(
            CORSMiddleware, allow_credentials=True,
            allow_origins=[o.strip() for o in
                           settings.cors_origins.split(",") if o.strip()],
            allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(FxRateMissing)
    async def _fx_missing(_: Request, exc: FxRateMissing):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    for module in (system, core, transactions, extras, planning,
                   investments, analytics, automation, reports):
        app.include_router(module.router)
    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist,
                                   html=True), name="ui")
    else:
        log.warning("Frontend build not found at %s; serving API only.",
                    settings.frontend_dist)
    return app


app = create_app()
