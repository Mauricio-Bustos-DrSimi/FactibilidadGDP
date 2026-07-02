"""FastAPI application: API endpoints + static frontend."""
from __future__ import annotations

import csv
import io
import json
import asyncio
import logging
import os
import smtplib
import threading
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape as html_escape
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

# Load the project env file so GOOGLE_MAPS_API_KEY is available regardless of how the worker is spawned.
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env.example", override=True)

import secrets

import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import auth, ingestion, models, schemas, workflow
from app.database import SessionLocal, get_db, init_db

STATIC_DIR = Path(__file__).resolve().parent / "static"
IMAGE_DIR = Path(__file__).resolve().parent.parent / "image"
POSTGRES_SYNC_INTERVAL_SECONDS = int(os.getenv("POSTGRES_SYNC_INTERVAL_SECONDS", "1800"))
POSTGRES_AUTO_SYNC = os.getenv("POSTGRES_AUTO_SYNC", "true").lower() not in {"0", "false", "no"}
POSTGRES_SYNC_PROJECT_NAME = os.getenv("POSTGRES_SYNC_PROJECT_NAME", "Postgres Sync")
SMTP_SERVER = "192.168.100.31"
SMTP_PORT = 25
ORIGIN_EMAIL = "mbustos@farmaciasdoctorsimi.cl"
CORREO_COPIA = ["mbustos@farmaciasdoctorsimi.cl"]
logger = logging.getLogger("site_swiper")
postgres_sync_lock = threading.Lock()
SANTIAGO_TZ = ZoneInfo("America/Santiago")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # auto-create the configured database schema on first run
    # Ensure a sysadmin exists so a fresh install is usable.
    db = SessionLocal()
    try:
        auth.seed_sysadmin(db)
    finally:
        db.close()
    sync_task = None
    if POSTGRES_AUTO_SYNC:
        sync_task = asyncio.create_task(_postgres_sync_loop())
        app.state.postgres_sync_task = sync_task
    try:
        yield
    finally:
        if sync_task:
            sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await sync_task


app = FastAPI(title="Site Swiper", version="1.0.0", lifespan=lifespan)

# Signed-cookie sessions. SESSION_SECRET must be set in production; for local
# dev we fall back to a random per-process key (logs everyone out on restart).
_session_secret = os.environ.get("SESSION_SECRET")
if not _session_secret:
    _session_secret = secrets.token_urlsafe(32)
    print("WARNING: SESSION_SECRET not set â€” using an ephemeral key "
          "(sessions won't survive restart). Set SESSION_SECRET for production.")
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    https_only=False,  # set True behind HTTPS in production
    same_site="lax",
)


def _versioned_image_url(url: str | None) -> str | None:
    """Append a file mtime cache-buster for locally served image assets."""
    if not url or not url.startswith("/images/"):
        return url
    filename = url.split("?", 1)[0].removeprefix("/images/")
    image_path = IMAGE_DIR / filename
    if not image_path.exists():
        return url
    return f"{url.split('?', 1)[0]}?v={int(image_path.stat().st_mtime)}"


# --------------------------------------------------------------------------- #
# Auth endpoints
# --------------------------------------------------------------------------- #
@app.post("/auth/login", response_model=schemas.UserOut)
def login(
    payload: schemas.LoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = db.scalar(select(models.User).where(models.User.email == payload.email))
    if user is None or not user.active or not auth.verify_password(
        payload.password, user.password_hash
    ):
        raise HTTPException(401, "Invalid email or password")
    request.session[auth.SESSION_USER_KEY] = user.id
    if POSTGRES_AUTO_SYNC:
        background_tasks.add_task(_run_postgres_sync_once, "login")
    return user


@app.post("/auth/logout")
def logout(request: Request):
    request.session.pop(auth.SESSION_USER_KEY, None)
    return {"ok": True}


@app.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(auth.get_current_user)):
    return user


# --------------------------------------------------------------------------- #
# Config (exposes the Maps API key to the frontend; never hardcoded)
# --------------------------------------------------------------------------- #
@app.get("/config")
def get_config():
    return {
        "google_maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY", ""),
    }


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
@app.post("/projects", response_model=schemas.ProjectOut)
def create_project(
    payload: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_role("sysadmin")),
):
    project = models.Project(
        name=payload.name,
        project_url=payload.project_url,
        notes=payload.notes,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.get("/projects", response_model=list[schemas.ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.get_current_user),
):
    return db.scalars(select(models.Project).order_by(models.Project.created_at.desc())).all()


@app.get("/projects/{project_id}", response_model=schemas.ProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.get_current_user),
):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _parse_config(config: Optional[str]) -> schemas.IngestConfig:
    """Accept the ingest config as JSON or YAML in a form field."""
    if not config:
        return schemas.IngestConfig()
    try:
        data = json.loads(config)
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(config)
        except yaml.YAMLError as exc:  # pragma: no cover
            raise HTTPException(400, f"Could not parse config: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(400, "Config must be a mapping/object")
    return schemas.IngestConfig(**data)


@app.post("/projects/{project_id}/ingest", response_model=schemas.IngestResult)
async def ingest_project(
    project_id: str,
    file: UploadFile = File(...),
    config: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_role("sysadmin")),
):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    cfg = _parse_config(config)
    content = await file.read()
    try:
        df = ingestion.read_table(content, file.filename or "upload.csv")
    except Exception as exc:
        raise HTTPException(400, f"Could not read tabular file: {exc}")

    if df.empty:
        raise HTTPException(400, "Source file has no rows")

    # Prefer explicit Latitud/Longitud columns over a single map-reference column.
    lat_col, lng_col = ingestion.detect_latlon_columns(df)
    map_column: Optional[str] = None
    if lat_col and lng_col:
        coord_label = f"{lat_col} + {lng_col}"
        # If the file also has an address column, keep it as map_ref display.
        addr_lowered = {c.lower(): c for c in df.columns}
        map_column = (
            addr_lowered.get("dirección")
            or addr_lowered.get("direccion")
            or addr_lowered.get("address")
            or addr_lowered.get("direccion")
        )
    else:
        try:
            map_column = ingestion.resolve_map_column(df, cfg.map_column)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        coord_label = map_column
        lat_col = lng_col = None

    records, parsed, failed = ingestion.build_candidates(df, map_column, lat_col, lng_col)

    for rec in records:
        db.add(
            models.LocationCandidate(
                project_id=project_id,
                map_ref=rec["map_ref"],
                lat=rec["lat"],
                lng=rec["lng"],
                display_data=rec["display_data"],
                current_stage=workflow.JEFATURA,
                workflow_group=workflow.PENDING,
            )
        )
    project.source_file = file.filename
    db.commit()

    return schemas.IngestResult(
        project_id=project_id,
        rows_read=len(df),
        candidates_created=len(records),
        map_column=coord_label,
        parsed_coordinates=parsed,
        failed_coordinates=failed,
    )


