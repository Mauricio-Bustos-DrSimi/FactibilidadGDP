"""API integration test for the approval and project-role flow."""
import os
import tempfile

db_path = os.path.join(tempfile.gettempdir(), "ss_role_flow_api.db")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("SITE_SWIPER_DATABASE_URL", None)
os.environ["SITE_SWIPER_DB"] = db_path
os.environ["POSTGRES_AUTO_SYNC"] = "false"
os.environ["SESSION_SECRET"] = "role-flow-test"
os.environ["SYSADMIN_EMAIL"] = "admin@role-flow.test"
os.environ["SYSADMIN_PASSWORD"] = "admin-password"
if os.path.exists(db_path):
    os.remove(db_path)

from fastapi.testclient import TestClient  # noqa: E402

from app import models, workflow  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


def login(client: TestClient, email: str, password: str) -> None:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


with TestClient(app) as admin:
    login(admin, "admin@role-flow.test", "admin-password")
    user_ids = {}
    users = (
        ("arriendo", workflow.ARRIENDO, None),
        ("gerente", workflow.GERENTE, None),
        ("comite", workflow.COMITE, None),
        ("general", workflow.GERENTE_GENERAL, None),
        ("coordinador", workflow.COORDINADOR, "SUCURSAL"),
        ("jefecomercial", workflow.JEFE_COMERCIAL, "SUCURSAL"),
    )
    for email_prefix, role, division in users:
        payload = {
            "email": f"{email_prefix}@role-flow.test",
            "name": email_prefix.title(),
            "password": "test-password",
            "role": role,
        }
        if division:
            payload["commercial_division"] = division
        if role == workflow.JEFE_COMERCIAL:
            payload["supervisor_emails"] = "supervisor@role-flow.test"
        response = admin.post("/users", json=payload)
        assert response.status_code == 200, response.text
        user_ids[role] = response.json()["id"]

    db = SessionLocal()
    project = models.Project(name="Role flow")
    db.add(project)
    db.flush()
    candidate = models.LocationCandidate(
        project_id=project.project_id,
        display_data={"ID": "FLOW-1", "DIVISION": "SUCURSAL"},
        status=workflow.PENDING,
        workflow_group=workflow.PENDING,
    )
    db.add(candidate)
    own_pending = models.LocationCandidate(
        project_id=project.project_id,
        display_data={
            "ID": "OWN-PENDING",
            "DIVISION": "SUCURSAL",
            "CorreoSolicitante": "jefecomercial@role-flow.test",
        },
        status=workflow.PENDING,
        workflow_group=workflow.PENDING,
    )
    own_proposed = models.LocationCandidate(
        project_id=project.project_id,
        display_data={
            "ID": "OWN-PROPOSED",
            "DIVISION": "SUCURSAL",
            "CorreoSolicitante": "JEFEComercial@role-flow.test",
        },
        status=workflow.APPROVED_FINAL,
        workflow_group=workflow.APPROVED_FINAL,
    )
    admin_approved = models.LocationCandidate(
        project_id=project.project_id,
        display_data={"ID": "ADMIN-APPROVED", "DIVISION": "SUCURSAL"},
        status=workflow.PROJECT,
        workflow_group=workflow.PROJECT,
    )
    db.add_all([own_pending, own_proposed, admin_approved])
    db.commit()
    candidate_id = candidate.id
    own_pending_id = own_pending.id
    own_proposed_id = own_proposed.id
    admin_approved_id = admin_approved.id
    db.close()

arriendo = TestClient(app)
gerente = TestClient(app)
comite = TestClient(app)
general = TestClient(app)
coordinador = TestClient(app)
jefe_comercial = TestClient(app)
login(arriendo, "arriendo@role-flow.test", "test-password")
login(gerente, "gerente@role-flow.test", "test-password")
login(comite, "comite@role-flow.test", "test-password")
login(general, "general@role-flow.test", "test-password")
login(coordinador, "coordinador@role-flow.test", "test-password")
login(jefe_comercial, "jefecomercial@role-flow.test", "test-password")

