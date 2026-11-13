"""Entry point of ``pfi-api.exe`` (and of ``python run.py`` in development).

Examples
--------
Development (data in ``%LOCALAPPDATA%\\PersonalFinanceIntelligence`` or
``PFI_DATA_DIR``)::

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
    from app.main import app
    server = uvicorn.Server(uvicorn.Config(
        app, host=args.host, port=args.port, log_config=None))
    app.state.server = server
    server.run()


if __name__ == "__main__":
    main()
