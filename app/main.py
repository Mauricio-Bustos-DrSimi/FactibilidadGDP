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

import yaml
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ingestion, models, schemas
from app.database import get_db, init_db

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # auto-create the SQLite schema on first run
    yield


app = FastAPI(title="Site Swiper", version="1.0.0", lifespan=lifespan)


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
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
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
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(models.Project).order_by(models.Project.created_at.desc())).all()


@app.get("/projects/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
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


@app.get("/projects/{project_id}/next", response_model=schemas.NextCandidateOut)
def next_candidate(project_id: str, db: Session = Depends(get_db)):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Counts.
    all_ids = db.scalars(
        select(models.LocationCandidate.id).where(
            models.LocationCandidate.project_id == project_id
        )
    ).all()
    decided_ids = set(
        db.scalars(
            select(models.Decision.candidate_id).where(
                models.Decision.project_id == project_id
            )
        ).all()
    )
    total = len(all_ids)
    decided = len(decided_ids)

    # Serve only undecided candidates that have valid coordinates first, then any.
    candidate = db.scalars(
        select(models.LocationCandidate)
        .where(models.LocationCandidate.project_id == project_id)
        .where(models.LocationCandidate.id.notin_(decided_ids) if decided_ids else True)
        .where(models.LocationCandidate.lat.isnot(None))
        .order_by(models.LocationCandidate.id)
        .limit(1)
    ).first()

    if candidate is None:
        # Fall back to undecided rows even without coordinates (so they aren't lost).
        candidate = db.scalars(
            select(models.LocationCandidate)
            .where(models.LocationCandidate.project_id == project_id)
            .where(models.LocationCandidate.id.notin_(decided_ids) if decided_ids else True)
            .order_by(models.LocationCandidate.id)
            .limit(1)
        ).first()

    return schemas.NextCandidateOut(
        candidate=candidate,
        remaining=total - decided,
        decided=decided,
        total=total,
    )


@app.post("/projects/{project_id}/decisions", response_model=schemas.DecisionOut)
def record_decision(
    project_id: str,
    payload: schemas.DecisionCreate,
    db: Session = Depends(get_db),
):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    candidate = db.get(models.LocationCandidate, payload.candidate_id)
    if not candidate or candidate.project_id != project_id:
        raise HTTPException(404, "Candidate not found in this project")

    # Upsert — idempotent per (project_id, candidate_id).
    existing = db.scalar(
        select(models.Decision).where(
            models.Decision.project_id == project_id,
            models.Decision.candidate_id == payload.candidate_id,
        )
    )
    if existing:
        existing.verdict = payload.verdict
        existing.note = payload.note
        db.commit()
        db.refresh(existing)
        return existing

    decision = models.Decision(
        project_id=project_id,
        candidate_id=payload.candidate_id,
        verdict=payload.verdict,
        note=payload.note,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


@app.get("/projects/{project_id}/results")
def export_results(project_id: str, db: Session = Depends(get_db)):
    """Export accepted / rejected / starred candidates as CSV."""
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    rows = db.execute(
        select(models.LocationCandidate, models.Decision)
        .join(
            models.Decision,
            (models.Decision.candidate_id == models.LocationCandidate.id)
            & (models.Decision.project_id == project_id),
        )
        .where(models.LocationCandidate.project_id == project_id)
        .order_by(models.Decision.verdict, models.LocationCandidate.id)
    ).all()

    # Collect the union of display_data keys for a stable header.
    display_keys: list[str] = []
    for cand, _dec in rows:
        for k in (cand.display_data or {}):
            if k not in display_keys:
                display_keys.append(k)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    header = ["candidate_id", "verdict", "lat", "lng", "map_ref", "note", "decided_at"] + display_keys
    writer.writerow(header)

    for cand, dec in rows:
        row = [
            cand.id,
            dec.verdict,
            cand.lat if cand.lat is not None else "",
            cand.lng if cand.lng is not None else "",
            cand.map_ref or "",
            dec.note or "",
            dec.decided_at.isoformat() if dec.decided_at else "",
        ]
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
def list_business(db: Session = Depends(get_db)):
    return db.scalars(select(models.BusinessLocation)).all()


@app.post("/business/ingest", response_model=schemas.BusinessIngestResult)
async def ingest_business(
    file: UploadFile = File(...),
    replace: bool = Form(True),
    config: Optional[str] = Form(None),
    db: Session = Depends(get_db),
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
