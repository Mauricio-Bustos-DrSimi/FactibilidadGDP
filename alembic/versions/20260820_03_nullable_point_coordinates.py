"""Preserve legacy points whose coordinates are unknown."""
from __future__ import annotations

from alembic import op


revision = "20260820_03"
down_revision = "20260820_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE gestor.punto_interes
          ALTER COLUMN latitud DROP NOT NULL,
          ALTER COLUMN longitud DROP NOT NULL;
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is intentionally disabled.")