# Sysadmin can perform the Coordinator variable and activation workflow.
admin_actions = TestClient(app)
login(admin_actions, "admin@role-flow.test", "admin-password")
assert admin_actions.get(f"/candidates/{admin_approved_id}/project-variables").status_code == 200
response = admin_actions.put(
    f"/candidates/{admin_approved_id}/project-variables",
    json={
        "cve_unidad": "CLADMIN",
        "unidad": "LOCAL ADMIN",
        "region": "METROPOLITANA DE SANTIAGO",
        "comuna": "SANTIAGO",
    },
)
assert response.status_code == 200, response.text
response = admin_actions.post(
    f"/candidates/{admin_approved_id}/status",
    json={"group": "opening", "note": "Alta por sysadmin"},
)
assert response.status_code == 200, response.text
assert response.json()["candidate"]["workflow_group"] == "opening"

# Jefe Comercial can see their own pending/proposed locations, but cannot vote on them.
response = jefe_comercial.get("/candidates")
assert response.status_code == 200, response.text
visible_ids = {item["id"] for item in response.json()}
assert own_pending_id in visible_ids
assert own_proposed_id in visible_ids
response = jefe_comercial.post(
    f"/candidates/{own_pending_id}/review",
    json={"action": "like"},
)
assert response.status_code == 409, response.text

# Arriendo rejects a pending location and Gerente proposes it again.
response = arriendo.post(
    f"/candidates/{own_pending_id}/status",
    json={"group": "rejected", "note": "Antecedentes incompletos"},
)
assert response.status_code == 200, response.text
assert response.json()["candidate"]["workflow_group"] == "rejected"
response = gerente.post(
    f"/candidates/{own_pending_id}/status",
    json={"group": "proposed", "note": "Antecedentes corregidos"},
)
assert response.status_code == 200, response.text
assert response.json()["candidate"]["workflow_group"] == "proposed"

# Gerente General can omit a proposed location without changing its group.
response = general.post(
    f"/candidates/{own_proposed_id}/review",
    json={"action": "skip"},
)
assert response.status_code == 200, response.text
assert response.json()["candidate"]["workflow_group"] == "proposed"

response = arriendo.post(f"/candidates/{candidate_id}/status", json={"group": "proposed"})
assert response.status_code == 200, response.text
assert response.json()["candidate"]["workflow_group"] == "proposed"

response = comite.post(f"/candidates/{candidate_id}/status", json={"group": "approved"})
assert response.status_code == 200, response.text
assert response.json()["candidate"]["workflow_group"] == "approved"

assert comite.get(f"/candidates/{candidate_id}/project-variables").status_code == 403
assert coordinador.get(f"/candidates/{candidate_id}/project-variables").status_code == 200

variables = {
    "cve_unidad": "CL9999",
    "unidad": "LOCAL TEST",
    "region": "METROPOLITANA DE SANTIAGO",
    "comuna": "SANTIAGO",
}
response = coordinador.put(f"/candidates/{candidate_id}/project-variables", json=variables)
assert response.status_code == 200, response.text
response = coordinador.post(f"/candidates/{candidate_id}/status", json={"group": "opening"})
assert response.status_code == 200, response.text
assert response.json()["candidate"]["workflow_group"] == "opening"

response = general.post(
    f"/candidates/{candidate_id}/status",
    json={"group": "rejected", "note": "Dar de baja desde Proyectos"},
)
assert response.status_code == 200, response.text
assert response.json()["candidate"]["workflow_group"] == "rejected"

# Sysadmin can delete a Gerente General with history without losing the audit trail.
admin_delete = TestClient(app)
login(admin_delete, "admin@role-flow.test", "admin-password")
general_user_id = user_ids[workflow.GERENTE_GENERAL]
response = admin_delete.delete(f"/users/{general_user_id}")
assert response.status_code == 200, response.text
assert general_user_id not in {user["id"] for user in admin_delete.get("/users").json()}
assert general.post(
    "/auth/login",
    json={"email": "general@role-flow.test", "password": "test-password"},
).status_code == 401

db = SessionLocal()
deleted_general = db.get(models.User, general_user_id)
assert deleted_general is not None
assert deleted_general.deleted_at is not None and deleted_general.active is False
assert db.query(models.Review).filter(models.Review.reviewer_id == general_user_id).count() > 0
db.close()

response = admin_delete.post("/users", json={
    "email": "general@role-flow.test",
    "name": "General Reemplazo",
    "password": "replacement-password",
    "role": workflow.GERENTE_GENERAL,
})
assert response.status_code == 200, response.text

print("ROLE FLOW API TESTS PASSED")
