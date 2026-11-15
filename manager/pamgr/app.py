"""FastAPI アプリ。画面（static/）と API（/api/...）を出す。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import router

STATIC = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Pair Agent Manager", version=__version__)
    app.include_router(router, prefix="/api")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.on_event("startup")
    def _start_resident() -> None:      # 常駐を入れてあれば、起動と同時に点検を回す
        from . import resident, settings
        if settings.get().get("resident_enabled"):
            resident.start()

    return app
