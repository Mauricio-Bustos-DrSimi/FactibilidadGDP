"""Logical-decoding consumer for an already authorized, pre-created slot.

This module never creates or drops publications or replication slots. The
initial implementation consumes ``wal2json`` because the destination schema is
different from the legacy schema and therefore requires transformation.
"""
from __future__ import annotations

import itertools
import json
import threading
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.replication.db import target_session
from app.replication.events import IncomingEvent, payload_hash, receive_event


def _dsn(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://", 1)


def _lsn(value: int) -> str:
    return f"{value >> 32:X}/{value & 0xFFFFFFFF:X}"


def _change_payload(change: dict[str, Any]) -> dict[str, Any]:
    names = change.get("columnnames") or []
    values = change.get("columnvalues") or []
    payload = dict(zip(names, values))
    if change.get("oldkeys"):
        payload["_oldkeys"] = dict(zip(
            change["oldkeys"].get("keynames") or [],
            change["oldkeys"].get("keyvalues") or [],
        ))
    return payload


def consume_existing_slot(
    slot_name: str,
    *,
    stop_event: threading.Event | None = None,
) -> None:
    """Run forever and acknowledge WAL only after inbox commit.

    The slot must already exist with output plugin ``wal2json``. Creating it is
    a separately authorized administrator operation.
    """
    if settings.replication_mode != "cdc":
        raise RuntimeError("REPLICATION_MODE must be cdc")
    if not settings.cdc_database_url:
        raise RuntimeError("CDC_DATABASE_URL is required")
    try:
        import psycopg2
        from psycopg2.extras import LogicalReplicationConnection
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("psycopg2 with logical replication support is required") from exc

    connection = psycopg2.connect(
        _dsn(settings.cdc_database_url),
        connection_factory=LogicalReplicationConnection,
    )
    with closing(connection):
        with closing(connection.cursor()) as cursor:
            if stop_event is not None and stop_event.is_set():
                return
            sequence = itertools.count(1)

            def handle(message) -> None:
                decoded = json.loads(message.payload)
                changes = decoded.get("change") or []
                with target_session() as target:
                    for index, change in enumerate(changes):
                        payload = _change_payload(change)
                        schema = change.get("schema") or "public"
                        table = change.get("table") or "unknown"
                        key = (
                            payload.get("id")
                            or payload.get("id_proyecto")
                            or payload.get("correo")
                            or payload_hash(payload)
                        )
                        candidate_id = payload.get("id_candidato")
                        # data_start is the WAL byte position and preserves commit
                        # order; index preserves row order inside the wal2json batch.
                        order = int(message.data_start or 0) + index
                        if not order:
                            order = next(sequence)
                        receive_event(target, IncomingEvent(
                            origin_id=f"cdc:{_lsn(message.data_start)}:{index}:{schema}.{table}:{key}",
                            source_lsn=_lsn(message.data_start),
                            table=f"{schema}.{table}",
                            operation=str(change.get("kind") or "unknown").upper(),
                            key=str(key),
                            order=order,
                            occurred_at=datetime.now(timezone.utc),
                            payload=payload,
                            candidate_legacy_id=str(candidate_id) if candidate_id is not None else None,
                        ))
                    target.commit()
                # At-least-once delivery: a crash before this feedback replays messages;
                # the inbox unique key makes their effects exactly once.
                message.cursor.send_feedback(flush_lsn=message.data_start)

            cursor.start_replication(
                slot_name=slot_name,
                decode=True,
                options={"include-lsn": "1", "include-xids": "1", "format-version": "1"},
            )
            finished = threading.Event()
            cancellation_thread = None
            if stop_event is not None:
                def cancel_when_requested() -> None:
                    while not finished.wait(0.1):
                        if stop_event.is_set():
                            connection.cancel()
                            return

                cancellation_thread = threading.Thread(
                    target=cancel_when_requested,
                    daemon=True,
                    name="cdc-cancellation",
                )
                cancellation_thread.start()
            try:
                cursor.consume_stream(handle)
            except psycopg2.errors.QueryCanceled:
                if stop_event is None or not stop_event.is_set():
                    raise
            finally:
                finished.set()
                if cancellation_thread is not None:
                    cancellation_thread.join(timeout=1)
