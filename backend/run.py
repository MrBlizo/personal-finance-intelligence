"""Entry point of ``pfi-api.exe`` (and of ``python run.py`` in development).

Examples
--------
Development against your own PostgreSQL (settings from ``.env``)::

    python run.py --port 8765

Embedded PostgreSQL, as launched by PFI.exe::

    set PFI_PG_BIN=C:\\path\\to\\pgsql\\bin
    python run.py --port 8765
"""
import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Personal Finance Intelligence API server.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Interface to bind (keep 127.0.0.1 so the API "
                             "is not reachable from the network).")
    parser.add_argument("--port", type=int, default=8765,
                        help="TCP port of the API (default: 8765).")
    parser.add_argument("--log-file", type=Path, default=None,
                        help="Write logs to this file (rotated at 5 MB).")
    parser.add_argument("--selftest-legacy", type=Path, default=None,
                        metavar="DIR",
                        help="Create a PFI 0.3 PostgreSQL database in the "
                             "empty folder DIR, move it to SQLite with the "
                             "bundled PostgreSQL (PFI_PG_BIN) and check the "
                             "result, then exit. Used by the build.")
    args = parser.parse_args()
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(
            args.log_file, maxBytes=5_000_000, backupCount=3,
            encoding="utf-8"))
    logging.basicConfig(
        level=os.environ.get("PFI_LOG_LEVEL", "INFO"), handlers=handlers,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.selftest_legacy:
        import json
        from app import legacy
        from app.config import get_settings
        settings = get_settings()
        try:
            result = legacy.selftest(settings.pg_bin, args.selftest_legacy,
                                     settings.pg_relocate)
        except Exception as exc:  # report every failure to the build
            print(f"legacy self-test FAILED: {exc}")
            sys.exit(1)
        print("legacy self-test ok: " + json.dumps(result))
        return
    from app.main import app
    server = uvicorn.Server(uvicorn.Config(
        app, host=args.host, port=args.port, log_config=None))
    app.state.server = server
    server.run()


if __name__ == "__main__":
    main()
