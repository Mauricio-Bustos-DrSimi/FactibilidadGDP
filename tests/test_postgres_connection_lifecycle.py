from __future__ import annotations

import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.ingestion import fetch_postgres_rows
from app.replication import cdc
from app.replication import worker
from app.replication.cancellation import cancel_connection
from app.replication.snapshot import poll_once


class QueryCanceled(Exception):
    pass


def test_connection_cancel_and_close_are_both_time_bounded():
    release = threading.Event()

    class BlockedConnection:
        def cancel(self):
            release.wait(timeout=1)

        def close(self):
            release.wait(timeout=1)

    started_at = time.monotonic()
    failures = cancel_connection(BlockedConnection(), timeout=0.05)
    elapsed = time.monotonic() - started_at
    release.set()

    assert elapsed < 0.5
    assert [str(failure) for failure in failures] == [
        "PostgreSQL cancellation timed out",
        "PostgreSQL forced close timed out",
    ]


class QueryCursor:
    def __init__(self, *, fail: bool = False):
        self.closed = False
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.close()

    def execute(self, _sql, _params):
        if self.fail:
            raise RuntimeError("query failed")
        return None

    def __iter__(self):
        return iter([{"id": 847}])

    def close(self):
        self.closed = True


class QueryConnection:
    def __init__(self, *, fail: bool = False):
        self.closed = False
        self.query_cursor = QueryCursor(fail=fail)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        # psycopg2 connection contexts end a transaction but do not close.
        return False

    def cursor(self, **_kwargs):
        return self.query_cursor

    def close(self):
        self.closed = True


def install_fake_psycopg(monkeypatch, connection, *, logical=False):
    psycopg2 = ModuleType("psycopg2")
    psycopg2.connect = lambda *_args, **_kwargs: connection
    psycopg2.errors = SimpleNamespace(QueryCanceled=QueryCanceled)
    extras = ModuleType("psycopg2.extras")
    extras.RealDictCursor = object
    if logical:
        extras.LogicalReplicationConnection = object
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", extras)


def test_postgres_query_closes_connection_after_success(monkeypatch):
    connection = QueryConnection()
    install_fake_psycopg(monkeypatch, connection)

    rows = fetch_postgres_rows(
        "SolicitudesProyecciones",
        schema="dw_simi",
        connection_settings={"host": "database.test"},
    )

    assert rows == [{"id": 847}]
    assert connection.query_cursor.closed is True
    assert connection.closed is True


class StreamCursor:
    def __init__(self, *, failure: BaseException | None = None):
        self.closed = False
        self.started = False
        self.failure = failure

    def start_replication(self, **_kwargs):
        self.started = True

    def consume_stream(self, _handler):
        if self.failure is not None:
            raise self.failure
        return None

    def close(self):
        self.closed = True


class StreamConnection:
    def __init__(self, *, failure: BaseException | None = None):
        self.closed = False
        self.stream_cursor = StreamCursor(failure=failure)

    def cursor(self):
        return self.stream_cursor

    def close(self):
        self.closed = True


def test_cdc_closes_cursor_and_connection_when_stream_ends(monkeypatch):
    connection = StreamConnection()
    install_fake_psycopg(monkeypatch, connection, logical=True)
    monkeypatch.setattr(cdc, "settings", SimpleNamespace(
        replication_mode="cdc",
        cdc_database_url="postgresql://replica@database.test/source",
    ))

    cdc.consume_existing_slot("existing_slot")

    assert connection.stream_cursor.started is True
    assert connection.stream_cursor.closed is True
    assert connection.closed is True


def test_cdc_closes_cursor_and_connection_when_stream_fails(monkeypatch):
    connection = StreamConnection(failure=RuntimeError("stream failed"))
    install_fake_psycopg(monkeypatch, connection, logical=True)
    monkeypatch.setattr(cdc, "settings", SimpleNamespace(
        replication_mode="cdc",
        cdc_database_url="postgresql://replica@database.test/source",
    ))

    with pytest.raises(RuntimeError, match="stream failed"):
        cdc.consume_existing_slot("existing_slot")

    assert connection.stream_cursor.closed is True
    assert connection.closed is True


