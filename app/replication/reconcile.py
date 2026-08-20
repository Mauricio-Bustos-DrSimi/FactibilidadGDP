"""Read-only source/target reconciliation with JSON and CSV reports."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.replication.events import payload_hash
from app.replication.documents import _projection_id
from app.replication.models import Candidato, Reconciliacion, TransicionEstado, Usuario, VariableProyectoVersion
from app.replication.state_mapping import translate_state


def _source_rows(engine: Engine, query: str) -> list[dict]:
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(query)).mappings()]


def reconcile(
    legacy: Engine,
    target: Session,
    *,
    dry_run: bool,
    output_dir: Path,
) -> dict:
    source_candidates = _source_rows(legacy, 'SELECT * FROM "candidato_ubicacion" ORDER BY "id"')
    target_candidates = list(target.scalars(select(Candidato).order_by(Candidato.legacy_candidato_id)))
    source_by_id = {str(row["id"]): row for row in source_candidates}
    target_by_id = {row.legacy_candidato_id: row for row in target_candidates}

    differences: list[dict] = []
    for legacy_id in sorted(set(source_by_id) | set(target_by_id), key=lambda value: (len(value), value)):
        source = source_by_id.get(legacy_id)
        replica = target_by_id.get(legacy_id)
        if source is None:
            differences.append({"entity": "candidate", "legacy_id": legacy_id, "field": "presence", "source": "missing", "target": "present"})
            continue
        if replica is None:
            differences.append({"entity": "candidate", "legacy_id": legacy_id, "field": "presence", "source": "present", "target": "missing"})
            continue
        expected = translate_state(source.get("estado"))
        actual_code = target.scalar(text(
            "SELECT codigo FROM gestor.estado_catalogo WHERE id=:state_id"
        ), {"state_id": replica.estado_actual_id})
        if actual_code != expected.codigo:
            differences.append({"entity": "candidate", "legacy_id": legacy_id, "field": "state", "source": expected.codigo, "target": actual_code})
        source_projection_id = _projection_id(source.get("datos_visualizacion") or {})
        if replica.id_proyeccion != source_projection_id:
            differences.append({
                "entity": "candidate",
                "legacy_id": legacy_id,
                "field": "id_proyeccion",
                "source": source_projection_id,
                "target": replica.id_proyeccion,
            })
        source_payload = dict(source)
        target_payload = dict(replica.payload_origen)
        # This is a deterministic local ordering marker, not a legacy field.
        target_payload.pop("_source_version", None)
        if payload_hash(source_payload) != payload_hash(target_payload):
            differences.append({"entity": "candidate", "legacy_id": legacy_id, "field": "record_hash", "source": payload_hash(source_payload), "target": payload_hash(target_payload)})

    source_state_counts = Counter(
        translate_state(row.get("estado")).codigo for row in source_candidates
    )
    target_state_counts = dict(target.execute(text("""
        SELECT e.codigo, count(c.id)::bigint
        FROM gestor.estado_catalogo e LEFT JOIN gestor.candidato c ON c.estado_actual_id=e.id
        GROUP BY e.codigo
    """)).all())
    source_review_count = int(_source_rows(legacy, 'SELECT count(*) AS n FROM "revision"')[0]["n"])
    source_comment_count = int(_source_rows(legacy, 'SELECT count(*) AS n FROM "revision" WHERE "comentario" IS NOT NULL AND btrim("comentario") <> \'\'')[0]["n"])
    target_transition_count = int(target.scalar(select(func.count(TransicionEstado.id))) or 0)
    target_comment_count = int(target.scalar(text("""
        SELECT count(*) FROM gestor.actividad_candidato
        WHERE coalesce(detalle->>'comentario','') <> ''
    """)) or 0)
    source_user_count = int(_source_rows(legacy, 'SELECT count(*) AS n FROM "usuario"')[0]["n"])
    target_user_count = int(target.scalar(select(func.count(Usuario.id))) or 0)
    source_variable_count = int(_source_rows(legacy, 'SELECT count(*) AS n FROM "variables_proyecto_candidato"')[0]["n"])
    target_variable_count = int(target.scalar(select(func.count(VariableProyectoVersion.id)).where(VariableProyectoVersion.vigente.is_(True))) or 0)

    source_users = _source_rows(legacy, 'SELECT * FROM "usuario" ORDER BY "id"')
    target_users = {row.legacy_usuario_id: row for row in target.scalars(select(Usuario))}
    for source_user in source_users:
        legacy_id = str(source_user["id"])
        replica = target_users.get(legacy_id)
        if replica is None or payload_hash(source_user) != payload_hash(replica.payload_origen):
            differences.append({
                "entity": "user", "legacy_id": legacy_id, "field": "record_hash",
                "source": payload_hash(source_user),
                "target": payload_hash(replica.payload_origen) if replica else "missing",
            })

    source_variables = _source_rows(
        legacy, 'SELECT * FROM "variables_proyecto_candidato" ORDER BY "id_candidato"'
    )
    target_variables = {
        legacy_id: variable
        for variable, legacy_id in target.execute(
            select(VariableProyectoVersion, Candidato.legacy_candidato_id)
            .join(Candidato, Candidato.id == VariableProyectoVersion.candidato_id)
            .where(VariableProyectoVersion.vigente.is_(True))
        )
    }
    for source_variable in source_variables:
        legacy_id = str(source_variable["id_candidato"])
        replica = target_variables.get(legacy_id)
        if replica is None or payload_hash(source_variable) != payload_hash(replica.valores):
            differences.append({
                "entity": "variables", "legacy_id": legacy_id, "field": "current_hash",
                "source": payload_hash(source_variable),
                "target": payload_hash(replica.valores) if replica else "missing",
            })

    source_review_rows = _source_rows(
        legacy,
        'SELECT "id", "id_candidato", "accion", "comentario", "creado_en" '
        'FROM "revision" ORDER BY "id_candidato", "creado_en", "id"',
    )
    source_review_sequences: dict[str, list] = {}
    for row in source_review_rows:
        source_review_sequences.setdefault(str(row["id_candidato"]), []).append(row)
    target_review_rows = list(target.execute(text("""
        SELECT payload FROM integracion.evento_entrada
        WHERE lower(split_part(tabla_origen,'.',-1))='revision'
          AND estado='APLICADO'
        ORDER BY candidato_legacy_id, orden_origen
    """)).scalars())
    target_review_sequences: dict[str, list] = {}
    for row in target_review_rows:
        candidate_id = str(row.get("id_candidato") or row.get("candidate_id") or "")
        target_review_sequences.setdefault(candidate_id, []).append({
            "id": row.get("id"),
            "id_candidato": row.get("id_candidato") or row.get("candidate_id"),
            "accion": row.get("accion") or row.get("action"),
            "comentario": row.get("comentario") or row.get("note"),
            "creado_en": row.get("creado_en") or row.get("created_at"),
        })
    for legacy_id in set(source_review_sequences) | set(target_review_sequences):
        source_hash = payload_hash(source_review_sequences.get(legacy_id, []))
        target_hash = payload_hash(target_review_sequences.get(legacy_id, []))
        if source_hash != target_hash:
            differences.append({
                "entity": "reviews", "legacy_id": legacy_id, "field": "ordered_hash",
                "source": source_hash, "target": target_hash,
            })

    legacy_documents_setting = os.getenv("LEGACY_DOCUMENTS_DIR", "").strip()
    legacy_documents_root = Path(legacy_documents_setting) if legacy_documents_setting else None
    source_document_hashes: set[str] = set()
    source_projection_ids = {
        projection_id
        for row in source_candidates
        if (projection_id := _projection_id(row.get("datos_visualizacion") or {}))
    }
    if legacy_documents_root and legacy_documents_root.exists():
        for directory in legacy_documents_root.iterdir():
            match = (
                re.fullmatch(r"Proyeccion(\d+)", directory.name, re.IGNORECASE)
                if directory.is_dir() else None
            )
            if not match or match.group(1) not in source_projection_ids:
                continue
            for path in directory.rglob("*"):
                if not path.is_file():
                    continue
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                source_document_hashes.add(digest.hexdigest())
    target_document_hashes = set(target.scalars(text(
        "SELECT sha256 FROM gestor.documento_candidato WHERE presente"
    )))
    if source_document_hashes != target_document_hashes:
        differences.append({
            "entity": "documents", "legacy_id": "*", "field": "sha256_set",
            "source": payload_hash(sorted(source_document_hashes)),
            "target": payload_hash(sorted(target_document_hashes)),
        })

    totals_source = {
        "candidates": len(source_candidates), "states": dict(source_state_counts),
        "reviews": source_review_count, "comments": source_comment_count,
        "users": source_user_count, "current_variables": source_variable_count,
        "documents": len(source_document_hashes),
    }
    totals_target = {
        "candidates": len(target_candidates), "states": target_state_counts,
        "transitions": target_transition_count, "comments": target_comment_count,
        "users": target_user_count, "current_variables": target_variable_count,
        "documents": len(target_document_hashes),
    }
    report_id = uuid.uuid4()
    report = {
        "id": str(report_id), "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run, "source": totals_source, "target": totals_target,
        "difference_count": len(differences), "differences": differences,
    }
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"reconciliation-{report_id}.json"
        csv_path = output_dir / f"reconciliation-{report_id}.csv"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["entity", "legacy_id", "field", "source", "target"])
            writer.writeheader()
            writer.writerows(differences)
        target.add(Reconciliacion(
            id=report_id, estado="OK" if not differences else "DIFERENCIAS",
            totales_origen=totals_source, totales_destino=totals_target,
            diferencias={"items": differences}, diferencias_cantidad=len(differences),
            finalizado_en=datetime.now(timezone.utc), reporte_json=str(json_path), reporte_csv=str(csv_path),
        ))
        target.commit()
        report["json_path"] = str(json_path)
        report["csv_path"] = str(csv_path)
    return report