# --------------------------------------------------------------------------- #
# Review queue + actions (role-scoped)
# --------------------------------------------------------------------------- #
def _review_out(r: models.Review) -> schemas.ReviewOut:
    return schemas.ReviewOut(
        id=r.id,
        candidate_id=r.candidate_id,
        stage=r.stage,
        action=r.action,
        note=r.note,
        created_at=r.created_at,
        reviewer_id=r.reviewer_id,
        reviewer_name=r.reviewer.name if r.reviewer else None,
        reviewer_role=r.reviewer.role if r.reviewer else None,
    )


def _latest_review(
    db: Session,
    candidate_id: int,
    actions: set[str],
    stage: Optional[str] = None,
) -> Optional[models.Review]:
    q = (
        select(models.Review)
        .where(models.Review.candidate_id == candidate_id)
        .where(models.Review.action.in_(actions))
    )
    if stage:
        q = q.where(models.Review.stage == stage)
    q = q.order_by(models.Review.created_at.desc(), models.Review.id.desc()).limit(1)
    return db.scalars(q).first()


def _as_utc_datetime(value: object) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _santiago_datetime(value: object) -> Optional[datetime]:
    dt = _as_utc_datetime(value)
    return dt.astimezone(SANTIAGO_TZ) if dt else None


def _santiago_iso(value: object) -> Optional[str]:
    dt = _santiago_datetime(value)
    return dt.isoformat() if dt else None


def _santiago_display(value: object) -> str:
    dt = _santiago_datetime(value)
    if not dt:
        return "" if value in (None, "") else str(value)
    return dt.strftime("%d-%m-%Y %H:%M")


def _review_date(review: Optional[models.Review]) -> Optional[str]:
    return _santiago_iso(review.created_at) if review else None


DECIDING_ACTIONS_FOR_UI = {"accept", "reject", "star", "project", "like"}


def _candidate_out(db: Session, candidate: models.LocationCandidate) -> schemas.CandidateOut:
    group = workflow.candidate_group(db, candidate)
    last_decision = (
        candidate.last_action
        if candidate.last_action in DECIDING_ACTIONS_FOR_UI
        else None
    )
    workflow_dates = {
        "jefatura_like": _santiago_iso(candidate.suggested_at),
        "rejected": _santiago_iso(candidate.rejected_at),
        "comite_approved": _santiago_iso(candidate.approved_at),
        "project": _santiago_iso(candidate.project_at),
    }
    return schemas.CandidateOut(
        id=candidate.id,
        project_id=candidate.project_id,
        map_ref=candidate.map_ref,
        lat=candidate.lat,
        lng=candidate.lng,
        display_data=candidate.display_data or {},
        current_stage=candidate.current_stage,
        status=candidate.status,
        workflow_group=group,
        priority=candidate.priority,
        last_decision=last_decision,
        last_reject_note=candidate.last_reject_note,
        workflow_dates=workflow_dates,
    )


def _stats_payload(db: Session, project_id: Optional[str] = None) -> dict:
    q = select(models.LocationCandidate)
    if project_id:
        q = q.where(models.LocationCandidate.project_id == project_id)

    queues = {stage: 0 for stage in workflow.STAGES}
    statuses = {
        "pending": 0,
        "returned": 0,
        "suggested": 0,
        "rejected": 0,
        "approved_final": 0,
        "locales_proyecto": 0,
    }
    total = 0
    for candidate in db.scalars(q).all():
        total += 1
        group = workflow.candidate_group(db, candidate)
        if group == "pending":
            statuses["pending"] += 1
            queues["jefatura"] += 1
        elif group == "suggested":
            statuses["suggested"] += 1
            queues["comite"] += 1
        elif group == "approved":
            statuses["approved_final"] += 1
            queues["comite"] += 1
            queues["gerente"] += 1
        elif group == "rejected":
            statuses["rejected"] += 1
            queues["comite"] += 1
        elif group == "project":
            statuses["locales_proyecto"] += 1
    return {"total": total, "queues": queues, "statuses": statuses}


def _action_out(
    db: Session,
    candidate: models.LocationCandidate,
    user: models.User,
    project_id: Optional[str] = None,
) -> schemas.CandidateActionOut:
    next_items = workflow.candidates_for_role(db, user.role, project_id)
    next_candidate = next((c for c in next_items if c.id != candidate.id), None)
    return schemas.CandidateActionOut(
        candidate=_candidate_out(db, candidate),
        next_candidate=_candidate_out(db, next_candidate) if next_candidate else None,
        remaining=len(next_items),
        stats=_stats_payload(db, project_id),
    )


@app.get("/queue", response_model=schemas.QueueOut)
def get_queue(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """Next candidate in the current user's review layer (sysadmin has none)."""
    stage = workflow.role_stage(user.role)
    if stage is None:
        return schemas.QueueOut(candidate=None, remaining=0, stage=None)

    candidates = workflow.candidates_for_role(db, user.role, project_id)
    remaining = len(candidates)
    candidate = candidates[0] if candidates else None
    return schemas.QueueOut(
        candidate=_candidate_out(db, candidate) if candidate else None,
        remaining=remaining,
        stage=stage,
    )


@app.get("/candidates", response_model=list[schemas.CandidateOut])
def list_candidates(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.get_current_user),
):
    q = select(models.LocationCandidate).order_by(models.LocationCandidate.id)
    if project_id:
        q = q.where(models.LocationCandidate.project_id == project_id)
    return [_candidate_out(db, c) for c in db.scalars(q).all()]


