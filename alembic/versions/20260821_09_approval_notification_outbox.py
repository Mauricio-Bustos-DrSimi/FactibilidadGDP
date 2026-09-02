"""Make outgoing approval notifications transactional and retryable."""
from __future__ import annotations

from alembic import op


revision = "20260821_09"
down_revision = "20260820_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE integracion.evento_salida
          DROP CONSTRAINT IF EXISTS ck_evento_salida_modo;
        ALTER TABLE integracion.evento_salida
          ADD CONSTRAINT ck_evento_salida_modo
          CHECK (modo IN ('PRUEBA','SUPRIMIDO','PRODUCTIVO'));
        ALTER TABLE integracion.evento_salida
          ADD COLUMN IF NOT EXISTS estado varchar(24) NOT NULL DEFAULT 'REGISTRADO',
          ADD COLUMN IF NOT EXISTS intentos integer NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS ultimo_error text;
        ALTER TABLE integracion.evento_salida
          DROP CONSTRAINT IF EXISTS ck_evento_salida_estado;
        ALTER TABLE integracion.evento_salida
          ADD CONSTRAINT ck_evento_salida_estado
          CHECK (estado IN ('REGISTRADO','PENDIENTE','ENVIADO'));
        CREATE INDEX IF NOT EXISTS ix_evento_salida_pendiente
          ON integracion.evento_salida(tipo, creado_en)
          WHERE modo='PRODUCTIVO' AND publicado_en IS NULL;
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS integracion.ix_evento_salida_pendiente;
        UPDATE integracion.evento_salida
          SET modo='SUPRIMIDO'
          WHERE modo='PRODUCTIVO';
        ALTER TABLE integracion.evento_salida
          DROP CONSTRAINT IF EXISTS ck_evento_salida_modo;
        ALTER TABLE integracion.evento_salida
          DROP CONSTRAINT IF EXISTS ck_evento_salida_estado;
        ALTER TABLE integracion.evento_salida
          ADD CONSTRAINT ck_evento_salida_modo
          CHECK (modo IN ('PRUEBA','SUPRIMIDO'));
        ALTER TABLE integracion.evento_salida
          DROP COLUMN IF EXISTS ultimo_error,
          DROP COLUMN IF EXISTS intentos,
          DROP COLUMN IF EXISTS estado;
    """)
