"""Focused isolation tests for the Factibilidad module."""
import os
import base64
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


db_path = os.path.join(tempfile.gettempdir(), "factibilidad_gdp_test.db")
documents_path = os.path.join(tempfile.gettempdir(), "factibilidad_gdp_documents_test")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("SITE_SWIPER_DATABASE_URL", None)
os.environ["SITE_SWIPER_DB"] = db_path
os.environ["PROJECTION_DOCUMENTS_DIR"] = documents_path
os.environ["POSTGRES_AUTO_SYNC"] = "false"
if os.path.exists(db_path):
    os.remove(db_path)
shutil.rmtree(documents_path, ignore_errors=True)

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
assert inspector.has_table("factibilidad_visto_bueno_local")
assert inspector.get_foreign_keys("factibilidad_tarea_local") == []
assert inspector.get_foreign_keys("factibilidad_decision_local") == []
assert inspector.get_foreign_keys("factibilidad_visto_bueno_local") == []

db = SessionLocal()
user = models.User(
    email="factibilidad@example.com",
    name="Factibilidad",
    password_hash=auth.hash_password("factibilidad-test"),
    role="sysadmin",
)
allowed_user = models.User(
    email="admjennifer@porunpaismejor.com.mx",
    name="Jennifer",
    password_hash=auth.hash_password("factibilidad-allowed"),
    role="arriendo",
)
denied_user = models.User(
    email="sinpermiso@example.com",
    name="Sin permiso",
    password_hash=auth.hash_password("factibilidad-denied"),
    role="arriendo",
)
project = models.Project(name="Factibilidad test")
db.add_all([user, allowed_user, denied_user, project])
db.flush()