def test_cdc_closes_cursor_and_connection_when_stream_is_cancelled(monkeypatch):
    class StreamCancelled(BaseException):
        pass

    connection = StreamConnection(failure=StreamCancelled())
    install_fake_psycopg(monkeypatch, connection, logical=True)
    monkeypatch.setattr(cdc, "settings", SimpleNamespace(
        replication_mode="cdc",
        cdc_database_url="postgresql://replica@database.test/source",
    ))

    with pytest.raises(StreamCancelled):
        cdc.consume_existing_slot("existing_slot")

    assert connection.stream_cursor.closed is True
    assert connection.closed is True


def test_cdc_stop_request_cancels_a_blocked_stream(monkeypatch):
    class BlockingStreamCursor(StreamCursor):
        def __init__(self):
            super().__init__()
            self.entered = threading.Event()
            self.cancelled = threading.Event()

        def consume_stream(self, _handler):
            self.entered.set()
            self.cancelled.wait(timeout=2)
            raise QueryCanceled("stream cancelled")

    class CancelableStreamConnection(StreamConnection):
        def __init__(self):
            super().__init__()
            self.stream_cursor = BlockingStreamCursor()
            self.cancel_called = False

        def cancel(self):
            self.cancel_called = True
            self.stream_cursor.cancelled.set()

    connection = CancelableStreamConnection()
    install_fake_psycopg(monkeypatch, connection, logical=True)
    monkeypatch.setattr(cdc, "settings", SimpleNamespace(
        replication_mode="cdc",
        cdc_database_url="postgresql://replica@database.test/source",
    ))
    stop_event = threading.Event()
    failures = []

    consumer = threading.Thread(
        target=lambda: _capture_failure(
            failures,
            lambda: cdc.consume_existing_slot("existing_slot", stop_event=stop_event),
        )
    )
    consumer.start()
    assert connection.stream_cursor.entered.wait(timeout=1)
    stop_event.set()
    consumer.join(timeout=2)

    assert consumer.is_alive() is False
    assert failures == []
    assert connection.cancel_called is True
    assert connection.stream_cursor.closed is True
    assert connection.closed is True


def test_cdc_cancel_failure_forces_connection_closed(monkeypatch):
    class StreamBlockedUntilCloseCursor(StreamCursor):
        def __init__(self):
            super().__init__()
            self.closed_by_connection = threading.Event()

        def consume_stream(self, _handler):
            if not self.closed_by_connection.wait(timeout=1):
                raise RuntimeError("stream remained blocked")
            raise RuntimeError("stream closed after cancellation failure")

    class CancelFailureConnection(StreamConnection):
        def __init__(self):
            super().__init__()
            self.stream_cursor = StreamBlockedUntilCloseCursor()

        def cancel(self):
            raise RuntimeError("cancel failed")

        def close(self):
            super().close()
            self.stream_cursor.closed_by_connection.set()

    connection = CancelFailureConnection()
    install_fake_psycopg(monkeypatch, connection, logical=True)
    monkeypatch.setattr(cdc, "settings", SimpleNamespace(
        replication_mode="cdc",
        cdc_database_url="postgresql://replica@database.test/source",
    ))
    stop_event = threading.Event()
    failures = []

    consumer = threading.Thread(
        target=lambda: _capture_failure(
            failures,
            lambda: cdc.consume_existing_slot("existing_slot", stop_event=stop_event),
        )
    )
    consumer.start()
    stop_event.set()
    consumer.join(timeout=2)

    assert consumer.is_alive() is False
    assert len(failures) == 1
    assert str(failures[0]) == "CDC cancellation failed"
    assert connection.closed is True


def test_cdc_blocked_cancel_falls_back_to_connection_close(monkeypatch):
    class BlockingCancelConnection(StreamConnection):
        def __init__(self):
            super().__init__()
            self.cancel_started = threading.Event()
            self.connection_closed = threading.Event()

        def cancel(self):
            self.cancel_started.set()
            self.connection_closed.wait(timeout=2)

        def close(self):
            super().close()
            self.connection_closed.set()

    class StreamBlockedUntilConnectionClose(StreamCursor):
        def __init__(self, connection):
            super().__init__()
            self.connection = connection

        def consume_stream(self, _handler):
            if not self.connection.connection_closed.wait(timeout=2):
                raise RuntimeError("stream remained blocked")
            raise RuntimeError("stream closed after cancellation timeout")

    connection = BlockingCancelConnection()
    connection.stream_cursor = StreamBlockedUntilConnectionClose(connection)
    install_fake_psycopg(monkeypatch, connection, logical=True)
    monkeypatch.setattr(cdc, "settings", SimpleNamespace(
        replication_mode="cdc",
        cdc_database_url="postgresql://replica@database.test/source",
    ))
    stop_event = threading.Event()
    failures = []

    consumer = threading.Thread(
        target=lambda: _capture_failure(
            failures,
            lambda: cdc.consume_existing_slot("existing_slot", stop_event=stop_event),
        )
    )
    consumer.start()
    stop_event.set()
    consumer.join(timeout=3)

    assert connection.cancel_started.is_set()
    assert consumer.is_alive() is False
    assert len(failures) == 1
    assert str(failures[0]) == "CDC cancellation failed"
    assert connection.closed is True


