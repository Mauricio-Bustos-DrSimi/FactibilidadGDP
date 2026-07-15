"""Focused tests for source-status sync and project-variable permissions."""
import os
import tempfile


db_path = os.path.join(tempfile.gettempdir(), "ss_candidate_status.db")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("SITE_SWIPER_DATABASE_URL", None)
os.environ["SITE_SWIPER_DB"] = db_path
if os.path.exists(db_path):
    os.remove(db_path)

from app import models, workflow  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import (  # noqa: E402
    _candidate_out,
    _ensure_project_variables_allowed,
    _santiago_iso,
    _upsert_candidate_records,
)
from fastapi import HTTPException  # noqa: E402


def record(source_id: str, source_status: str, source_date: str = "2026-07-15T12:00:00") -> dict:
    return {
        "map_ref": None,
        "lat": None,
        "lng": None,
        "display_data": {"ID": source_id, "ESTATUS": source_status, "FECHA": source_date},
    }


init_db()
db = SessionLocal()
project = models.Project(name="Source status test")
db.add(project)
db.flush()

created, updated = _upsert_candidate_records(
    db,
    [record("P-1", "PROCESADO"), record("P-2", "RECHAZADO")],
    project.project_id,
)
db.commit()
assert (created, updated) == (2, 0)

processed, observed = db.query(models.LocationCandidate).order_by(models.LocationCandidate.id).all()
assert workflow.candidate_group(db, processed) == "pending"
assert workflow.candidate_group(db, observed) == "observation"
assert processed.rejected_at is None
assert observed.rejected_at is not None
assert _candidate_out(db, observed).workflow_dates["observation"] == "2026-07-15T08:00:00-04:00"
assert _santiago_iso("2026-01-15T12:00:00Z") == "2026-01-15T09:00:00-03:00"

# A normal refresh must preserve decisions made inside the app.
processed.status = workflow.APPROVED_FINAL
processed.workflow_group = workflow.APPROVED_FINAL
db.commit()
_upsert_candidate_records(db, [record("P-1", "PROCESADO")], project.project_id)
db.commit()
assert workflow.candidate_group(db, processed) == "proposed"

# Source changes in either direction are reflected in the corresponding tab.
_upsert_candidate_records(db, [record("P-1", "RECHAZADO")], project.project_id)
_upsert_candidate_records(db, [record("P-2", "PROCESADO")], project.project_id)
db.commit()
assert workflow.candidate_group(db, processed) == "observation"
assert workflow.candidate_group(db, observed) == "pending"
assert observed.rejected_at is None

coordinator = models.User(
    email="coordinator@test",
    name="Coordinator",
    password_hash="x",
    role=workflow.COORDINADOR,
)
committee = models.User(
    email="committee@test",
    name="Committee",
    password_hash="x",
    role=workflow.COMITE,
)
db.add_all([coordinator, committee])
observed.status = workflow.PROJECT
observed.workflow_group = workflow.PROJECT
db.commit()
_ensure_project_variables_allowed(db, observed, coordinator)
try:
    _ensure_project_variables_allowed(db, observed, committee)
    raise AssertionError("Only Coordinador should edit project variables")
except HTTPException as exc:
    assert exc.status_code == 403

db.close()
print("CANDIDATE STATUS TESTS PASSED")
