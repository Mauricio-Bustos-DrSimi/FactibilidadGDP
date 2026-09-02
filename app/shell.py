"""Application Shell HTTP boundary and versioned frontend entry point."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


class ApplicationShell:
    """Serve the shared browser shell without depending on GDP or Factibilidad."""

    versioned_assets = (
        "shell.js",
        "gdp.js",
        "factibilidad.js",
        "app.js",
        "onboarding.js",
        "style.css",
    )

    def __init__(self, static_dir: Path, *, google_maps_api_key: str) -> None:
        self.static_dir = static_dir
        self.google_maps_api_key = google_maps_api_key

    def asset_version(self, filename: str) -> str:
        try:
            return str(int((self.static_dir / filename).stat().st_mtime))
        except OSError:
            return "0"

    def render_index(self) -> HTMLResponse:
        html = (self.static_dir / "index.html").read_text(encoding="utf-8")
        for name in self.versioned_assets:
            html = re.sub(
                rf"/static/{re.escape(name)}(?:\?v=[^\"'>\s]*)?",
                f"/static/{name}?v={self.asset_version(name)}",
                html,
            )
        return HTMLResponse(html)

    def frontend_config(self) -> dict[str, str]:
        return {"google_maps_api_key": self.google_maps_api_key}

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/")
        def index():
            return self.render_index()

        @router.get("/ID={projection_id}")
        def index_projection(projection_id: str):
            return self.render_index()

        @router.get("/config")
        def get_config():
            return self.frontend_config()

        return router


__all__ = ["ApplicationShell"]
