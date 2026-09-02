from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app


def test_application_shell_serves_versioned_assets_and_existing_public_routes(
    tmp_path: Path,
):
    from app.shell import ApplicationShell

    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        '<script src="/static/shell.js"></script>'
        '<script src="/static/app.js?v=old"></script>',
        encoding="utf-8",
    )
    (static_dir / "shell.js").write_text("window.ApplicationShell = {};", encoding="utf-8")
    (static_dir / "app.js").write_text("", encoding="utf-8")

    shell = ApplicationShell(static_dir, google_maps_api_key="maps-key")
    application = FastAPI()
    application.include_router(shell.router())

    with TestClient(application) as client:
        root = client.get("/")
        projection = client.get("/ID=847")
        frontend_config = client.get("/config")

    assert {
        "root_status": root.status_code,
        "root_shell_asset": "/static/shell.js?v=" in root.text,
        "root_app_asset": "/static/app.js?v=" in root.text,
        "projection_status": projection.status_code,
        "projection_matches_root": projection.text == root.text,
        "config": frontend_config.json(),
    } == {
        "root_status": 200,
        "root_shell_asset": True,
        "root_app_asset": True,
        "projection_status": 200,
        "projection_matches_root": True,
        "config": {"google_maps_api_key": "maps-key"},
    }


def test_browser_entrypoint_loads_the_extracted_application_shell_module():
    with TestClient(app) as client:
        root = client.get("/")
        shell_module = client.get("/static/shell.js")

    assert root.status_code == 200
    assert 'src="/static/shell.js?v=' in root.text
    assert shell_module.status_code == 200
    assert "window.ApplicationShell" in shell_module.text
