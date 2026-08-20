"""Keep upstream candidate attributes live underneath local workflow overrides."""
from __future__ import annotations

from alembic import op


revision = "20260820_05"
down_revision = "20260820_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        DROP VIEW IF EXISTS pruebas_gestor.candidato_ubicacion;
        CREATE VIEW pruebas_gestor.candidato_ubicacion AS
         SELECT b.id, b.id_proyecto, b.referencia_mapa, b.latitud, b.longitud,
                b.datos_visualizacion,
                CASE WHEN o.id IS NULL THEN b.etapa_actual ELSE o.etapa_actual END AS etapa_actual,
                CASE WHEN o.id IS NULL THEN b.estado ELSE o.estado END AS estado,
                CASE WHEN o.id IS NULL THEN b.prioridad ELSE o.prioridad END AS prioridad,
                CASE WHEN o.id IS NULL THEN b.grupo_flujo ELSE o.grupo_flujo END AS grupo_flujo,
                CASE WHEN o.id IS NULL THEN b.ultima_accion ELSE o.ultima_accion END AS ultima_accion,
                CASE WHEN o.id IS NULL THEN b.ultima_accion_en ELSE o.ultima_accion_en END AS ultima_accion_en,
                CASE WHEN o.id IS NULL THEN b.rol_ultimo_actor ELSE o.rol_ultimo_actor END AS rol_ultimo_actor,
                CASE WHEN o.id IS NULL THEN b.comentario_ultimo_rechazo ELSE o.comentario_ultimo_rechazo END AS comentario_ultimo_rechazo,
                CASE WHEN o.id IS NULL THEN b.sugerido_en ELSE o.sugerido_en END AS sugerido_en,
                CASE WHEN o.id IS NULL THEN b.aprobado_en ELSE o.aprobado_en END AS aprobado_en,
                CASE WHEN o.id IS NULL THEN b.rechazado_en ELSE o.rechazado_en END AS rechazado_en,
                CASE WHEN o.id IS NULL THEN b.proyecto_en ELSE o.proyecto_en END AS proyecto_en,
                CASE WHEN o.id IS NULL THEN b.omitido_en ELSE o.omitido_en END AS omitido_en,
                CASE WHEN o.id IS NULL THEN b.devuelto_en ELSE o.devuelto_en END AS devuelto_en,
                CASE WHEN o.id IS NULL THEN b.reabierto_en ELSE o.reabierto_en END AS reabierto_en,
                CASE WHEN o.id IS NULL THEN b.rechazado_desde_aprobado_en ELSE o.rechazado_desde_aprobado_en END AS rechazado_desde_aprobado_en,
                CASE WHEN o.id IS NULL THEN b.rechazado_desde_proyecto_en ELSE o.rechazado_desde_proyecto_en END AS rechazado_desde_proyecto_en
         FROM gestor.candidato_ubicacion b
         LEFT JOIN pruebas_gestor.candidato_override o ON o.id=b.id;

        CREATE TRIGGER trg_guardar_candidato_override
        INSTEAD OF UPDATE ON pruebas_gestor.candidato_ubicacion
        FOR EACH ROW EXECUTE FUNCTION pruebas_gestor.guardar_candidato_override();
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is intentionally disabled.")
