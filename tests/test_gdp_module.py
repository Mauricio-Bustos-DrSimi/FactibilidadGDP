from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from app import main
from app.gdp import GDPService
from tests.characterization.support import login, seed_candidate, seed_user


def test_gdp_public_module_preserves_candidate_query_contract():
    candidate = seed_candidate(projection_id=990601, group="pending")

    assert isinstance(main.gdp_service, GDPService)
    with TestClient(main.app) as client:
        login(
            client,
            "characterization-admin@example.test",
            "characterization-admin-password",
        )
        response = client.get(f"/candidates/{candidate.id}")

    assert response.status_code == 200, response.text
    assert response.json()["display_data"]["ID"] == 990601


def test_gdp_service_owns_status_and_review_commands():
    assert callable(getattr(main.gdp_service, "update_status"))
    assert callable(getattr(main.gdp_service, "submit_review"))


def test_gdp_review_command_preserves_http_response(monkeypatch):
    candidate = seed_candidate(projection_id=990602, group="pending")
    seed_user(
        "jef@local",
        "gdp-jefatura-password",
        role="jefatura",
    )
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, shadow_mode=False, email_delivery_enabled=False),
    )

    with TestClient(main.app) as client:
        login(client, "jef@local", "gdp-jefatura-password")
        response = client.post(
            f"/candidates/{candidate.id}/review",
            json={"action": "accept", "note": "Caracterización comando GDP"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["candidate"]["display_data"]["ID"] == 990602


def test_gdp_frontend_is_served_as_an_independent_module():
    with TestClient(main.app) as client:
        index = client.get("/")
        module = client.get("/static/gdp.js")

    assert index.status_code == 200
    assert '/static/gdp.js?v=' in index.text
    assert module.status_code == 200
    assert "global.GDPModule" in module.text
    assert "loadGoogleMaps" in module.text
    assert "StreetViewService" in module.text
    assert "renderFunnel" in module.text
