"""Record the stable completion time of each Factibilidad subtask."""
from __future__ import annotations

from alembic import op


revision = "20260820_07"
down_revision = "20260820_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE factibilidad.tarea_local
          ADD COLUMN IF NOT EXISTS completado_en timestamptz;

        UPDATE factibilidad.tarea_local
        SET completado_en = actualizado_en
        WHERE estado IN ('realizado', 'no_aplica')
          AND completado_en IS NULL;

        CREATE INDEX IF NOT EXISTS ix_tarea_local_completado
          ON factibilidad.tarea_local(id_candidato, completado_en);
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is intentionally disabled.")
