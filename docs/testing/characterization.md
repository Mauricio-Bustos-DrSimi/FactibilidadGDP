# Pruebas de caracterización

Esta suite fija el comportamiento observable de FactibilidadGDP antes de su
extracción modular. No utiliza la base ni los documentos configurados en `.env`:
`tests/conftest.py` fuerza SQLite y un directorio temporal para la aplicación, y
las pruebas PostgreSQL crean mediante Alembic una base exclusiva
`factibilidad_test_<UUID>` cuando `TEST_DATABASE_ADMIN_URL` está configurada.

## Seams y cobertura

| Seam | Comportamiento protegido | Pruebas |
|---|---|---|
| HTTP FastAPI | Login, sesión, logout, selector, permisos, consulta y comentario GDP, embudo | `tests/characterization/test_http_contracts.py` |
| HTTP FastAPI | Locales, checklist Legal/Arquitectura, progreso, vistos buenos, decisión y ficha independiente | `tests/characterization/test_http_contracts.py` |
| Navegador | Cambio GDP/Factibilidad, embudo, tabla, Street View, comentario con ENTER y acceso denegado | `tests/e2e/test_module_navigation.py` |
| Filesystem | Biblioteca por macrotarea y máximo de dos imágenes en la ficha | `tests/characterization/test_filesystem_contracts.py` |
| CLI | Comandos operacionales, dry-run de apply/replay y reconciliación | `tests/characterization/test_replication_cli_contracts.py`, `test_postgres_cli_contracts.py` |
| PostgreSQL | Alembic, snapshot reanudable, polling eventual, idempotencia, replay, dead-letter y reconciliación | `tests/characterization/test_postgres_replication_contracts.py` y pruebas preexistentes de replicación |
| Configuración | Prohibición de correo real durante `SHADOW_MODE=true` | `tests/characterization/test_replication_cli_contracts.py` |
| Propiedad de datos | Overlay `pruebas_gestor.*` sin modificar `gestor.*` | `tests/test_gestor_test_overlay.py` |

## Ejecución

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests/characterization -q
python -m pytest tests/e2e -q
python -m pytest tests -q
```

Las pruebas E2E reutilizan Chrome o Edge instalado localmente; no descargan un
navegador adicional.

Para ejecutar PostgreSQL, definir `TEST_DATABASE_ADMIN_URL` de forma privada.
La fixture crea la base temporal, aplica `alembic upgrade head`, ejecuta las
pruebas y elimina exclusivamente esa base al finalizar.

## Límites deliberados

- No se comprueba el contenido remoto de Google Maps o de un panorama real de
  Street View; se caracteriza la navegación y el fallback sin clave para no
  depender de red ni consumir una credencial.
- No se entrega correo. Se caracteriza el cierre preventivo de configuración y
  las pruebas existentes del outbox utilizan un adaptador controlado.
- PDF e imágenes representan el contrato documental; no se carga una muestra
  de cada extensión admitida.
- Las pruebas PostgreSQL se reportan como omitidas cuando no existe
  `TEST_DATABASE_ADMIN_URL`; nunca sustituyen esa ausencia conectándose a una
  base configurada para la aplicación.
