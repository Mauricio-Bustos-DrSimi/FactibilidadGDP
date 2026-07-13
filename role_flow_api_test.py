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
    db.commit()
    candidate_id = candidate.id
    db.close()

arriendo = TestClient(app)
comite = TestClient(app)
general = TestClient(app)
coordinador = TestClient(app)
login(arriendo, "arriendo@role-flow.test", "test-password")
login(comite, "comite@role-flow.test", "test-password")
login(general, "general@role-flow.test", "test-password")
login(coordinador, "coordinador@role-flow.test", "test-password")

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
