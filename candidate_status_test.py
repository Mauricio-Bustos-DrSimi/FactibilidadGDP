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
from app.database import (  # noqa: E402
    SessionLocal,
    init_db,
    migrate_rejected_candidates_to_observation,
)
from app.main import (  # noqa: E402
    _candidate_out,
    _candidate_commune_locations,
    _candidate_requested_by,
    _ensure_project_variables_allowed,
    _project_sheet_variables,
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

processed.display_data["CorreoSolicitante"] = "ADMJennifer@porunpaismejor.com.mx"
assert _candidate_requested_by(processed) == "Sucursal"
assert _candidate_out(db, processed).requested_by == "Sucursal"
processed.display_data["CorreoSolicitante"] = "franmauricio@porunpaismejor.com.mx"
assert _candidate_requested_by(processed) == "Franquicia"
processed.display_data["CorreoSolicitante"] = "aypcelia@porunpaismejor.com.mx"
assert _candidate_requested_by(processed) == "Arriendos"
processed.display_data["CorreoSolicitante"] = "sin-categoria@example.com"
assert _candidate_requested_by(processed) is None

# The sheet always takes MT2 and ValorArriendo from CANDIDATE_DISPLAY_COLUMNS.
processed.display_data = {
    **processed.display_data,
    "MT2": 85.5,
    "ValorArriendo": "72 UF",
}
processed.project_variables = models.CandidateProjectVariables(
    mt2=60,
    valor_arriendo="50 UF",
)
sheet_variables = _project_sheet_variables(processed)
assert sheet_variables["mt2"] == 85.5
assert sheet_variables["valor_arriendo"] == "72 UF"

processed.display_data = {**processed.display_data, "CUT": 13101}
db.add_all(
    [
        models.BusinessLocation(
            name="LOCAL UNO",
            lat=-33.4,
            lng=-70.6,
            attributes={
                "_source_table": "LocalesSimi",
                "CUT": "13101.0",
                "CveUnidad": "CL0001",
                "Unidad": "LOCAL UNO",
                "Estatus": "ABIERTA",
            },
        ),
        models.BusinessLocation(
            name="OTRA COMUNA",
            lat=-33.5,
            lng=-70.7,
            attributes={"_source_table": "LocalesSimi", "CUT": "13102"},
        ),
    ]
)
db.commit()
commune_locations = _candidate_commune_locations(db, processed)
assert commune_locations == [
    {"CveUnidad": "CL0001", "Unidad": "LOCAL UNO", "Estatus": "ABIERTA"}
]

# Legacy rejected rows are moved from projection 690 onward only.
legacy_689 = models.LocationCandidate(
    project_id=project.project_id,
    display_data={"ID Proyección": 689},
    status=workflow.REJECTED,
    workflow_group=workflow.REJECTED,
)
legacy_690 = models.LocationCandidate(
    project_id=project.project_id,
    display_data={"ID Proyección": "690.0"},
    status=workflow.REJECTED,
    workflow_group=workflow.REJECTED,
)
legacy_700 = models.LocationCandidate(
    project_id=project.project_id,
    display_data={"ID": 700},
    status=workflow.REJECTED,
    workflow_group=workflow.REJECTED,
)
db.add_all([legacy_689, legacy_690, legacy_700])
db.commit()
assert migrate_rejected_candidates_to_observation(db) == 2
assert workflow.candidate_group(db, legacy_689) == "rejected"
assert workflow.candidate_group(db, legacy_690) == "observation"
assert workflow.candidate_group(db, legacy_700) == "observation"

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

# A user decision takes precedence over the source ESTATUS on later syncs.
processed.status = workflow.REJECTED
processed.workflow_group = workflow.REJECTED
processed.last_action = "reject"
db.commit()
_upsert_candidate_records(db, [record("P-1", "RECHAZADO")], project.project_id)
db.commit()
assert workflow.candidate_group(db, processed) == "rejected"

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
observed.status = workflow.OPENING
observed.workflow_group = workflow.OPENING
db.commit()
_ensure_project_variables_allowed(db, observed, coordinator)
try:
    _ensure_project_variables_allowed(db, observed, committee)
    raise AssertionError("Only Coordinador should edit project variables")
except HTTPException as exc:
    assert exc.status_code == 403

db.close()
print("CANDIDATE STATUS TESTS PASSED")
