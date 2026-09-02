from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import auth, models
from app.database import SessionLocal, init_db


def login(client: TestClient, email: str, password: str) -> dict:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()


def seed_user(email: str, password: str, role: str = "jefatura") -> models.User:
    init_db()
    with SessionLocal() as db:
        existing = db.scalar(select(models.User).where(models.User.email == email))
        if existing is not None:
            return existing
        user = models.User(
            email=email,
            name=f"Characterization {role}",
            password_hash=auth.hash_password(password),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def seed_candidate(*, projection_id: int, group: str) -> models.LocationCandidate:
    init_db()
    project_id = f"characterization-project-{projection_id}"
    with SessionLocal() as db:
        project = db.get(models.Project, project_id)
        if project is None:
            project = models.Project(
                project_id=project_id,
                name=f"Characterization {projection_id}",
            )
            db.add(project)
        candidate = db.scalar(
            select(models.LocationCandidate).where(
                models.LocationCandidate.project_id == project_id
            )
        )
        if candidate is None:
            status_by_group = {
                "pending": "pendiente",
                "opening": "por_abrir",
            }
            candidate = models.LocationCandidate(
                project_id=project_id,
                map_ref="-33.4500,-70.6500",
                lat=-33.45,
                lng=-70.65,
                display_data={
                    "ID": projection_id,
                    "CveUnidad": f"CL{projection_id}",
                    "Unidad": f"LOCAL {projection_id}",
                    "Comuna": "SANTIAGO",
                    "Region": "METROPOLITANA",
                },
                current_stage="jefatura",
                status=status_by_group[group],
                workflow_group=group,
                project_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            )
            db.add(candidate)
        db.commit()
        db.refresh(candidate)
        db.expunge(candidate)
        return candidate
