# Gestor de Proyecciones

Aplicacion web para revisar candidatos de nuevas ubicaciones sobre Google Maps, gestionar su
avance entre estados y conservar una bitacora completa de las decisiones. La interfaz incluye
aprobación tipo red social de citas, vista de tablas, puntos de interes, filtros, exportacion a Excel, variables de
proyecto, envio de correo y administracion de usuarios.

La aplicacion usa FastAPI, SQLAlchemy y JavaScript sin framework. Puede trabajar con PostgreSQL
como base principal o con SQLite para desarrollo y pruebas.

## Flujo de candidatos

Los candidatos se sincronizan desde `SolicitudesProyecciones` y nacen en `Pendientes`. Las
acciones posteriores los distribuyen en las vistas operativas:

```text
Pendientes --proponer--> Propuestos --aprobar--> Aprobados --proyecto--> Proyectos
     |                           |                    |
     +-------- rechazar ---------+-------- dar de baja+--> Rechazados

Pendientes/Observacion --estudiar--> En Estudio --proponer--> Propuestos
                                            +------rechazar--> Rechazados
```

En cada estado actua un conjunto distinto de roles:

- En `Pendientes`, los roles tipo Jefatura (`jefatura`, `jefecomercial`, `coordinador`) registran
  **like/dislike** como metrica —no cambian el estado del candidato— y pueden omitir; `arriendo` y
  `gerente` **proponen** el candidato a `Propuestos` o lo **rechazan**.
- En `Propuestos`, `comite` y `gerentegeneral` **aprueban** el candidato a `Aprobados` o lo
  **rechazan**.
- En `Aprobados`, `coordinador` completa las Variables del local y lo envia a **Proyecto**
  (`Proyectos`), estado final.
- `comite` y `gerentegeneral` pueden **dar de baja** (rechazar) candidatos que ya estan en
  `Aprobados` o `Proyectos`.
- `arriendo` y `gerente` pueden enviar candidatos de `Pendientes` u `Observacion` a
  `En Estudio`; desde ahi pueden resolverlos hacia `Propuestos` o `Rechazados`.
- `arriendo` y `gerente` pueden **reproponer** a `Propuestos` los candidatos que quedaron en
  `Rechazados` u `Observacion`; desde `Rechazados` tambien pueden devolverlos a `Pendientes`
  o enviarlos a `En Estudio`.

El flujo conserva en base de datos:

- estado y etapa actuales;
- usuario, rol, accion, comentario, fecha y hora de cada movimiento;
- fechas de sugerencia, aprobacion, rechazo, omision, reapertura y proyecto;
- comentarios obligatorios para rechazos y dislikes;
- comentarios independientes, sin cambio de estado, guardados con fecha y hora;
- variables comerciales y datos de contacto asociados al candidato.

`revision` es una bitacora de solo anexado: las acciones nuevas agregan registros y no borran el
historial anterior.

## Roles y visibilidad

**Visibilidad.** `arriendo`, `gerente`, `comite`, `gerentegeneral` y `sysadmin` ven **todos** los
candidatos. Los roles tipo Jefatura estan acotados:

- `jefatura`: por su grupo comercial. `SUCURSAL` o `FRANQUICIA` limitan a los candidatos de esa
  division de origen; `APERTURA` (o la cuenta `jef@local`) ve todos; sin grupo valido solo ve los
  candidatos cuya proyeccion fue solicitada por su propio correo.
- `jefecomercial`: ve los candidatos propios y los de sus correos supervisados, dentro de su
  division (`SUCURSAL` o `FRANQUICIA`); para `Propuestos`/`Aprobados`/`Proyectos` se usa la
  division elegida por el aprobador.
- `coordinador`: ve los candidatos de su division (`SUCURSAL` o `FRANQUICIA`).

Pedir un candidato fuera del alcance del usuario devuelve `403`.

**Acciones por rol.**

