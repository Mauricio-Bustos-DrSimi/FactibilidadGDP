from __future__ import annotations

import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from app.ingestion import fetch_postgres_rows
from app.replication import cdc
from app.replication import worker


class QueryCanceled(Exception):
    pass


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
    observed = {"consumer_stopped": False, "joined": False}

    class WorkerThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            return None

        def join(self, timeout):
            observed["joined"] = timeout == 5

    monkeypatch.setattr(worker.threading, "Thread", WorkerThread)

    def consume(_slot_name, *, stop_event):
        handlers[worker.signal.SIGTERM](worker.signal.SIGTERM, None)
        observed["consumer_stopped"] = stop_event.is_set()

    monkeypatch.setattr(worker, "consume_existing_slot", consume)

    worker.main()

    assert observed == {"consumer_stopped": True, "joined": True}


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
