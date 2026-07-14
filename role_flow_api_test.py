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
    users = (
        ("arriendo", workflow.ARRIENDO, None),
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
    db.add_all([own_pending, own_proposed])
    db.commit()
    candidate_id = candidate.id
    own_pending_id = own_pending.id
    own_proposed_id = own_proposed.id
    db.close()

arriendo = TestClient(app)
comite = TestClient(app)
general = TestClient(app)
coordinador = TestClient(app)
jefe_comercial = TestClient(app)
login(arriendo, "arriendo@role-flow.test", "test-password")
login(comite, "comite@role-flow.test", "test-password")
login(general, "general@role-flow.test", "test-password")
login(coordinador, "coordinador@role-flow.test", "test-password")
login(jefe_comercial, "jefecomercial@role-flow.test", "test-password")

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

print("ROLE FLOW API TESTS PASSED")