| Rol | Visibilidad y acciones principales |
|---|---|
| `jefatura` | Ve segun `SUCURSAL`, `FRANQUICIA` o `APERTURA` (o todo si es `jef@local`); registra like, dislike y omitir en Pendientes. |
| `jefecomercial` | Como Jefatura, acotado a su division y a sus correos supervisados; no puede votar por sus propios locales. |
| `coordinador` | Como Jefatura en su division; no vota sus propios locales; edita las Variables en Aprobados y los envia a Proyecto. |
| `arriendo` | Ve todo; gestiona Pendientes y Observacion hacia En Estudio, Propuestos o Rechazados, y resuelve En Estudio. |
| `gerente` | Ve todo; mismas acciones de evaluacion que Arriendo en Pendientes, Observacion y En Estudio. |
| `comite` | Aprueba o rechaza desde Propuestos; puede dar de baja Aprobados o Proyectos. |
| `gerentegeneral` | Mismas acciones que Comite sobre Propuestos, Aprobados y Proyectos (ademas puede omitir Propuestos). |
| `sysadmin` | Acceso global, gestion de usuarios, importacion, estadisticas y acciones administrativas (incluye devolver/reabrir). |

Los usuarios se crean desde el menu de administracion. El rol, cargo, division, correos de
supervisores y posicion en el organigrama forman parte del perfil; `jefatura`, `jefecomercial` y
`coordinador` requieren una division al crearse. `sysadmin` puede crear, editar, desactivar o
eliminar usuarios que no tengan historial asociado.

## Inicio rapido

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

La configuracion real se carga desde `.env`. `.env.example` es solo una plantilla y no debe
contener contrasenas, tokens ni claves reales.

Por defecto `run.py` escucha en `0.0.0.0:8002`. En el equipo local se abre:

```text
http://127.0.0.1:8002
```

Endpoints de diagnostico:

- `GET /health`: confirma que FastAPI esta activo.
- `GET /health/db`: comprueba la conexion a la base de datos.
- `GET /docs`: documentacion interactiva de la API.

## Configuracion

Variables principales:

| Variable | Proposito |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Clave de Google Maps JavaScript API. Sin ella la aplicacion funciona, pero el mapa no se renderiza. |
| `SESSION_SECRET` | Firma las cookies de sesion. Debe ser estable y secreta. |
| `SYSADMIN_EMAIL` / `SYSADMIN_PASSWORD` | Credenciales iniciales del sysadmin creado en una instalacion nueva. |
| `APP_HOST` / `APP_PORT` | Host y puerto de Uvicorn; valores usuales `0.0.0.0` y `8002`. |
| `DATABASE_URL` | URL completa de base de datos; tiene la mayor prioridad. |
| `SITE_SWIPER_DATABASE_URL` | URL compatible con instalaciones anteriores. |
| `SITE_SWIPER_USE_POSTGRES` | Activa PostgreSQL usando variables `POSTGRES_*`. |
| `SITE_SWIPER_DB` | Fuerza un archivo SQLite, especialmente util para pruebas. |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Servidor y puerto de PostgreSQL. |
| `POSTGRES_DB` | Nombre de la base PostgreSQL. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | Credenciales de PostgreSQL; deben existir solo en `.env` o en el entorno del servidor. |
| `POSTGRES_CONNECT_TIMEOUT` | Tiempo maximo de conexion a PostgreSQL. |
| `PG_SCHEMA` | Esquema de las tablas fuente. |
| `CAND_TABLE` | Tabla de candidatos, normalmente `SolicitudesProyecciones`. |
| `BUS_TABLES` | Tablas de puntos de interes separadas por coma. |
| `CANDIDATE_MIN_ID` | ID minimo que se importa o sincroniza; vacio desactiva el filtro. |
| `CANDIDATE_INCLUDE_IDS` | IDs adicionales que se importan aunque sean menores al minimo, separados por coma. |
| `POSTGRES_AUTO_SYNC` | Activa la sincronizacion automatica. |
| `POSTGRES_SYNC_INTERVAL_SECONDS` | Intervalo del sincronizador; `1800` equivale a 30 minutos. |
| `POSTGRES_SYNC_PROJECT_NAME` | Nombre del proyecto utilizado por la sincronizacion. |

