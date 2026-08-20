from __future__ import annotations

from sqlalchemy import text


CANDIDATE_TABLES = {
    ("gestor", "candidato"),
    ("gestor", "transicion_estado"),
    ("gestor", "actividad_candidato"),
    ("gestor", "variable_proyecto_version"),
    ("gestor", "documento_candidato"),
    ("gestor", "notificacion_envio"),
    ("integracion", "evento_entrada"),
    ("integracion", "evento_salida"),
    ("integracion", "evento_fallido"),
    ("factibilidad", "entrega"),
    ("factibilidad", "tarea_local"),
    ("factibilidad", "decision_local"),
    ("factibilidad", "visto_bueno_local"),
    ("pruebas_gestor", "candidato_override"),
    ("pruebas_gestor", "revision_local"),
    ("pruebas_gestor", "variable_override"),
}


def test_every_candidate_owned_table_exposes_projection_id(db):
    rows = db.execute(text("""
        SELECT table_schema, table_name
        FROM information_schema.columns
        WHERE column_name='id_proyeccion'
    """)).all()
    assert CANDIDATE_TABLES <= set(rows)


def test_projection_id_is_automatic_and_follows_source_correction(db):
    db.execute(text("""
        INSERT INTO gestor.candidato
          (legacy_candidato_id, id_proyeccion, estado_actual_id, estado_origen,
           certeza_mapeo, version_origen, datos, payload_origen, hash_origen)
        VALUES
          ('100', '900', 1, 'pendiente', 'EXACTA', 1,
           '{}'::jsonb, '{}'::jsonb, 'traceability-candidate')
    """))
    db.execute(text("""
        INSERT INTO factibilidad.tarea_local
          (id_candidato, clave_grupo, clave_tarea, estado)
        VALUES (100, 'grupo', 'tarea', 'en_proceso')
    """))
    assert db.scalar(text("""
        SELECT id_proyeccion FROM factibilidad.tarea_local
        WHERE id_candidato=100 AND clave_tarea='tarea'
    """)) == "900"

    db.execute(text("""
        UPDATE gestor.candidato SET id_proyeccion='901'
        WHERE legacy_candidato_id='100'
    """))
    assert db.scalar(text("""
        SELECT id_proyeccion FROM factibilidad.tarea_local
        WHERE id_candidato=100 AND clave_tarea='tarea'
    """)) == "901"
