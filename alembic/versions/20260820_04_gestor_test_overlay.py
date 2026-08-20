"""Add an isolated writable overlay for Gestor tests on port 8003."""
from __future__ import annotations

from alembic import op


revision = "20260820_04"
down_revision = "20260820_03"
branch_labels = None
depends_on = None


DDL = r"""
CREATE SCHEMA IF NOT EXISTS pruebas_gestor;

CREATE TABLE IF NOT EXISTS pruebas_gestor.candidato_override (
  id integer PRIMARY KEY,
  id_proyecto varchar(120) NOT NULL,
  referencia_mapa text,
  latitud double precision,
  longitud double precision,
  datos_visualizacion jsonb NOT NULL DEFAULT '{}'::jsonb,
  etapa_actual varchar NOT NULL,
  estado varchar NOT NULL,
  prioridad boolean NOT NULL DEFAULT false,
  grupo_flujo varchar,
  ultima_accion varchar,
  ultima_accion_en timestamptz,
  rol_ultimo_actor varchar,
  comentario_ultimo_rechazo text,
  sugerido_en timestamptz,
  aprobado_en timestamptz,
  rechazado_en timestamptz,
  proyecto_en timestamptz,
  omitido_en timestamptz,
  devuelto_en timestamptz,
  reabierto_en timestamptz,
  rechazado_desde_aprobado_en timestamptz,
  rechazado_desde_proyecto_en timestamptz,
  actualizado_en timestamptz NOT NULL DEFAULT now()
);

CREATE SEQUENCE IF NOT EXISTS pruebas_gestor.revision_local_id_seq
  AS bigint START WITH -1 INCREMENT BY -1 MINVALUE -9223372036854775808 MAXVALUE -1 NO CYCLE;
CREATE TABLE IF NOT EXISTS pruebas_gestor.revision_local (
  id bigint PRIMARY KEY DEFAULT nextval('pruebas_gestor.revision_local_id_seq'),
  id_candidato integer NOT NULL,
  etapa varchar NOT NULL,
  id_revisor varchar(120) NOT NULL,
  accion varchar NOT NULL,
  comentario text,
  creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pruebas_revision_candidato
  ON pruebas_gestor.revision_local(id_candidato, creado_en, id);

CREATE SEQUENCE IF NOT EXISTS pruebas_gestor.variable_local_id_seq
  AS bigint START WITH -1 INCREMENT BY -1 MINVALUE -9223372036854775808 MAXVALUE -1 NO CYCLE;
CREATE TABLE IF NOT EXISTS pruebas_gestor.variable_override (
  id bigint PRIMARY KEY DEFAULT nextval('pruebas_gestor.variable_local_id_seq'),
  id_candidato integer NOT NULL UNIQUE,
  cve_unidad varchar,
  unidad varchar,
  comuna varchar,
  provincia varchar,
  region varchar,
  mt2 double precision,
  valor_arriendo varchar,
  gastos_comunes varchar,
  clausula_salida text,
  meses_gracia varchar,
  plazo_arriendo varchar,
  garantia varchar,
  tipo_proyecto varchar,
  fecha_apertura_aproximada date,
  contacto_nombre varchar,
  contacto_telefono varchar,
  contacto_email varchar,
  flujo_franquicia varchar,
  franquiciado_nombre varchar,
  franquiciado_telefono varchar,
  franquiciado_email varchar,
  tiendas_anclas text,
  proyeccion_supervisor varchar,
  proyeccion_jefe_comercial varchar,
  fecha_entrega_local date,
  actualizado_por_id varchar(120),
  actualizado_en timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW pruebas_gestor.candidato_ubicacion AS
 SELECT b.* FROM gestor.candidato_ubicacion b
 WHERE NOT EXISTS (
   SELECT 1 FROM pruebas_gestor.candidato_override o WHERE o.id=b.id
 )
 UNION ALL
 SELECT o.id, o.id_proyecto, o.referencia_mapa, o.latitud, o.longitud,
        o.datos_visualizacion, o.etapa_actual, o.estado, o.prioridad,
        o.grupo_flujo, o.ultima_accion, o.ultima_accion_en,
        o.rol_ultimo_actor, o.comentario_ultimo_rechazo, o.sugerido_en,
        o.aprobado_en, o.rechazado_en, o.proyecto_en, o.omitido_en,
        o.devuelto_en, o.reabierto_en, o.rechazado_desde_aprobado_en,
        o.rechazado_desde_proyecto_en
 FROM pruebas_gestor.candidato_override o;

CREATE OR REPLACE FUNCTION pruebas_gestor.guardar_candidato_override()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO pruebas_gestor.candidato_override (
    id,id_proyecto,referencia_mapa,latitud,longitud,datos_visualizacion,
    etapa_actual,estado,prioridad,grupo_flujo,ultima_accion,ultima_accion_en,
    rol_ultimo_actor,comentario_ultimo_rechazo,sugerido_en,aprobado_en,
    rechazado_en,proyecto_en,omitido_en,devuelto_en,reabierto_en,
    rechazado_desde_aprobado_en,rechazado_desde_proyecto_en,actualizado_en
  ) VALUES (
    NEW.id,NEW.id_proyecto,NEW.referencia_mapa,NEW.latitud,NEW.longitud,
    NEW.datos_visualizacion,NEW.etapa_actual,NEW.estado,NEW.prioridad,
    NEW.grupo_flujo,NEW.ultima_accion,NEW.ultima_accion_en,
    NEW.rol_ultimo_actor,NEW.comentario_ultimo_rechazo,NEW.sugerido_en,
    NEW.aprobado_en,NEW.rechazado_en,NEW.proyecto_en,NEW.omitido_en,
    NEW.devuelto_en,NEW.reabierto_en,NEW.rechazado_desde_aprobado_en,
    NEW.rechazado_desde_proyecto_en,now()
  ) ON CONFLICT (id) DO UPDATE SET
    id_proyecto=EXCLUDED.id_proyecto,
    referencia_mapa=EXCLUDED.referencia_mapa,
    latitud=EXCLUDED.latitud,
    longitud=EXCLUDED.longitud,
    datos_visualizacion=EXCLUDED.datos_visualizacion,
    etapa_actual=EXCLUDED.etapa_actual,
    estado=EXCLUDED.estado,
    prioridad=EXCLUDED.prioridad,
    grupo_flujo=EXCLUDED.grupo_flujo,
    ultima_accion=EXCLUDED.ultima_accion,
    ultima_accion_en=EXCLUDED.ultima_accion_en,
    rol_ultimo_actor=EXCLUDED.rol_ultimo_actor,
    comentario_ultimo_rechazo=EXCLUDED.comentario_ultimo_rechazo,
    sugerido_en=EXCLUDED.sugerido_en,
    aprobado_en=EXCLUDED.aprobado_en,
    rechazado_en=EXCLUDED.rechazado_en,
    proyecto_en=EXCLUDED.proyecto_en,
    omitido_en=EXCLUDED.omitido_en,
    devuelto_en=EXCLUDED.devuelto_en,
    reabierto_en=EXCLUDED.reabierto_en,
    rechazado_desde_aprobado_en=EXCLUDED.rechazado_desde_aprobado_en,
    rechazado_desde_proyecto_en=EXCLUDED.rechazado_desde_proyecto_en,
    actualizado_en=now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_guardar_candidato_override ON pruebas_gestor.candidato_ubicacion;
CREATE TRIGGER trg_guardar_candidato_override
INSTEAD OF UPDATE ON pruebas_gestor.candidato_ubicacion
FOR EACH ROW EXECUTE FUNCTION pruebas_gestor.guardar_candidato_override();

CREATE OR REPLACE VIEW pruebas_gestor.revision AS
 SELECT id::bigint,id_candidato,etapa,id_revisor,accion,comentario,creado_en
 FROM gestor.revision
 UNION ALL
 SELECT id,id_candidato,etapa,id_revisor,accion,comentario,creado_en
 FROM pruebas_gestor.revision_local;

CREATE OR REPLACE FUNCTION pruebas_gestor.insertar_revision_local()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO pruebas_gestor.revision_local (
    id_candidato,etapa,id_revisor,accion,comentario,creado_en
  ) VALUES (
    NEW.id_candidato,NEW.etapa,NEW.id_revisor,NEW.accion,NEW.comentario,
    coalesce(NEW.creado_en,now())
  ) RETURNING id,creado_en INTO NEW.id,NEW.creado_en;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_insertar_revision_local ON pruebas_gestor.revision;
CREATE TRIGGER trg_insertar_revision_local
INSTEAD OF INSERT ON pruebas_gestor.revision
FOR EACH ROW EXECUTE FUNCTION pruebas_gestor.insertar_revision_local();

CREATE OR REPLACE VIEW pruebas_gestor.variables_proyecto_candidato AS
 SELECT b.* FROM gestor.variables_proyecto_candidato b
 WHERE NOT EXISTS (
   SELECT 1 FROM pruebas_gestor.variable_override o
   WHERE o.id_candidato=b.id_candidato
 )
 UNION ALL
 SELECT id,id_candidato,cve_unidad,unidad,comuna,provincia,region,mt2,
        valor_arriendo,gastos_comunes,clausula_salida,meses_gracia,
        plazo_arriendo,garantia,tipo_proyecto,fecha_apertura_aproximada,
        contacto_nombre,contacto_telefono,contacto_email,flujo_franquicia,
        franquiciado_nombre,franquiciado_telefono,franquiciado_email,
        tiendas_anclas,proyeccion_supervisor,proyeccion_jefe_comercial,
        fecha_entrega_local,actualizado_por_id,actualizado_en
 FROM pruebas_gestor.variable_override;

CREATE OR REPLACE FUNCTION pruebas_gestor.guardar_variable_override()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO pruebas_gestor.variable_override (
    id_candidato,cve_unidad,unidad,comuna,provincia,region,mt2,
    valor_arriendo,gastos_comunes,clausula_salida,meses_gracia,
    plazo_arriendo,garantia,tipo_proyecto,fecha_apertura_aproximada,
    contacto_nombre,contacto_telefono,contacto_email,flujo_franquicia,
    franquiciado_nombre,franquiciado_telefono,franquiciado_email,
    tiendas_anclas,proyeccion_supervisor,proyeccion_jefe_comercial,
    fecha_entrega_local,actualizado_por_id,actualizado_en
  ) VALUES (
    NEW.id_candidato,NEW.cve_unidad,NEW.unidad,NEW.comuna,NEW.provincia,
    NEW.region,NEW.mt2,NEW.valor_arriendo,NEW.gastos_comunes,
    NEW.clausula_salida,NEW.meses_gracia,NEW.plazo_arriendo,NEW.garantia,
    NEW.tipo_proyecto,NEW.fecha_apertura_aproximada,NEW.contacto_nombre,
    NEW.contacto_telefono,NEW.contacto_email,NEW.flujo_franquicia,
    NEW.franquiciado_nombre,NEW.franquiciado_telefono,
    NEW.franquiciado_email,NEW.tiendas_anclas,NEW.proyeccion_supervisor,
    NEW.proyeccion_jefe_comercial,NEW.fecha_entrega_local,
    NEW.actualizado_por_id,coalesce(NEW.actualizado_en,now())
  ) ON CONFLICT (id_candidato) DO UPDATE SET
    cve_unidad=EXCLUDED.cve_unidad, unidad=EXCLUDED.unidad,
    comuna=EXCLUDED.comuna, provincia=EXCLUDED.provincia,
    region=EXCLUDED.region, mt2=EXCLUDED.mt2,
    valor_arriendo=EXCLUDED.valor_arriendo,
    gastos_comunes=EXCLUDED.gastos_comunes,
    clausula_salida=EXCLUDED.clausula_salida,
    meses_gracia=EXCLUDED.meses_gracia,
    plazo_arriendo=EXCLUDED.plazo_arriendo,
    garantia=EXCLUDED.garantia, tipo_proyecto=EXCLUDED.tipo_proyecto,
    fecha_apertura_aproximada=EXCLUDED.fecha_apertura_aproximada,
    contacto_nombre=EXCLUDED.contacto_nombre,
    contacto_telefono=EXCLUDED.contacto_telefono,
    contacto_email=EXCLUDED.contacto_email,
    flujo_franquicia=EXCLUDED.flujo_franquicia,
    franquiciado_nombre=EXCLUDED.franquiciado_nombre,
    franquiciado_telefono=EXCLUDED.franquiciado_telefono,
    franquiciado_email=EXCLUDED.franquiciado_email,
    tiendas_anclas=EXCLUDED.tiendas_anclas,
    proyeccion_supervisor=EXCLUDED.proyeccion_supervisor,
    proyeccion_jefe_comercial=EXCLUDED.proyeccion_jefe_comercial,
    fecha_entrega_local=EXCLUDED.fecha_entrega_local,
    actualizado_por_id=EXCLUDED.actualizado_por_id,
    actualizado_en=EXCLUDED.actualizado_en
  RETURNING id,actualizado_en INTO NEW.id,NEW.actualizado_en;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_insertar_variable_override ON pruebas_gestor.variables_proyecto_candidato;
CREATE TRIGGER trg_insertar_variable_override
INSTEAD OF INSERT ON pruebas_gestor.variables_proyecto_candidato
FOR EACH ROW EXECUTE FUNCTION pruebas_gestor.guardar_variable_override();
DROP TRIGGER IF EXISTS trg_actualizar_variable_override ON pruebas_gestor.variables_proyecto_candidato;
CREATE TRIGGER trg_actualizar_variable_override
INSTEAD OF UPDATE ON pruebas_gestor.variables_proyecto_candidato
FOR EACH ROW EXECUTE FUNCTION pruebas_gestor.guardar_variable_override();
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is intentionally disabled.")