La seleccion de base de datos sigue este orden:

1. `DATABASE_URL`.
2. `SITE_SWIPER_DATABASE_URL`.
3. `SITE_SWIPER_DB`, que fuerza SQLite.
4. Variables `POSTGRES_*` cuando `SITE_SWIPER_USE_POSTGRES=true`.
5. `data/site_swiper.db` como respaldo local.

## Sincronizacion Postgres

El endpoint protegido `POST /admin/import-postgres` permite importar candidatos y puntos de
interes de forma controlada. Tambien existe sincronizacion automatica al iniciar sesion y cada
intervalo configurado cuando `POSTGRES_AUTO_SYNC=true`.

La sincronizacion usa el ID de `SolicitudesProyecciones` como identificador estable. Los datos
descriptivos provenientes de Postgres se actualizan, mientras que el workflow local conserva
estados, comentarios, fechas, variables e historial de revisiones.

Fuentes de puntos de interes soportadas:

- `PI_CruzVerde`;
- `PI_Ahumada`;
- `PI_Salcobrand`;
- `PI_Maicao`;
- `PI_EstacionesMetro`;
- `LocalesSimi`.

Tambien se mantiene la ingesta manual por CSV/XLSX para candidatos y puntos de interes. El lector
admite delimitadores comunes, codificaciones UTF-8/cp1252/Latin-1, coordenadas separadas y comas
decimales.

## Uso de la interfaz

### Vista de mapa

- Muestra el candidato actual, Score, proyeccion y sus datos relevantes.
- Permite like, dislike, proponer, aprobar, rechazar u omitir segun el rol.
- Los rechazos y dislikes exigen comentario.
- La cola se ordena por Score descendente de forma predeterminada y puede recorrerse sin volver
  inmediatamente a candidatos omitidos.
- La URL `/ID=<id_proyeccion>` abre directamente un candidato pendiente visible para el usuario.
- Los puntos de interes usan iconos de marca y muestran sus atributos en el mapa.

### Vista de tablas

- Pestañas para Pendientes, Observación, Rechazados, En Estudio, Propuestos, Aprobados y Proyectos.
- Busqueda por ID, direccion, comuna, region y solicitante.
- Filtros de fecha, orden ascendente/descendente y columnas ajustables.
- La fila correspondiente al candidato abierto en el panel queda destacada.
- Exportacion de la vista actual o de todas las vistas en hojas separadas de Excel.
- Exportacion de la sesion de Comite o Gerente General.

### Variables de proyecto

Solo Coordinador puede editar las Variables de los candidatos en Aprobados: CveUnidad, Unidad, region, provincia, comuna, metros
cuadrados, arriendo, gastos comunes, condiciones contractuales, tipo de proyecto, fechas y datos
de contacto. Los cambios y correos enviados tambien quedan registrados en la bitacora.

## API principal

Todos los endpoints operativos requieren sesion, salvo la pagina principal, configuracion y login.
Las rutas administrativas requieren `sysadmin`.

