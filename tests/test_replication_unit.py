from app.replication.events import canonical_json, payload_hash
from app.replication import snapshot as snapshot_module
from app.replication.snapshot import _event_time, poll_once
from app.replication.state_mapping import translate_state

from datetime import datetime, timezone


def test_hash_is_stable_across_key_order():
    assert payload_hash({"b": 2, "a": 1}) == payload_hash({"a": 1, "b": 2})
    assert canonical_json({"ñ": "sí"}) == '{"ñ":"sí"}'


def test_state_origin_is_preserved_and_classified():
    assert translate_state("pendiente").codigo == "PENDIENTE"
    assert translate_state("pendiente").certeza == "EXACTA"
    assert translate_state("aprobado").codigo == "PROPUESTO"
    assert translate_state("aprobado").certeza == "INFERIDA"
    assert translate_state("locales_proyecto").codigo == "APROBADO"
    assert translate_state("por_abrir").codigo == "PROYECTO"
    assert translate_state("estado_nuevo").certeza == "DESCONOCIDA"


def test_missing_source_timestamp_is_deterministic():
    expected = datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert _event_time({}, "ultima_accion_en") == expected
    assert _event_time({}, None) == expected


def test_polling_hash_scan_captures_new_candidate_without_action_date(monkeypatch):
    missing_candidate = {
        "id": 560,
        "estado": "pendiente",
        "grupo_flujo": "pendiente",
        "ultima_accion_en": None,
        "datos_visualizacion": {"ID": 560},
    }

    class Rows:
        def __init__(self, values):
            self.values = values

        def mappings(self):
            return self

        def __iter__(self):
            return iter(self.values)

    class Source:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _params=None):
            sql = str(statement)
            if sql.strip() == 'SELECT * FROM "candidato_ubicacion" ORDER BY "id"':
                return Rows([missing_candidate])
            return Rows([])

    class Legacy:
        def connect(self):
            return Source()

    checkpoint = type("Checkpoint", (), {
        "ultimo_id": "559",
        "ultima_fecha": datetime(2026, 8, 25, tzinfo=timezone.utc),
        "ultimo_hash": None,
        "actualizado_en": None,
    })()

    class Target:
        def get(self, _model, key):
            return checkpoint if key == "poll:candidato_ubicacion" else None

        def add(self, _row):
            return None

        def commit(self):
            return None

        def scalars(self, _query):
            return []

    received = []
    monkeypatch.setattr(
        snapshot_module,
        "receive_event",
        lambda _target, event: (received.append(event) or event, True),
    )

    poll_once(Legacy(), Target(), dry_run=False)

    candidate_events = [event for event in received if event.table == "candidato_ubicacion"]
    assert len(candidate_events) == 1
    assert candidate_events[0].key == "560"
    assert candidate_events[0].operation == "HASH_SCAN"
