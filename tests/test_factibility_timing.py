from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.factibility_timing import completion_timestamp


def test_completion_time_is_stable_for_completed_statuses():
    first = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    later = first + timedelta(days=3)

    assert completion_timestamp("en_proceso", "realizado", None, first) == first
    assert completion_timestamp("realizado", "no_aplica", first, later) == first
    assert completion_timestamp("no_aplica", "no_aplica", first, later) == first


def test_reopening_clears_time_and_recompletion_records_a_new_time():
    first = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    later = first + timedelta(days=3)

    assert completion_timestamp("realizado", "en_proceso", first, later) is None
    assert completion_timestamp("en_proceso", "no_aplica", None, later) == later