| Metodo | Ruta | Proposito |
|---|---|---|
| `POST` | `/auth/login` | Iniciar sesion y ejecutar sincronizacion en segundo plano si esta activa. |
| `POST` | `/auth/logout` | Cerrar sesion. |
| `GET` | `/me` | Obtener el usuario actual. |
| `GET` | `/queue` | Obtener el candidato actual y el total de la cola del rol. |
| `GET` | `/candidates` | Listar candidatos visibles para el usuario. |
| `GET` | `/candidates/by-projection/{id}` | Buscar una proyeccion pendiente por su ID externo. |
| `GET` | `/candidates/by-projection/{id}/audit` | Consultar estado e historial por ID de proyeccion. |
| `GET` | `/candidates/{id}` | Obtener un candidato. |
| `POST` | `/candidates/{id}/review` | Registrar una accion de workflow. |
| `POST` | `/candidates/{id}/status` | Cambiar grupo mediante la vista de tablas. |
| `POST` | `/candidates/{id}/comment` | Guardar un comentario sin cambiar el estado. |
| `GET` | `/candidates/{id}/reviews` | Consultar la bitacora completa. |
| `GET/PUT` | `/candidates/{id}/project-variables` | Consultar o guardar variables del proyecto. |
| `POST` | `/candidates/{id}/project-variables/email` | Guardar variables y enviar el correo del proyecto. |
| `GET` | `/candidates/export.xlsx` | Exportar una vista o todas las vistas. |
| `GET` | `/candidates/export-session.xlsx` | Exportar la sesion de Comite o Gerente General. |
| `GET/POST` | `/users` | Listar o crear usuarios. |
| `PUT/DELETE` | `/users/{id}` | Editar o eliminar usuarios. |
| `GET` | `/business` | Listar puntos de interes. |
| `POST` | `/business/ingest` | Cargar puntos de interes desde archivo. |
| `POST` | `/admin/import-postgres` | Sincronizar candidatos y puntos de interes desde Postgres. |
| `GET` | `/stats` | Obtener conteos del workflow. |

## Modelo de datos

Tablas administradas por la aplicacion:

- `usuario`: identidad, rol, division, cargo, supervisores y posicion del organigrama.
- `proyecto`: agrupacion de candidatos y metadatos de origen.
- `candidato_ubicacion`: coordenadas, datos de visualizacion y estado resumido del workflow.
- `revision`: bitacora inmutable de acciones con usuario, etapa, comentario y fecha UTC.
- `variables_proyecto_candidato`: informacion comercial y contractual del local.
- `punto_interes`: capa global de farmacias, estaciones y Locales Simi.

Los nombres fisicos de tablas y columnas de la aplicacion estan en español. Los timestamps se
guardan en UTC y se presentan en la zona horaria de Santiago.

## Estructura

```text
app/
  auth.py          Autenticacion, hashing y guardias de rol
  database.py      Seleccion de motor, sesiones y compatibilidad de esquema
  ingestion.py     Lectura de archivos y mapeo desde Postgres
  main.py          API FastAPI, sincronizacion, exportaciones y correo
  models.py        Modelos SQLAlchemy
  schemas.py       Contratos Pydantic
  workflow.py      Reglas de estados, acciones y colas
  static/          Interfaz web
image/             Iconos de marcadores y recursos de marca
scripts/           Migracion, backfill y reinicio controlado
data/              SQLite y archivos de prueba local
run.py             Arranque de Uvicorn
```

## Pruebas

```powershell
.venv\Scripts\python.exe -m py_compile app\*.py
.venv\Scripts\python.exe auth_test.py
.venv\Scripts\python.exe workflow_test.py
.venv\Scripts\python.exe postgres_mapper_test.py
.venv\Scripts\python.exe smoke_test.py
```

Las pruebas usan una base temporal cuando corresponde. Para evitar conexiones externas en pruebas
aisladas se puede definir `POSTGRES_AUTO_SYNC=false` y `SITE_SWIPER_USE_POSTGRES=false`.

## Despliegue en red local

En el servidor, `APP_HOST=0.0.0.0` permite que Uvicorn reciba conexiones de la red. El nombre
`https://gestordeproyecctiones` debe resolverse por DNS interno o por el archivo `hosts`, y un
proxy inverso como Nginx o Caddy debe terminar HTTPS y reenviar al puerto interno de FastAPI.

No se deben versionar `.env`, bases locales, logs, certificados ni respaldos con informacion real.
