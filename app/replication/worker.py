"""Long-running replication worker for systemd."""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.replication.cancellation import cancel_connection
from app.replication.cdc import consume_existing_slot
from app.replication.db import legacy_engine, target_session
from app.replication.events import process_pending
from app.replication.documents import inventory_documents
from app.replication.snapshot import poll_once
from app.replication.models import CheckpointCDC

logger = logging.getLogger("factibilidad.replication")


class _ActiveTargetConnection:
    """Tracks the one checked-out target connection owned by the applier."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connection: Any | None = None
        self._cancel_requested = False

    def bind(self, target) -> None:
        proxy = target.connection().connection
        connection = getattr(proxy, "driver_connection", proxy)
        with self._lock:
            self._connection = connection
            cancel_now = self._cancel_requested
        if cancel_now:
            self._cancel(connection)

    def release(self) -> None:
        with self._lock:
            self._connection = None

    def request_cancel(self) -> None:
        with self._lock:
            self._cancel_requested = True
            connection = self._connection
        if connection is not None:
            self._cancel(connection)

    @staticmethod
    def _cancel(connection) -> None:
        failures = cancel_connection(connection)
        if failures:
            logger.warning(
                "Target PostgreSQL cancellation required a forced close (%s)",
                type(failures[0]).__name__,
            )


def _heartbeat(target) -> None:
    checkpoint = target.get(CheckpointCDC, "worker")
    if checkpoint is None:
        checkpoint = CheckpointCDC(consumidor="worker")
        target.add(checkpoint)
    checkpoint.ultima_fecha = datetime.now(timezone.utc)
    checkpoint.actualizado_en = datetime.now(timezone.utc)
    target.commit()


def _apply_forever(
    stop_event: threading.Event,
    active_connection: _ActiveTargetConnection | None = None,
) -> None:
    active_connection = active_connection or _ActiveTargetConnection()
    last_document_inventory = 0.0
    document_interval = max(30, int(os.getenv("DOCUMENT_INVENTORY_SECONDS", "300")))
    document_root = os.getenv("LEGACY_DOCUMENTS_DIR", "").strip()
    while not stop_event.is_set():
        with target_session() as target:
            active_connection.bind(target)
            try:
                result = process_pending(target, 500)
                if stop_event.is_set():
                    return
                if document_root and time.monotonic() - last_document_inventory >= document_interval:
                    inventory_documents(Path(document_root), target, dry_run=False)
                    last_document_inventory = time.monotonic()
                if stop_event.is_set():
                    return
                _heartbeat(target)
            finally:
                active_connection.release()
        if not result["aplicados"] and not result["fallidos"]:
            stop_event.wait(1)


def main(*, stop_event: threading.Event | None = None) -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    if not settings.legacy_sync_enabled or settings.replication_mode == "disabled":
        logger.warning("Legacy replication is disabled")
        return
    owns_stop_event = stop_event is None
    stop_event = stop_event or threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    previous_handlers: dict[int, object] = {}
    if owns_stop_event and threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)
    try:
        if settings.replication_mode == "cdc":
            slot_name = os.getenv("CDC_SLOT_NAME", "").strip()
            if not slot_name:
                raise RuntimeError("CDC_SLOT_NAME is required for CDC mode")
            active_connection = _ActiveTargetConnection()
            applier = threading.Thread(
                target=_apply_forever,
                args=(stop_event, active_connection),
                daemon=False,
                name="event-applier",
            )
            applier.start()
            # This only consumes an existing slot; it never creates source objects.
            try:
                consume_existing_slot(slot_name, stop_event=stop_event)
            finally:
                stop_event.set()
                active_connection.request_cancel()
                # Do not return while the applier still owns a target session.
                applier.join()
            return
        logger.warning("Polling mode provides eventual consistency, not transactional CDC")
        last_document_inventory = 0.0
        document_interval = max(30, int(os.getenv("DOCUMENT_INVENTORY_SECONDS", "300")))
        document_root = os.getenv("LEGACY_DOCUMENTS_DIR", "").strip()
        while not stop_event.is_set():
            with target_session() as target:
                poll_once(legacy_engine(), target, dry_run=False, limit=1000)
                result = process_pending(target, 500)
                if document_root and time.monotonic() - last_document_inventory >= document_interval:
                    inventory_documents(Path(document_root), target, dry_run=False)
                    last_document_inventory = time.monotonic()
                _heartbeat(target)
            logger.info("Polling cycle applied=%s failed=%s", result["aplicados"], result["fallidos"])
            stop_event.wait(settings.replication_poll_seconds)
    finally:
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)


if __name__ == "__main__":
    main()
