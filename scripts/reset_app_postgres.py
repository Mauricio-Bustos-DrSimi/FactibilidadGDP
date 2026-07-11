"""Reset only the app-owned Postgres tables and import fresh source data.

This leaves the source schema/tables intact, including dw_simi.SolicitudesProyecciones
and the PI_* / LocalesSimi point-of-interest tables.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.example", override=True)

from app import auth, schemas  # noqa: E402
from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.main import _sync_postgres  # noqa: E402


APP_TABLES = [
    "variables_proyecto_candidato",
    "revision",
    "candidato_ubicacion",
    "punto_interes",
    "proyecto",
    "usuario",
    "candidate_project_variables",
    "review",
    "location_candidate",
    "business_location",
    "project",
    "user",
]


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def reset_app_data() -> None:
    with engine.begin() as conn:
        for table_name in APP_TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS {_quote_identifier(table_name)} CASCADE"))

    init_db()

    with SessionLocal() as db:
        auth.seed_sysadmin(db)
        result = _sync_postgres(
            db,
            schemas.PostgresImportRequest(
                import_candidates=True,
                import_business=True,
                replace_candidates=True,
                replace_business=True,
            ),
        )
        db.commit()

    print("Reset complete:")
    print(f"  project_id: {result.project_id}")
    print(f"  candidate_rows_read: {result.candidate_rows_read}")
    print(f"  candidates_created: {result.candidates_created}")
    print(f"  business_rows_read: {result.business_rows_read}")
    print(f"  business_locations_created: {result.business_locations_created}")


if __name__ == "__main__":
    reset_app_data()