opening = models.LocationCandidate(
    project_id=project.project_id,
    display_data={
        "ID Proyección": 900,
        "DIRECCION": "Local de prueba",
        "DIVISION": "FRANQUICIA",
    },
    status="locales_proyecto",
    workflow_group="opening",
    current_stage="done",
    project_at=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
)
opening.project_variables = models.CandidateProjectVariables(
    cve_unidad="CL0600",
    unidad="PIRQUE",
    contacto_nombre="Contacto Legal",
    contacto_telefono="+56 9 1111 2222",
    contacto_email="contacto@example.com",
    flujo_franquicia="SUBARRIENDO",
    franquiciado_nombre="Franquiciado Ejemplo",
    franquiciado_telefono="+56 9 3333 4444",
    franquiciado_email="franquiciado@example.com",
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
assert locations[0]["candidate"].project_variables["cve_unidad"] == "CL0600"
assert locations[0]["candidate"].project_variables["unidad"] == "PIRQUE"
assert locations[0]["candidate"].approved_division == "FRANQUICIA"
assert locations[0]["candidate"].project_variables["flujo_franquicia"] == "SUBARRIENDO"
assert len(locations[0]["task_groups"]) == 16
assert {group["area"] for group in locations[0]["task_groups"]} == {"legal", "arquitectura"}
assert sum(len(group["subtasks"]) for group in locations[0]["task_groups"]) == 83
assert locations[0]["task_groups"][0]["title"] == "Ingreso del local"
assert locations[0]["task_groups"][1]["title"] == "Creación del expediente único del local y contrato"
assert all(
    task["key"] != "legal_crear_expediente"
    for group in locations[0]["task_groups"]
    for task in group["subtasks"]
)
assert all(group["progress"] == 0 for group in locations[0]["task_groups"])
assert locations[0]["approvals"] == {}

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
    assert client.get("/factibilidad/sync-version").status_code == 200
    library_url = f"/factibilidad/locations/{opening.id}/groups/legal_nuevo/attachments"
    uploaded = client.post(
        library_url,
        files=[
            ("files", ("fachada.png", b"\x89PNG\r\n\x1a\ncontenido", "image/png")),
            ("files", ("plano_local.dwg", b"AC1032-plano", "application/vnd.dwg")),
        ],
    )
    assert uploaded.status_code == 200, uploaded.text
    assert {item["name"] for item in uploaded.json()} == {"fachada.png", "plano_local.dwg"}
    library_folder = (
        Path(documents_path) / "Factibilidad" / "Proyeccion900" / "legal" / "legal_nuevo"
    )
    assert (library_folder / "fachada.png").is_file()
    assert (library_folder / "plano_local.dwg").is_file()
    consolidated = client.get(f"/factibilidad/locations/{opening.id}/attachments")
    assert consolidated.status_code == 200
    assert len(consolidated.json()) == 16
    legal_library = next(group for group in consolidated.json() if group["key"] == "legal_nuevo")
    assert legal_library["area"] == "legal"
    assert {item["name"] for item in legal_library["files"]} == {
        "fachada.png",
        "plano_local.dwg",
    }
    downloaded = client.get(f"{library_url}/plano_local.dwg")
    assert downloaded.status_code == 200
    assert downloaded.content == b"AC1032-plano"
    assert client.get(
        f"/factibilidad/locations/{opening.id}/groups/grupo_inexistente/attachments"
    ).status_code == 404
    deleted = client.delete(f"{library_url}/fachada.png")
    assert deleted.status_code == 200
    assert [item["name"] for item in deleted.json()] == ["plano_local.dwg"]

    client.post("/auth/logout")
    denied_login = client.post(
        "/auth/login",
        json={"email": denied_user.email, "password": "factibilidad-denied"},
    )
    assert denied_login.status_code == 200
    assert client.get("/factibilidad/locations").status_code == 403
    assert client.get("/factibilidad/sync-version").status_code == 403

    client.post("/auth/logout")
    allowed_login = client.post(
        "/auth/login",
        json={"email": allowed_user.email, "password": "factibilidad-allowed"},
    )
    assert allowed_login.status_code == 200
    legal_approval_url = f"/factibilidad/locations/{opening.id}/approvals/legal"
    legal_approval = client.put(legal_approval_url)
    assert legal_approval.status_code == 200, legal_approval.text
    assert legal_approval.json()["area"] == "legal"
    original_approval_date = legal_approval.json()["approved_at"]
    repeated_approval = client.put(legal_approval_url)
    assert repeated_approval.status_code == 200
    assert repeated_approval.json()["approved_at"] == original_approval_date
    architecture_approval = client.put(
        f"/factibilidad/locations/{opening.id}/approvals/arquitectura"
    )
    assert architecture_approval.status_code == 200
    assert client.put(
        f"/factibilidad/locations/{opening.id}/approvals/otra"
    ).status_code == 422
    refreshed_location = client.get("/factibilidad/locations").json()[0]
    assert set(refreshed_location["approvals"]) == {"legal", "arquitectura"}
    sales_sheet_url = f"/factibilidad/locations/{opening.id}/sales-sheet"
    initial_sheet = client.get(sales_sheet_url)
    assert initial_sheet.status_code == 200
    assert initial_sheet.json()["cve_unidad"] == "CL0600"
    edited_sheet = dict(initial_sheet.json())
    edited_sheet["cve_unidad"] = "CL0999"
    edited_sheet["unidad"] = "COPIA FACTIBILIDAD"
    saved_sheet = client.put(sales_sheet_url, json=edited_sheet)
    assert saved_sheet.status_code == 200, saved_sheet.text
    assert saved_sheet.json()["cve_unidad"] == "CL0999"
    sales_sheet_path = Path(documents_path) / "Factibilidad" / "Proyeccion900" / "ficha_ventas.json"
    assert sales_sheet_path.is_file()
    factibility_pdf = client.get(f"{sales_sheet_url}.pdf")
    assert factibility_pdf.status_code == 200
    assert factibility_pdf.content.startswith(b"%PDF")
    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    sheet_images_url = f"{sales_sheet_url}/images"
    uploaded_images = client.post(
        sheet_images_url,
        files=[
            ("files", ("fachada.png", image_bytes, "image/png")),
            ("files", ("interior.png", image_bytes, "image/png")),
        ],
    )
    assert uploaded_images.status_code == 200, uploaded_images.text
    assert len(uploaded_images.json()) == 2
    too_many_images = client.post(
        sheet_images_url,
        files=[("files", ("tercera.png", image_bytes, "image/png"))],
    )
    assert too_many_images.status_code == 400
    assert "máximo de dos" in too_many_images.json()["detail"]
    assert client.get(uploaded_images.json()[0]["url"]).content == image_bytes
    pdf_with_images = client.get(f"{sales_sheet_url}.pdf")
    assert pdf_with_images.status_code == 200
    assert pdf_with_images.content.startswith(b"%PDF")
    deleted_image = client.delete(f"{sheet_images_url}/fachada.png")
    assert deleted_image.status_code == 200
    assert len(deleted_image.json()) == 1
    db.expire_all()
    assert db.get(models.LocationCandidate, opening.id).project_variables.cve_unidad == "CL0600"

index_html = Path("app/static/index.html").read_text(encoding="utf-8")
app_javascript = Path("app/static/app.js").read_text(encoding="utf-8")
assert 'id="gestorModuleBtn"' in index_html
assert 'id="factibilityModuleBtn"' in index_html
assert 'id="factibilityViewBtn"' not in index_html
assert 'data-factibility-area="legal"' in index_html
assert 'data-factibility-area="arquitectura"' in index_html
assert 'id="factibilitySidebarDivision"' in index_html
assert 'id="moduleBackBtn"' in index_html
assert 'id="funnelPanel"' in index_html
assert 'id="factibilityAttachmentsModal"' in index_html
assert 'id="factibilityLocalLibraryModal"' in index_html
assert "async function startFactibilityApp(user)" in app_javascript
assert "title: `ID ${projectionId}`" in app_javascript
assert 'return started ? "en_proceso" : "pendiente"' in app_javascript
assert "function renderFunnel()" in app_javascript
assert "Biblioteca del local" in app_javascript
assert "Adjuntar / ver archivos" in app_javascript
assert "Editar ficha" in app_javascript
assert "Vista previa de ficha" in app_javascript
assert 'id="factibilitySearchInput"' in index_html
assert 'id="factibilitySortSelect"' in index_html
assert 'id="factibilitySidebarProjectDate"' in index_html
assert 'id="factibilitySidebarApprovals"' in index_html
assert 'id="factibilityApprovalConfirmModal"' in index_html
assert 'id="factibilitySheetImageInput"' in index_html
assert "function visibleFactibilityLocations()" in app_javascript
assert "function svgFileAsPng(file)" in app_javascript
assert "async function saveFactibilityApproval" in app_javascript
assert "¿Estás seguro de asignar el visto bueno" in app_javascript
assert "function requestFactibilityApprovalConfirmation" in app_javascript
assert "desde notificación de proyecto" in app_javascript
assert "{${delta}}" not in app_javascript
assert "admjennifer@porunpaismejor.com.mx" in app_javascript
assert "setInterval(pollFactibilityChanges, 2000)" in app_javascript
assert 'event.key !== "Enter" || event.shiftKey' in app_javascript
table_function = app_javascript.split("async function openCandidateTable()", 1)[1].split(
    "function closeCandidateTable()", 1
)[0]
assert "closeFactibilityView()" not in table_function
assert '$("candidateTableView").classList.remove("hidden")' in table_function
assert "State.map?.getCenter?.()?.toJSON?.()" in app_javascript

original_state = (opening.status, opening.workflow_group, opening.current_stage)
task_result = update_factibility_task(
    candidate_id=opening.id,
    task_key="legal_recepcion_oportunidad",
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
    task_key="arquitectura_recibir_solicitud",
    payload=schemas.FactibilityTaskUpdate(status="no_aplica"),
    db=db,
    user=user,
)

locations = list_factibility_locations(db=db, _=user)
legal_new = next(group for group in locations[0]["task_groups"] if group["key"] == "legal_nuevo")
architecture_new = next(
    group
    for group in locations[0]["task_groups"]
    if group["key"] == "arquitectura_ingreso_asignacion"
)
assert legal_new["completed"] == 1
assert legal_new["progress"] == 25
assert architecture_new["completed"] == 1
assert architecture_new["progress"] == 20

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
shutil.rmtree(documents_path, ignore_errors=True)
print("factibility_test: OK")
