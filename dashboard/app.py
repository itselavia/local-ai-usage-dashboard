from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import PACKAGE_DIR
from . import config
from .routes import router


TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def create_app(db_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="Local AI Usage Dashboard")
    resolved_db_path = db_path or os.environ.get("LOCAL_AI_USAGE_DASHBOARD_DB") or config.default_db_path()
    app.state.db_path = Path(resolved_db_path).expanduser()
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)
    return app


app = create_app()
