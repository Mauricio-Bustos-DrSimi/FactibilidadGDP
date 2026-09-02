from __future__ import annotations

from fastapi.testclient import TestClient

from app import main
from app.factibilidad import FactibilityService
from tests.characterization.support import login, seed_candidate


def test_factibility_public_module_preserves_location_contract():
    candidate = seed_candidate(projection_id=990701, group="opening")

    assert isinstance(main.factibility_service, FactibilityService)
    with TestClient(main.app) as client:
        login(
            client,
            "characterization-admin@example.test",
            "characterization-admin-password",
        )
        response = client.get("/factibilidad/locations")

    assert response.status_code == 200
    location = next(
        item for item in response.json() if item["candidate"]["id"] == candidate.id
    )
    assert location["candidate"]["display_data"]["ID"] == 990701
    assert {group["area"] for group in location["task_groups"]} == {
        "legal",
        "arquitectura",
    }


def test_factibility_frontend_is_served_as_an_independent_module():
    with TestClient(main.app) as client:
        index = client.get("/")
        module = client.get("/static/factibilidad.js")

    assert index.status_code == 200
    assert '/static/factibilidad.js?v=' in index.text
    assert module.status_code == 200
    assert "global.FactibilityModule" in module.text
