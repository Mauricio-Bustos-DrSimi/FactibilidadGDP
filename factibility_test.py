"""Focused isolation tests for the Factibilidad module."""
import os
import tempfile


db_path = os.path.join(tempfile.gettempdir(), "factibilidad_gdp_test.db")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("SITE_SWIPER_DATABASE_URL", None)
os.environ["SITE_SWIPER_DB"] = db_path
os.environ["POSTGRES_AUTO_SYNC"] = "false"
if os.path.exists(db_path):
    os.remove(db_path)

from sqlalchemy import inspect, select  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, models, schemas  # noqa: E402
from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.main import (  # noqa: E402
    app,
    list_factibility_locations,
    update_factibility_decision,
    update_factibility_task,
)


init_db()
inspector = inspect(engine)
assert inspector.has_table("factibilidad_tarea_local")
assert inspector.has_table("factibilidad_decision_local")
assert inspector.get_foreign_keys("factibilidad_tarea_local") == []
assert inspector.get_foreign_keys("factibilidad_decision_local") == []

db = SessionLocal()
user = models.User(
    email="factibilidad@example.com",
    name="Factibilidad",
    password_hash=auth.hash_password("factibilidad-test"),
    role="sysadmin",
)
project = models.Project(name="Factibilidad test")
db.add_all([user, project])
db.flush()

opening = models.LocationCandidate(
    project_id=project.project_id,
    display_data={"ID Proyección": 900, "DIRECCION": "Local de prueba"},
    status="locales_proyecto",
    workflow_group="opening",
    current_stage="done",
)
approved = models.LocationCandidate(
    project_id=project.project_id,
    display_data={"ID Proyección": 899},
    status="aprobado",
    workflow_group="approved",
    current_stage="done",
)
db.add_all([opening, approved])
db.commit()

locations = list_factibility_locations(db=db, _=user)
assert user.role == "sysadmin"  # Admin can load the complete Factibilidad view.
assert len(locations) == 1
assert locations[0]["candidate"].id == opening.id
assert len(locations[0]["task_groups"]) == 3
assert all(len(group["subtasks"]) == 5 for group in locations[0]["task_groups"])
assert all(group["progress"] == 0 for group in locations[0]["task_groups"])

with TestClient(app) as client:
    login = client.post(
        "/auth/login",
        json={"email": user.email, "password": "factibilidad-test"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "sysadmin"
    response = client.get("/factibilidad/locations")
    assert response.status_code == 200
    assert len(response.json()) == 1

original_state = (opening.status, opening.workflow_group, opening.current_stage)
task_result = update_factibility_task(
    candidate_id=opening.id,
    task_key="levantamiento_terreno",
    payload=schemas.FactibilityTaskUpdate(
        status="realizado",
        comment="Levantamiento validado",
    ),
    db=db,
    user=user,
)
assert task_result["status"] == "realizado"
assert task_result["comment"] == "Levantamiento validado"

update_factibility_task(
    candidate_id=opening.id,
    task_key="factibilidad_servicios",
    payload=schemas.FactibilityTaskUpdate(status="no_aplica"),
    db=db,
    user=user,
)

locations = list_factibility_locations(db=db, _=user)
technical = locations[0]["task_groups"][0]
assert technical["completed"] == 2
assert technical["progress"] == 40

decision_result = update_factibility_decision(
    candidate_id=opening.id,
    payload=schemas.FactibilityDecisionUpdate(decision="rechazado"),
    db=db,
    user=user,
)
assert decision_result["decision"] == "rechazado"

db.refresh(opening)
assert (opening.status, opening.workflow_group, opening.current_stage) == original_state
assert db.scalars(select(models.Review).where(models.Review.candidate_id == opening.id)).all() == []
assert db.scalar(
    select(models.FactibilityLocationDecision).where(
        models.FactibilityLocationDecision.candidate_id == opening.id
    )
).decision == "rechazado"

db.close()
engine.dispose()
print("factibility_test: OK")
