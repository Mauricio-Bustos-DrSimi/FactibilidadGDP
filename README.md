# Site Swiper — Flujo de Revisión de Ubicaciones

"Tinder para selección de sitios", ahora con un **flujo de aprobación multinivel**. Los
revisores evalúan ubicaciones geográficas candidatas una por una sobre un mapa de Google con
una leyenda de metadatos, y luego **aceptan / rechazan / destacan / omiten** cada una. Cada
acción se persiste en una base de datos SQLite local y queda registrada en una bitácora de
auditoría de solo anexado. Una capa global de ubicaciones de negocios existentes (farmacias,
estaciones de metro, …) se dibuja sobre el mapa como contexto.

Cada candidato recorre tres capas de revisión secuenciales:

```
coordinator  →  manager  →  director  →  approved_final
```

Un usuario solo ve la cola de **su propio rol**. Aceptar (o destacar) hace avanzar al candidato
una capa hacia arriba; la aceptación del `director` es la aprobación final. Los rechazos,
devoluciones y reaperturas también están soportados y quedan registrados.

Funciona tanto en **móvil (táctil)** como en **escritorio (ratón + teclado)**.

---

## Roles y flujo de trabajo

| Rol           | Ve la cola de       | También puede                                          |
|---------------|---------------------|--------------------------------------------------------|
| `coordinator` | capa coordinator    | aceptar / rechazar / destacar / omitir                 |
| `manager`     | capa manager        | + **devolver** al coordinator                          |
| `director`    | capa director       | + **devolver** al manager; aprobación final al aceptar |
| `sysadmin`    | *(sin cola)*        | gestionar usuarios y proyectos, ingerir datos, ver estadísticas, exportar |

### Acciones de revisión

- **aceptar (accept)** — hace avanzar al candidato a la siguiente capa (o a `approved_final` si
  es el director).
- **destacar (star)** — una aceptación fuerte: avanza *y* marca al candidato como `priority`.
- **rechazar (reject)** — marca como rechazado; se recuerda la etapa para que una **reapertura**
  posterior retome ahí.
- **omitir (skip)** — aplaza sin decidir; el candidato pasa al final de tu cola.
- **devolver (send back)** — regresa al candidato una capa hacia abajo para re-revisión (solo
  manager/director).
- **reabrir (reopen)** — devuelve un candidato rechazado a su cola (el dueño de esa etapa, o un
  sysadmin).

Cada una de estas acciones escribe una fila en la bitácora de auditoría `review` — nada se
actualiza en el sitio, de modo que se puede reconstruir el historial completo de decisiones de
cualquier candidato. La tarjeta del candidato muestra este historial en línea.

---

## Inicio rápido

```bash
# 1. Crea un entorno virtual e instala las dependencias
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell/CMD
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt

# 2. Configura el entorno
copy .env.example .env            # Windows  (cp en macOS/Linux)
#   luego edita .env — como mínimo define GOOGLE_MAPS_API_KEY y SESSION_SECRET

# 3. Ejecuta
python run.py
#   …o bien:  uvicorn app.main:app --reload
```

Luego abre **http://127.0.0.1:8001** (`run.py` usa el puerto **8001**).

La base de datos SQLite se crea automáticamente en el primer arranque en
`./data/site_swiper.db`.

### Primer inicio de sesión

En el primer arranque la aplicación **crea una cuenta sysadmin** para que una instalación nueva
sea utilizable:

- Si `SYSADMIN_EMAIL` / `SYSADMIN_PASSWORD` están definidas en `.env`, se crea esa cuenta.
- En caso contrario se crea un `admin@local` por defecto y se **imprime en consola una
  contraseña aleatoria de un solo uso** — cópiala de los registros de arranque y cámbiala tras
  iniciar sesión.

Inicia sesión como sysadmin y luego crea los usuarios `coordinator` / `manager` / `director` que
harán la revisión real (cajón de configuración → usuarios, o `POST /users`).

> **¿Sin clave de Google Maps API?** La aplicación funciona igualmente — autenticación,
> ingesta, cola de revisión, decisiones y exportación a CSV se ejecutan. Solo no se renderizan
> las teselas del mapa; la tarjeta del candidato, la leyenda y el flujo de decisión siguen
> siendo usables.

---

## Uso de la herramienta

**Como sysadmin (configuración):**

