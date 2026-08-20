"""Read-only legacy document inventory."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.replication.models import Candidato, DocumentoCandidato
from app.replication.identity import projection_id_from_display_data


def _projection_id(data: dict) -> str | None:
    return projection_id_from_display_data(data)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_documents(root: Path, target: Session, *, dry_run: bool) -> dict:
    """Hash files without deleting, moving or modifying the source directory."""
    candidates = list(target.scalars(select(Candidato)))
    by_projection = {
        projection_id: candidate
        for candidate in candidates
        if (projection_id := _projection_id(candidate.datos))
    }
    found: set[tuple[int, str]] = set()
    counters = {"files": 0, "updated": 0, "unmatched_directories": 0, "dry_run": dry_run}
    if not root.exists():
        return {**counters, "status": "source_directory_missing"}
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        match = re.fullmatch(r"Proyeccion(\d+)", directory.name, re.IGNORECASE)
        candidate = by_projection.get(match.group(1)) if match else None
        if candidate is None:
            counters["unmatched_directories"] += 1
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            stat = path.stat()
            digest = _sha256(path)
            counters["files"] += 1
            found.add((candidate.id, relative))
            if dry_run:
                continue
            row = target.scalar(select(DocumentoCandidato).where(
                DocumentoCandidato.candidato_id == candidate.id,
                DocumentoCandidato.ruta_origen == relative,
            ))
            if row is None:
                row = DocumentoCandidato(
                    candidato_id=candidate.id, ruta_origen=relative, nombre=path.name,
                    tamano=stat.st_size, modificado_en=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                    sha256=digest, presente=True,
                )
                target.add(row)
            else:
                row.nombre = path.name
                row.tamano = stat.st_size
                row.modificado_en = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                row.sha256 = digest
                row.presente = True
                row.inventariado_en = datetime.now(timezone.utc)
            counters["updated"] += 1
    if not dry_run:
        for row in target.scalars(select(DocumentoCandidato)).all():
            if (row.candidato_id, row.ruta_origen) not in found:
                row.presente = False
                row.inventariado_en = datetime.now(timezone.utc)
        target.commit()
    return counters