EXPORT_GROUPS = {
    "pending": "Pendientes",
    "suggested": "Sugeridos",
    "approved": "Aprobados",
    "rejected": "Rechazados",
    "project": "Locales Proyecto",
}

EXPORT_FILE_SLUGS = {
    "pending": "pendientes",
    "suggested": "sugeridos",
    "approved": "aprobados",
    "rejected": "rechazados",
    "project": "proyecto",
}

PROJECT_VARIABLE_EXPORT_COLUMNS = [
    ("cve_unidad", "CveUnidad"),
    ("unidad", "Unidad"),
    ("comuna", "Comuna"),
    ("provincia", "Provincia"),
    ("region", "Region"),
    ("mt2", "MT2"),
    ("valor_arriendo", "Valor de Arriendo"),
    ("gastos_comunes", "Gastos Comunes"),
    ("clausula_salida", "Clausula de salida"),
    ("meses_gracia", "Meses de gracia"),
    ("plazo_arriendo", "Plazo de arriendo"),
    ("garantia", "Garantia"),
    ("tipo_proyecto", "Tipo de Proyecto"),
    ("fecha_apertura_aproximada", "Fecha aproximada de apertura"),
    ("contacto_nombre", "Nombre contacto"),
    ("contacto_telefono", "Telefono contacto"),
    ("contacto_email", "Email contacto"),
    ("fecha_entrega_local", "Fecha entrega local"),
]


def _candidate_export_group(db: Session, candidate: models.LocationCandidate) -> str:
    return workflow.candidate_group(db, candidate)


def _project_variables_out(
    candidate_id: int,
    variables: Optional[models.CandidateProjectVariables],
) -> schemas.CandidateProjectVariablesOut:
    if variables is None:
        return schemas.CandidateProjectVariablesOut(candidate_id=candidate_id)

    def text_or_none(value: object) -> Optional[str]:
        if value in (None, ""):
            return None
        return str(value)

    return schemas.CandidateProjectVariablesOut(
        candidate_id=candidate_id,
        cve_unidad=variables.cve_unidad,
        unidad=variables.unidad,
        comuna=variables.comuna,
        provincia=variables.provincia,
        region=variables.region,
        mt2=variables.mt2,
        valor_arriendo=text_or_none(variables.valor_arriendo),
        gastos_comunes=text_or_none(variables.gastos_comunes),
        clausula_salida=variables.clausula_salida,
        meses_gracia=text_or_none(variables.meses_gracia),
        plazo_arriendo=variables.plazo_arriendo,
        garantia=variables.garantia,
        tipo_proyecto=variables.tipo_proyecto,
        fecha_apertura_aproximada=variables.fecha_apertura_aproximada,
        contacto_nombre=variables.contacto_nombre,
        contacto_telefono=variables.contacto_telefono,
        contacto_email=variables.contacto_email,
        fecha_entrega_local=variables.fecha_entrega_local,
        updated_at=variables.updated_at,
        updated_by_id=variables.updated_by_id,
    )


def _clean_project_variables_payload(
    payload: schemas.CandidateProjectVariablesIn,
) -> dict:
    values = payload.model_dump()
    for key, value in list(values.items()):
        if isinstance(value, str):
            value = value.strip()
            values[key] = value.upper() if value else None
    for key in ("cve_unidad", "unidad"):
        if values.get(key):
            values[key] = str(values[key]).upper()
        else:
            raise HTTPException(400, "CveUnidad y Unidad son obligatorios.")
    return values


def _project_email_value(value: object, fallback: str = "") -> str:
    if value in (None, ""):
        return fallback
    return str(value)


def _project_email_context(
    candidate: models.LocationCandidate,
    values: dict,
) -> dict[str, str]:
    data = candidate.display_data or {}
    projection_id = _display_value(data, ["ID Proyección", "ID Proyeccion", "ID"]) or candidate.id
    address = _display_value(data, ["DIRECCIÓN", "DIRECCION", "Direccion", "DIRECCIÃ“N"]) or candidate.map_ref or ""
    comuna = values.get("comuna") or _display_value(data, ["Comuna", "COMUNA"])
    provincia = values.get("provincia") or _display_value(data, ["Provincia", "PROVINCIA"])
    region = values.get("region") or _display_value(data, ["Region", "REGION"])
    mt2 = _project_email_value(values.get("mt2") or data.get("MT2"))
    delivery_date = _project_email_value(
        values.get("fecha_entrega_local") or values.get("fecha_apertura_aproximada"),
        "A PARTIR DE LA FIRMA DE CONTRATO",
    )
    return {
        "candidate_id": _project_email_value(candidate.id),
        "projection_id": _project_email_value(projection_id),
        "delivery_date": delivery_date,
        "cve_unidad": _project_email_value(values.get("cve_unidad")),
        "unidad": _project_email_value(values.get("unidad")),
        "address": _project_email_value(address),
        "comuna": _project_email_value(comuna),
        "provincia": _project_email_value(provincia),
        "region": _project_email_value(region),
        "mt2": f"{mt2} MT2" if mt2 else "",
        "valor_arriendo": _project_email_value(values.get("valor_arriendo")),
        "gastos_comunes": _project_email_value(values.get("gastos_comunes")),
        "clausula_salida": _project_email_value(values.get("clausula_salida")),
        "meses_gracia": _project_email_value(values.get("meses_gracia")),
        "plazo_arriendo": _project_email_value(values.get("plazo_arriendo")),
        "garantia": _project_email_value(values.get("garantia")),
        "contact_name": _project_email_value(values.get("contacto_nombre"), "SOLICITAR CON CELIA FOLSCH"),
        "contact_phone": _project_email_value(values.get("contacto_telefono"), "SOLICITAR CON CELIA FOLSCH"),
        "contact_email": _project_email_value(values.get("contacto_email")),
    }