def test_cdc_does_not_hide_unrelated_error_during_stop(monkeypatch):
    stop_event = threading.Event()

    class FailingWhileStoppingCursor(StreamCursor):
        def consume_stream(self, _handler):
            stop_event.set()
            raise RuntimeError("unrelated failure")

    connection = StreamConnection()
    connection.stream_cursor = FailingWhileStoppingCursor()
    install_fake_psycopg(monkeypatch, connection, logical=True)
    monkeypatch.setattr(cdc, "settings", SimpleNamespace(
        replication_mode="cdc",
        cdc_database_url="postgresql://replica@database.test/source",
    ))

    with pytest.raises(RuntimeError, match="unrelated failure"):
        cdc.consume_existing_slot("existing_slot", stop_event=stop_event)

    assert connection.stream_cursor.closed is True
    assert connection.closed is True


def _capture_failure(failures, callback):
    try:
        callback()
    except BaseException as exc:
        failures.append(exc)


def test_cdc_worker_forwards_shutdown_to_consumer(monkeypatch):
    monkeypatch.setattr(worker, "settings", SimpleNamespace(
        legacy_sync_enabled=True,
        replication_mode="cdc",
    ))
    monkeypatch.setenv("CDC_SLOT_NAME", "existing_slot")
    handlers = {}
    monkeypatch.setattr(
        worker.signal,
        "signal",
        lambda signum, handler: handlers.__setitem__(signum, handler),
    )
    previous_handlers = {
        worker.signal.SIGINT: object(),
        worker.signal.SIGTERM: object(),
    }
    monkeypatch.setattr(
        worker.signal,
        "getsignal",
        lambda signum: previous_handlers[signum],
    )
    observed = {
        "consumer_stopped": False,
        "joined": False,
        "daemon": None,
    }

    class WorkerThread:
        def __init__(self, **kwargs):
            observed["daemon"] = kwargs.get("daemon")

        def start(self):
            return None

        def join(self, timeout=None):
            observed["joined"] = timeout is None

    monkeypatch.setattr(worker.threading, "Thread", WorkerThread)

    def consume(_slot_name, *, stop_event):
        handlers[worker.signal.SIGTERM](worker.signal.SIGTERM, None)
        observed["consumer_stopped"] = stop_event.is_set()

    monkeypatch.setattr(worker, "consume_existing_slot", consume)

    worker.main()

    assert observed == {
        "consumer_stopped": True,
        "joined": True,
        "daemon": False,
    }
    assert handlers == previous_handlers


def test_cdc_worker_can_run_outside_main_thread(monkeypatch):
    monkeypatch.setattr(worker, "settings", SimpleNamespace(
        legacy_sync_enabled=True,
        replication_mode="cdc",
    ))
    monkeypatch.setenv("CDC_SLOT_NAME", "existing_slot")
    monkeypatch.setattr(worker, "_apply_forever", lambda *_args: None)
    monkeypatch.setattr(
        worker,
        "consume_existing_slot",
        lambda _slot_name, *, stop_event: None,
    )
    failures = []

    host_thread = threading.Thread(
        target=lambda: _capture_failure(failures, worker.main)
    )
    host_thread.start()
    host_thread.join(timeout=2)

    assert host_thread.is_alive() is False
    assert failures == []


def test_cdc_worker_with_host_stop_event_preserves_signal_handlers(monkeypatch):
    monkeypatch.setattr(worker, "settings", SimpleNamespace(
        legacy_sync_enabled=True,
        replication_mode="cdc",
    ))
    monkeypatch.setenv("CDC_SLOT_NAME", "existing_slot")
    monkeypatch.setattr(worker, "_apply_forever", lambda *_args: None)
    monkeypatch.setattr(
        worker,
        "consume_existing_slot",
        lambda _slot_name, *, stop_event: None,
    )
    monkeypatch.setattr(
        worker.signal,
        "signal",
        lambda *_args: pytest.fail("host-managed worker replaced a signal handler"),
    )

    worker.main(stop_event=threading.Event())


