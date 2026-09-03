"""Persist metadata for documents owned by Factibilidad."""
from __future__ import annotations

from alembic import op


revision = "20260903_10"
down_revision = "20260821_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS factibilidad.documento_local (
          id bigserial PRIMARY KEY,
          id_candidato bigint NOT NULL,
          id_proyeccion varchar(120) NOT NULL,
          local_referencia varchar(300),
          area varchar(32),
          clave_grupo varchar(100),
          categoria varchar(32) NOT NULL,
          nombre_original varchar(255) NOT NULL,
          nombre_fisico varchar(255) NOT NULL,
          ruta_fisica varchar(700) NOT NULL,
          extension varchar(24) NOT NULL,
          tipo_mime varchar(180) NOT NULL,
          tamano_bytes bigint NOT NULL,
          sha256 varchar(64) NOT NULL,
          cargado_por_id varchar(120),
          cargado_en timestamptz NOT NULL DEFAULT now(),
          presente boolean NOT NULL DEFAULT true
        );
        CREATE INDEX IF NOT EXISTS ix_documento_local_candidato
          ON factibilidad.documento_local(id_candidato);
        CREATE INDEX IF NOT EXISTS ix_documento_local_id_proyeccion
          ON factibilidad.documento_local(id_proyeccion);
        CREATE INDEX IF NOT EXISTS ix_documento_local_sha256
          ON factibilidad.documento_local(sha256);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_factibilidad_documento_ruta_activa
          ON factibilidad.documento_local(ruta_fisica) WHERE presente;

        DROP TRIGGER IF EXISTS trg_documento_local_id_proyeccion
          ON factibilidad.documento_local;
        CREATE TRIGGER trg_documento_local_id_proyeccion
          BEFORE INSERT OR UPDATE OF id_candidato
          ON factibilidad.documento_local
          FOR EACH ROW EXECUTE FUNCTION factibilidad.asignar_id_proyeccion_legacy();

        CREATE OR REPLACE FUNCTION factibilidad.propagar_documento_id_proyeccion()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          UPDATE factibilidad.documento_local
             SET id_proyeccion=NEW.id_proyeccion
           WHERE id_candidato::text=NEW.legacy_candidato_id;
          RETURN NEW;
        END $$;
        DROP TRIGGER IF EXISTS trg_candidato_propagar_documento_id_proyeccion
          ON gestor.candidato;
        CREATE TRIGGER trg_candidato_propagar_documento_id_proyeccion
          AFTER UPDATE OF id_proyeccion ON gestor.candidato
          FOR EACH ROW EXECUTE FUNCTION factibilidad.propagar_documento_id_proyeccion();
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade is disabled; preserve document traceability metadata."
    )
