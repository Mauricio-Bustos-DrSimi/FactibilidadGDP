from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text


def _seed_baseline(db) -> None:
    now = datetime.now(timezone.utc)
    db.execute(text("""
        INSERT INTO gestor.proyecto_importacion
          (id,legacy_proyecto_id,nombre,creado_origen_en,payload_origen,hash_origen)
        VALUES ('project-1','project-1','Replica',:now,'{}'::jsonb,'project-hash')
    """), {"now": now})
    db.execute(text("""
        INSERT INTO gestor.candidato
          (legacy_candidato_id,proyecto_id,estado_actual_id,estado_origen,
           certeza_mapeo,version_origen,datos,payload_origen,hash_origen)
        VALUES ('847','project-1',1,'pendiente','EXACTA',1,
                '{"Unidad":"PIRQUE"}'::jsonb,
                '{"etapa_actual":"jefatura","grupo_flujo":"pendiente"}'::jsonb,
                'candidate-hash')
    """))
    db.commit()


def test_candidate_action_is_isolated_from_replicated_baseline(db):
    _seed_baseline(db)

    db.execute(text("""
        UPDATE pruebas_gestor.candidato_ubicacion
        SET estado='aprobado', grupo_flujo='proposed', ultima_accion='accept'
        WHERE id=847
    """))
    db.execute(text("""
        INSERT INTO pruebas_gestor.revision
          (id_candidato,etapa,id_revisor,accion,comentario,creado_en)
        VALUES (847,'comite','test-user','accept','accion 8003',now())
    """))
    db.commit()

    baseline = db.execute(text("""
        SELECT estado_origen,payload_origen->>'grupo_flujo'
        FROM gestor.candidato WHERE legacy_candidato_id='847'
    """)).one()
    overlay = db.execute(text("""
        SELECT estado,grupo_flujo,ultima_accion
        FROM pruebas_gestor.candidato_ubicacion WHERE id=847
    """)).one()
    local_reviews = db.scalar(text("""
        SELECT count(*) FROM pruebas_gestor.revision_local
        WHERE id_candidato=847 AND accion='accept'
    """))

    assert baseline == ("pendiente", "pendiente")
    assert overlay == ("aprobado", "proposed", "accept")
    assert local_reviews == 1

    db.execute(text("""
        UPDATE gestor.candidato
        SET datos='{"Unidad":"PIRQUE ACTUALIZADO"}'::jsonb
        WHERE legacy_candidato_id='847'
    """))
    db.commit()
    live_values = db.execute(text("""
        SELECT datos_visualizacion->>'Unidad',estado
        FROM pruebas_gestor.candidato_ubicacion WHERE id=847
    """)).one()
    assert live_values == ("PIRQUE ACTUALIZADO", "aprobado")


def test_variables_override_does_not_version_replicated_variables(db):
    _seed_baseline(db)
    event_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO integracion.evento_entrada
          (id,evento_origen_id,tabla_origen,operacion,clave_origen,
           orden_origen,ocurrido_en,payload,payload_hash,estado)
        VALUES (:id,'variable:847:1','variables_proyecto_candidato','SNAPSHOT','847',
                1,now(),'{}'::jsonb,'event-hash','APLICADO')
    """), {"id": event_id})
    db.execute(text("""
        INSERT INTO gestor.variable_proyecto_version
          (candidato_id,evento_origen_id,legacy_variable_id,version,valores,
           hash_origen,vigente,ocurrido_en)
        SELECT id,:event_id,'1',1,'{"unidad":"ORIGEN"}'::jsonb,
               'variable-hash',true,now()
        FROM gestor.candidato WHERE legacy_candidato_id='847'
    """), {"event_id": event_id})
    db.execute(text("""
        INSERT INTO pruebas_gestor.variables_proyecto_candidato
          (id_candidato,unidad,actualizado_por_id,actualizado_en)
        VALUES (847,'PRUEBA 8003','test-user',now())
    """))
    db.commit()

    assert db.scalar(text("""
        SELECT valores->>'unidad' FROM gestor.variable_proyecto_version
        WHERE vigente
    """)) == "ORIGEN"
    assert db.scalar(text("""
        SELECT unidad FROM pruebas_gestor.variables_proyecto_candidato
        WHERE id_candidato=847
    """)) == "PRUEBA 8003"
