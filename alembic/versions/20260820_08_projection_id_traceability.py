"""Materialize the business projection ID in every candidate-owned table."""
from __future__ import annotations

from alembic import op


revision = "20260820_08"
down_revision = "20260820_07"
branch_labels = None
depends_on = None


GESTOR_REQUIRED = (
    "transicion_estado",
    "actividad_candidato",
    "variable_proyecto_version",
    "documento_candidato",
)
FACTIBILIDAD_REQUIRED = (
    "entrega",
    "tarea_local",
    "decision_local",
    "visto_bueno_local",
)
PRUEBAS_REQUIRED = (
    "candidato_override",
    "revision_local",
    "variable_override",
)


def upgrade() -> None:
    for table in GESTOR_REQUIRED + ("notificacion_envio",):
        op.execute(
            f"ALTER TABLE gestor.{table} "
            "ADD COLUMN IF NOT EXISTS id_proyeccion varchar(120)"
        )
    for table in FACTIBILIDAD_REQUIRED:
        op.execute(
            f"ALTER TABLE factibilidad.{table} "
            "ADD COLUMN IF NOT EXISTS id_proyeccion varchar(120)"
        )
    for table in PRUEBAS_REQUIRED:
        op.execute(
            f"ALTER TABLE pruebas_gestor.{table} "
            "ADD COLUMN IF NOT EXISTS id_proyeccion varchar(120)"
        )
    for table in ("evento_entrada", "evento_salida", "evento_fallido"):
        op.execute(
            f"ALTER TABLE integracion.{table} "
            "ADD COLUMN IF NOT EXISTS id_proyeccion varchar(120)"
        )

    op.execute("""
        UPDATE gestor.transicion_estado t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.id=t.candidato_id;
        UPDATE gestor.actividad_candidato t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.id=t.candidato_id;
        UPDATE gestor.variable_proyecto_version t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.id=t.candidato_id;
        UPDATE gestor.documento_candidato t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.id=t.candidato_id;
        UPDATE gestor.notificacion_envio t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.id=t.candidato_id;

        UPDATE factibilidad.entrega t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.legacy_candidato_id=t.id_candidato::text;
        UPDATE factibilidad.tarea_local t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.legacy_candidato_id=t.id_candidato::text;
        UPDATE factibilidad.decision_local t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.legacy_candidato_id=t.id_candidato::text;
        UPDATE factibilidad.visto_bueno_local t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.legacy_candidato_id=t.id_candidato::text;

        UPDATE pruebas_gestor.candidato_override t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.legacy_candidato_id=t.id::text;
        UPDATE pruebas_gestor.revision_local t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.legacy_candidato_id=t.id_candidato::text;
        UPDATE pruebas_gestor.variable_override t SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c WHERE c.legacy_candidato_id=t.id_candidato::text;

        UPDATE integracion.evento_entrada e SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c
          WHERE c.legacy_candidato_id=e.candidato_legacy_id;
        UPDATE integracion.evento_salida e SET id_proyeccion=c.id_proyeccion
          FROM gestor.candidato c
          WHERE c.legacy_candidato_id=e.clave_agregado;
        UPDATE integracion.evento_fallido f SET id_proyeccion=e.id_proyeccion
          FROM integracion.evento_entrada e WHERE e.id=f.evento_entrada_id;
    """)

    for table in GESTOR_REQUIRED:
        op.execute(
            f"ALTER TABLE gestor.{table} "
            "ALTER COLUMN id_proyeccion SET NOT NULL"
        )
    for table in FACTIBILIDAD_REQUIRED:
        op.execute(
            f"ALTER TABLE factibilidad.{table} "
            "ALTER COLUMN id_proyeccion SET NOT NULL"
        )
    for table in PRUEBAS_REQUIRED:
        op.execute(
            f"ALTER TABLE pruebas_gestor.{table} "
            "ALTER COLUMN id_proyeccion SET NOT NULL"
        )

    op.execute("""
        CREATE OR REPLACE FUNCTION gestor.asignar_id_proyeccion_interno()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          SELECT c.id_proyeccion INTO NEW.id_proyeccion
          FROM gestor.candidato c WHERE c.id=NEW.candidato_id;
          IF NEW.id_proyeccion IS NULL THEN
            RAISE EXCEPTION 'No existe ID de Proyección para candidato interno %', NEW.candidato_id;
          END IF;
          RETURN NEW;
        END $$;

        CREATE OR REPLACE FUNCTION gestor.asignar_id_proyeccion_notificacion()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.candidato_id IS NULL THEN
            NEW.id_proyeccion := NULL;
          ELSE
            SELECT c.id_proyeccion INTO NEW.id_proyeccion
            FROM gestor.candidato c WHERE c.id=NEW.candidato_id;
          END IF;
          RETURN NEW;
        END $$;

        CREATE OR REPLACE FUNCTION factibilidad.asignar_id_proyeccion_legacy()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          SELECT c.id_proyeccion INTO NEW.id_proyeccion
          FROM gestor.candidato c
          WHERE c.legacy_candidato_id=NEW.id_candidato::text;
          IF NEW.id_proyeccion IS NULL THEN
            RAISE EXCEPTION 'No existe ID de Proyección para candidato legacy %', NEW.id_candidato;
          END IF;
          RETURN NEW;
        END $$;

        CREATE OR REPLACE FUNCTION pruebas_gestor.asignar_id_proyeccion_legacy()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE legacy_id text;
        BEGIN
          legacy_id := CASE WHEN TG_TABLE_NAME='candidato_override'
                       THEN NEW.id::text ELSE NEW.id_candidato::text END;
          SELECT c.id_proyeccion INTO NEW.id_proyeccion
          FROM gestor.candidato c WHERE c.legacy_candidato_id=legacy_id;
          IF NEW.id_proyeccion IS NULL THEN
            RAISE EXCEPTION 'No existe ID de Proyección para candidato legacy %', legacy_id;
          END IF;
          RETURN NEW;
        END $$;

        CREATE OR REPLACE FUNCTION integracion.asignar_id_proyeccion_entrada()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.candidato_legacy_id IS NOT NULL THEN
            SELECT c.id_proyeccion INTO NEW.id_proyeccion
            FROM gestor.candidato c
            WHERE c.legacy_candidato_id=NEW.candidato_legacy_id;
          END IF;
          RETURN NEW;
        END $$;

        CREATE OR REPLACE FUNCTION integracion.asignar_id_proyeccion_salida()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.clave_agregado IS NOT NULL THEN
            SELECT c.id_proyeccion INTO NEW.id_proyeccion
            FROM gestor.candidato c
            WHERE c.legacy_candidato_id=NEW.clave_agregado;
          END IF;
          RETURN NEW;
        END $$;

        CREATE OR REPLACE FUNCTION integracion.asignar_id_proyeccion_fallido()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          SELECT e.id_proyeccion INTO NEW.id_proyeccion
          FROM integracion.evento_entrada e WHERE e.id=NEW.evento_entrada_id;
          RETURN NEW;
        END $$;

        CREATE OR REPLACE FUNCTION gestor.propagar_id_proyeccion_candidato()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          UPDATE gestor.transicion_estado SET id_proyeccion=NEW.id_proyeccion
            WHERE candidato_id=NEW.id;
          UPDATE gestor.actividad_candidato SET id_proyeccion=NEW.id_proyeccion
            WHERE candidato_id=NEW.id;
          UPDATE gestor.variable_proyecto_version SET id_proyeccion=NEW.id_proyeccion
            WHERE candidato_id=NEW.id;
          UPDATE gestor.documento_candidato SET id_proyeccion=NEW.id_proyeccion
            WHERE candidato_id=NEW.id;
          UPDATE gestor.notificacion_envio SET id_proyeccion=NEW.id_proyeccion
            WHERE candidato_id=NEW.id;

          UPDATE factibilidad.entrega SET id_proyeccion=NEW.id_proyeccion
            WHERE id_candidato::text=NEW.legacy_candidato_id;
          UPDATE factibilidad.tarea_local SET id_proyeccion=NEW.id_proyeccion
            WHERE id_candidato::text=NEW.legacy_candidato_id;
          UPDATE factibilidad.decision_local SET id_proyeccion=NEW.id_proyeccion
            WHERE id_candidato::text=NEW.legacy_candidato_id;
          UPDATE factibilidad.visto_bueno_local SET id_proyeccion=NEW.id_proyeccion
            WHERE id_candidato::text=NEW.legacy_candidato_id;

          UPDATE pruebas_gestor.candidato_override SET id_proyeccion=NEW.id_proyeccion
            WHERE id::text=NEW.legacy_candidato_id;
          UPDATE pruebas_gestor.revision_local SET id_proyeccion=NEW.id_proyeccion
            WHERE id_candidato::text=NEW.legacy_candidato_id;
          UPDATE pruebas_gestor.variable_override SET id_proyeccion=NEW.id_proyeccion
            WHERE id_candidato::text=NEW.legacy_candidato_id;

          UPDATE integracion.evento_entrada SET id_proyeccion=NEW.id_proyeccion
            WHERE candidato_legacy_id=NEW.legacy_candidato_id;
          UPDATE integracion.evento_salida SET id_proyeccion=NEW.id_proyeccion
            WHERE clave_agregado=NEW.legacy_candidato_id;
          UPDATE integracion.evento_fallido f SET id_proyeccion=NEW.id_proyeccion
            FROM integracion.evento_entrada e
            WHERE e.id=f.evento_entrada_id
              AND e.candidato_legacy_id=NEW.legacy_candidato_id;
          RETURN NEW;
        END $$;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_propagar_id_proyeccion ON gestor.candidato;
        CREATE TRIGGER trg_propagar_id_proyeccion
        AFTER UPDATE OF id_proyeccion ON gestor.candidato
        FOR EACH ROW
        WHEN (OLD.id_proyeccion IS DISTINCT FROM NEW.id_proyeccion)
        EXECUTE FUNCTION gestor.propagar_id_proyeccion_candidato();
    """)

    for table in GESTOR_REQUIRED:
        op.execute(f"""
            DROP TRIGGER IF EXISTS trg_id_proyeccion ON gestor.{table};
            CREATE TRIGGER trg_id_proyeccion
            BEFORE INSERT OR UPDATE ON gestor.{table}
            FOR EACH ROW EXECUTE FUNCTION gestor.asignar_id_proyeccion_interno();
        """)
    op.execute("""
        DROP TRIGGER IF EXISTS trg_id_proyeccion ON gestor.notificacion_envio;
        CREATE TRIGGER trg_id_proyeccion
        BEFORE INSERT OR UPDATE ON gestor.notificacion_envio
        FOR EACH ROW EXECUTE FUNCTION gestor.asignar_id_proyeccion_notificacion();
    """)
    for table in FACTIBILIDAD_REQUIRED:
        op.execute(f"""
            DROP TRIGGER IF EXISTS trg_id_proyeccion ON factibilidad.{table};
            CREATE TRIGGER trg_id_proyeccion
            BEFORE INSERT OR UPDATE ON factibilidad.{table}
            FOR EACH ROW EXECUTE FUNCTION factibilidad.asignar_id_proyeccion_legacy();
        """)
    for table in PRUEBAS_REQUIRED:
        op.execute(f"""
            DROP TRIGGER IF EXISTS trg_id_proyeccion ON pruebas_gestor.{table};
            CREATE TRIGGER trg_id_proyeccion
            BEFORE INSERT OR UPDATE ON pruebas_gestor.{table}
            FOR EACH ROW EXECUTE FUNCTION pruebas_gestor.asignar_id_proyeccion_legacy();
        """)
    op.execute("""
        DROP TRIGGER IF EXISTS trg_id_proyeccion ON integracion.evento_entrada;
        CREATE TRIGGER trg_id_proyeccion
        BEFORE INSERT OR UPDATE ON integracion.evento_entrada
        FOR EACH ROW EXECUTE FUNCTION integracion.asignar_id_proyeccion_entrada();
        DROP TRIGGER IF EXISTS trg_id_proyeccion ON integracion.evento_salida;
        CREATE TRIGGER trg_id_proyeccion
        BEFORE INSERT OR UPDATE ON integracion.evento_salida
        FOR EACH ROW EXECUTE FUNCTION integracion.asignar_id_proyeccion_salida();
        DROP TRIGGER IF EXISTS trg_id_proyeccion ON integracion.evento_fallido;
        CREATE TRIGGER trg_id_proyeccion
        BEFORE INSERT OR UPDATE ON integracion.evento_fallido
        FOR EACH ROW EXECUTE FUNCTION integracion.asignar_id_proyeccion_fallido();
    """)

    for schema, table in (
        *(("gestor", table) for table in GESTOR_REQUIRED + ("notificacion_envio",)),
        *(("factibilidad", table) for table in FACTIBILIDAD_REQUIRED),
        *(("pruebas_gestor", table) for table in PRUEBAS_REQUIRED),
        *(("integracion", table) for table in ("evento_entrada", "evento_salida", "evento_fallido")),
    ):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{schema}_{table}_id_proyeccion "
            f"ON {schema}.{table}(id_proyeccion)"
        )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is intentionally disabled.")
