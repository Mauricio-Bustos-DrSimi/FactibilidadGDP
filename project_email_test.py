"""Focused tests for project email plans and full/reduced templates."""
import os
import tempfile

from fastapi import HTTPException


db_path = os.path.join(tempfile.gettempdir(), "ss_project_email.db")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("SITE_SWIPER_DATABASE_URL", None)
os.environ["SITE_SWIPER_DB"] = db_path
os.environ["POSTGRES_AUTO_SYNC"] = "false"
if os.path.exists(db_path):
    os.remove(db_path)

from app import models, workflow  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import (  # noqa: E402
    FRANCHISE_ORIGIN_EMAIL,
    SUCURSAL_ORIGIN_EMAIL,
    _normalize_project_email_addresses,
    _project_email_body,
    _project_email_plans,
)


init_db()
db = SessionLocal()
project = models.Project(name="Email plans")
db.add(project)
db.flush()


def approved_candidate(source_id: str, division: str, applicant: str) -> models.LocationCandidate:
    candidate = models.LocationCandidate(
        project_id=project.project_id,
        display_data={
            "ID": source_id,
            "DIVISION": division,
            "CorreoSolicitante": applicant,
            "DIRECCIÓN": "AVENIDA SIEMPRE VIVA 123",
        },
        status=workflow.PROJECT,
        workflow_group=workflow.PROJECT,
    )
    db.add(candidate)
    db.flush()
    return candidate


base_values = {
    "cve_unidad": "CL9000",
    "unidad": "LOCAL PRUEBA",
    "comuna": "SANTIAGO",
    "provincia": "SANTIAGO",
    "region": "METROPOLITANA DE SANTIAGO",
    "mt2": 120,
    "valor_arriendo": "100 UF",
    "gastos_comunes": "10 UF",
    "contacto_nombre": "CONTACTO",
    "contacto_telefono": "+56911111111",
    "contacto_email": "contacto@example.com",
}

sucursal = approved_candidate("S-1", "SUCURSAL", "solicitante@example.com")
sucursal_plans = _project_email_plans(db, sucursal, base_values)
assert [plan["plan_id"] for plan in sucursal_plans] == [
    "sucursal_legal",
    "sucursal_reducido",
]
assert all(plan["from_email"] == SUCURSAL_ORIGIN_EMAIL for plan in sucursal_plans)
assert sucursal_plans[0]["recipients"] == [
    "curibe@farmaciasdoctorsimi.cl",
    "arriendos@farmaciasdoctorsimi.cl",
    "jvasquez@farmaciasdoctorsimi.cl",
]
assert "VALOR" in sucursal_plans[0]["html_body"]
assert "MTS2 LOCAL" in sucursal_plans[1]["html_body"]
assert "VALOR" not in sucursal_plans[1]["html_body"]
assert "CONTACTO" in sucursal_plans[1]["html_body"]
assert "contacto@example.com" in sucursal_plans[1]["html_body"]
assert "SOLICITAR CON CELIA FOLSCH" not in sucursal_plans[1]["html_body"]
assert "Jennifer Villavicencio" in sucursal_plans[0]["html_body"]
assert "Coordinadora de Proyecto" in sucursal_plans[0]["html_body"]
assert "GARANTIA" not in sucursal_plans[0]["html_body"]
assert "MESES DE GRACIA" not in sucursal_plans[0]["html_body"]
sucursal_text = _project_email_body(
    sucursal,
    base_values,
    signature_name=sucursal_plans[0]["signature_name"],
    signature_title=sucursal_plans[0]["signature_title"],
)
assert "Jennifer Villavicencio\nCoordinadora de Proyecto" in sucursal_text
assert "GARANTIA:" not in sucursal_text

franchise = approved_candidate("F-1", "FRANQUICIA", "franowner@example.com")
franchise_values = {
    **base_values,
    "franquiciado_nombre": "PERSONA FRANQUICIADA",
    "franquiciado_telefono": "+56922222222",
    "franquiciado_email": "franquiciado@example.com",
}

direct_plans = _project_email_plans(
    db,
    franchise,
    {**franchise_values, "flujo_franquicia": "FRANQUICIADO DIRECTO"},
)
assert len(direct_plans) == 1
assert direct_plans[0]["from_email"] == FRANCHISE_ORIGIN_EMAIL
assert direct_plans[0]["recipients"] == [
    "mbustos@farmaciasdoctorsimi.cl",
    "rmalave@farmaciasdoctorsimi.cl",
]
assert direct_plans[0]["cc"] == ["franowner@example.com"]
assert "FRANQUICIADO" in direct_plans[0]["html_body"]
assert "Leonel Albornoz" in direct_plans[0]["html_body"]
assert "Coordinador de proyectos franquicias" in direct_plans[0]["html_body"]

direct_without_franchisee = _project_email_plans(
    db,
    franchise,
    {**base_values, "flujo_franquicia": "FRANQUICIADO DIRECTO"},
)
assert len(direct_without_franchisee) == 1
assert "FRANQUICIADO</b>" not in direct_without_franchisee[0]["html_body"]

try:
    _project_email_plans(
        db,
        franchise,
        {
            **base_values,
            "contacto_telefono": None,
            "flujo_franquicia": "FRANQUICIADO DIRECTO",
        },
    )
    raise AssertionError("Franchise email plans must require contact data")
except HTTPException as exc:
    assert exc.status_code == 400

sublease_plans = _project_email_plans(
    db,
    franchise,
    {**franchise_values, "flujo_franquicia": "SUBARRIENDO"},
)
assert [plan["plan_id"] for plan in sublease_plans] == [
    "subarriendo_legal",
    "subarriendo_arquitectura",
]
assert all(plan["from_email"] == FRANCHISE_ORIGIN_EMAIL for plan in sublease_plans)
assert sublease_plans[0]["recipients"] == [
    "cfolsch@farmaciasdoctorsimi.cl",
    "curibe@farmaciasdoctorsimi.cl",
]
assert sublease_plans[1]["recipients"] == ["ptarsetti@farmaciasdoctorsimi.cl"]
assert sublease_plans[1]["reduced"] is True
assert sublease_plans[1]["include_franchisee"] is True
assert "VALOR" not in sublease_plans[1]["html_body"]
assert "CONTACTO" in sublease_plans[1]["html_body"]
assert "FRANQUICIADO" in sublease_plans[1]["html_body"]
assert "PERSONA FRANQUICIADA" in sublease_plans[1]["html_body"]
sublease_architecture_text = _project_email_body(
    franchise,
    {**franchise_values, "flujo_franquicia": "SUBARRIENDO"},
    reduced=True,
    include_franchisee=True,
    signature_name=sublease_plans[1]["signature_name"],
    signature_title=sublease_plans[1]["signature_title"],
)
assert "FRANQUICIADO\nNOMBRE: PERSONA FRANQUICIADA" in sublease_architecture_text

assert _normalize_project_email_addresses(
    ["nuevo@example.com;COPIA@example.com", "nuevo@example.com"],
    "Para",
) == ["nuevo@example.com", "COPIA@example.com"]
try:
    _normalize_project_email_addresses(["correo-invalido"], "CC")
    raise AssertionError("Invalid manual email must be rejected")
except HTTPException as exc:
    assert exc.status_code == 400

db.close()
print("PROJECT EMAIL TESTS PASSED")
