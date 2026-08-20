from app.replication.events import canonical_json, payload_hash
from app.replication.state_mapping import translate_state


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
