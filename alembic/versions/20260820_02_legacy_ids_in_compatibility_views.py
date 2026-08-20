"""Expose legacy candidate identifiers through compatibility views."""
from __future__ import annotations

from alembic import op


revision = "20260820_02"
down_revision = "20260820_01"
branch_labels = None
depends_on = None


DDL = r"""
DROP VIEW IF EXISTS gestor.variables_proyecto_candidato;
DROP VIEW IF EXISTS gestor.revision;
DROP VIEW IF EXISTS gestor.candidato_ubicacion;

CREATE OR REPLACE VIEW gestor.candidato_ubicacion AS
 SELECT c.legacy_candidato_id::integer AS id,
        c.proyecto_id AS id_proyecto, c.referencia_mapa,
        c.latitud::double precision, c.longitud::double precision,
        c.datos AS datos_visualizacion,
        coalesce(c.payload_origen->>'etapa_actual','jefatura') AS etapa_actual,
        c.estado_origen AS estado,
        coalesce((c.payload_origen->>'prioridad')::boolean,false) AS prioridad,
        coalesce(c.payload_origen->>'grupo_flujo',c.estado_origen) AS grupo_flujo,
        c.payload_origen->>'ultima_accion' AS ultima_accion,
        nullif(c.payload_origen->>'ultima_accion_en','')::timestamptz AS ultima_accion_en,
        c.payload_origen->>'rol_ultimo_actor' AS rol_ultimo_actor,
        c.payload_origen->>'comentario_ultimo_rechazo' AS comentario_ultimo_rechazo,
        nullif(c.payload_origen->>'sugerido_en','')::timestamptz AS sugerido_en,
        nullif(c.payload_origen->>'aprobado_en','')::timestamptz AS aprobado_en,
        nullif(c.payload_origen->>'rechazado_en','')::timestamptz AS rechazado_en,
        nullif(c.payload_origen->>'proyecto_en','')::timestamptz AS proyecto_en,
        nullif(c.payload_origen->>'omitido_en','')::timestamptz AS omitido_en,
        nullif(c.payload_origen->>'devuelto_en','')::timestamptz AS devuelto_en,
        nullif(c.payload_origen->>'reabierto_en','')::timestamptz AS reabierto_en,
        nullif(c.payload_origen->>'rechazado_desde_aprobado_en','')::timestamptz AS rechazado_desde_aprobado_en,
        nullif(c.payload_origen->>'rechazado_desde_proyecto_en','')::timestamptz AS rechazado_desde_proyecto_en
 FROM gestor.candidato c;

CREATE OR REPLACE VIEW gestor.revision AS
 SELECT t.id * 2 AS id, c.legacy_candidato_id::integer AS id_candidato,
        coalesce(e.payload->>'etapa','replica') AS etapa,
        coalesce(t.actor_legacy_id,'') AS id_revisor,
        t.accion_origen AS accion, t.comentario, t.ocurrido_en AS creado_en
 FROM gestor.transicion_estado t
 JOIN gestor.candidato c ON c.id=t.candidato_id
 JOIN integracion.evento_entrada e ON e.id=t.evento_origen_id
 UNION ALL
 SELECT a.id * 2 + 1 AS id, c.legacy_candidato_id::integer AS id_candidato,
        coalesce(e.payload->>'etapa','replica') AS etapa,
        coalesce(e.payload->>'id_revisor','') AS id_revisor,
        coalesce(e.payload->>'accion','comment') AS accion,
        a.detalle->>'comentario' AS comentario, a.ocurrido_en AS creado_en
 FROM gestor.actividad_candidato a
 JOIN gestor.candidato c ON c.id=a.candidato_id
 JOIN integracion.evento_entrada e ON e.id=a.evento_origen_id
 WHERE a.tipo='COMENTARIO';

CREATE OR REPLACE VIEW gestor.variables_proyecto_candidato AS
 SELECT v.id, c.legacy_candidato_id::integer AS id_candidato,
        v.valores->>'cve_unidad' AS cve_unidad, v.valores->>'unidad' AS unidad,
        v.valores->>'comuna' AS comuna, v.valores->>'provincia' AS provincia,
        v.valores->>'region' AS region, nullif(v.valores->>'mt2','')::double precision AS mt2,
        v.valores->>'valor_arriendo' AS valor_arriendo,
        v.valores->>'gastos_comunes' AS gastos_comunes,
        v.valores->>'clausula_salida' AS clausula_salida,
        v.valores->>'meses_gracia' AS meses_gracia,
        v.valores->>'plazo_arriendo' AS plazo_arriendo,
        v.valores->>'garantia' AS garantia, v.valores->>'tipo_proyecto' AS tipo_proyecto,
        nullif(v.valores->>'fecha_apertura_aproximada','')::date AS fecha_apertura_aproximada,
        v.valores->>'contacto_nombre' AS contacto_nombre,
        v.valores->>'contacto_telefono' AS contacto_telefono,
        v.valores->>'contacto_email' AS contacto_email,
        v.valores->>'flujo_franquicia' AS flujo_franquicia,
        v.valores->>'franquiciado_nombre' AS franquiciado_nombre,
        v.valores->>'franquiciado_telefono' AS franquiciado_telefono,
        v.valores->>'franquiciado_email' AS franquiciado_email,
        v.valores->>'tiendas_anclas' AS tiendas_anclas,
        v.valores->>'proyeccion_supervisor' AS proyeccion_supervisor,
        v.valores->>'proyeccion_jefe_comercial' AS proyeccion_jefe_comercial,
        nullif(v.valores->>'fecha_entrega_local','')::date AS fecha_entrega_local,
        v.valores->>'actualizado_por_id' AS actualizado_por_id,
        v.ocurrido_en AS actualizado_en
 FROM gestor.variable_proyecto_version v
 JOIN gestor.candidato c ON c.id=v.candidato_id
 WHERE v.vigente;
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is intentionally disabled.")
