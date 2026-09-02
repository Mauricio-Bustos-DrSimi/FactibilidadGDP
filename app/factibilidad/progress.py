"""Pure progress and completion calculations for Factibilidad checklists."""
from __future__ import annotations

from collections.abc import Iterable

from app import models
from app.factibilidad.definitions import (
    FACTIBILITY_COMPLETED_STATUSES,
    FACTIBILITY_TASK_GROUPS,
)


def build_progress(
    progress_rows: Iterable[models.FactibilityTaskProgress],
) -> tuple[list[dict], dict]:
    saved = {row.task_key: row for row in progress_rows}
    groups: list[dict] = []
    for area_key, group_key, group_title, task_definitions in FACTIBILITY_TASK_GROUPS:
        subtasks = []
        for task_key, task_title in task_definitions:
            row = saved.get(task_key)
            subtasks.append({
                "key": task_key,
                "title": task_title,
                "status": row.status if row else "no_realizado",
                "comment": row.comment if row else None,
                "updated_at": row.updated_at if row else None,
                "completed_at": row.completed_at if row else None,
            })
        completed = sum(
            subtask["status"] in FACTIBILITY_COMPLETED_STATUSES
            for subtask in subtasks
        )
        completed_at = (
            max(subtask["completed_at"] for subtask in subtasks)
            if subtasks
            and completed == len(subtasks)
            and all(subtask["completed_at"] is not None for subtask in subtasks)
            else None
        )
        groups.append({
            "area": area_key,
            "key": group_key,
            "title": group_title,
            "completed": completed,
            "total": len(subtasks),
            "progress": round((completed / len(subtasks)) * 100) if subtasks else 0,
            "completed_at": completed_at,
            "subtasks": subtasks,
        })

    area_completion = {}
    for area_key in ("legal", "arquitectura"):
        area_groups = [group for group in groups if group["area"] == area_key]
        area_completion[area_key] = (
            max(group["completed_at"] for group in area_groups)
            if area_groups
            and all(group["completed_at"] is not None for group in area_groups)
            else None
        )
    overall_completed_at = (
        max(area_completion.values()) if all(area_completion.values()) else None
    )
    return groups, {
        "areas": area_completion,
        "completed_at": overall_completed_at,
    }


__all__ = ["build_progress"]
