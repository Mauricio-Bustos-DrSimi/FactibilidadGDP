"""Backfill denormalized workflow columns and readable JSON in Postgres."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.example", override=True)

from app import models, workflow  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402


def _decode_text(value: str) -> str:
    if "\\u" not in value:
        return value
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value


def _readable_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {_decode_text(str(k)): _readable_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_readable_json(item) for item in value]
    if isinstance(value, str):
        return _decode_text(value)
    return value


def _apply_review(candidate: models.LocationCandidate, review: models.Review, group: str) -> str:
    candidate.last_action = review.action
    candidate.last_action_at = review.created_at
    candidate.last_actor_role = review.reviewer.role if review.reviewer else None
    if review.action == "skip":
        candidate.skipped_at = review.created_at
    elif review.action == "like":
        candidate.suggested_at = review.created_at
        group = "suggested"
    elif review.action in {"accept", "star"}:
        candidate.approved_at = review.created_at
        group = "approved"
    elif review.action == "project":
        candidate.project_at = review.created_at
        group = "project"
    elif review.action == "reject":
        candidate.rejected_at = review.created_at
        candidate.last_reject_note = review.note
        if group == "approved":
            candidate.rejected_from_approved_at = review.created_at
        elif group == "project":
            candidate.rejected_from_project_at = review.created_at
        group = "rejected"
    elif review.action == "send_back":
        candidate.returned_at = review.created_at
        group = "pending"
    elif review.action == "reopen":
        candidate.reopened_at = review.created_at
        group = "pending"
    return group


def _review_sort_key(review: models.Review):
    return (review.created_at or datetime.min, review.id)


def backfill() -> None:
    init_db()
    with SessionLocal() as db:
        candidates = db.scalars(select(models.LocationCandidate)).all()
        for candidate in candidates:
            candidate.workflow_group = "pending"
            candidate.last_action = None
            candidate.last_action_at = None
            candidate.last_actor_role = None
            candidate.last_reject_note = None
            candidate.suggested_at = None
            candidate.approved_at = None
            candidate.rejected_at = None
            candidate.project_at = None
            candidate.skipped_at = None
            candidate.returned_at = None
            candidate.reopened_at = None
            candidate.rejected_from_approved_at = None
            candidate.rejected_from_project_at = None
            group = "pending"
            for review in sorted(candidate.reviews, key=_review_sort_key):
                group = _apply_review(candidate, review, group)
            candidate.workflow_group = workflow.candidate_group(db, candidate)
            candidate.display_data = _readable_json(candidate.display_data or {})
            flag_modified(candidate, "display_data")

        for business in db.scalars(select(models.BusinessLocation)).all():
            business.attributes = _readable_json(business.attributes or {})
            flag_modified(business, "attributes")

        db.commit()
        print(f"Backfilled {len(candidates)} candidates")


if __name__ == "__main__":
    backfill()
