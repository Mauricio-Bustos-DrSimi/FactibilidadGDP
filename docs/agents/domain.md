# Domain Docs

Este repositorio utiliza documentación de dominio de contexto único.

## Antes de explorar o modificar el proyecto

Leer, cuando existan:

1. `CONTEXT.md` en la raíz.
2. Los ADR relacionados dentro de `docs/adr/`.
3. Las restricciones específicas de `AGENTS.md`.

Si alguno de estos archivos todavía no existe, continuar silenciosamente. Las skills de modelado y arquitectura los crearán cuando exista contenido real que registrar.

## Estructura

```text
/
├── AGENTS.md
├── CONTEXT.md
├── docs/
│   ├── agents/
│   │   ├── issue-tracker.md
│   │   └── domain.md
│   └── adr/
│       └── NNNN-descripcion.md
├── app/
├── alembic/
└── tests/
```

## CONTEXT.md

Debe mantener un glosario breve con los términos del dominio, sus significados y los sinónimos que deben evitarse.

Para FactibilidadGDP debe distinguir claramente, entre otros:

- Gestor de Proyecciones.
- Factibilidad.
- Candidato.
- Local.
- ID de Proyección.
- Estado de origen y estado normalizado.
- Macrotarea y subtarea.
- Legal y Arquitectura.
- Réplica, modo espejo y sistema de registro.

No crear términos nuevos cuando ya exista un término empresarial definido.

## ADR

Registrar en `docs/adr/` decisiones difíciles de revertir, especialmente las relacionadas con:

- Propiedad de datos entre los puertos 8002 y 8003.
- Replicación unidireccional.
- Límites entre `gestor.*`, `integracion.*` y `factibilidad.*`.
- Migraciones y compatibilidad.
- Autenticación, documentos y efectos productivos.

Si una propuesta contradice un ADR vigente, señalarlo explícitamente antes de implementar.
