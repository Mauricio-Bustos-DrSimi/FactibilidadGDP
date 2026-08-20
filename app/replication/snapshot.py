"""Resumable read-only snapshot and polling fallback.

Polling is intentionally documented as eventual consistency.  It does not
claim the lossless boundary provided by an exported logical-decoding snapshot.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session

from app.replication.events import IncomingEvent, canonical_json, payload_hash, receive_event
from app.replication.models import CheckpointCDC


SNAPSHOT_TABLES = (
    ("usuario", "id", "creado_en"),
    ("proyecto", "id_proyecto", "creado_en"),
    ("candidato_ubicacion", "id", "ultima_accion_en"),
    ("revision", "id", "creado_en"),
    ("variables_proyecto_candidato", "id", "actualizado_en"),
    ("punto_interes", "id", None),
)


def _dict_rows(connection: Connection, sql: str, params: dict | None = None) -> list[dict]:
    return [dict(row) for row in connection.execute(text(sql), params or {}).mappings()]


def _event_time(row: dict, time_column: str | None) -> datetime:
    value = row.get(time_column) if time_column else None
    if not isinstance(value, datetime):
        # Missing legacy timestamps must not make a resumed snapshot produce a
        # different payload/order for the same immutable source row.
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _event_order(occurred_at: datetime, key: object) -> int:
    numeric_key = int(key) if str(key).isdigit() else 0
    return int(occurred_at.timestamp()) * 1_000_000 + numeric_key % 1_000_000


def read_only_preflight(engine: Engine) -> dict[str, Any]:
    """Inspect CDC prerequisites without creating publications or slots."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT current_database() AS database_name,
                   current_user AS database_user,
                   current_setting('server_version') AS server_version,
                   current_setting('wal_level') AS wal_level,
                   current_setting('max_replication_slots')::int AS max_replication_slots,
                   current_setting('max_wal_senders')::int AS max_wal_senders,
                   EXISTS (
                     SELECT 1 FROM pg_roles
                     WHERE rolname='pg_create_subscription'
                       AND pg_has_role(current_user, oid, 'MEMBER')
                   ) AS can_create_subscription
        """)).mappings().one()
        privileges = conn.execute(text("""
            SELECT has_database_privilege(current_user, current_database(), 'CONNECT') AS can_connect,
                   has_schema_privilege(current_user, 'public', 'USAGE') AS can_use_public
        """)).mappings().one()
        publications = _dict_rows(conn, "SELECT pubname FROM pg_publication ORDER BY pubname")
        slots = _dict_rows(conn, """
            SELECT slot_name, plugin, slot_type, database, active
            FROM pg_replication_slots ORDER BY slot_name
        """)
        return {
            **dict(row),
            **dict(privileges),
            "publications": publications,
            "replication_slots": slots,
            "mutation_performed": False,
        }


def snapshot(
    legacy: Engine,
    target: Session,
    *,
    dry_run: bool,
    batch_size: int = 1000,
) -> dict[str, Any]:
    result: dict[str, Any] = {"dry_run": dry_run, "tables": {}, "consistency": "eventual"}
    with legacy.connect().execution_options(isolation_level="REPEATABLE READ") as source:
        transaction = source.begin()
        try:
            result["snapshot_lsn"] = source.scalar(text("SELECT pg_current_wal_lsn()::text"))
            for table, key_column, time_column in SNAPSHOT_TABLES:
                count = int(source.scalar(text(f'SELECT count(*) FROM "{table}"')) or 0)
                result["tables"][table] = {"read": count, "queued": 0}
                if dry_run:
                    continue
                last_key: Any = None
                while True:
                    where = "" if last_key is None else f'WHERE "{key_column}" > :last_key'
                    rows = _dict_rows(
                        source,
                        f'SELECT * FROM "{table}" {where} ORDER BY "{key_column}" LIMIT :limit',
                        {"last_key": last_key, "limit": batch_size},
                    )
                    if not rows:
                        break
                    for row in rows:
                        key = row[key_column]
                        occurred = _event_time(row, time_column)
                        digest = hashlib.sha256(canonical_json(row).encode()).hexdigest()
                        order = _event_order(occurred, key)
                        payload = row
                        origin_prefix = "snapshot"
                        # Entity rows must exist before their append-only
                        # history is replayed. The final mutable candidate row
                        # is queued again after all historical revisions.
                        if table in {"usuario", "proyecto"}:
                            order = -8_000_000_000_000_000_000 + result["tables"][table]["queued"]
                        if table == "candidato_ubicacion":
                            base_payload = dict(row)
                            base_payload["estado"] = "pendiente"
                            base_payload["grupo_flujo"] = "pendiente"
                            base_payload["_source_version"] = 0
                            base_event, base_created = receive_event(target, IncomingEvent(
                                origin_id=f"snapshot-base:{table}:{key}:{digest}",
                                table=table, operation="SNAPSHOT_BASE", key=str(key),
                                order=-7_000_000_000_000_000_000 + int(key),
                                occurred_at=occurred, payload=base_payload,
                                source_lsn=result["snapshot_lsn"],
                                candidate_legacy_id=str(key),
                            ))
                            result["tables"][table]["queued"] += int(base_created)
                            order = 7_000_000_000_000_000_000 + int(key)
                            origin_prefix = "snapshot-final"
                            payload = dict(row)
                            payload["_source_version"] = _event_order(occurred, key)
                        event, created = receive_event(target, IncomingEvent(
                            origin_id=f"{origin_prefix}:{table}:{key}:{digest}",
                            table=table,
                            operation="SNAPSHOT",
                            key=str(key),
                            order=order,
                            occurred_at=occurred,
                            payload=payload,
                            source_lsn=result["snapshot_lsn"],
                            candidate_legacy_id=str(row.get("id_candidato") or row.get("id") or "") or None,
                        ))
                        result["tables"][table]["queued"] += int(created)
                    target.commit()
                    last_key = rows[-1][key_column]
            if not dry_run:
                # The snapshot already contains every row visible in this
                # transaction. Seed incremental checkpoints at its exact high
                # water marks so the first polling cycle starts afterwards
                # instead of replaying the complete history under poll:* IDs.
                checkpoint_queries = {
                    "poll:revision": """
                        SELECT id::text AS last_id, creado_en AS last_date
                        FROM revision ORDER BY id DESC LIMIT 1
                    """,
                    "poll:candidato_ubicacion": """
                        SELECT id::text AS last_id,
                               COALESCE(ultima_accion_en, TIMESTAMP 'epoch') AS last_date
                        FROM candidato_ubicacion
                        ORDER BY COALESCE(ultima_accion_en, TIMESTAMP 'epoch') DESC, id DESC
                        LIMIT 1
                    """,
                    "poll:variables_proyecto_candidato": """
                        SELECT id::text AS last_id, actualizado_en AS last_date
                        FROM variables_proyecto_candidato
                        ORDER BY actualizado_en DESC, id DESC LIMIT 1
                    """,
                }
                for checkpoint_name, query in checkpoint_queries.items():
                    high_water = source.execute(text(query)).mappings().first()
                    if high_water is None:
                        continue
                    checkpoint = target.get(CheckpointCDC, checkpoint_name)
                    if checkpoint is None:
                        checkpoint = CheckpointCDC(consumidor=checkpoint_name)
                        target.add(checkpoint)
                    checkpoint.ultimo_id = high_water["last_id"]
                    checkpoint.ultima_fecha = _event_time(high_water, "last_date")
                    checkpoint.ultimo_hash = payload_hash(dict(high_water))
                    checkpoint.actualizado_en = datetime.now(timezone.utc)
                target.commit()
            transaction.commit()
        except Exception:
            transaction.rollback()
            target.rollback()
            raise
    return result


POLL_QUERIES = {
    "revision": (
        'SELECT * FROM "revision" WHERE "id" > :last_id ORDER BY "id" LIMIT :limit',
        "id",
        "creado_en",
    ),
    "candidato_ubicacion": (
        'SELECT * FROM "candidato_ubicacion" '
        'WHERE (COALESCE("ultima_accion_en", TIMESTAMP \'epoch\'), "id") > (:last_date, :last_id) '
        'ORDER BY COALESCE("ultima_accion_en", TIMESTAMP \'epoch\'), "id" LIMIT :limit',
        "id",
        "ultima_accion_en",
    ),
    "variables_proyecto_candidato": (
        'SELECT * FROM "variables_proyecto_candidato" '
        'WHERE ("actualizado_en", "id") > (:last_date, :last_id) '
        'ORDER BY "actualizado_en", "id" LIMIT :limit',
        "id",
        "actualizado_en",
    ),
}


def poll_once(
    legacy: Engine,
    target: Session,
    *,
    dry_run: bool,
    limit: int = 1000,
) -> dict[str, Any]:
    """Incremental fallback with date+id+hash checkpoints (eventual consistency)."""
    output: dict[str, Any] = {"dry_run": dry_run, "consistency": "eventual", "tables": {}}
    with legacy.connect() as source:
        for table, (query, key_column, time_column) in POLL_QUERIES.items():
            checkpoint_name = f"poll:{table}"
            checkpoint = target.get(CheckpointCDC, checkpoint_name)
            last_id = int(checkpoint.ultimo_id) if checkpoint and str(checkpoint.ultimo_id or "").isdigit() else 0
            last_date = checkpoint.ultima_fecha if checkpoint and checkpoint.ultima_fecha else datetime(1970, 1, 1, tzinfo=timezone.utc)
            source_last_date = last_date.replace(tzinfo=None) if last_date.tzinfo else last_date
            params = {"last_id": last_id, "last_date": source_last_date, "limit": limit}
            if table == "revision":
                params = {"last_id": last_id, "limit": limit}
            rows = _dict_rows(source, query, params)
            output["tables"][table] = len(rows)
            if dry_run:
                continue
            for row in rows:
                key = row[key_column]
                occurred = _event_time(row, time_column)
                digest = hashlib.sha256(canonical_json(row).encode()).hexdigest()
                receive_event(target, IncomingEvent(
                    origin_id=f"poll:{table}:{key}:{digest}",
                    table=table,
                    operation="UPSERT",
                    key=str(key),
                    order=_event_order(occurred, key),
                    occurred_at=occurred,
                    payload=row,
                    candidate_legacy_id=str(row.get("id_candidato") or row.get("id") or "") or None,
                ))
                if checkpoint is None:
                    checkpoint = CheckpointCDC(consumidor=checkpoint_name)
                    target.add(checkpoint)
                checkpoint.ultima_fecha = occurred
                checkpoint.ultimo_id = str(key)
                checkpoint.ultimo_hash = digest
                checkpoint.actualizado_en = datetime.now(timezone.utc)
            target.commit()
        # usuario has no reliable updated timestamp in the legacy model. A
        # complete hash scan detects profile changes and logical deletions.
        user_rows = _dict_rows(source, 'SELECT * FROM "usuario" ORDER BY "id"')
        output["tables"]["usuario_hash_scan"] = len(user_rows)
        if not dry_run:
            for row in user_rows:
                key = row["id"]
                occurred = _event_time(row, "eliminado_en")
                digest = hashlib.sha256(canonical_json(row).encode()).hexdigest()
                receive_event(target, IncomingEvent(
                    origin_id=f"poll:usuario:{key}:{digest}",
                    table="usuario", operation="UPSERT", key=str(key),
                    order=_event_order(occurred, key), occurred_at=occurred,
                    payload=row,
                ))
            target.commit()
    return output
