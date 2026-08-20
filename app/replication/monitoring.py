"""Replication health without exposing connection strings or payloads."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, text

from app.config import settings
from app.replication import models
from app.replication.db import legacy_engine, target_session


def legacy_health() -> tuple[dict, int]:
    if not settings.legacy_database_url:
        return {"status": "disabled", "legacy_sync_enabled": settings.legacy_sync_enabled}, 200
    try:
        with legacy_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "mode": settings.replication_mode}, 200
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__}, 503


def replication_health() -> tuple[dict, int]:
    if not settings.legacy_sync_enabled or settings.replication_mode == "disabled":
        return {"status": "disabled", "shadow_mode": settings.shadow_mode}, 200
    try:
        with target_session() as db:
            checkpoint = db.get(models.CheckpointCDC, "replica")
            heartbeat = db.get(models.CheckpointCDC, "worker")
            counts = dict(db.execute(
                select(models.EventoEntrada.estado, func.count(models.EventoEntrada.id))
                .group_by(models.EventoEntrada.estado)
            ).all())
            latest_reconciliation = db.scalar(
                select(models.Reconciliacion)
                .order_by(models.Reconciliacion.iniciado_en.desc())
                .limit(1)
            )
            now = datetime.now(timezone.utc)
            checkpoint_time = heartbeat.actualizado_en if heartbeat else None
            if checkpoint_time and checkpoint_time.tzinfo is None:
                checkpoint_time = checkpoint_time.replace(tzinfo=timezone.utc)
            lag = max(0, int((now - checkpoint_time).total_seconds())) if checkpoint_time else None
            inconsistent = bool(
                latest_reconciliation and latest_reconciliation.diferencias_cantidad
            )
            delayed = lag is None or lag > settings.replication_lag_alert_seconds
            payload = {
                "status": "degraded" if delayed or inconsistent else "ok",
                "mode": settings.replication_mode,
                "consistency": "transactional" if settings.replication_mode == "cdc" else "eventual",
                "shadow_mode": settings.shadow_mode,
                "last_lsn": checkpoint.source_lsn if checkpoint else None,
                "last_checkpoint": checkpoint_time,
                "lag_seconds": lag,
                "pending": counts.get("PENDIENTE", 0),
                "failed": counts.get("FALLIDO", 0),
                "retrying": counts.get("REINTENTO", 0),
                "reconciliation_differences": (
                    latest_reconciliation.diferencias_cantidad if latest_reconciliation else None
                ),
                "alert": delayed or inconsistent,
            }
            return payload, 503 if payload["status"] == "degraded" else 200
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__, "alert": True}, 503
