from __future__ import annotations

from dataclasses import replace
import uuid

import pytest
from fastapi.testclient import TestClient

from app import main
from tests.characterization.support import login, seed_candidate, seed_user


app = main.app


def test_login_session_and_logout_http_contract():
    with TestClient(app) as client:
        assert client.get("/me").status_code == 401

        login = client.post(
            "/auth/login",
            json={
                "email": "characterization-admin@example.test",
                "password": "characterization-admin-password",
            },
        )

        assert login.status_code == 200
        assert login.json() == {
            "id": login.json()["id"],
            "email": "characterization-admin@example.test",
            "name": "System Administrator",
            "role": "sysadmin",
            "commercial_division": None,
            "job_title": None,
            "supervisor_emails": None,
            "org_x": None,
            "org_y": None,
            "active": True,
        }
        assert "factibilidad_session=" in login.headers["set-cookie"]
        assert client.get("/me").json() == login.json()

        logout = client.post("/auth/logout")
        assert logout.status_code == 200
        assert logout.json() == {"ok": True}
        assert client.get("/me").status_code == 401


def test_application_shell_exposes_both_modules_and_gdp_views():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for visible_contract in (
        'id="gestorModuleBtn"',
        'id="factibilityModuleBtn"',
        'id="toggleViewBtn"',
        'id="tableViewBtn"',
        'id="funnelBtn"',
        'id="factibilityView"',
    ):
        assert visible_contract in response.text


def test_factibility_access_is_limited_to_sysadmin_and_assigned_user():
    denied_email = f"denied-{uuid.uuid4().hex}@example.test"
    seed_user(denied_email, "denied-password")
    seed_user(
        "admjennifer@porunpaismejor.com.mx",
        "assigned-password",
    )

    with TestClient(app) as denied:
        login(denied, denied_email, "denied-password")
        response = denied.get("/factibilidad/locations")
        assert response.status_code == 403
        assert response.json()["detail"].startswith("Acceso denegado")

    with TestClient(app) as assigned:
        login(
            assigned,
            "admjennifer@porunpaismejor.com.mx",
            "assigned-password",
        )
        assert assigned.get("/factibilidad/locations").status_code == 200

    with TestClient(app) as administrator:
        login(
            administrator,
            "characterization-admin@example.test",
            "characterization-admin-password",
        )
        assert administrator.get("/factibilidad/locations").status_code == 200


def test_gdp_candidate_query_comment_and_funnel_contract(monkeypatch: pytest.MonkeyPatch):
    candidate = seed_candidate(projection_id=990101, group="pending")
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, shadow_mode=False, email_delivery_enabled=False),
    )

    with TestClient(app) as client:
        login(
            client,
            "characterization-admin@example.test",
            "characterization-admin-password",
        )
        detail = client.get(f"/candidates/{candidate.id}")
        funnel = client.get("/funnel/baseline")
        comment = client.post(
            f"/candidates/{candidate.id}/comment",
            json={"note": "Comentario de caracterización GDP"},
        )
        history = client.get(f"/candidates/{candidate.id}/reviews")

    assert detail.status_code == 200
    assert detail.json()["display_data"]["ID"] == 990101
    assert funnel.status_code == 200
    assert funnel.json()["max_projection_id"] >= 990101
    assert comment.status_code == 200
    assert comment.json()["action"] == "comment"
    assert history.status_code == 200
    assert history.json()[-1]["note"] == "Comentario de caracterización GDP"


def test_factibility_checklist_progress_approvals_decision_and_sheet_contract():
    candidate = seed_candidate(projection_id=990201, group="opening")

    with TestClient(app) as client:
        login(
            client,
            "characterization-admin@example.test",
            "characterization-admin-password",
        )
        locations = client.get("/factibilidad/locations")
        assert locations.status_code == 200
        item = next(
            row for row in locations.json()
            if row["candidate"]["id"] == candidate.id
        )
        assert {group["area"] for group in item["task_groups"]} == {
            "legal",
            "arquitectura",
        }

        task = client.put(
            f"/factibilidad/locations/{candidate.id}/tasks/legal_recepcion_oportunidad",
            json={
                "status": "realizado",
                "comment": "Antecedentes recibidos",
            },
        )
        legal_approval = client.put(
            f"/factibilidad/locations/{candidate.id}/approvals/legal"
        )
        architecture_approval = client.put(
            f"/factibilidad/locations/{candidate.id}/approvals/arquitectura"
        )
        decision = client.put(
            f"/factibilidad/locations/{candidate.id}/decision",
            json={"decision": "completado"},
        )

        original_sheet = client.get(
            f"/factibilidad/locations/{candidate.id}/sales-sheet"
        )
        changed_values = original_sheet.json() | {
            "cve_unidad": "CLF9001",
            "unidad": "FICHA FACTIBILIDAD",
        }
        changed_sheet = client.put(
            f"/factibilidad/locations/{candidate.id}/sales-sheet",
            json=changed_values,
        )
        gdp_detail = client.get(f"/candidates/{candidate.id}")
        refreshed = client.get("/factibilidad/locations")

    assert task.status_code == 200
    assert task.json()["status"] == "realizado"
    assert task.json()["comment"] == "Antecedentes recibidos"
    assert task.json()["completed_at"] is not None
    assert legal_approval.status_code == 200
    assert legal_approval.json()["area"] == "legal"
    assert architecture_approval.status_code == 200
    assert architecture_approval.json()["area"] == "arquitectura"
    assert decision.status_code == 200
    assert decision.json()["decision"] == "completado"
    assert original_sheet.status_code == 200
    assert changed_sheet.status_code == 200
    assert changed_sheet.json()["unidad"] == "FICHA FACTIBILIDAD"
    assert gdp_detail.json()["display_data"]["Unidad"] == "LOCAL 990201"

    refreshed_item = next(
        row for row in refreshed.json()
        if row["candidate"]["id"] == candidate.id
    )
    legal_group = next(
        group for group in refreshed_item["task_groups"]
        if group["key"] == "legal_nuevo"
    )
    saved_task = next(
        row for row in legal_group["subtasks"]
        if row["key"] == "legal_recepcion_oportunidad"
    )
    assert legal_group["progress"] == 25
    assert saved_task["comment"] == "Antecedentes recibidos"
    assert set(refreshed_item["approvals"]) == {"legal", "arquitectura"}
    assert refreshed_item["decision"]["decision"] == "completado"
