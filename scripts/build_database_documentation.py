"""Build the formal production database documentation as a styled PDF."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "FactibilidadGDP_Documentacion_Base_Datos_Produccion.pdf"
LOGO = ROOT / "image" / "LOGO SIMI LETREROS.png"

NAVY = colors.HexColor("#17365D")
BLUE = colors.HexColor("#1F4E78")
TEAL = colors.HexColor("#0F766E")
SKY = colors.HexColor("#D9EAF7")
PALE = colors.HexColor("#EEF4F8")
INK = colors.HexColor("#243447")
MUTED = colors.HexColor("#5E6E7E")
LINE = colors.HexColor("#B8C7D1")
GREEN = colors.HexColor("#DDEFE8")
AMBER = colors.HexColor("#FFF2CC")
RED = colors.HexColor("#FCE4E4")
WHITE = colors.white


def register_fonts() -> tuple[str, str, str]:
    candidates = [
        (
            Path("C:/Windows/Fonts/aptos.ttf"),
            Path("C:/Windows/Fonts/aptos-bold.ttf"),
            Path("C:/Windows/Fonts/aptos-mono.ttf"),
        ),
        (
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/consola.ttf"),
        ),
    ]
    for regular, bold, mono in candidates:
        if regular.exists() and bold.exists() and mono.exists():
            pdfmetrics.registerFont(TTFont("DocRegular", str(regular)))
            pdfmetrics.registerFont(TTFont("DocBold", str(bold)))
            pdfmetrics.registerFont(TTFont("DocMono", str(mono)))
            return "DocRegular", "DocBold", "DocMono"
    return "Helvetica", "Helvetica-Bold", "Courier"


FONT, FONT_BOLD, FONT_MONO = register_fonts()


class ArchitectureFlow(Flowable):
    def __init__(self, width: float = 17.2 * cm, height: float = 5.3 * cm):
        super().__init__()
        self.width = width
        self.height = height

    def draw_box(self, x, y, w, h, title, subtitle, fill):
        c = self.canv
        c.setFillColor(fill)
        c.setStrokeColor(NAVY)
        c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
        c.setFillColor(NAVY)
        c.setFont(FONT_BOLD, 9)
        c.drawCentredString(x + w / 2, y + h - 15, title)
        c.setFillColor(INK)
        c.setFont(FONT, 7.2)
        for idx, line in enumerate(subtitle.split("\n")):
            c.drawCentredString(x + w / 2, y + h - 29 - idx * 10, line)

    def arrow(self, x1, y1, x2, y2, label=""):
        c = self.canv
        c.setStrokeColor(TEAL)
        c.setFillColor(TEAL)
        c.setLineWidth(1.5)
        c.line(x1, y1, x2, y2)
        direction = 1 if x2 >= x1 else -1
        c.line(x2, y2, x2 - direction * 6, y2 + 3)
        c.line(x2, y2, x2 - direction * 6, y2 - 3)
        if label:
            c.setFont(FONT, 6.7)
            c.setFillColor(MUTED)
            c.drawCentredString((x1 + x2) / 2, y1 + 6, label)

    def draw(self):
        box_w, box_h = 3.35 * cm, 1.45 * cm
        top_y = 3.35 * cm
        self.draw_box(0, top_y, box_w, box_h, "GESTOR 8002", "TinderLocales\nSistema de registro", PALE)
        self.draw_box(4.55 * cm, top_y, box_w, box_h, "INTEGRACIÓN", "Polling / inbox\nCheckpoint y replay", AMBER)
        self.draw_box(9.1 * cm, top_y, box_w, box_h, "GESTOR", "Réplica normalizada\nSolo lectura", SKY)
        self.draw_box(13.65 * cm, top_y, box_w, box_h, "FASTAPI 8003", "Aplicación\nFactibilidadGDP", GREEN)
        self.arrow(box_w, top_y + box_h / 2, 4.55 * cm, top_y + box_h / 2, "solo lectura")
        self.arrow(7.9 * cm, top_y + box_h / 2, 9.1 * cm, top_y + box_h / 2, "aplica")
        self.arrow(12.45 * cm, top_y + box_h / 2, 13.65 * cm, top_y + box_h / 2, "consulta")

        low_y = 0.45 * cm
        self.draw_box(3.2 * cm, low_y, box_w, box_h, "FACTIBILIDAD", "Checklist, decisión,\nVB y entregas", GREEN)
        self.draw_box(8.0 * cm, low_y, box_w, box_h, "PRUEBAS_GESTOR", "Acciones GDP locales\nSin retorno a 8002", RED)
        self.draw_box(12.8 * cm, low_y, box_w, box_h, "FILESYSTEM", "Adjuntos y fichas\npor expediente", PALE)
        self.arrow(15.25 * cm, top_y, 14.48 * cm, low_y + box_h, "archivos")
        self.arrow(14.15 * cm, top_y, 9.68 * cm, low_y + box_h, "acciones GDP")
        self.arrow(13.8 * cm, top_y, 4.88 * cm, low_y + box_h, "dominio propio")


class ProductionDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str):
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=1.65 * cm,
            rightMargin=1.65 * cm,
            topMargin=1.85 * cm,
            bottomMargin=1.65 * cm,
            title="FactibilidadGDP - Documentación de Base de Datos de Producción",
            author="Arquitectura de Datos",
            subject="Especificación técnica y operativa de PostgreSQL",
        )
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="content")
        self.addPageTemplates(PageTemplate(id="main", frames=[frame], onPage=self.draw_page))

    def draw_page(self, canvas, doc):
        if doc.page == 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(self.leftMargin, A4[1] - 1.15 * cm, A4[0] - self.rightMargin, A4[1] - 1.15 * cm)
        canvas.setFillColor(NAVY)
        canvas.setFont(FONT_BOLD, 7.5)
        canvas.drawString(self.leftMargin, A4[1] - 0.88 * cm, "FACTIBILIDADGDP · BASE DE DATOS DE PRODUCCIÓN")
        canvas.setFillColor(MUTED)
        canvas.setFont(FONT, 7)
        canvas.drawRightString(A4[0] - self.rightMargin, A4[1] - 0.88 * cm, "Versión documental 1.3 · Alembic 20260820_08")
        canvas.line(self.leftMargin, 1.05 * cm, A4[0] - self.rightMargin, 1.05 * cm)
        canvas.setFont(FONT, 7)
        canvas.drawString(self.leftMargin, 0.72 * cm, "Clasificación: Uso interno · Producción")
        canvas.drawRightString(A4[0] - self.rightMargin, 0.72 * cm, f"Página {doc.page}")
        canvas.restoreState()


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverKicker", fontName=FONT_BOLD, fontSize=10, leading=13, textColor=TEAL, alignment=TA_CENTER, spaceAfter=12))
styles.add(ParagraphStyle(name="CoverTitle", fontName=FONT_BOLD, fontSize=25, leading=29, textColor=NAVY, alignment=TA_CENTER, spaceAfter=12))
styles.add(ParagraphStyle(name="CoverSub", fontName=FONT, fontSize=12, leading=17, textColor=MUTED, alignment=TA_CENTER, spaceAfter=18))
styles.add(ParagraphStyle(name="H1x", fontName=FONT_BOLD, fontSize=16, leading=20, textColor=NAVY, spaceBefore=4, spaceAfter=9, keepWithNext=True))
styles.add(ParagraphStyle(name="H2x", fontName=FONT_BOLD, fontSize=11.5, leading=15, textColor=BLUE, spaceBefore=10, spaceAfter=5, keepWithNext=True))
styles.add(ParagraphStyle(name="H3x", fontName=FONT_BOLD, fontSize=9.5, leading=13, textColor=TEAL, spaceBefore=8, spaceAfter=4, keepWithNext=True))
styles.add(ParagraphStyle(name="Bodyx", fontName=FONT, fontSize=8.6, leading=12.5, textColor=INK, spaceAfter=6))
styles.add(ParagraphStyle(name="Smallx", fontName=FONT, fontSize=7.3, leading=10, textColor=MUTED))
styles.add(ParagraphStyle(name="TableHeader", fontName=FONT_BOLD, fontSize=7.3, leading=10, textColor=WHITE))
styles.add(ParagraphStyle(name="Bulletx", fontName=FONT, fontSize=8.4, leading=12, textColor=INK, leftIndent=12, firstLineIndent=-7, bulletIndent=2, spaceAfter=3))
styles.add(ParagraphStyle(name="Codex", fontName=FONT_MONO, fontSize=7.1, leading=9.5, textColor=INK, backColor=PALE, borderColor=LINE, borderWidth=0.4, borderPadding=7, spaceBefore=4, spaceAfter=7))
styles.add(ParagraphStyle(name="Callout", fontName=FONT, fontSize=8.4, leading=12, textColor=NAVY, backColor=SKY, borderColor=BLUE, borderWidth=0.6, borderPadding=8, spaceBefore=5, spaceAfter=8))
styles.add(ParagraphStyle(name="TOC", fontName=FONT, fontSize=9, leading=14, textColor=INK, leftIndent=10))


def P(text: str, style: str = "Bodyx") -> Paragraph:
    return Paragraph(text, styles[style])


def bullet(text: str) -> Paragraph:
    return Paragraph(f"• {text}", styles["Bulletx"])


def table(data, widths=None, header=True, font_size=7.2, aligns=None):
    cooked = []
    for row_index, row in enumerate(data):
        style_name = "TableHeader" if header and row_index == 0 else "Smallx"
        cooked.append([cell if isinstance(cell, Flowable) else P(str(cell), style_name) for cell in row])
    result = Table(cooked, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    rules = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [WHITE, PALE]),
    ]
    if header:
        rules += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ]
    if aligns:
        for col, align in enumerate(aligns):
            rules.append(("ALIGN", (col, 0), (col, -1), align))
    result.setStyle(TableStyle(rules))
    return result


def section(title: str, number: str):
    return [P(f"{number}. {title}", "H1x"), Table([[""]], colWidths=[17.2 * cm], rowHeights=[1.5], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL)])), Spacer(1, 5)]


def object_block(name: str, purpose: str, columns: str, integrity: str):
    return KeepTogether([
        P(name, "H3x"),
        P(purpose),
        table([
            ["Elementos", "Definición"],
            ["Columnas", columns],
            ["Integridad", integrity],
        ], [3.0 * cm, 14.2 * cm]),
        Spacer(1, 5),
    ])


GESTOR_OBJECTS = [
    ("gestor.estado_catalogo", "Catálogo canónico que traduce los estados literales del origen al flujo normalizado.", "id integer; codigo varchar(32); nombre varchar(80); orden integer; estados_origen jsonb; activo boolean.", "PK id; UQ codigo."),
    ("gestor.rol", "Catálogo de roles de acceso replicados.", "id integer; codigo varchar(50); nombre varchar(100); activo boolean.", "PK id; UQ codigo."),
    ("gestor.usuario", "Identidades, autenticación y atributos organizacionales provenientes del Gestor.", "id; legacy_usuario_id; rol_id; rol; correo; nombre; hash_contrasena; division_comercial; cargo; correos_supervisores; organigrama_x/y; activo; eliminado_en; creado_en; payload_origen; hash_origen; sincronizado_en.", "PK id; UQ legacy_usuario_id; FK rol_id → rol.id; índice correo."),
    ("gestor.proyecto_importacion", "Agrupador de candidatos y metadatos del proyecto de origen.", "id; legacy_proyecto_id; nombre; archivo_origen; creado_origen_en; payload_origen; hash_origen.", "PK id; UQ legacy_proyecto_id."),
    ("gestor.candidato", "Entidad maestra normalizada del local candidato. id_proyeccion es el identificador empresarial obligatorio desde el origen.", "id; legacy_candidato_id; id_proyeccion; proyecto_id; estado_actual_id; estado_origen; certeza_mapeo; version_origen; referencia_mapa; latitud; longitud; datos; payload_origen; hash_origen; actualizado_origen_en; sincronizado_en.", "PK id; UQ legacy_candidato_id; índice no único id_proyeccion; FK proyecto y estado; CHECK certeza_mapeo."),
    ("gestor.transicion_estado", "Historial inmutable de cada cambio real de estado.", "id; candidato_id; id_proyeccion; legacy_revision_id; evento_origen_id; estado_anterior_id; estado_nuevo_id; estado_origen; accion_origen; comentario; actor_legacy_id; orden_origen; ocurrido_en; creado_en.", "PK id; UQ legacy_revision_id; UQ evento_origen_id; FK candidato, evento y estados; índices de proyección y candidato+orden."),
    ("gestor.actividad_candidato", "Comentarios y actividades que no cambian el estado.", "id; candidato_id; id_proyeccion; evento_origen_id; tipo; detalle jsonb; ocurrido_en.", "PK id; UQ evento_origen_id+tipo; FK candidato y evento; índice de proyección."),
    ("gestor.variable_proyecto_version", "Versionamiento completo de Variables del proyecto.", "id; candidato_id; id_proyeccion; evento_origen_id; legacy_variable_id; version; valores jsonb; hash_origen; vigente; ocurrido_en.", "PK id; UQ candidato+version; UQ evento_origen_id; FK candidato y evento; índice de proyección."),
    ("gestor.documento_candidato", "Inventario y huella criptográfica de archivos del Gestor; no almacena binarios.", "id; candidato_id; id_proyeccion; ruta_origen; nombre; tamano; modificado_en; sha256; presente; inventariado_en.", "PK id; UQ candidato+ruta; FK candidato; índice de proyección."),
    ("gestor.notificacion_envio", "Bitácora y deduplicación de notificaciones.", "id; evento_origen_id; candidato_id; id_proyeccion; tipo; destinatarios jsonb; estado; suprimido_por_shadow; registrado_en.", "PK id; UQ evento+tipo; FK evento y candidato; índice de proyección."),
    ("gestor.punto_interes", "Capa geográfica global replicada.", "id; legacy_punto_id; nombre; latitud; longitud; categoria; atributos jsonb; hash_origen.", "PK id; UQ legacy_punto_id; coordenadas opcionales."),
]

INTEGRATION_OBJECTS = [
    ("integracion.evento_entrada", "Inbox idempotente de cambios capturados.", "id uuid; evento_origen_id; source_lsn; tabla_origen; operacion; clave_origen; candidato_legacy_id; id_proyeccion; orden_origen; ocurrido_en; recibido_en; payload; payload_hash; estado; intentos; siguiente_intento_en; aplicado_en.", "PK id; UQ evento_origen_id; índices estado+orden, candidato y proyección."),
    ("integracion.evento_salida", "Registro de acciones suprimidas o locales; no publica hacia 8002.", "id uuid; modo; tipo; clave_agregado; id_proyeccion; payload; creado_en; publicado_en.", "PK id; CHECK modo IN (PRUEBA, SUPRIMIDO); índice de proyección."),
    ("integracion.checkpoint_cdc", "Posición durable de cada consumidor.", "consumidor; source_lsn; ultima_fecha; ultimo_id; ultimo_hash; actualizado_en.", "PK consumidor."),
    ("integracion.evento_fallido", "Dead-letter para eventos que agotaron reintentos.", "id; evento_entrada_id; id_proyeccion; error_tipo; error_detalle; intentos; primer_fallo_en; ultimo_fallo_en; resuelto_en.", "PK id; UQ evento_entrada_id; FK evento_entrada; índice de proyección."),
    ("integracion.reconciliacion", "Resultado auditable de la comparación origen/destino.", "id uuid; iniciado_en; finalizado_en; estado; totales_origen; totales_destino; diferencias; diferencias_cantidad; reporte_json; reporte_csv.", "PK id."),
    ("integracion.migracion_control", "Checkpoint reanudable para snapshot y procesos extensos.", "clave; fase; estado; checkpoint jsonb; iniciado_en; actualizado_en; finalizado_en.", "PK clave."),
]

FACT_OBJECTS = [
    ("factibilidad.tarea_local", "Estado, comentario y término estable de cada subtarea.", "id; id_candidato; id_proyeccion; clave_grupo; clave_tarea; estado; comentario; actualizado_por_id; actualizado_en; completado_en.", "PK id; UQ candidato+tarea; índices de proyección y término; sin FK al Gestor."),
    ("factibilidad.decision_local", "Decisión final local, Rechazado o Completado.", "id; id_candidato; id_proyeccion; decision; actualizado_por_id; actualizado_en.", "PK id; UQ id_candidato; índice de proyección; sin FK al Gestor."),
    ("factibilidad.visto_bueno_local", "Visto bueno de Legal o Arquitectura con autor y fecha.", "id; id_candidato; id_proyeccion; area; aprobado_por_id; aprobado_en.", "PK id; UQ candidato+área; índice de proyección; sin FK al Gestor."),
    ("factibilidad.entrega", "Traspaso estructurado del expediente a un área posterior.", "id; id_candidato; id_proyeccion; area_destino; estado; antecedentes jsonb; entregado_por; entregado_en; creado_en; actualizado_en.", "PK id; índices de candidato y proyección; sin FK al Gestor."),
]

OVERLAY_OBJECTS = [
    ("pruebas_gestor.candidato_override", "Workflow local de candidatos operados en 8003.", "id; id_proyeccion; columnas de estado, etapa, última acción, actor y timestamps del flujo.", "PK id; índice de proyección; no modifica gestor.candidato."),
    ("pruebas_gestor.revision_local", "Revisiones y comentarios generados desde 8003.", "id negativo; id_candidato; id_proyeccion; etapa; id_revisor; accion; comentario; creado_en.", "PK id; secuencia negativa; índices de proyección y candidato+fecha+id."),
    ("pruebas_gestor.variable_override", "Copia editable local de Variables.", "id negativo; id_candidato; id_proyeccion; datos comerciales, contractuales y de contacto; actualizado_por_id; actualizado_en.", "PK id; UQ id_candidato; secuencia negativa; índice de proyección."),
]


def build_story():
    s = []
    s += [Spacer(1, 1.7 * cm)]
    if LOGO.exists():
        logo = Image(str(LOGO), width=16.2 * cm, height=2.5 * cm)
        logo.hAlign = "CENTER"
        s += [logo, Spacer(1, 1.3 * cm)]
    s += [
        P("ARQUITECTURA DE DATOS", "CoverKicker"),
        P("Documentación de Base de Datos de Producción", "CoverTitle"),
        P("FactibilidadGDP · PostgreSQL", "CoverSub"),
        Spacer(1, 0.7 * cm),
        table([
            ["Control documental", "Valor"],
            ["Código", "FGDP-DB-PROD-001"],
            ["Versión", "1.3"],
            ["Esquema", "Alembic 20260820_08"],
            ["Fecha de emisión", "20 de agosto de 2026"],
            ["Clasificación", "Uso interno · Producción"],
            ["Responsable técnico", "Arquitectura de Datos / Desarrollo Backend"],
        ], [5.0 * cm, 10.8 * cm]),
        Spacer(1, 1.0 * cm),
        P("Documento maestro para administración, soporte, auditoría, continuidad y evolución del modelo transaccional.", "CoverSub"),
        PageBreak(),
    ]

    s += section("Control del documento", "0")
    s += [
        table([
            ["Versión", "Fecha", "Cambio", "Estado"],
            ["1.3", "20-08-2026", "ID de Proyección en todas las tablas asociadas a candidatos", "Vigente"],
            ["1.2", "20-08-2026", "Medición estable del término de tareas de Factibilidad", "Reemplazada"],
            ["1.1", "20-08-2026", "ID de proyección como atributo empresarial de primer nivel", "Reemplazada"],
            ["1.0", "20-08-2026", "Emisión inicial sobre Alembic 20260820_05", "Reemplazada"],
        ], [2.2 * cm, 3.0 * cm, 8.7 * cm, 3.3 * cm]),
        Spacer(1, 8),
        P("Aprobaciones requeridas", "H2x"),
        table([
            ["Rol", "Nombre", "Fecha", "Firma / aprobación"],
            ["Dueño de producto", "Pendiente", "—", "—"],
            ["Arquitectura / TI", "Pendiente", "—", "—"],
            ["Operaciones", "Pendiente", "—", "—"],
        ], [4.1 * cm, 4.7 * cm, 3.2 * cm, 5.2 * cm]),
        P("Nota de gobierno", "H2x"),
        P("La aprobación documental no sustituye la autorización técnica exigida antes de ejecutar DDL, restauraciones, truncados, publicaciones o slots sobre entornos productivos.", "Callout"),
        PageBreak(),
    ]

    s += section("Contenido", "1")
    toc = [
        "1. Resumen ejecutivo", "2. Alcance y principios de diseño", "3. Arquitectura productiva",
        "4. Propiedad y gobierno del dato", "5. Modelo relacional", "6. Diccionario: gestor",
        "7. Diccionario: integracion", "8. Diccionario: factibilidad",
        "9. Capa operativa pruebas_gestor", "10. Vistas y contratos de lectura",
        "11. Estados y trazabilidad", "12. Transacciones e idempotencia",
        "13. Seguridad", "14. Archivos y adjuntos", "15. Migraciones y liberaciones",
        "16. Monitoreo y reconciliación", "17. Respaldo y recuperación",
        "18. Procedimientos controlados", "19. Consultas operativas", "20. Glosario y pendientes de gobierno",
    ]
    s += [P(item, "TOC") for item in toc] + [PageBreak()]

    s += section("Resumen ejecutivo", "1")
    s += [
        P("FactibilidadGDP es la base PostgreSQL transaccional del servicio ejecutado inicialmente en el puerto 8003. Consolida una réplica normalizada del Gestor, el dominio propio de Factibilidad y los componentes técnicos necesarios para sincronización, auditoría y recuperación."),
        P("Durante la convivencia, el servicio 8002 continúa siendo el sistema de registro de candidatos, estados, comentarios, usuarios, Variables y documentos del Gestor. El servicio 8003 recibe esos cambios en una sola dirección y nunca corrige la fuente."),
        P("Decisión arquitectónica principal", "H2x"),
        P("Separar físicamente propiedad, integración y operación local mediante esquemas PostgreSQL. Esta separación reduce el riesgo de escritura cruzada, permite reconciliar el origen y facilita un cutover futuro controlado.", "Callout"),
        table([
            ["Indicador", "Definición vigente"],
            ["Base", "FactibilidadGDP"],
            ["Motor", "PostgreSQL"],
            ["Versión lógica", "Alembic 20260820_08"],
            ["Aplicación", "FastAPI · puerto 8003"],
            ["Replicación", "Polling incremental · consistencia eventual"],
            ["Dirección", "8002 → 8003"],
            ["Esquemas", "gestor, integracion, factibilidad, pruebas_gestor"],
        ], [4.6 * cm, 12.6 * cm]),
    ]

    s += section("Alcance y principios de diseño", "2")
    for item in [
        "Separación explícita entre datos replicados y datos propios.",
        "Sin sincronización bidireccional sobre candidatos, estados, revisiones o usuarios.",
        "Idempotencia mediante identificadores de origen, hashes y restricciones únicas.",
        "Trazabilidad inmutable de transiciones y actividades.",
        "Variables versionadas; no se sobrescribe el historial.",
        "Migraciones exclusivamente mediante Alembic.",
        "Adjuntos fuera de PostgreSQL, respaldados junto con la base.",
        "Correos y efectos externos bloqueados durante modo espejo.",
    ]:
        s.append(bullet(item))
    s += [P("Fuera de alcance", "H2x"), P("Este documento no contiene contraseñas, cadenas de conexión, secretos de sesión, claves de Google Maps, contenido de documentos ni datos personales de usuarios finales.")]

    s += section("Arquitectura productiva", "3")
    s += [ArchitectureFlow(), Spacer(1, 8), P("La ruta oficial de cambios es unidireccional. El consumidor captura cambios, los registra en el inbox, los transforma al modelo normalizado y confirma el checkpoint dentro del proceso controlado. Las acciones del Gestor efectuadas en 8003 se redirigen a una capa local y no vuelven a 8002."),
          P("Configuración lógica", "H2x"),
          P("SHADOW_MODE=true\nGESTOR_TEST_MODE=true\nEMAIL_DELIVERY_ENABLED=false\nTARGET_SEARCH_PATH=pruebas_gestor,factibilidad,gestor,integracion,public", "Codex")]

    s += section("Propiedad y gobierno del dato", "4")
    s += [table([
        ["Dominio", "Sistema de registro", "Esquema 8003", "Política de escritura"],
        ["Candidatos y estados", "Gestor 8002", "gestor", "Solo consumidor"],
        ["Usuarios y roles", "Gestor 8002", "gestor", "Solo consumidor"],
        ["Variables oficiales", "Gestor 8002", "gestor", "Solo consumidor"],
        ["Integración", "FactibilidadGDP", "integracion", "Servicios técnicos"],
        ["Checklist y VB", "FactibilidadGDP", "factibilidad", "Aplicación 8003"],
        ["GDP local 8003", "FactibilidadGDP", "pruebas_gestor", "Aplicación 8003"],
        ["Binarios", "FactibilidadGDP", "Filesystem", "Aplicación 8003"],
    ], [4.0 * cm, 4.3 * cm, 3.4 * cm, 5.5 * cm]),
    P("Las referencias id_candidato de los dominios locales son lógicas. La ausencia deliberada de FK evita cascadas hacia la réplica y permite ciclos de limpieza independientes.", "Callout")]

    s += section("Modelo relacional", "5")
    s += [P("Núcleo de relaciones físicas", "H2x"), table([
        ["Origen", "Cardinalidad", "Destino", "Significado"],
        ["estado_catalogo", "1:N", "candidato", "Estado vigente"],
        ["rol", "1:N", "usuario", "Rol normalizado"],
        ["proyecto_importacion", "1:N", "candidato", "Agrupación de origen"],
        ["candidato", "1:N", "transicion_estado", "Historial de estado"],
        ["candidato", "1:N", "actividad_candidato", "Actividad sin transición"],
        ["candidato", "1:N", "variable_proyecto_version", "Versiones de Variables"],
        ["evento_entrada", "1:0..1", "transicion_estado", "Evento aplicado"],
        ["evento_entrada", "1:0..1", "evento_fallido", "Dead-letter"],
    ], [4.3 * cm, 2.5 * cm, 4.8 * cm, 5.6 * cm]),
    P("Los dominios factibilidad y pruebas_gestor referencian el ID legado sin FK física.")]

    s += section("Diccionario de datos · gestor", "6")
    s += [P("Réplica normalizada de solo lectura para la aplicación. Cada registro conserva identificadores, payload y hash de origen cuando corresponde.")]
    s += [object_block(*obj) for obj in GESTOR_OBJECTS]

    s += section("Diccionario de datos · integracion", "7")
    s += [P("Componentes técnicos de captura, aplicación, reintento, conciliación y control operacional.")]
    s += [object_block(*obj) for obj in INTEGRATION_OBJECTS]

    s += section("Diccionario de datos · factibilidad", "8")
    s += [P("Dominio transaccional propio del módulo Factibilidad. Las operaciones se confirman en PostgreSQL y se comparten entre los usuarios del módulo.")]
    s += [object_block(*obj) for obj in FACT_OBJECTS]

    s += section("Capa operativa · pruebas_gestor", "9")
    s += [P("Esta capa permite operar el GDP dentro del servicio 8003 sin escribir en TinderLocales ni alterar la réplica gestor.*. El nombre físico se mantiene por compatibilidad durante la convivencia.", "Callout")]
    s += [object_block(*obj) for obj in OVERLAY_OBJECTS]
    s += [P("Vistas escribibles", "H2x"), table([
        ["Vista", "Lectura", "Escritura"],
        ["candidato_ubicacion", "Atributos vivos de gestor + workflow local", "Trigger INSTEAD OF UPDATE"],
        ["revision", "Historial oficial + local", "Trigger INSTEAD OF INSERT"],
        ["variables_proyecto_candidato", "Oficial o copia local", "Triggers INSERT/UPDATE"],
    ], [5.0 * cm, 6.5 * cm, 5.7 * cm])]

    s += section("Vistas y contratos de lectura", "10")
    s += [table([
        ["Vista", "Contrato"],
        ["gestor.vw_pendientes", "Candidatos PENDIENTE"],
        ["gestor.vw_observacion", "Candidatos OBSERVACION"],
        ["gestor.vw_rechazados", "Candidatos RECHAZADO"],
        ["gestor.vw_en_estudio", "Candidatos EN_ESTUDIO"],
        ["gestor.vw_propuestos", "Candidatos PROPUESTO"],
        ["gestor.vw_aprobados", "Candidatos APROBADO"],
        ["gestor.vw_proyectos", "Candidatos PROYECTO"],
        ["gestor.vw_metricas_flujo", "Conteo por estado y orden"],
        ["gestor.proyecto", "Adaptador ORM histórico"],
        ["gestor.candidato_ubicacion", "Adaptador de candidato"],
        ["gestor.revision", "Transiciones + comentarios"],
        ["gestor.variables_proyecto_candidato", "Variables vigentes"],
    ], [6.6 * cm, 10.6 * cm])]

    s += section("Estados y trazabilidad", "11")
    s += [table([
        ["Código normalizado", "Valores de origen representativos", "Certeza"],
        ["PENDIENTE", "pendiente, pending", "EXACTA"],
        ["PENDIENTE", "devuelto, returned, sugerido, suggested", "INFERIDA"],
        ["OBSERVACION", "observacion, observation", "EXACTA"],
        ["RECHAZADO", "rechazado, rejected", "EXACTA"],
        ["EN_ESTUDIO", "en_estudio, study", "EXACTA"],
        ["PROPUESTO", "aprobado, approved, approved_final", "INFERIDA"],
        ["APROBADO", "locales_proyecto, approved_location", "INFERIDA"],
        ["PROYECTO", "por_abrir, opening, project", "INFERIDA"],
        ["PENDIENTE provisional", "valor desconocido", "DESCONOCIDA"],
    ], [5.0 * cm, 8.8 * cm, 3.4 * cm]),
    P("Todo valor de origen se conserva. Un mapeo DESCONOCIDA debe generar observación de reconciliación; nunca se corrige silenciosamente la fuente.", "Callout")]

    s += section("Transacciones e idempotencia", "12")
    for item in [
        "Registrar o reconocer evento_origen_id.", "Validar orden y versión del candidato.",
        "Actualizar estado actual.", "Insertar transición o actividad.",
        "Versionar Variables cuando corresponda.", "Actualizar checkpoint.",
        "Confirmar todo o revertir todo.",
    ]:
        s.append(bullet(item))
    s += [P("Garantías", "H2x"), table([
        ["Riesgo", "Control"],
        ["Entrega repetida", "Restricciones únicas por evento y efecto"],
        ["Eventos fuera de orden", "orden_origen y checkpoint"],
        ["Fallo parcial", "Transacción ACID"],
        ["Fallo persistente", "Backoff, dead-letter y replay"],
        ["Deriva silenciosa", "Hashes y reconciliación"],
    ], [5.0 * cm, 12.2 * cm])]

    s += section("Seguridad", "13")
    for item in [
        "Usuario de aplicación limitado a FactibilidadGDP.",
        "Usuario legado con privilegio SELECT sobre TinderLocales.",
        "Credenciales únicamente en .env con permiso 600.",
        "Cookie independiente: factibilidad_session.",
        "SHADOW_MODE y EMAIL_DELIVERY_ENABLED actúan como barreras de efectos externos.",
        "No se crean publicaciones ni slots automáticamente.",
        "Respaldos, adjuntos, logs y .env están fuera de Git.",
    ]:
        s.append(bullet(item))
    s += [P("Datos sensibles", "H2x"), P("hash_contrasena, payloads, comentarios, destinatarios, contactos, rutas y reportes deben tratarse conforme a las políticas internas de acceso, retención y cifrado.")]

    s += section("Archivos y adjuntos", "14")
    s += [P("Los binarios no se almacenan en PostgreSQL. La base puede contener inventario y hashes del Gestor, mientras que Factibilidad utiliza el filesystem aislado:"),
          P("/home/mbustos/FactibilidadGDP/DocumentosProyeccion", "Codex"),
          P("Un respaldo recuperable exige consistencia entre dump PostgreSQL, directorio de documentos, configuración cifrada y unidades de servicio.", "Callout")]

    s += section("Migraciones y liberaciones", "15")
    s += [table([
        ["Revisión", "Descripción"],
        ["20260820_01", "Modelo normalizado, integración, Factibilidad, estados y vistas"],
        ["20260820_02", "Identificadores legados en vistas"],
        ["20260820_03", "Coordenadas opcionales de puntos de interés"],
        ["20260820_04", "Capa aislada GDP en 8003"],
        ["20260820_05", "Atributos vivos bajo workflow local"],
        ["20260820_06", "ID de proyección empresarial obligatorio e indexado"],
        ["20260820_07", "Timestamp estable de término para subtareas de Factibilidad"],
        ["20260820_08", "ID de Proyección en tablas de trazabilidad por candidato"],
    ], [4.0 * cm, 13.2 * cm]),
    P("python -m app.replication.cli migrate --dry-run\npython -m app.replication.cli migrate", "Codex"),
    P("Cada liberación se valida primero sobre una base temporal factibilidad_test_<UUID>. Base.metadata.create_all() no se utiliza para el esquema productivo.")]

    s += section("Monitoreo y reconciliación", "16")
    s += [table([
        ["Control", "Resultado esperado"],
        ["GET /health", "FastAPI disponible"],
        ["GET /health/db", "Conexión destino OK"],
        ["GET /health/legacy", "Lectura fuente OK"],
        ["GET /health/replication", "Lag bajo umbral; 0 fallidos; 0 diferencias"],
    ], [6.0 * cm, 11.2 * cm]),
    P("Reconciliación continua", "H2x")]
    for item in ["Total y conteo por estado.", "Último estado por candidato.", "Cantidad y orden de revisiones.", "Comentarios y usuarios.", "Variables vigentes.", "Inventario documental.", "Hashes relevantes."]:
        s.append(bullet(item))

    s += section("Respaldo y recuperación", "17")
    s += [P("Respaldo previo a cambio", "H2x"),
          P("docker exec postgres_tinder_locales sh -c \\\n+  'pg_dump -U \"$POSTGRES_USER\" -d FactibilidadGDP -Fc' \\\n+  > /home/mbustos/backups/FactibilidadGDP/FactibilidadGDP_YYYYMMDDTHHMMSSZ.dump", "Codex"),
          P("La restauración se ensaya primero en una base nueva. El procedimiento incluye validación del dump, migraciones, reconciliación, autenticación, documentos y endpoints de salud."),
          P("Gobierno pendiente", "H2x"),
          P("El repositorio no define todavía RPO, RTO ni retención contractual. Operaciones debe aprobar estos valores y documentar pruebas periódicas de restauración.", "Callout")]

    s += section("Procedimientos controlados", "18")
    s += [P("Limpieza exclusiva de acciones GDP locales", "H2x"),
          P("BEGIN;\nTRUNCATE TABLE pruebas_gestor.revision_local,\n               pruebas_gestor.variable_override,\n               pruebas_gestor.candidato_override\nRESTART IDENTITY;\nCOMMIT;", "Codex"),
          P("Requisitos: confirmar base FactibilidadGDP, crear respaldo, contar con autorización y verificar posteriormente que gestor.*, integracion.*, factibilidad.* y documentos no cambiaron."),
          P("Replay de dead-letter", "H2x"),
          P("python -m app.replication.cli replay --dry-run\npython -m app.replication.cli replay", "Codex")]

    s += section("Consultas operativas de solo lectura", "19")
    queries = [
        ("Versión", "SELECT version_num FROM alembic_version;"),
        ("Trazabilidad", "SELECT id_proyeccion, legacy_candidato_id, id, estado_origen FROM gestor.candidato ORDER BY id_proyeccion, legacy_candidato_id;"),
        ("Métricas", "SELECT * FROM gestor.vw_metricas_flujo;"),
        ("Inbox", "SELECT estado, count(*) FROM integracion.evento_entrada GROUP BY estado ORDER BY estado;"),
        ("Checkpoint", "SELECT consumidor, source_lsn, ultima_fecha, ultimo_id, actualizado_en FROM integracion.checkpoint_cdc ORDER BY actualizado_en DESC;"),
        ("Dead-letter", "SELECT id, evento_entrada_id, error_tipo, intentos, ultimo_fallo_en FROM integracion.evento_fallido WHERE resuelto_en IS NULL ORDER BY ultimo_fallo_en DESC;"),
    ]
    for name, query in queries:
        s += [P(name, "H3x"), P(query, "Codex")]

    s += section("Glosario y pendientes de gobierno", "20")
    s += [table([
        ["Término", "Definición"],
        ["CDC", "Captura continua de cambios desde el log transaccional"],
        ["Checkpoint", "Última posición durable confirmada"],
        ["Dead-letter", "Evento fallido aislado para análisis o replay"],
        ["Idempotencia", "Repetir un evento no repite su efecto"],
        ["LSN", "Posición del WAL de PostgreSQL"],
        ["Polling", "Consulta incremental periódica de la fuente"],
        ["RPO", "Pérdida máxima de datos tolerable"],
        ["RTO", "Tiempo objetivo de recuperación"],
        ["Shadow mode", "Operación espejo con efectos externos bloqueados"],
    ], [4.1 * cm, 13.1 * cm]),
    P("Pendientes formales", "H2x")]
    for item in [
        "Aprobar RPO, RTO y política de retención.",
        "Definir responsable nominal de base y suplencia.",
        "Calendarizar pruebas de restauración.",
        "Formalizar matriz de acceso por rol PostgreSQL.",
        "Aprobar criterios y ventana del cutover futuro.",
    ]:
        s.append(bullet(item))
    s += [Spacer(1, 14), P("Fin del documento", "CoverKicker")]
    return s


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = ProductionDocTemplate(str(OUTPUT))
    document.build(build_story())
    print(OUTPUT)


if __name__ == "__main__":
    main()
