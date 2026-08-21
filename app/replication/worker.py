"""Long-running replication worker for systemd."""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from pathlib import Path
from datetime import datetime, timezone

from app.config import settings
from app.replication.cdc import consume_existing_slot
from app.replication.db import legacy_engine, target_session
from app.replication.events import process_pending
from app.replication.documents import inventory_documents
from app.replication.snapshot import poll_once
from app.replication.models import CheckpointCDC

logger = logging.getLogger("factibilidad.replication")


def _heartbeat(target) -> None:
    checkpoint = target.get(CheckpointCDC, "worker")
    if checkpoint is None:
        checkpoint = CheckpointCDC(consumidor="worker")
        target.add(checkpoint)
    checkpoint.ultima_fecha = datetime.now(timezone.utc)
    checkpoint.actualizado_en = datetime.now(timezone.utc)
    target.commit()


def _apply_forever(stop_event: threading.Event) -> None:
    last_document_inventory = 0.0
    document_interval = max(30, int(os.getenv("DOCUMENT_INVENTORY_SECONDS", "300")))
    document_root = os.getenv("LEGACY_DOCUMENTS_DIR", "").strip()
    while not stop_event.is_set():
        with target_session() as target:
            result = process_pending(target, 500)
            if document_root and time.monotonic() - last_document_inventory >= document_interval:
                inventory_documents(Path(document_root), target, dry_run=False)
                last_document_inventory = time.monotonic()
            _heartbeat(target)
        if not result["aplicados"] and not result["fallidos"]:
            stop_event.wait(1)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    if not settings.legacy_sync_enabled or settings.replication_mode == "disabled":
        logger.warning("Legacy replication is disabled")
        return
    stop_event = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    if settings.replication_mode == "cdc":
        slot_name = os.getenv("CDC_SLOT_NAME", "").strip()
        if not slot_name:
            raise RuntimeError("CDC_SLOT_NAME is required for CDC mode")
        applier = threading.Thread(
            target=_apply_forever,
            args=(stop_event,),
            daemon=True,
            name="event-applier",
        )
        applier.start()
        # This only consumes an existing slot; it never creates source objects.
        try:
            consume_existing_slot(slot_name, stop_event=stop_event)
        finally:
            stop_event.set()
            applier.join(timeout=5)
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


if __name__ == "__main__":
    main()