1. Abre el **cajón de configuración ☰** (arriba a la izquierda).
2. **Crea los usuarios revisores** (coordinator / manager / director).
3. **Crea un proyecto** (la unidad de trabajo; los candidatos se asocian a él).
4. **Carga candidatos** — ya sea:
   - subiendo un archivo CSV/XLSX (ver [Fuentes de datos](#fuentes-de-datos)), o
   - lanzando una **importación desde Postgres** (`POST /admin/import-postgres`) para traerlos
     directamente desde la base de datos configurada.
5. (Opcional) **Carga ubicaciones de negocios** — una capa de enriquecimiento global compartida
   entre todos los proyectos. También disponible por subida de archivo o por la importación de
   Postgres.
6. Sigue el avance en el **panel** (`GET /stats`) y **exporta resultados** a CSV cuando quieras.

**Como revisor (coordinator / manager / director):**

1. Inicia sesión — aterrizas directamente en tu cola.
2. Revisa cada candidato (aceptar / rechazar / destacar / omitir; managers y directores también
   pueden devolver).
3. Cuando tu cola queda vacía, no hay nada esperando en tu capa.

---

## Controles de decisión (los tres métodos de entrada son equivalentes)

| Acción   | Táctil (móvil)       | Ratón (escritorio)        | Teclado       |
|----------|----------------------|---------------------------|---------------|
| Aceptar  | desliza a la **derecha** | arrastra la tarjeta a la derecha / **✓** | **→**   |
| Rechazar | desliza a la **izquierda** | arrastra la tarjeta a la izquierda / **✕** | **←** |
| Destacar | desliza hacia **arriba** | arrastra la tarjeta hacia arriba / **★** | **↑** o **S** |

Omitir, devolver y reabrir se exponen como controles dentro de la tarjeta (no tienen gesto de
deslizamiento).

La cola de revisión es **reanudable**: solo se sirven candidatos en estado `pending`/`returned`
**en tu etapa**, y un candidato recién omitido pasa al final de la cola para que recorras el
resto primero.

---

## Fuentes de datos

Los candidatos y las ubicaciones de negocios se pueden cargar de dos maneras.

### 1. Subida de archivo (CSV / XLSX)

`POST /projects/{id}/ingest` acepta un `file` multipart más un campo de formulario `config`
opcional (JSON o YAML) que declara la columna del mapa:

```json
{ "map_column": "maps" }
```

El lector detecta automáticamente:

- **Delimitador** — punto y coma (exportaciones en configuración regional española), coma o
  tabulación.
- **Codificación** — UTF-8/BOM, Windows-1252 (cp1252), Latin-1.
- **Coordenadas** — columnas explícitas `Latitud`/`Longitud` (o `lat`/`lng`), **o** una única
  columna de referencia de mapa. También normaliza las comas decimales europeas
  (`-33,40214` → `-33.40214`) y da formato de porcentaje a las columnas de rangos etarios.

Si no se declara ninguna columna de mapa, se prueban nombres comunes (`maps`, `map`, `url`,
`coordinates`, `coordenadas`, `ubicacion`, …) antes de recurrir a la primera columna. Todas las
columnas que no sean de coordenadas pasan a formar la leyenda de la tarjeta.

### 2. Importación desde Postgres

`POST /admin/import-postgres` (sysadmin) trae candidatos y puntos de interés directamente desde
una base de datos Postgres configurada — sin necesidad de archivo. Lee:

- **Candidatos** desde el esquema/tabla configurados (por defecto `dw_simi.SolicitudesProyecciones`).
- **Ubicaciones de negocios** desde las tablas de puntos de interés configuradas (por defecto
  `PI_Ahumada`, `PI_CruzVerde`, `PI_Salcobrand`, `PI_Maicao`, `PI_EstacionesMetro`), cada una
  etiquetada y con un ícono de mapa acorde a su categoría.

El cuerpo de la solicitud controla el comportamiento:

```json
{
  "project_id": null,          // reutilizar un proyecto existente, o…
  "project_name": "…",         // …nombrar uno nuevo (autonombrado si se omite)
  "import_candidates": true,
  "import_business": true,
  "replace_candidates": false, // vaciar primero los candidatos de este proyecto
  "replace_business": true     // vaciar primero la capa global de negocios
}
```

La conexión y los nombres de tablas provienen de variables de entorno (ver
[Configuración](#configuración)). `psycopg2` se importa de forma perezosa, así que la ingesta
por archivo sigue funcionando aunque no esté instalado.

### Datos de ejemplo (ejecución de extremo a extremo sin fuente externa)

- `data/sample_candidates.csv` — ubicaciones candidatas (mezcla de `lat,lng` y URLs de Maps)
- `data/sample_business_locations.csv` — ubicaciones de negocios existentes

---

## Notas sobre móvil

- Responsivo desde teléfono hasta escritorio, sin desplazamiento horizontal; `viewport-fit=cover`
  + insets de área segura para dispositivos con muesca (notch).
- Objetivos táctiles ≥ 44px; los botones de acción están anclados abajo para uso con una sola mano.
- Los gestos de deslizamiento están limitados a la **tarjeta del candidato** (`touch-action: none`)
  para que nunca compitan con el paneo/zoom nativo del mapa. La superposición de leyenda se colapsa
  en pantallas pequeñas.

---

## Endpoints de la API

Todos los endpoints excepto `GET /config`, `GET /` y `POST /auth/login` requieren una cookie de
sesión autenticada. Los marcados con **(sysadmin)** requieren además el rol sysadmin.

| Método | Ruta                                | Propósito                                                     |
|--------|-------------------------------------|---------------------------------------------------------------|
| POST   | `/auth/login`                       | Iniciar sesión (email + contraseña) → establece la cookie     |
| POST   | `/auth/logout`                      | Cerrar la sesión                                              |
| GET    | `/me`                               | Usuario actualmente autenticado                              |
| GET    | `/config`                           | Devuelve la clave de Maps API para el frontend                |
| POST   | `/projects`                         | Crear un proyecto **(sysadmin)**                              |
| GET    | `/projects`                         | Listar proyectos                                             |
| GET    | `/projects/{id}`                    | Obtener un proyecto                                          |
| POST   | `/projects/{id}/ingest`             | Subir archivo tabular → poblar candidatos **(sysadmin)**     |
| GET    | `/queue`                            | Siguiente candidato + cuenta restante para el rol del usuario |
| GET    | `/candidates/{id}`                  | Obtener un candidato (incl. estado del flujo)                 |
| GET    | `/candidates/{id}/reviews`          | Bitácora de auditoría completa de un candidato               |
| POST   | `/candidates/{id}/review`           | Registrar aceptar / rechazar / destacar / omitir             |
| POST   | `/candidates/{id}/send-back`        | Devolver una capa hacia abajo (manager/director)             |
| POST   | `/candidates/{id}/reopen`           | Reabrir un candidato rechazado                               |
| GET    | `/stats`                            | Conteos del flujo por etapa y estado **(sysadmin)**          |
| POST   | `/users`                            | Crear un usuario **(sysadmin)**                              |
| GET    | `/users`                            | Listar usuarios **(sysadmin)**                               |
| GET    | `/projects/{id}/results`            | Exportar candidatos + veredictos por etapa a CSV **(sysadmin)** |
| GET    | `/business`                         | Listar marcadores de enriquecimiento global                  |
| POST   | `/business/ingest`                  | Cargar/reemplazar ubicaciones de negocios **(sysadmin)**     |
| POST   | `/admin/import-postgres`            | Importar candidatos + PIs desde Postgres **(sysadmin)**      |

Documentación interactiva de la API en **http://127.0.0.1:8001/docs**.

---

## Modelo de datos (SQLAlchemy → SQLite)

- **user** — `id` (UUID PK), `email` (único), `name`, `password_hash` (bcrypt),
  `role` (`coordinator|manager|director|sysadmin`), `active`, `created_at`.
- **project** — `project_id` (UUID PK), `project_url` (distinta de las URLs de mapa por
  ubicación), `name`, `source_file`, `notes`, `created_at`.
- **location_candidate** — `id`, `project_id` (FK), `map_ref` (valor crudo), `lat`, `lng`
  (parseados), `display_data` (JSON → leyenda), más el estado del flujo:
  `current_stage` (`coordinator|manager|director|done`),
  `status` (`pending|returned|rejected|approved_final`), y `priority` (se activa al destacar).
- **review** — bitácora de auditoría de solo anexado: `id`, `candidate_id` (FK), `stage`,
  `reviewer_id` (FK), `action` (`accept|reject|star|skip|send_back|reopen`), `note`,
  `created_at`. Nunca se actualiza ni se borra; la "decisión actual en una etapa" es la última
  fila accept/reject/star de esa etapa.
- **business_location** — `id`, `name`, `lat`, `lng`, `category`, `attributes` (JSON, puede
  incluir `image_url` y metadatos de origen). Global; sin FK de proyecto.

---

## Análisis de la referencia de mapa

La columna de mapa se analiza (`app/ingestion.py`) a partir de cualquiera de:

- Columnas explícitas `Latitud`/`Longitud` (o `lat`/`lng`), incluyendo comas decimales europeas.
- `lat,lng` simple con decimales de punto (opcionalmente entre paréntesis): `19.4326,-99.1332`,
  `(19.43, -99.13)`.
- URLs de Google Maps: `@lat,lng,zoom`, `!3dlat!4dlng`, y formas de consulta
  `?q=`/`ll=`/`center=`/`destination=`/`daddr=`.

Las filas cuyas coordenadas no se pueden analizar igual se almacenan (y se cuentan en el resumen
de ingesta); los candidatos con coordenadas se sirven primero para que el mapa siempre tenga un
pin.

---

## Configuración

Toda la configuración se hace mediante variables de entorno (cargadas desde `.env`; ver
`.env.example`).

| Variable                              | Propósito                                                      |
|---------------------------------------|----------------------------------------------------------------|
| `GOOGLE_MAPS_API_KEY`                 | Clave de Maps JavaScript API (solo teselas; la app funciona sin ella) |
| `SESSION_SECRET`                      | Firma las cookies de sesión. **Defínela en producción** — si no se define, se usa una clave aleatoria por proceso que cierra la sesión de todos al reiniciar. |
| `SYSADMIN_EMAIL` / `SYSADMIN_PASSWORD`| Controla el sysadmin creado. Si no se definen, se crea `admin@local` con una contraseña aleatoria impresa. |
| `POSTGRES_HOST` / `POSTGRES_PORT`     | Host/puerto de la fuente Postgres (por defecto `localhost:5433`) |
| `POSTGRES_DB`                         | Nombre de la base de datos Postgres (por defecto `TinderLocales`) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | Credenciales de Postgres — **nunca embebidas**; solo desde el entorno |
| `PG_SCHEMA`                           | Esquema para la importación (por defecto `dw_simi`)            |
| `CAND_TABLE`                          | Tabla origen de candidatos (por defecto `SolicitudesProyecciones`) |
| `BUS_TABLES`                          | Tablas de PIs separadas por comas para la capa de negocios     |

---

## Estructura del proyecto

```
app/
  main.py        App FastAPI: auth, proyectos, cola de revisión, estadísticas, usuarios, importación Postgres, servido estático
  auth.py        Hashing bcrypt, dependencias de usuario-actual por cookie de sesión + guardia de rol, seeder de sysadmin
  workflow.py    Máquina de estados de revisión multinivel (etapas, acciones, colas, bitácora)
  database.py    Motor/sesión; crea automáticamente ./data/site_swiper.db
  models.py      Modelos ORM de SQLAlchemy (User, Project, LocationCandidate, Review, BusinessLocation)
  schemas.py     Esquemas Pydantic de solicitud/respuesta
  ingestion.py   Ingesta por archivo + Postgres; análisis de coordenadas; formateo de visualización
  static/        index.html, style.css, app.js (frontend responsivo)
data/            BD SQLite (auto) + CSVs de ejemplo
image/           Íconos de marcadores de ubicaciones de negocios
run.py           Lanzador de conveniencia (puerto 8001)
requirements.txt
```

---

## Pruebas

Ejecuta los scripts de prueba directamente:

```bash
python smoke_test.py          # flujo de API de extremo a extremo sobre una BD temporal
python auth_test.py           # login / guardia de rol / comportamiento de sesión
python workflow_test.py       # máquina de estados de revisión (avanzar, devolver, reabrir, omitir)
python api_test.py            # verificaciones a nivel de API
python postgres_mapper_test.py# mapeo de fila Postgres → registro de candidato/negocio
```

`smoke_test.py` ejercita el flujo completo: crear usuarios → crear proyecto → ingesta → recorrer
la cola de revisión a través de las tres capas (incl. omitir/devolver/reabrir) → ingesta/listado
de negocios → exportación a CSV.