def _project_email_body(
    candidate: models.LocationCandidate,
    values: dict,
) -> str:
    ctx = _project_email_context(candidate, values)
    return "\n".join(
        [
            "Estimados, buen dia",
            "",
            "Dejo el contacto nuevo proyecto para gestion de cada area",
            f"El ID asociado es #{ctx['candidate_id']}",
            "",
            f"El ID de proyeccion es #{ctx['projection_id']}",
            "Area de Aperturas y Remodelacion, su apoyo con factibilidad y desarrollo de proyectos.",
            "",
            f"ENTREGA DE PROYECTO FECHA APROXIMADA: {ctx['delivery_date']}",
            "",
            "LOCAL PARA PROYECTO NUEVO",
            f"UNIDAD: {ctx['cve_unidad']}",
            f"NOMBRE: {ctx['unidad']}",
            f"DIRECCION: {ctx['address']}",
            f"COMUNA: {ctx['comuna']}",
            f"PROVINCIA: {ctx['provincia']}",
            f"REGION: {ctx['region']}",
            f"MT2 LOCAL: {ctx['mt2']}",
            f"VALOR: {ctx['valor_arriendo']}",
            f"GGCC: {ctx['gastos_comunes']}",
            f"CLAUSULA SALIDA MES A FAVOR DE SIMI: {ctx['clausula_salida']}",
            f"MESES DE GRACIA: {ctx['meses_gracia']}",
            f"PLAZO DE ARRIENDO: {ctx['plazo_arriendo']}",
            f"GARANTIA: {ctx['garantia']}",
            "",
            "CONTACTO",
            f"NOMBRE: {ctx['contact_name']}",
            f"TELEFONO: {ctx['contact_phone']}",
            f"EMAIL: {ctx['contact_email']}",
            "",
            "Saludos,",
        ]
    )


def _project_email_html_table(ctx: dict[str, str]) -> str:
    def e(key: str) -> str:
        return html_escape(ctx.get(key, ""))

    def row(label: str, value: str, underline: bool = False) -> str:
        value_style = "padding:6px; border:1px solid black;"
        if underline:
            value_style += " text-decoration: underline;"
        return (
            "<tr>"
            '<td style="background:#D9E1F2; color:black; padding:6px; border:1px solid black; white-space: nowrap;">'
            f"<b>{html_escape(label)}</b></td>"
            f'<td style="{value_style}">{value}</td>'
            "</tr>"
        )

    email = e("contact_email")
    email_html = (
        f'<a href="mailto:{email}" style="color:#0070C0;">{email}</a>'
        if email
        else ""
    )
    return (
        '<table style="border-collapse: collapse; border-spacing:0; width: auto; '
        'font-family: Arial, sans-serif; font-size:12px; border:1px solid black; '
        'table-layout: auto; mso-table-lspace:0pt; mso-table-rspace:0pt;">'
        "<thead><tr>"
        '<th colspan="2" style="background-color:#D9E1F2; color:black; padding:10px; border:1px solid black; text-align:center;">'
        "<b>LOCAL PARA PROYECTO NUEVO</b></th>"
        "</tr></thead><tbody>"
        + row("UNIDAD", e("cve_unidad"))
        + row("NOMBRE", e("unidad"))
        + row("DIRECCIÓN", e("address"))
        + row("COMUNA", e("comuna"))
        + row("PROVINCIA", e("provincia"), underline=True)
        + row("REGIÓN", e("region"), underline=True)
        + row("MTS2 LOCAL", e("mt2"))
        + row("VALOR", e("valor_arriendo"))
        + row("GGCC", e("gastos_comunes"))
        + row("CLAUSULA SALIDA MES A FAVOR DE SIMI", e("clausula_salida"))
        + row("MESES DE GRACIA", e("meses_gracia"))
        + row("PLAZO DE ARRIENDO", e("plazo_arriendo"))
        + row("GARANTIA", e("garantia"))
        + '<tr><td colspan="2" style="background:#D9E1F2; color:black; padding:10px; border:1px solid black; text-align:center;"><b>CONTACTO</b></td></tr>'
        + row("NOMBRE", e("contact_name"))
        + row("TELÉFONO", e("contact_phone"))
        + row("EMAIL", email_html)
        + "</tbody></table>"
    )


def _project_email_html_body(
    candidate: models.LocationCandidate,
    values: dict,
) -> str:
    ctx = _project_email_context(candidate, values)
    return f"""\
<html>
  <body style="font-family: Arial, sans-serif; font-size:14px; color:#222;">
    <p>Estimados, buen día</p>
    <p>Dejo el contacto nuevo proyecto para gestión de cada área<br>
    El ID asociado es #{html_escape(ctx['candidate_id'])}</p>
    <p>El ID de proyección es #{html_escape(ctx['projection_id'])}<br>
    Área de Aperturas y Remodelación, su apoyo con factibilidad y desarrollo de proyectos.</p>
    <p>ENTREGA DE PROYECTO FECHA APROXIMADA: {html_escape(ctx['delivery_date'])}</p>
    {_project_email_html_table(ctx)}
    <p>Saludos,</p>
  </body>
</html>
"""


def _send_project_variables_email(
    candidate: models.LocationCandidate,
    recipients: list[str],
    values: dict,
) -> tuple[list[str], list[str], str]:
    clean_recipients = sorted({email.strip().lower() for email in recipients if email and email.strip()})
    if not clean_recipients:
        raise HTTPException(400, "Debe seleccionar al menos un destinatario.")
    subject = f"NUEVO LOCAL APROBADO {values['cve_unidad']} {values['unidad']}".strip()
    msg = EmailMessage()
    msg["From"] = ORIGIN_EMAIL
    msg["To"] = ", ".join(clean_recipients)
    msg["Cc"] = ", ".join(CORREO_COPIA)
    msg["Subject"] = subject
    msg.set_content(_project_email_body(candidate, values))
    msg.add_alternative(_project_email_html_body(candidate, values), subtype="html")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as smtp:
            smtp.send_message(msg, from_addr=ORIGIN_EMAIL, to_addrs=clean_recipients + CORREO_COPIA)
    except OSError as exc:
        raise HTTPException(502, f"No se pudo enviar el correo por SMTP: {exc}") from exc
    return clean_recipients, CORREO_COPIA, subject


