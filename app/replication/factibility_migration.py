"""One-time, resumable copy of pre-schema Factibilidad-owned rows."""
from __future__ import annotations

from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session

from app.replication.models import DecisionLocal, TareaLocal, VistoBuenoLocal


TABLE_MODEL = {
    "factibilidad_tarea_local": TareaLocal,
    "factibilidad_decision_local": DecisionLocal,
    "factibilidad_visto_bueno_local": VistoBuenoLocal,
}


def migrate_factibility(legacy: Engine, target: Session, *, dry_run: bool) -> dict:
    result = {"dry_run": dry_run, "tables": {}}
    with legacy.connect() as source:
        existing = set(inspect(source).get_table_names())
        for table, model in TABLE_MODEL.items():
            if table not in existing:
                result["tables"][table] = {"source": 0, "upserted": 0, "missing": True}
                continue
            rows = list(source.execute(text(f'SELECT * FROM "{table}" ORDER BY "id"')).mappings())
            result["tables"][table] = {"source": len(rows), "upserted": 0, "missing": False}
            if dry_run:
                continue
            for raw in rows:
                row = dict(raw)
                candidate_id = int(row["id_candidato"])
                if model is TareaLocal:
                    current = target.scalar(select(TareaLocal).where(
                        TareaLocal.candidato_legacy_id == candidate_id,
                        TareaLocal.clave_tarea == row["clave_tarea"],
                    ))
                    values = dict(
                        clave_grupo=row["clave_grupo"], clave_tarea=row["clave_tarea"],
                        estado=row["estado"], comentario=row.get("comentario"),
                        actualizado_por=row.get("actualizado_por_id"), actualizado_en=row["actualizado_en"],
                    )
                elif model is DecisionLocal:
                    current = target.scalar(select(DecisionLocal).where(
                        DecisionLocal.candidato_legacy_id == candidate_id
                    ))
                    values = dict(
                        decision=row["decision"], actualizado_por=row.get("actualizado_por_id"),
                        actualizado_en=row["actualizado_en"],
                    )
                else:
                    current = target.scalar(select(VistoBuenoLocal).where(
                        VistoBuenoLocal.candidato_legacy_id == candidate_id,
                        VistoBuenoLocal.area == row["area"],
                    ))
                    values = dict(
                        area=row["area"], aprobado_por=row.get("aprobado_por_id"),
                        aprobado_en=row["aprobado_en"],
                    )
                if current is None:
                    current = model(candidato_legacy_id=candidate_id, **values)
                    target.add(current)
                else:
                    for key, value in values.items():
                        setattr(current, key, value)
                result["tables"][table]["upserted"] += 1
            target.commit()
    return result
