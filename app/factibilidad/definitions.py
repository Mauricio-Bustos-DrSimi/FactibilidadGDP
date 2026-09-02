"""Code-owned workflow definitions for the Factibilidad module."""

FACTIBILITY_TASK_GROUPS = (
    (
        "legal",
        "legal_nuevo",
        "Ingreso del local",
        (
            ("legal_recepcion_oportunidad", "Recibir oportunidad desde Ventas o Franquicias"),
            ("legal_identificar_operacion", "Identificar tipo de operación"),
            ("legal_registrar_contactos", "Registrar contactos y arrendador"),
            ("legal_asignar_responsable", "Asignar responsable interno"),
        ),
    ),
    (
        "legal",
        "legal_documentacion",
        "Creación del expediente único del local y contrato",
        (
            ("legal_asociar_ficha_ventas", "Asociar ficha del local de Ventas"),
            ("legal_asociar_carta_interes", "Asociar carta de interés"),
            ("legal_crear_carpeta", "Crear carpeta documental"),
            ("legal_enviar_borrador_base", "Enviar borrador base del contrato"),
            ("legal_enviar_checklist", "Enviar checklist de documentos requeridos"),
            ("legal_controlar_antecedentes", "Recibir, revisar y observar antecedentes"),
        ),
    ),
    (
        "legal",
        "legal_validacion",
        "Validación",
        (
            ("legal_validar_documentos", "Validar suficiencia de documentos"),
            ("legal_recibir_factibilidad", "Recibir resultado de factibilidad de Arquitectura"),
            ("legal_revisar_restricciones", "Revisar restricciones y exigencias al arrendador"),
            ("legal_definir_condiciones", "Definir condiciones suspensivas"),
            ("legal_autorizar_continuidad", "Autorizar continuidad del contrato"),
        ),
    ),
    (
        "legal",
        "legal_contrato",
        "Contrato",
        (
            ("legal_preparar_borrador", "Preparar borrador contractual"),
            ("legal_enviar_arrendador", "Enviar borrador al arrendador"),
            ("legal_registrar_observaciones", "Registrar observaciones y fecha de respuesta"),
            ("legal_corregir_version", "Corregir y emitir nueva versión"),
            ("legal_registrar_responsable", "Registrar responsable actual y motivo de bloqueo"),
            ("legal_acordar_borrador", "Confirmar borrador acordado entre las partes"),
        ),
    ),
    (
        "legal",
        "legal_firma",
        "Firma",
        (
            ("legal_aprobar_version", "Aprobar versión definitiva para firma"),
            ("legal_definir_modalidad", "Definir modalidad de firma o excepción"),
            ("legal_firma_empresa", "Gestionar firma de la empresa"),
            ("legal_firma_arrendador", "Gestionar firma del arrendador"),
            ("legal_tramite_notarial", "Completar trámite notarial"),
            ("legal_formalizar_contrato", "Confirmar contrato legalmente formalizado"),
        ),
    ),
    (
        "legal",
        "legal_entregado",
        "Entregado",
        (
            ("legal_generar_ficha", "Generar ficha contractual"),
            ("legal_registrar_obligaciones", "Registrar renta, garantía, fechas y obligaciones"),
            ("legal_entregar_areas", "Entregar contrato y antecedentes a Arriendos / Mantención"),
            ("legal_registrar_pendientes", "Informar pendientes y condiciones suspensivas"),
            ("legal_confirmar_recepcion", "Confirmar recepción por las áreas siguientes"),
            ("legal_cerrar_proceso", "Cerrar proceso contractual"),
        ),
    ),
    (
        "arquitectura",
        "arquitectura_ingreso_asignacion",
        "Ingreso y asignación del local",
        (
            ("arquitectura_recibir_solicitud", "Recibir solicitud de evaluación del local"),
            ("arquitectura_clasificar_local", "Clasificar el tipo de local"),
            ("arquitectura_asignar_interno", "Asignar arquitecto interno"),
            ("arquitectura_asignar_externo", "Definir arquitecto externo u oficina técnica"),
            ("arquitectura_iniciar_proceso", "Confirmar inicio del proceso técnico"),
        ),
    ),
    (
        "arquitectura",
        "arquitectura_factibilidad_levantamiento",
        "Factibilidad y levantamiento",
        (
            ("arquitectura_revisar_normativa", "Revisar normativa, destino comercial y DOM"),
            ("arquitectura_revisar_permisos", "Revisar permisos, recepciones y regularización"),
            ("arquitectura_revisar_instalaciones", "Revisar instalaciones, accesibilidad y construcción"),
            ("arquitectura_levantar_inmueble", "Levantar plantas, elevaciones, cortes y superficies"),
            ("arquitectura_comparar_planos", "Comparar planos aprobados con la realidad construida"),
            ("arquitectura_emitir_informe", "Emitir informe de factibilidad y levantamiento"),
        ),
    ),
    (
        "arquitectura",
        "arquitectura_aprobacion_tecnica",
        "Aprobación técnica del local",
        (
            ("arquitectura_revision_interna", "Completar revisión del arquitecto interno"),
            ("arquitectura_revision_coordinador", "Completar segunda evaluación del coordinador"),
            ("arquitectura_definir_resultado", "Definir resultado técnico del local"),
            ("arquitectura_comunicar_vb", "Comunicar VB u observaciones a Ventas y Arriendos"),
            ("arquitectura_sincronizar_legal", "Informar restricciones y condiciones al área Legal"),
        ),
    ),
    (
        "arquitectura",
        "arquitectura_desarrollo_proyecto",
        "Desarrollo del proyecto",
        (
            ("arquitectura_desarrollar_layout", "Desarrollar layout de la farmacia"),
            ("arquitectura_desarrollar_planos", "Desarrollar arquitectura, fachada y cortes"),
            ("arquitectura_desarrollar_especialidades", "Desarrollar clima, cielos, cámaras e instalaciones"),
            ("arquitectura_definir_mobiliario", "Definir luminarias, enchufes y mobiliario"),
            ("arquitectura_validar_areas", "Validar proyecto con Ventas, Apertura e Imagen"),
            ("arquitectura_aprobar_proyecto", "Aprobar proyecto arquitectónico para construir"),
        ),
    ),
    (
        "arquitectura",
        "arquitectura_cubicacion",
        "Cubicación y preparación de licitación",
        (
            ("arquitectura_cubicar", "Preparar cubicación e itemizado"),
            ("arquitectura_preparar_licitacion", "Cargar planos y preparar licitación"),
            ("arquitectura_validar_cantidades", "Validar cantidades, superficies y partidas particulares"),
            ("arquitectura_publicar_antecedentes", "Publicar proyecto completo para proveedores"),
        ),
    ),
    (
        "arquitectura",
        "arquitectura_licitacion",
        "Licitación y adjudicación",
        (
            ("arquitectura_visita_proveedores", "Coordinar visita técnica y consultas"),
            ("arquitectura_recibir_cotizaciones", "Recibir y revisar cotizaciones"),
            ("arquitectura_adjudicar", "Confirmar adjudicación, fecha de obra e ITO"),
            ("arquitectura_entregar_planos", "Entregar al adjudicado la versión correcta de planos"),
        ),
    ),
    (
        "arquitectura",
        "arquitectura_habilitacion",
        "Habilitación y construcción",
        (
            ("arquitectura_iniciar_obra", "Confirmar inicio de obra"),
            ("arquitectura_supervisar_obra", "Supervisar construcción, cambios y correcciones"),
            ("arquitectura_resolver_consultas", "Resolver consultas técnicas de obra"),
            ("arquitectura_generar_as_built", "Generar planos As Built"),
        ),
    ),
    (
        "arquitectura",
        "arquitectura_entrega_local",
        "Entrega del local",
        (
            ("arquitectura_entregar_local", "Entregar local y subsanar observaciones"),
            ("arquitectura_cerrar_as_built", "Cerrar documentación As Built"),
            ("arquitectura_recibir_layout_imagen", "Recibir layout definitivo de Imagen"),
            ("arquitectura_cerrar_observaciones", "Confirmar corrección de observaciones de entrega"),
            ("arquitectura_reunir_certificados", "Recopilar certificados de construcción"),
        ),
    ),
    (
        "arquitectura",
        "arquitectura_regularizacion",
        "Regularización y tramitaciones",
        (
            ("arquitectura_gestionar_dom", "Gestionar permisos, expediente DOM y recepción final"),
            ("arquitectura_gestionar_sanitario", "Gestionar dotación y proyectos sanitarios"),
            ("arquitectura_gestionar_inspecciones", "Dar seguimiento a inspecciones y externos"),
            ("arquitectura_documentar_instalaciones", "Completar documentación de instalaciones"),
            ("arquitectura_confirmar_rf", "Confirmar recepción final"),
        ),
    ),
    (
        "arquitectura",
        "arquitectura_apertura_cierre",
        "Apertura y cierre",
        (
            ("arquitectura_obtener_certificados", "Obtener TE1 y certificados para autorización sanitaria"),
            ("arquitectura_confirmar_autorizacion", "Confirmar autorización sanitaria"),
            ("arquitectura_confirmar_apertura", "Confirmar apertura del local"),
            ("arquitectura_confirmar_regularizacion", "Confirmar regularización completa"),
            ("arquitectura_confirmar_patente", "Confirmar patente definitiva"),
            ("arquitectura_cerrar_proceso", "Cerrar proceso de Arquitectura"),
        ),
    ),
)
FACTIBILITY_TASK_INDEX = {
    task_key: (area_key, group_key, task_title)
    for area_key, group_key, _, tasks in FACTIBILITY_TASK_GROUPS
    for task_key, task_title in tasks
}
FACTIBILITY_GROUP_INDEX = {
    group_key: (area_key, group_title)
    for area_key, group_key, group_title, _ in FACTIBILITY_TASK_GROUPS
}
FACTIBILITY_COMPLETED_STATUSES = {"realizado", "no_aplica"}

__all__ = [
    "FACTIBILITY_COMPLETED_STATUSES",
    "FACTIBILITY_GROUP_INDEX",
    "FACTIBILITY_TASK_GROUPS",
    "FACTIBILITY_TASK_INDEX",
]
