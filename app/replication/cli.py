"""Operational CLI. Mutating commands always support --dry-run."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Operational commands are normally launched from the checkout. Load its
# private environment before importing modules that construct typed settings.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)

from alembic import command
from alembic.config import Config

from app.config import settings
from app.replication.db import cdc_engine, legacy_engine, target_session
from app.replication.events import process_pending, replay_failed
from app.replication.documents import inventory_documents
from app.replication.factibility_migration import migrate_factibility
from app.replication.reconcile import reconcile
from app.replication.snapshot import poll_once, read_only_preflight, snapshot


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="factibilidad-replication")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    for name in ("migrate", "snapshot", "factibility-snapshot", "poll", "apply", "reconcile", "replay", "documents"):
        item = commands.add_parser(name)
        item.add_argument("--dry-run", action="store_true", required=False)
    commands.choices["snapshot"].add_argument("--batch-size", type=int, default=1000)
    commands.choices["poll"].add_argument("--limit", type=int, default=1000)
    commands.choices["apply"].add_argument("--limit", type=int, default=100)
    commands.choices["replay"].add_argument("--event-id")
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "preflight":
        result = read_only_preflight(
            cdc_engine() if settings.cdc_database_url else legacy_engine()
        )
    elif args.command == "migrate":
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        command.upgrade(config, "head", sql=args.dry_run)
        result = {"dry_run": args.dry_run, "migration": "head"}
    else:
        with target_session() as target:
            if args.command == "snapshot":
                result = snapshot(
                    legacy_engine(), target, dry_run=args.dry_run, batch_size=args.batch_size
                )
            elif args.command == "factibility-snapshot":
                result = migrate_factibility(
                    legacy_engine(), target, dry_run=args.dry_run
                )
            elif args.command == "poll":
                result = poll_once(
                    legacy_engine(), target, dry_run=args.dry_run, limit=args.limit
                )
            elif args.command == "apply":
                if args.dry_run:
                    result = {"dry_run": True, "message": "No events were applied"}
                else:
                    result = process_pending(target, args.limit)
            elif args.command == "reconcile":
                result = reconcile(
                    legacy_engine(),
                    target,
                    dry_run=args.dry_run,
                    output_dir=Path("data") / "reconciliation",
                )
            elif args.command == "replay":
                if args.dry_run:
                    result = {"dry_run": True, "message": "No failed events were replayed"}
                else:
                    import uuid
                    result = {"requeued": replay_failed(
                        target, uuid.UUID(args.event_id) if args.event_id else None
                    )}
            elif args.command == "documents":
                source_dir = os.getenv("LEGACY_DOCUMENTS_DIR", "").strip()
                if not source_dir:
                    raise RuntimeError("LEGACY_DOCUMENTS_DIR is required")
                result = inventory_documents(Path(source_dir), target, dry_run=args.dry_run)
            else:  # pragma: no cover
                raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
