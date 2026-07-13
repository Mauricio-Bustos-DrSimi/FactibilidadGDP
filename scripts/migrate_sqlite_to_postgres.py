"""Copy the current local SQLite app data into the configured Postgres DB.

Run from the project root after setting SITE_SWIPER_USE_POSTGRES=true and the
POSTGRES_* variables in .env.example.

By default this script appends/mixes by primary key and fails on conflicts. Use
--replace-app-data only when you intentionally want to clear the app-owned
tables in Postgres before copying.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, delete, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.example", override=True)

from app import models  # noqa: E402
from app.database import DATA_DIR, SessionLocal, init_db  # noqa: E402


TABLES = [
    models.User,
    models.Project,
    models.LocationCandidate,
    models.Review,
    models.BusinessLocation,
    models.CandidateProjectVariables,
]


def sqlite_rows(db_path: Path, table_name: str) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        exists = conn.execute(
            "select 1 from sqlite_master where type='table' and name=?",
            (table_name,),
        ).fetchone()
        if not exists:
            return []
        return [dict(row) for row in conn.execute(f'select * from "{table_name}"')]


def _parse_datetime(value: Any) -> Any:
    if value in (None, "") or isinstance(value, datetime):
        return value
    text_value = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text_value)
    except ValueError:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")


def _parse_date(value: Any) -> Any:
    if value in (None, "") or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def normalize_row(model: type, row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for column in model.__table__.columns:
        if column.name not in normalized:
            continue
        value = normalized[column.name]
        if isinstance(column.type, JSON) and isinstance(value, str):
            normalized[column.name] = json.loads(value) if value else None
        elif isinstance(column.type, DateTime):
            normalized[column.name] = _parse_datetime(value)
        elif isinstance(column.type, Date):
            normalized[column.name] = _parse_date(value)
        elif isinstance(column.type, Boolean) and value is not None:
            normalized[column.name] = bool(value)
    return normalized


def reset_sequences(db, models_with_rows: list[type]) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for model in models_with_rows:
        table_name = model.__tablename__
        id_column = model.__table__.columns.get("id")
        if id_column is None or not isinstance(id_column.type, Integer):
            continue
        db.execute(text(
            f"""
            select setval(
                pg_get_serial_sequence('{table_name}', 'id'),
                coalesce((select max(id) from {table_name}), 1),
                true
            )
            """
        ))


def migrate(sqlite_path: Path, replace_app_data: bool) -> None:
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite DB not found: {sqlite_path}")

    init_db()
    copied: dict[str, int] = {}
    with SessionLocal() as db:
        if replace_app_data:
            for model in reversed(TABLES):
                db.execute(delete(model))
            db.commit()

        models_with_rows: list[type] = []
        for model in TABLES:
            rows = [
                normalize_row(model, row)
                for row in sqlite_rows(sqlite_path, model.__tablename__)
            ]
            if not rows:
                copied[model.__tablename__] = 0
                continue
            db.bulk_insert_mappings(model, rows)
            copied[model.__tablename__] = len(rows)
            models_with_rows.append(model)
        db.commit()
        reset_sequences(db, models_with_rows)
        db.commit()

    print("Migration complete:")
    for table_name, count in copied.items():
        print(f"  {table_name}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=DATA_DIR / "site_swiper.db",
        help="Source SQLite DB path.",
    )
    parser.add_argument(
        "--replace-app-data",
        action="store_true",
        help="Clear app-owned tables in Postgres before copying.",
    )
    args = parser.parse_args()
    migrate(args.sqlite_path, args.replace_app_data)


if __name__ == "__main__":
    main()
