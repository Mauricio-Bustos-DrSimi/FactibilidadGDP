"""One-off local seeder to make the onboarding tour testable.

Creates a test user for every role (known passwords), a demo project, ingests
the sample candidates, and loads the sample business layer. Safe to re-run:
skips users/projects/data that already exist.

Run:  .venv/Scripts/python.exe seed_testdata.py
Undo: delete data/site_swiper.db to reset everything, or remove the
      'Onboarding Demo' project + *@test.local users.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import func, select

from app.database import SessionLocal, init_db
from app import auth, ingestion, models

ROOT = Path(__file__).resolve().parent

TEST_USERS = [
    ("Javiera Jefatura", "jefatura@test.local", "test1234", "jefatura", "APERTURA"),
    ("Jose Jefe Comercial", "jefecomercial@test.local", "test1234", "jefecomercial", "SUCURSAL"),
    ("Carla Coordinadora", "coordinador@test.local", "test1234", "coordinador", "SUCURSAL"),
    ("Ana Arriendo", "arriendo@test.local", "test1234", "arriendo", None),
    ("Camilo Comite", "comite@test.local", "test1234", "comite", None),
    ("Gerardo Gerente", "gerente@test.local", "test1234", "gerente", None),
    ("Sara Sysadmin", "sysadmin@test.local", "test1234", "sysadmin", None),
]


def seed_users(db) -> None:
    for name, email, pw, role, division in TEST_USERS:
        if db.scalar(select(models.User).where(models.User.email == email)):
            print(f"= user {email} already exists")
            continue
        db.add(models.User(
            name=name, email=email,
            password_hash=auth.hash_password(pw), role=role,
            commercial_division=division,
        ))
        print(f"+ user {email} ({role})  pw={pw}")
    db.commit()


def seed_project_and_candidates(db) -> None:
    proj = db.scalar(select(models.Project).where(models.Project.name == "Onboarding Demo"))
    if proj is None:
        proj = models.Project(name="Onboarding Demo", notes="Seeded for tour testing")
        db.add(proj)
        db.commit()
        print(f"+ project 'Onboarding Demo' ({proj.project_id})")
    else:
        print("= project 'Onboarding Demo' already exists")

    n = db.scalar(
        select(func.count()).select_from(models.LocationCandidate)
        .where(models.LocationCandidate.project_id == proj.project_id)
    )
    if n:
        print(f"= project already has {n} candidates")
        return

    content = (ROOT / "data" / "sample_candidates.csv").read_bytes()
    df = ingestion.read_table(content, "sample_candidates.csv")
    lat_col, lng_col = ingestion.detect_latlon_columns(df)
    map_column = None if (lat_col and lng_col) else ingestion.resolve_map_column(df, None)
    records, parsed, failed = ingestion.build_candidates(df, map_column, lat_col, lng_col)
    for rec in records:
        db.add(models.LocationCandidate(
            project_id=proj.project_id,
            map_ref=rec["map_ref"], lat=rec["lat"], lng=rec["lng"],
            display_data=rec["display_data"],
        ))
    proj.source_file = "sample_candidates.csv"
    db.commit()
    print(f"+ ingested {len(records)} candidates ({parsed} with coords, {failed} without)")


def seed_business(db) -> None:
    nb = db.scalar(select(func.count()).select_from(models.BusinessLocation))
    if nb:
        print(f"= {nb} business locations already loaded")
        return
    df = pd.read_csv(ROOT / "data" / "sample_business_locations.csv")
    reserved = {"name", "lat", "lng", "category"}
    created = 0
    for _, row in df.iterrows():
        attrs = {k: row[k] for k in df.columns if k not in reserved and pd.notna(row[k])}
        db.add(models.BusinessLocation(
            name=str(row.get("name")) if pd.notna(row.get("name")) else None,
            lat=float(row["lat"]), lng=float(row["lng"]),
            category=str(row.get("category")) if pd.notna(row.get("category")) else None,
            attributes={k: (v.item() if hasattr(v, "item") else v) for k, v in attrs.items()},
        ))
        created += 1
    db.commit()
    print(f"+ loaded {created} business locations")


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_users(db)
        seed_project_and_candidates(db)
        seed_business(db)
        print("\nDone. Log in at http://127.0.0.1:8002 with any of:")
        for _, email, pw, role, _ in TEST_USERS:
            print(f"   {role:12} {email}  /  {pw}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
