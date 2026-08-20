"""Create normalized shadow replica and Factibilidad ownership schemas."""
from __future__ import annotations

from alembic import op

revision = "20260820_01"
down_revision = None
branch_labels = None
depends_on = None


DDL = r"""
CREATE SCHEMA IF NOT EXISTS gestor;
CREATE SCHEMA IF NOT EXISTS integracion;
CREATE SCHEMA IF NOT EXISTS factibilidad;

CREATE TABLE IF NOT EXISTS gestor.estado_catalogo (
  id integer PRIMARY KEY, codigo varchar(32) NOT NULL UNIQUE,
  nombre varchar(80) NOT NULL, orden integer NOT NULL,
  estados_origen jsonb NOT NULL DEFAULT '[]'::jsonb,
  activo boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS gestor.rol (
  id integer PRIMARY KEY, codigo varchar(50) NOT NULL UNIQUE,
  nombre varchar(100) NOT NULL, activo boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS gestor.proyecto_importacion (
  id varchar(120) PRIMARY KEY, legacy_proyecto_id varchar(120) NOT NULL UNIQUE,
  nombre varchar(250) NOT NULL, archivo_origen text,
  creado_origen_en timestamptz, payload_origen jsonb NOT NULL DEFAULT '{}'::jsonb,
  hash_origen varchar(64) NOT NULL
);
CREATE TABLE IF NOT EXISTS integracion.evento_entrada (
  id uuid PRIMARY KEY, evento_origen_id varchar(250) NOT NULL UNIQUE,
  source_lsn varchar(40), tabla_origen varchar(160) NOT NULL,
  operacion varchar(16) NOT NULL, clave_origen varchar(250) NOT NULL,
  candidato_legacy_id varchar(120), orden_origen bigint NOT NULL,
  ocurrido_en timestamptz NOT NULL, recibido_en timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL, payload_hash varchar(64) NOT NULL,
  estado varchar(24) NOT NULL DEFAULT 'PENDIENTE', intentos integer NOT NULL DEFAULT 0,
  siguiente_intento_en timestamptz, aplicado_en timestamptz
);
CREATE INDEX IF NOT EXISTS ix_evento_entrada_estado_orden
  ON integracion.evento_entrada(estado, orden_origen);
CREATE INDEX IF NOT EXISTS ix_evento_entrada_candidato
  ON integracion.evento_entrada(candidato_legacy_id);
CREATE TABLE IF NOT EXISTS integracion.evento_salida (
  id uuid PRIMARY KEY, modo varchar(16) NOT NULL,
  tipo varchar(100) NOT NULL, clave_agregado varchar(250), payload jsonb NOT NULL,
  creado_en timestamptz NOT NULL DEFAULT now(), publicado_en timestamptz,
  CONSTRAINT ck_evento_salida_modo CHECK (modo IN ('PRUEBA','SUPRIMIDO'))
);
CREATE INDEX IF NOT EXISTS ix_evento_salida_clave ON integracion.evento_salida(clave_agregado);
CREATE TABLE IF NOT EXISTS integracion.checkpoint_cdc (
  consumidor varchar(100) PRIMARY KEY, source_lsn varchar(40), ultima_fecha timestamptz,
  ultimo_id varchar(160), ultimo_hash varchar(64), actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS integracion.migracion_control (
  clave varchar(180) PRIMARY KEY, fase varchar(80) NOT NULL, estado varchar(24) NOT NULL,
  checkpoint jsonb NOT NULL DEFAULT '{}'::jsonb, iniciado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(), finalizado_en timestamptz
);
CREATE TABLE IF NOT EXISTS gestor.usuario (
  id varchar(120) PRIMARY KEY, legacy_usuario_id varchar(120) NOT NULL UNIQUE,
  rol_id integer REFERENCES gestor.rol(id), rol varchar(50) NOT NULL, correo varchar(320) NOT NULL,
  nombre varchar(250) NOT NULL, hash_contrasena text NOT NULL,
  division_comercial varchar(120), cargo varchar(200), correos_supervisores text,
  organigrama_x numeric, organigrama_y numeric,
  activo boolean NOT NULL, eliminado_en timestamptz, creado_en timestamptz NOT NULL DEFAULT now(),
  payload_origen jsonb NOT NULL DEFAULT '{}'::jsonb, hash_origen varchar(64) NOT NULL,
  sincronizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_gestor_usuario_correo ON gestor.usuario(correo);
CREATE TABLE IF NOT EXISTS gestor.candidato (
  id bigserial PRIMARY KEY, legacy_candidato_id varchar(120) NOT NULL UNIQUE,
  proyecto_id varchar(120) REFERENCES gestor.proyecto_importacion(id),
  estado_actual_id integer NOT NULL REFERENCES gestor.estado_catalogo(id),
  estado_origen varchar(80) NOT NULL,
  certeza_mapeo varchar(16) NOT NULL CHECK (certeza_mapeo IN ('EXACTA','INFERIDA','DESCONOCIDA')),
  version_origen bigint NOT NULL DEFAULT 0, referencia_mapa text,
  latitud numeric(10,7), longitud numeric(10,7), datos jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload_origen jsonb NOT NULL DEFAULT '{}'::jsonb,
  hash_origen varchar(64) NOT NULL, actualizado_origen_en timestamptz,
  sincronizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_gestor_candidato_estado ON gestor.candidato(estado_actual_id);
CREATE TABLE IF NOT EXISTS gestor.transicion_estado (
  id bigserial PRIMARY KEY, candidato_id bigint NOT NULL REFERENCES gestor.candidato(id),
  legacy_revision_id varchar(120) UNIQUE,
  evento_origen_id uuid NOT NULL UNIQUE REFERENCES integracion.evento_entrada(id),
  estado_anterior_id integer REFERENCES gestor.estado_catalogo(id),
  estado_nuevo_id integer NOT NULL REFERENCES gestor.estado_catalogo(id),
  estado_origen varchar(80) NOT NULL, accion_origen varchar(80) NOT NULL,
  comentario text, actor_legacy_id varchar(120), orden_origen bigint NOT NULL,
  ocurrido_en timestamptz NOT NULL, creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_transicion_candidato_orden
  ON gestor.transicion_estado(candidato_id, orden_origen);
CREATE TABLE IF NOT EXISTS gestor.actividad_candidato (
  id bigserial PRIMARY KEY, candidato_id bigint NOT NULL REFERENCES gestor.candidato(id),
  evento_origen_id uuid NOT NULL REFERENCES integracion.evento_entrada(id),
  tipo varchar(80) NOT NULL, detalle jsonb NOT NULL DEFAULT '{}'::jsonb,
  ocurrido_en timestamptz NOT NULL,
  CONSTRAINT uq_actividad_evento_tipo UNIQUE(evento_origen_id, tipo)
);
CREATE INDEX IF NOT EXISTS ix_actividad_candidato ON gestor.actividad_candidato(candidato_id);
CREATE TABLE IF NOT EXISTS gestor.variable_proyecto_version (
  id bigserial PRIMARY KEY, candidato_id bigint NOT NULL REFERENCES gestor.candidato(id),
  evento_origen_id uuid NOT NULL UNIQUE REFERENCES integracion.evento_entrada(id),
  legacy_variable_id varchar(120), version integer NOT NULL, valores jsonb NOT NULL,
  hash_origen varchar(64) NOT NULL, vigente boolean NOT NULL DEFAULT true,
  ocurrido_en timestamptz NOT NULL,
  CONSTRAINT uq_variable_candidato_version UNIQUE(candidato_id, version)
);
CREATE TABLE IF NOT EXISTS gestor.documento_candidato (
  id bigserial PRIMARY KEY, candidato_id bigint NOT NULL REFERENCES gestor.candidato(id),
  ruta_origen text NOT NULL, nombre varchar(500) NOT NULL, tamano bigint NOT NULL,
  modificado_en timestamptz, sha256 varchar(64) NOT NULL,
  presente boolean NOT NULL DEFAULT true, inventariado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_documento_candidato_ruta UNIQUE(candidato_id, ruta_origen)
);
CREATE TABLE IF NOT EXISTS gestor.notificacion_envio (
  id bigserial PRIMARY KEY, evento_origen_id uuid REFERENCES integracion.evento_entrada(id),
  candidato_id bigint REFERENCES gestor.candidato(id), tipo varchar(80) NOT NULL,
  destinatarios jsonb NOT NULL DEFAULT '{}'::jsonb, estado varchar(32) NOT NULL,
  suprimido_por_shadow boolean NOT NULL DEFAULT true, registrado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_notificacion_evento_tipo UNIQUE(evento_origen_id, tipo)
);
CREATE TABLE IF NOT EXISTS gestor.punto_interes (
  id bigserial PRIMARY KEY, legacy_punto_id varchar(200) NOT NULL UNIQUE,
  nombre varchar(500), latitud numeric(10,7) NOT NULL, longitud numeric(10,7) NOT NULL,
  categoria varchar(200), atributos jsonb NOT NULL DEFAULT '{}'::jsonb,
  hash_origen varchar(64) NOT NULL
);
CREATE TABLE IF NOT EXISTS integracion.evento_fallido (
  id bigserial PRIMARY KEY,
  evento_entrada_id uuid NOT NULL UNIQUE REFERENCES integracion.evento_entrada(id),
  error_tipo varchar(200) NOT NULL, error_detalle text NOT NULL, intentos integer NOT NULL,
  primer_fallo_en timestamptz NOT NULL DEFAULT now(), ultimo_fallo_en timestamptz NOT NULL DEFAULT now(),
  resuelto_en timestamptz
);
CREATE TABLE IF NOT EXISTS integracion.reconciliacion (
  id uuid PRIMARY KEY, iniciado_en timestamptz NOT NULL DEFAULT now(), finalizado_en timestamptz,
  estado varchar(24) NOT NULL, totales_origen jsonb NOT NULL DEFAULT '{}'::jsonb,
  totales_destino jsonb NOT NULL DEFAULT '{}'::jsonb,
  diferencias jsonb NOT NULL DEFAULT '{}'::jsonb, diferencias_cantidad integer NOT NULL DEFAULT 0,
  reporte_json text, reporte_csv text
);
CREATE TABLE IF NOT EXISTS factibilidad.entrega (
  id bigserial PRIMARY KEY, id_candidato bigint NOT NULL,
  area_destino varchar(100) NOT NULL, estado varchar(32) NOT NULL,
  antecedentes jsonb NOT NULL DEFAULT '{}'::jsonb, entregado_por varchar(120),
  entregado_en timestamptz, creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_entrega_candidato ON factibilidad.entrega(id_candidato);
CREATE TABLE IF NOT EXISTS factibilidad.tarea_local (
  id bigserial PRIMARY KEY, id_candidato bigint NOT NULL,
  clave_grupo varchar(100) NOT NULL, clave_tarea varchar(100) NOT NULL,
  estado varchar(32) NOT NULL, comentario text, actualizado_por_id varchar(120),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_factibilidad_tarea UNIQUE(id_candidato, clave_tarea)
);
CREATE INDEX IF NOT EXISTS ix_tarea_local_candidato ON factibilidad.tarea_local(id_candidato);
CREATE TABLE IF NOT EXISTS factibilidad.decision_local (
  id bigserial PRIMARY KEY, id_candidato bigint NOT NULL UNIQUE,
  decision varchar(32) NOT NULL, actualizado_por_id varchar(120),
  actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS factibilidad.visto_bueno_local (
  id bigserial PRIMARY KEY, id_candidato bigint NOT NULL,
  area varchar(32) NOT NULL, aprobado_por_id varchar(120), aprobado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_factibilidad_vb UNIQUE(id_candidato, area)
);

INSERT INTO gestor.estado_catalogo(id,codigo,nombre,orden,estados_origen) VALUES
 (1,'PENDIENTE','Pendiente',10,'["pendiente","pending","devuelto","returned","sugerido","suggested"]'),
 (2,'OBSERVACION','Observación',20,'["observacion","observation"]'),
 (3,'RECHAZADO','Rechazado',30,'["rechazado","rejected"]'),
 (4,'EN_ESTUDIO','En estudio',40,'["en_estudio","study"]'),
 (5,'PROPUESTO','Propuesto',50,'["aprobado","approved","approved_final"]'),
 (6,'APROBADO','Aprobado',60,'["locales_proyecto","approved_location"]'),
 (7,'PROYECTO','Proyecto',70,'["por_abrir","opening","project"]')
ON CONFLICT (id) DO UPDATE SET
 codigo=EXCLUDED.codigo, nombre=EXCLUDED.nombre, orden=EXCLUDED.orden,
 estados_origen=EXCLUDED.estados_origen, activo=true;

CREATE OR REPLACE VIEW gestor.vw_pendientes AS
 SELECT c.* FROM gestor.candidato c JOIN gestor.estado_catalogo e ON e.id=c.estado_actual_id WHERE e.codigo='PENDIENTE';
CREATE OR REPLACE VIEW gestor.vw_observacion AS
 SELECT c.* FROM gestor.candidato c JOIN gestor.estado_catalogo e ON e.id=c.estado_actual_id WHERE e.codigo='OBSERVACION';
CREATE OR REPLACE VIEW gestor.vw_rechazados AS
 SELECT c.* FROM gestor.candidato c JOIN gestor.estado_catalogo e ON e.id=c.estado_actual_id WHERE e.codigo='RECHAZADO';
CREATE OR REPLACE VIEW gestor.vw_en_estudio AS
 SELECT c.* FROM gestor.candidato c JOIN gestor.estado_catalogo e ON e.id=c.estado_actual_id WHERE e.codigo='EN_ESTUDIO';
CREATE OR REPLACE VIEW gestor.vw_propuestos AS
 SELECT c.* FROM gestor.candidato c JOIN gestor.estado_catalogo e ON e.id=c.estado_actual_id WHERE e.codigo='PROPUESTO';
CREATE OR REPLACE VIEW gestor.vw_aprobados AS
 SELECT c.* FROM gestor.candidato c JOIN gestor.estado_catalogo e ON e.id=c.estado_actual_id WHERE e.codigo='APROBADO';
CREATE OR REPLACE VIEW gestor.vw_proyectos AS
 SELECT c.* FROM gestor.candidato c JOIN gestor.estado_catalogo e ON e.id=c.estado_actual_id WHERE e.codigo='PROYECTO';
CREATE OR REPLACE VIEW gestor.vw_metricas_flujo AS
 SELECT e.codigo AS estado, e.nombre, e.orden, count(c.id)::bigint AS cantidad
 FROM gestor.estado_catalogo e LEFT JOIN gestor.candidato c ON c.estado_actual_id=e.id
 WHERE e.activo GROUP BY e.codigo,e.nombre,e.orden ORDER BY e.orden;

-- Read-only adapters for the existing FastAPI presentation layer. All stored
-- data remains in the normalized gestor tables above.
CREATE OR REPLACE VIEW gestor.proyecto AS
 SELECT legacy_proyecto_id AS id_proyecto,
        payload_origen->>'url_proyecto' AS url_proyecto, nombre, archivo_origen,
        payload_origen->>'notas' AS notas, creado_origen_en AS creado_en
 FROM gestor.proyecto_importacion;

CREATE OR REPLACE VIEW gestor.candidato_ubicacion AS
 SELECT id, proyecto_id AS id_proyecto, referencia_mapa, latitud::double precision,
        longitud::double precision, datos AS datos_visualizacion,
        coalesce(payload_origen->>'etapa_actual','jefatura') AS etapa_actual,
        estado_origen AS estado,
        coalesce((payload_origen->>'prioridad')::boolean,false) AS prioridad,
        coalesce(payload_origen->>'grupo_flujo',estado_origen) AS grupo_flujo,
        payload_origen->>'ultima_accion' AS ultima_accion,
        nullif(payload_origen->>'ultima_accion_en','')::timestamptz AS ultima_accion_en,
        payload_origen->>'rol_ultimo_actor' AS rol_ultimo_actor,
        payload_origen->>'comentario_ultimo_rechazo' AS comentario_ultimo_rechazo,
        nullif(payload_origen->>'sugerido_en','')::timestamptz AS sugerido_en,
        nullif(payload_origen->>'aprobado_en','')::timestamptz AS aprobado_en,
        nullif(payload_origen->>'rechazado_en','')::timestamptz AS rechazado_en,
        nullif(payload_origen->>'proyecto_en','')::timestamptz AS proyecto_en,
        nullif(payload_origen->>'omitido_en','')::timestamptz AS omitido_en,
        nullif(payload_origen->>'devuelto_en','')::timestamptz AS devuelto_en,
        nullif(payload_origen->>'reabierto_en','')::timestamptz AS reabierto_en,
        nullif(payload_origen->>'rechazado_desde_aprobado_en','')::timestamptz AS rechazado_desde_aprobado_en,
        nullif(payload_origen->>'rechazado_desde_proyecto_en','')::timestamptz AS rechazado_desde_proyecto_en
 FROM gestor.candidato;

CREATE OR REPLACE VIEW gestor.revision AS
 SELECT t.id * 2 AS id, t.candidato_id AS id_candidato,
        coalesce(e.payload->>'etapa','replica') AS etapa,
        coalesce(t.actor_legacy_id,'') AS id_revisor,
        t.accion_origen AS accion, t.comentario, t.ocurrido_en AS creado_en
 FROM gestor.transicion_estado t JOIN integracion.evento_entrada e ON e.id=t.evento_origen_id
 UNION ALL
 SELECT a.id * 2 + 1 AS id, a.candidato_id AS id_candidato,
        coalesce(e.payload->>'etapa','replica') AS etapa,
        coalesce(e.payload->>'id_revisor','') AS id_revisor,
        coalesce(e.payload->>'accion','comment') AS accion,
        a.detalle->>'comentario' AS comentario, a.ocurrido_en AS creado_en
 FROM gestor.actividad_candidato a JOIN integracion.evento_entrada e ON e.id=a.evento_origen_id
 WHERE a.tipo='COMENTARIO';

CREATE OR REPLACE VIEW gestor.variables_proyecto_candidato AS
 SELECT v.id, v.candidato_id AS id_candidato,
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
 FROM gestor.variable_proyecto_version v WHERE v.vigente;
"""


def upgrade() -> None:
    # Every statement is idempotent. Alembic wraps the complete revision in one
    # PostgreSQL transaction, so an error leaves no partially applied schema.
    op.execute(DDL)


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade is intentionally disabled; use the documented rollback procedure."
    )
