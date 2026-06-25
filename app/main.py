"""FastAPI application: API endpoints + static frontend."""
from __future__ import annotations

import csv
import io
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

# Load .env so GOOGLE_MAPS_API_KEY is available regardless of how the worker is spawned.
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import secrets

import yaml
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import auth, ingestion, models, schemas, workflow
from app.database import SessionLocal, get_db, init_db

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # auto-create the SQLite schema on first run
    # Ensure a sysadmin exists so a fresh install is usable.
    db = SessionLocal()
    try:
        auth.seed_sysadmin(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Site Swiper", version="1.0.0", lifespan=lifespan)

# Signed-cookie sessions. SESSION_SECRET must be set in production; for local
# dev we fall back to a random per-process key (logs everyone out on restart).
_session_secret = os.environ.get("SESSION_SECRET")
if not _session_secret:
    _session_secret = secrets.token_urlsafe(32)
    print("WARNING: SESSION_SECRET not set — using an ephemeral key "
          "(sessions won't survive restart). Set SESSION_SECRET for production.")
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    https_only=False,  # set True behind HTTPS in production
    same_site="lax",
)


# --------------------------------------------------------------------------- #
# Auth endpoints
# --------------------------------------------------------------------------- #
@app.post("/auth/login", response_model=schemas.UserOut)
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.email == payload.email))
    if user is None or not user.active or not auth.verify_password(
        payload.password, user.password_hash
    ):
        raise HTTPException(401, "Invalid email or password")
    request.session[auth.SESSION_USER_KEY] = user.id
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

    count_q = (
        select(func.count(models.LocationCandidate.id))
        .where(models.LocationCandidate.current_stage == stage)
        .where(models.LocationCandidate.status.in_(workflow.ACTIVE_STATUSES))
    )
    if project_id:
        count_q = count_q.where(models.LocationCandidate.project_id == project_id)
    remaining = db.scalar(count_q) or 0

    candidate = db.scalars(workflow.queue_query(stage, project_id).limit(1)).first()
    return schemas.QueueOut(candidate=candidate, remaining=remaining, stage=stage)


@app.get("/candidates/{candidate_id}", response_model=schemas.CandidateOut)
def get_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.get_current_user),
):
    candidate = db.get(models.LocationCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return candidate


@app.get("/candidates/{candidate_id}/reviews", response_model=list[schemas.ReviewOut])
def candidate_reviews(
    candidate_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.get_current_user),
):
    """Full audit trail for a candidate — powers the card's review history."""
    if not db.get(models.LocationCandidate, candidate_id):
        raise HTTPException(404, "Candidate not found")
    reviews = db.scalars(
        select(models.Review)
        .where(models.Review.candidate_id == candidate_id)
        .order_by(models.Review.created_at, models.Review.id)
    ).all()
    return [_review_out(r) for r in reviews]


@app.post("/candidates/{candidate_id}/review", response_model=schemas.CandidateOut)
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
    return candidate


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
    return candidate


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
    return candidate


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
    base = select(
        models.LocationCandidate.current_stage,
        models.LocationCandidate.status,
        func.count(models.LocationCandidate.id),
    ).group_by(models.LocationCandidate.current_stage, models.LocationCandidate.status)
    if project_id:
        base = base.where(models.LocationCandidate.project_id == project_id)

    # Active queue size per review layer + terminal status totals.
    queues = {stage: 0 for stage in workflow.STAGES}
    statuses = {"pending": 0, "returned": 0, "rejected": 0, "approved_final": 0}
    total = 0
    for stage, status, count in db.execute(base).all():
        total += count
        if status in statuses:
            statuses[status] += count
        if stage in queues and status in workflow.ACTIVE_STATUSES:
            queues[stage] += count
    return {"total": total, "queues": queues, "statuses": statuses}


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
# Export (sysadmin oversight) — per-candidate workflow state + per-stage verdicts
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
    return db.scalars(select(models.BusinessLocation)).all()


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
    direccion_col = cols.get("direccion") or cols.get("dirección")
    id_col = cols.get("idpuntointeres") or cols.get("id")
    cat_col = cols.get("category") or cols.get("categoria") or cols.get("categoría")
    # For Ahumada data: use Region as category fallback.
    region_col = cols.get("region") or cols.get("región")

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
            display_name = f"{row.get(id_col, '')} — {row.get(direccion_col, '')}".strip(" —")
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
# Frontend (mounted last so API routes win)
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