def test_cdc_worker_cancels_active_applier_query_before_join(monkeypatch):
    query_released = threading.Event()
    query_started = threading.Event()
    observed = {"cancelled": False}

    class DriverConnection:
        def cancel(self):
            observed["cancelled"] = True
            query_released.set()

        def close(self):
            query_released.set()

    class TargetSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def connection(self):
            return SimpleNamespace(
                connection=SimpleNamespace(driver_connection=DriverConnection())
            )

    monkeypatch.setattr(worker, "settings", SimpleNamespace(
        legacy_sync_enabled=True,
        replication_mode="cdc",
    ))
    monkeypatch.setenv("CDC_SLOT_NAME", "existing_slot")
    monkeypatch.setattr(worker, "target_session", TargetSession)
    def blocked_process_pending(_target, _limit):
        query_started.set()
        query_released.wait(timeout=2)
        return {"aplicados": 0, "fallidos": 0}

    monkeypatch.setattr(worker, "process_pending", blocked_process_pending)
    monkeypatch.setattr(worker, "_heartbeat", lambda _target: None)
    monkeypatch.setattr(
        worker,
        "consume_existing_slot",
        lambda _slot_name, *, stop_event: query_started.wait(timeout=1),
    )

    worker.main(stop_event=threading.Event())

    assert observed["cancelled"] is True


def test_postgres_query_closes_connection_after_exception(monkeypatch):
    connection = QueryConnection(fail=True)
    install_fake_psycopg(monkeypatch, connection)

    with pytest.raises(RuntimeError, match="query failed"):
        fetch_postgres_rows(
            "SolicitudesProyecciones",
            schema="dw_simi",
            connection_settings={"host": "database.test"},
        )

    assert connection.query_cursor.closed is True
    assert connection.closed is True


def test_repeated_postgres_queries_leave_no_open_connections(monkeypatch):
    connections = []
    psycopg2 = ModuleType("psycopg2")

    def connect(*_args, **_kwargs):
        connection = QueryConnection()
        connections.append(connection)
        return connection

    psycopg2.connect = connect
    extras = ModuleType("psycopg2.extras")
    extras.RealDictCursor = object
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", extras)

    for _ in range(5):
        fetch_postgres_rows(
            "SolicitudesProyecciones",
            schema="dw_simi",
            connection_settings={"host": "database.test"},
        )

    assert len(connections) == 5
    assert all(connection.closed for connection in connections)


def test_repeated_real_postgres_polling_leaves_connection_count_stable(
    temporary_postgres_url,
):
    import psycopg2

    url = make_url(temporary_postgres_url)
    connection_settings = {
        "host": url.host,
        "port": url.port,
        "dbname": url.database,
        "user": url.username,
        "password": url.password,
    }
    legacy = create_engine(temporary_postgres_url)
    with legacy.begin() as connection:
        connection.execute(text(
            "CREATE TABLE revision (id bigint PRIMARY KEY, creado_en timestamp)"
        ))
        connection.execute(text(
            "CREATE TABLE candidato_ubicacion "
            "(id bigint PRIMARY KEY, ultima_accion_en timestamp)"
        ))
        connection.execute(text(
            "CREATE TABLE variables_proyecto_candidato "
            "(id bigint PRIMARY KEY, actualizado_en timestamp)"
        ))
        connection.execute(text(
            "CREATE TABLE usuario (id bigint PRIMARY KEY, eliminado_en timestamp)"
        ))
    target_engine = create_engine(temporary_postgres_url)
    observer = psycopg2.connect(**connection_settings)
    try:
        with Session(target_engine) as target:
            poll_once(legacy, target, dry_run=True)
        with observer.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
            before = cursor.fetchone()[0]

        with Session(target_engine) as target:
            for _ in range(5):
                result = poll_once(legacy, target, dry_run=True)
                assert result["consistency"] == "eventual"

        with observer.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
            after = cursor.fetchone()[0]
    finally:
        observer.close()
        legacy.dispose()
        target_engine.dispose()

    assert after == before
