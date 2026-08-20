"""Promote the business projection ID to a first-class candidate column."""
from __future__ import annotations

from alembic import op


revision = "20260820_06"
down_revision = "20260820_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        ALTER TABLE gestor.candidato
          ADD COLUMN IF NOT EXISTS id_proyeccion varchar(120);

        UPDATE gestor.candidato
        SET id_proyeccion = coalesce(
          nullif(datos->>'ID Proyección', ''),
          nullif(datos->>'ID Proyeccion', ''),
          nullif(datos->>'ID', ''),
          nullif(payload_origen#>>'{datos_visualizacion,ID Proyección}', ''),
          nullif(payload_origen#>>'{datos_visualizacion,ID Proyeccion}', ''),
          nullif(payload_origen#>>'{datos_visualizacion,ID}', '')
        )
        WHERE id_proyeccion IS NULL;

        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM gestor.candidato WHERE id_proyeccion IS NULL) THEN
            RAISE EXCEPTION 'Cannot enforce id_proyeccion: candidates without business projection ID exist';
          END IF;
        END $$;

        ALTER TABLE gestor.candidato
          ALTER COLUMN id_proyeccion SET NOT NULL;

        CREATE INDEX IF NOT EXISTS ix_gestor_candidato_id_proyeccion
          ON gestor.candidato(id_proyeccion);
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is intentionally disabled.")
