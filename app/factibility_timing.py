"""Pure timing rules for the Factibilidad checklist."""
from __future__ import annotations

from datetime import datetime


COMPLETED_STATUSES = frozenset({"realizado", "no_aplica"})


def completion_timestamp(
    previous_status: str | None,
    new_status: str,
    current_completed_at: datetime | None,
    now: datetime,
) -> datetime | None:
    """Keep completion stable until a completed task is reopened."""
    was_completed = previous_status in COMPLETED_STATUSES
    will_be_completed = new_status in COMPLETED_STATUSES
    if will_be_completed and not was_completed:
        return now
    if not will_be_completed:
        return None
    return current_completed_at or now
