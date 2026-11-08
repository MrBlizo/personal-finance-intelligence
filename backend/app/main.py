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
from .db import SessionLocal, init_engine
from .migrations import run_migrations
from .pg_embedded import EmbeddedPostgres
from .routers import analytics, core, investments, planning, system
from .routers import transactions
from .security import TokenMiddleware
from .seed import seed_defaults
from .services.backup import auto_backup_if_due
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


def background_tasks(pg: EmbeddedPostgres | None, data_dir: Path) -> None:
    """Weekly automatic backup and daily exchange-rate update.

    Runs in a daemon thread after start-up; failures are logged only, so a
    missing internet connection never blocks the app.
    """
    if pg is not None:
        try:
            made = auto_backup_if_due(pg, data_dir)
            if made:
                log.info("Automatic backup created: %s", made.name)
        except Exception:
            log.exception("Automatic backup failed")
    try:
        with SessionLocal() as db:
            if auto_update_due(db):
                result = update_rates(db, base_currency(db), backfill=True)
                log.info("Exchange rates updated: %s", result)
    except Exception as exc:
        log.warning("Automatic exchange-rate update skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pg = None
    if settings.pg_bin:
        pg = EmbeddedPostgres(settings.pg_bin, settings.data_dir,
                              settings.pg_port)
        url = pg.start()
    else:
        url = settings.database_url
    engine = init_engine(url)
    version = run_migrations(engine)
    with SessionLocal() as db:
        seed_defaults(db, settings.base_currency_default)
    log.info("Database ready (schema v%s)", version)
    app.state.pg = pg
    if settings.background_tasks:
        threading.Thread(target=background_tasks,
                         args=(pg, settings.data_dir), daemon=True).start()
    try:
        yield
    finally:
        engine.dispose()
        if pg is not None:
            pg.stop()


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

    for module in (system, core, transactions, planning, investments,
                   analytics):
        app.include_router(module.router)
    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist,
                                   html=True), name="ui")
    else:
        log.warning("Frontend build not found at %s; serving API only.",
                    settings.frontend_dist)
    return app


app = create_app()