def _ensure_project_variables_allowed(
    db: Session,
    candidate: models.LocationCandidate,
    user: models.User,
) -> None:
    if user.role not in {workflow.JEFATURA, workflow.SYSADMIN}:
        raise HTTPException(403, "Only Jefatura can edit project variables.")
    if workflow.candidate_group(db, candidate) != "project":
        raise HTTPException(409, "Project variables are only available for Locales Proyecto.")


def _display_value(display_data: dict, keys: list[str]) -> object:
    for key in keys:
        value = display_data.get(key)
        if value not in (None, ""):
            return value
    return ""


def _is_date_key(key: str) -> bool:
    return "fecha" in key.lower()


def _candidate_view_date(db: Session, candidate: models.LocationCandidate, group: str) -> object:
    if group == "pending":
        return _santiago_display(_display_value(candidate.display_data or {}, ["FECHA", "Fecha", "fecha"]))
    if group == "suggested":
        review = _latest_review(db, candidate.id, {"like"}, workflow.JEFATURA)
        return _santiago_display(review.created_at) if review else ""
    if group == "approved":
        review = _latest_review(db, candidate.id, {"accept", "star"}, workflow.COMITE)
        return _santiago_display(review.created_at) if review else ""
    if group == "rejected":
        review = _latest_review(db, candidate.id, {"reject"})
        return _santiago_display(review.created_at) if review else ""
    if group == "project":
        review = _latest_review(db, candidate.id, {"project"}, workflow.GERENTE)
        return _santiago_display(review.created_at) if review else ""
    return ""


def _export_rows(
    db: Session,
    candidates: list[models.LocationCandidate],
) -> tuple[list[str], list[list[object]]]:
    display_keys: list[str] = []
    for candidate in candidates:
        for key in candidate.display_data or {}:
            if key not in display_keys:
                display_keys.append(key)

    review_cols: list[str] = []
    for stage in workflow.STAGES:
        review_cols += [f"{stage}_accion", f"{stage}_comentario"]

    project_variable_headers = [label for _, label in PROJECT_VARIABLE_EXPORT_COLUMNS]

    header = [
        "candidate_id",
        "grupo",
        "fecha_vista",
        "estado",
        "etapa_actual",
        "prioridad",
        "latitud",
        "longitud",
        "map_ref",
    ] + review_cols + project_variable_headers + display_keys

    rows: list[list[object]] = []
    for candidate in candidates:
        group = _candidate_export_group(db, candidate)
        row: list[object] = [
            candidate.id,
            EXPORT_GROUPS.get(group, group),
            _candidate_view_date(db, candidate, group),
            candidate.status,
            candidate.current_stage,
            "Si" if candidate.priority else "",
            candidate.lat if candidate.lat is not None else "",
            candidate.lng if candidate.lng is not None else "",
            candidate.map_ref or "",
        ]
        for stage in workflow.STAGES:
            decision = workflow.current_decision(db, candidate.id, stage)
            row += [decision.action if decision else "", (decision.note if decision else "") or ""]
        variables = candidate.project_variables
        for attr, _label in PROJECT_VARIABLE_EXPORT_COLUMNS:
            value = getattr(variables, attr, "") if variables else ""
            row.append("" if value is None else value)
        for key in display_keys:
            value = (candidate.display_data or {}).get(key, "")
            if _is_date_key(key):
                value = _santiago_display(value)
            row.append("" if value is None else value)
        rows.append(row)
    return header, rows


def _add_export_sheet(
    wb: Workbook,
    title: str,
    db: Session,
    candidates: list[models.LocationCandidate],
):
    ws = wb.create_sheet(title=title[:31])
    header, rows = _export_rows(db, candidates)
    ws.append(header)
    for row in rows:
        ws.append(row)

    header_fill = PatternFill("solid", fgColor="1E293B")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col_idx, column_cells in enumerate(ws.columns, start=1):
        max_len = 12
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, min(len(value), 60))
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 62)


def _export_timestamp() -> str:
    return datetime.now(SANTIAGO_TZ).strftime("%Y%m%d")


@app.get("/candidates/export.xlsx")
def export_candidates_xlsx(
    group: Optional[str] = None,
    all_groups: bool = False,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.get_current_user),
):
    if group and group not in EXPORT_GROUPS:
        raise HTTPException(400, "Invalid export group.")

    q = select(models.LocationCandidate).order_by(models.LocationCandidate.id)
    if project_id:
        q = q.where(models.LocationCandidate.project_id == project_id)
    candidates = db.scalars(q).all()

    wb = Workbook()
    wb.remove(wb.active)

    if all_groups:
        for export_group, label in EXPORT_GROUPS.items():
            sheet_candidates = [c for c in candidates if _candidate_export_group(db, c) == export_group]
            _add_export_sheet(wb, label, db, sheet_candidates)
        filename = f"locales_todas_las_vistas_{_export_timestamp()}.xlsx"
    else:
        export_group = group or "pending"
        label = EXPORT_GROUPS[export_group]
        sheet_candidates = [c for c in candidates if _candidate_export_group(db, c) == export_group]
        _add_export_sheet(wb, label, db, sheet_candidates)
        filename = f"locales_{EXPORT_FILE_SLUGS[export_group]}_{_export_timestamp()}.xlsx"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/candidates/{candidate_id}", response_model=schemas.CandidateOut)
