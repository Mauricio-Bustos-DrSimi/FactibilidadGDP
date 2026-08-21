"""Bounded cancellation for PostgreSQL operations owned by replication."""
from __future__ import annotations

import threading
from typing import Any


def cancel_connection(
    connection: Any,
    *,
    timeout: float = 1.0,
    failures: list[Exception] | None = None,
) -> list[Exception]:
    """Request cancellation and force-close when libpq cannot answer promptly."""
    failures = failures if failures is not None else []

    def run_bounded(operation, name: str) -> tuple[bool, list[Exception]]:
        finished = threading.Event()
        operation_failures: list[Exception] = []

        def run() -> None:
            try:
                operation()
            except Exception as exc:
                operation_failures.append(exc)
            finally:
                finished.set()

        thread = threading.Thread(
            target=run,
            daemon=True,
            name=name,
        )
        thread.start()
        completed = finished.wait(timeout)
        return completed, list(operation_failures)

    cancel_completed, cancel_failures = run_bounded(
        connection.cancel,
        "postgres-cancellation",
    )
    if not cancel_completed:
        failures.append(TimeoutError("PostgreSQL cancellation timed out"))
    else:
        failures.extend(cancel_failures)
    if failures:
        try:
            close_completed, close_failures = run_bounded(
                connection.close,
                "postgres-forced-close",
            )
        except Exception as exc:
            failures.append(exc)
        else:
            if not close_completed:
                failures.append(TimeoutError("PostgreSQL forced close timed out"))
            else:
                failures.extend(close_failures)
    return failures