def get_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.get_current_user),
):
    candidate = db.get(models.LocationCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return _candidate_out(db, candidate)


@app.get(
    "/candidates/{candidate_id}/project-variables",
    response_model=schemas.CandidateProjectVariablesOut,
)
def get_candidate_project_variables(
    candidate_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    candidate = db.get(models.LocationCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    _ensure_project_variables_allowed(db, candidate, user)
    return _project_variables_out(candidate.id, candidate.project_variables)


@app.put(
    "/candidates/{candidate_id}/project-variables",
    response_model=schemas.CandidateProjectVariablesOut,
)
def save_candidate_project_variables(
    candidate_id: int,
    payload: schemas.CandidateProjectVariablesIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    candidate = db.get(models.LocationCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    _ensure_project_variables_allowed(db, candidate, user)
    values = _clean_project_variables_payload(payload)

    variables = candidate.project_variables
    if variables is None:
        variables = models.CandidateProjectVariables(candidate_id=candidate.id)
        db.add(variables)

    for key, value in values.items():
        setattr(variables, key, value)
    variables.updated_by_id = user.id
    db.commit()
    db.refresh(variables)
    return _project_variables_out(candidate.id, variables)


@app.post(
    "/candidates/{candidate_id}/project-variables/email",
    response_model=schemas.CandidateProjectVariablesEmailOut,
)
def email_candidate_project_variables(
    candidate_id: int,
    payload: schemas.CandidateProjectVariablesEmailIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    candidate = db.get(models.LocationCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    _ensure_project_variables_allowed(db, candidate, user)
    values = _clean_project_variables_payload(payload.variables)

    variables = candidate.project_variables
    if variables is None:
        variables = models.CandidateProjectVariables(candidate_id=candidate.id)
        db.add(variables)
    for key, value in values.items():
        setattr(variables, key, value)
    variables.updated_by_id = user.id
    db.flush()

    recipients, cc, subject = _send_project_variables_email(candidate, payload.recipients, values)
    db.commit()
    return schemas.CandidateProjectVariablesEmailOut(
        sent=True,
        recipients=recipients,
        cc=cc,
        subject=subject,
    )


@app.get("/candidates/{candidate_id}/reviews", response_model=list[schemas.ReviewOut])
def candidate_reviews(
    candidate_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.get_current_user),
):
    """Full audit trail for a candidate â€” powers the card's review history."""
    if not db.get(models.LocationCandidate, candidate_id):
        raise HTTPException(404, "Candidate not found")
    reviews = db.scalars(
        select(models.Review)
        .where(models.Review.candidate_id == candidate_id)
        .order_by(models.Review.created_at, models.Review.id)
    ).all()
    return [_review_out(r) for r in reviews]


@app.post("/candidates/{candidate_id}/status", response_model=schemas.CandidateActionOut)
def update_candidate_status(
    candidate_id: int,
    payload: schemas.CandidateStatusUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    candidate = db.get(models.LocationCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    if payload.group == "pending":
        if user.role != "sysadmin":
            raise HTTPException(403, "Only sysadmin can reset candidates to pending.")
        stage = candidate.current_stage if candidate.current_stage in workflow.STAGES else workflow.COMITE
        review = models.Review(
            candidate_id=candidate.id,
            stage=stage,
            reviewer_id=user.id,
            action="reopen",
            note=payload.note,
            created_at=datetime.now(timezone.utc),
        )
        db.add(review)
        candidate.current_stage = stage
        candidate.status = workflow.RETURNED
        candidate.workflow_group = workflow.PENDING
        candidate.last_action = "reopen"
        candidate.last_action_at = review.created_at
        candidate.last_actor_role = user.role
        candidate.reopened_at = candidate.last_action_at
        db.commit()
    else:
        action = {
            "suggested": "like",
            "approved": "accept",
            "rejected": "reject",
            "project": "project",
            "skip": "skip",
        }[payload.group]
        try:
            workflow.submit_review(db, candidate, user, action, payload.note)
        except workflow.WorkflowError as exc:
            raise HTTPException(409, str(exc))
        db.commit()
    db.refresh(candidate)
    return _action_out(db, candidate, user)


@app.post("/candidates/{candidate_id}/review", response_model=schemas.CandidateActionOut)
def review_candidate(
    candidate_id: int,
    payload: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    candidate = db.get(models.LocationCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    try:
        workflow.submit_review(db, candidate, user, payload.action, payload.note)
    except workflow.WorkflowError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    db.refresh(candidate)
    return _action_out(db, candidate, user)


@app.post("/candidates/{candidate_id}/send-back", response_model=schemas.CandidateOut)
def send_back_candidate(
    candidate_id: int,
    payload: schemas.NoteIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    candidate = db.get(models.LocationCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    try:
        workflow.send_back(db, candidate, user, payload.note)
    except workflow.WorkflowError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    db.refresh(candidate)
    return _candidate_out(db, candidate)


@app.post("/candidates/{candidate_id}/reopen", response_model=schemas.CandidateOut)
def reopen_candidate(
    candidate_id: int,
    payload: schemas.NoteIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    candidate = db.get(models.LocationCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    try:
        workflow.reopen(db, candidate, user, payload.note)
    except workflow.WorkflowError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    db.refresh(candidate)
    return _candidate_out(db, candidate)


# --------------------------------------------------------------------------- #
# Pipeline overview (sysadmin dashboard)
# --------------------------------------------------------------------------- #
@app.get("/stats")
def stats(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_role("sysadmin")),
):
    """Counts of candidates per active stage and per terminal status."""
    return _stats_payload(db, project_id)


# --------------------------------------------------------------------------- #
# User management (sysadmin)
# --------------------------------------------------------------------------- #
@app.post("/users", response_model=schemas.UserOut)
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_role("sysadmin")),
):
    if db.scalar(select(models.User).where(models.User.email == payload.email)):
        raise HTTPException(409, "A user with that email already exists")
    user = models.User(
        email=payload.email,
        name=payload.name,
        password_hash=auth.hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users", response_model=list[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_role("sysadmin")),
):
    return db.scalars(select(models.User).order_by(models.User.created_at)).all()


# --------------------------------------------------------------------------- #
# Export (sysadmin oversight) â€” per-candidate workflow state + per-stage verdicts
# --------------------------------------------------------------------------- #
@app.get("/projects/{project_id}/results")
def export_results(
    project_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_role("sysadmin")),
):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    candidates = db.scalars(
        select(models.LocationCandidate)
        .where(models.LocationCandidate.project_id == project_id)
        .order_by(models.LocationCandidate.id)
    ).all()

    # Stable union of display_data keys for the trailing columns.
    display_keys: list[str] = []
    for cand in candidates:
        for k in (cand.display_data or {}):
            if k not in display_keys:
                display_keys.append(k)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    stage_cols: list[str] = []
    for stage in workflow.STAGES:
        stage_cols += [f"{stage}_action", f"{stage}_note"]
    header = (
        ["candidate_id", "status", "current_stage", "priority", "lat", "lng", "map_ref"]
        + stage_cols
        + display_keys
    )
    writer.writerow(header)

    for cand in candidates:
        row = [
            cand.id,
            cand.status,
            cand.current_stage,
            "yes" if cand.priority else "",
            cand.lat if cand.lat is not None else "",
            cand.lng if cand.lng is not None else "",
            cand.map_ref or "",
        ]
        for stage in workflow.STAGES:
            dec = workflow.current_decision(db, cand.id, stage)
            row += [dec.action if dec else "", (dec.note if dec else "") or ""]
        for k in display_keys:
            row.append((cand.display_data or {}).get(k, ""))
        writer.writerow(row)

    buffer.seek(0)
    filename = f"results_{project.name.replace(' ', '_')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# Business locations (global enrichment layer)
# --------------------------------------------------------------------------- #
@app.get("/business", response_model=list[schemas.BusinessOut])
def list_business(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.get_current_user),
):
    rows = db.scalars(select(models.BusinessLocation)).all()
    result: list[schemas.BusinessOut] = []
    for row in rows:
        attributes = dict(row.attributes or {})
        if "image_url" in attributes:
            attributes["image_url"] = _versioned_image_url(attributes["image_url"])
        result.append(
            schemas.BusinessOut(
                id=row.id,
                name=row.name,
                lat=row.lat,
                lng=row.lng,
                category=row.category,
                attributes=attributes,
            )
        )
    return result


@app.post("/business/ingest", response_model=schemas.BusinessIngestResult)
async def ingest_business(
    file: UploadFile = File(...),
    replace: bool = Form(True),
    config: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_role("sysadmin")),
):
    """Load/replace the global business locations from a tabular file.

    Expects columns: name, lat, lng, category (+ any extras -> attributes).
    Also accepts a single map column ('maps'/'coordinates'/url) if lat/lng absent.
    """
    cfg = _parse_config(config)
    content = await file.read()
    try:
        df = ingestion.read_table(content, file.filename or "business.csv")
    except Exception as exc:
        raise HTTPException(400, f"Could not read tabular file: {exc}")

    if df.empty:
        raise HTTPException(400, "Source file has no rows")

    cols = {c.lower(): c for c in df.columns}
    lat_col = (
        cols.get("lat") or cols.get("latitude") or cols.get("latitud")
    )
    lng_col = (
        cols.get("lng") or cols.get("lon") or cols.get("longitude") or cols.get("longitud")
    )
    # Name: prefer explicit name/nombre, fall back to Direccion + ID composite.
    name_col = cols.get("name") or cols.get("nombre")
    direccion_col = cols.get("direccion") or cols.get("direcciÃ³n")
    id_col = cols.get("idpuntointeres") or cols.get("id")
    cat_col = cols.get("category") or cols.get("categoria") or cols.get("categorÃ­a")
    # For Ahumada data: use Region as category fallback.
    region_col = cols.get("region") or cols.get("regiÃ³n")

    # Optional map column fallback when lat/lng aren't separate.
    map_col = None
    if not (lat_col and lng_col):
        try:
            map_col = ingestion.resolve_map_column(df, cfg.map_column)
        except ValueError:
            raise HTTPException(
                400, "Provide lat/lng columns or a map/coordinates column"
            )

    if replace:
        db.query(models.BusinessLocation).delete()

    created = 0
    failed = 0
    reserved = {c for c in (lat_col, lng_col, name_col, cat_col, map_col) if c}

    for _, row in df.iterrows():
        lat = lng = None
        if lat_col and lng_col:
            lat = ingestion._parse_coord_float(row.get(lat_col))
            lng = ingestion._parse_coord_float(row.get(lng_col))
        elif map_col:
            lat, lng = ingestion.parse_map_ref(row.get(map_col))

        if lat is None or lng is None or not ingestion._valid(lat, lng):
            failed += 1
            continue

        # Build display name: explicit column > Direccion + ID > None.
        if name_col:
            display_name = str(row[name_col])
        elif direccion_col and id_col:
            display_name = f"{row.get(id_col, '')} â€” {row.get(direccion_col, '')}".strip(" â€”")
        elif direccion_col:
            display_name = str(row[direccion_col])
        else:
            display_name = None

        # Category: explicit > Region fallback.
        if cat_col:
            category = str(row[cat_col])
        elif region_col:
            category = str(row[region_col])
        else:
            category = None

        # Attributes: all non-reserved columns, skipping NULL/empty values.
        attributes = {}
        for c in df.columns:
            if c in reserved:
                continue
            v = row.get(c)
            v_str = "" if v is None else str(v).strip()
            if v_str and v_str.upper() != "NULL":
                attributes[c] = v_str

        db.add(
            models.BusinessLocation(
                name=display_name,
                lat=lat,
                lng=lng,
                category=category,
                attributes=attributes,
            )
        )
        created += 1

    db.commit()
    return schemas.BusinessIngestResult(
        rows_read=len(df), locations_created=created, failed_coordinates=failed
    )


# --------------------------------------------------------------------------- #
# Postgres import (sysadmin-triggered, no startup side effects)
# --------------------------------------------------------------------------- #
def _candidate_source_id(display_data: dict) -> str | None:
    for key, value in (display_data or {}).items():
        normalized_key = str(key).strip().lower()
        is_projection_id = (
            normalized_key == "id"
            or (normalized_key.startswith("id ") and "proyecci" in normalized_key)
            or normalized_key.startswith("id proyeccion")
        )
        if is_projection_id and value is not None and str(value).strip():
            return str(value).strip()
    return None


def _get_or_create_postgres_project(db: Session) -> tuple[models.Project, bool]:
    project = db.scalar(
        select(models.Project)
        .where(models.Project.source_file == "postgres")
        .order_by(models.Project.created_at.asc())
    )
    if project:
        return project, False
    project = models.Project(name=POSTGRES_SYNC_PROJECT_NAME, source_file="postgres")
    db.add(project)
    db.flush()
    return project, True


def _upsert_candidate_records(
    db: Session,
    records: list[dict],
    project_id: str,
    replace: bool = False,
) -> tuple[int, int]:
    if replace:
        existing = db.scalars(
            select(models.LocationCandidate)
            .where(models.LocationCandidate.project_id == project_id)
        ).all()
        for candidate in existing:
            db.delete(candidate)
        db.flush()

    existing_by_source_id: dict[str, models.LocationCandidate] = {}
    for candidate in db.scalars(select(models.LocationCandidate)).all():
        source_id = _candidate_source_id(candidate.display_data or {})
        if source_id:
            existing_by_source_id[source_id] = candidate

    created = 0
    updated = 0
    for rec in records:
        source_id = _candidate_source_id(rec.get("display_data") or {})
        candidate = existing_by_source_id.get(source_id) if source_id else None
        if candidate is None:
            db.add(
                models.LocationCandidate(
                    project_id=project_id,
                    map_ref=rec["map_ref"],
                    lat=rec["lat"],
                    lng=rec["lng"],
                    display_data=rec["display_data"],
                    current_stage=workflow.JEFATURA,
                    workflow_group=workflow.PENDING,
                )
            )
            created += 1
        else:
            candidate.map_ref = rec["map_ref"]
            candidate.lat = rec["lat"]
            candidate.lng = rec["lng"]
            candidate.display_data = rec["display_data"]
            updated += 1
    return created, updated


def _replace_business_records(db: Session) -> tuple[int, int, int]:
    business_records, failed_business_coordinates = (
        ingestion.fetch_business_records_from_postgres()
    )
    db.query(models.BusinessLocation).delete()
    db.flush()
    for rec in business_records:
        db.add(
            models.BusinessLocation(
                name=rec["name"],
                lat=rec["lat"],
                lng=rec["lng"],
                category=rec["category"],
                attributes=rec["attributes"],
            )
        )
    rows_read = len(business_records) + failed_business_coordinates
    return rows_read, len(business_records), failed_business_coordinates


def _sync_postgres(
    db: Session,
    payload: schemas.PostgresImportRequest,
) -> schemas.PostgresImportResult:
    project: models.Project | None = None
    project_created = False
    candidate_rows_read = 0
    candidates_created = 0
    parsed_candidate_coordinates = 0
    failed_candidate_coordinates = 0
    business_rows_read = 0
    business_locations_created = 0
    failed_business_coordinates = 0

    if payload.import_candidates:
        if payload.project_id:
            project = db.get(models.Project, payload.project_id)
            if not project:
                raise HTTPException(404, "Project not found")
        else:
            project, project_created = _get_or_create_postgres_project(db)
            if payload.project_name:
                project.name = payload.project_name

        records, parsed_candidate_coordinates, failed_candidate_coordinates = (
            ingestion.fetch_candidate_records_from_postgres(project.project_id)
        )
        candidate_rows_read = len(records)
        candidates_created, _ = _upsert_candidate_records(
            db,
            records,
            project.project_id,
            replace=payload.replace_candidates,
        )
        project.source_file = "postgres"

    if payload.import_business:
        if payload.replace_business:
            business_rows_read, business_locations_created, failed_business_coordinates = (
                _replace_business_records(db)
            )
        else:
            business_records, failed_business_coordinates = (
                ingestion.fetch_business_records_from_postgres()
            )
            business_rows_read = len(business_records) + failed_business_coordinates
            for rec in business_records:
                db.add(
                    models.BusinessLocation(
                        name=rec["name"],
                        lat=rec["lat"],
                        lng=rec["lng"],
                        category=rec["category"],
                        attributes=rec["attributes"],
                    )
                )
            business_locations_created = len(business_records)

    db.commit()
    return schemas.PostgresImportResult(
        project_id=project.project_id if project else payload.project_id,
        project_created=project_created,
        candidate_rows_read=candidate_rows_read,
        candidates_created=candidates_created,
        parsed_candidate_coordinates=parsed_candidate_coordinates,
        failed_candidate_coordinates=failed_candidate_coordinates,
        business_rows_read=business_rows_read,
        business_locations_created=business_locations_created,
        failed_business_coordinates=failed_business_coordinates,
        replaced_candidates=payload.replace_candidates,
        replaced_business=payload.replace_business,
    )


async def _postgres_sync_loop() -> None:
    while True:
        await asyncio.sleep(POSTGRES_SYNC_INTERVAL_SECONDS)
        await asyncio.to_thread(_run_postgres_sync_once, "interval")


def _run_postgres_sync_once(reason: str = "manual") -> None:
    if not postgres_sync_lock.acquire(blocking=False):
        logger.info("Postgres sync skipped (%s): another sync is already running", reason)
        return
    db = SessionLocal()
    try:
        result = _sync_postgres(
            db,
            schemas.PostgresImportRequest(
                import_candidates=True,
                import_business=True,
                replace_candidates=False,
                replace_business=True,
            ),
        )
        logger.info(
            "Postgres sync completed (%s): candidates read=%s created=%s business=%s",
            reason,
            result.candidate_rows_read,
            result.candidates_created,
            result.business_locations_created,
        )
    except Exception:
        db.rollback()
        logger.exception("Postgres sync failed (%s)", reason)
    finally:
        db.close()
        postgres_sync_lock.release()


@app.post("/admin/import-postgres", response_model=schemas.PostgresImportResult)
def import_postgres(
    payload: schemas.PostgresImportRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_role("sysadmin")),
):
    """Import candidates and global points of interest from the configured Postgres DB."""
    try:
        return _sync_postgres(db, payload)
    except HTTPException:
        db.rollback()
        raise
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(502, f"Postgres import failed: {exc}")


# --------------------------------------------------------------------------- #
# Frontend (mounted last so API routes win)
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if IMAGE_DIR.exists():
    app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")

