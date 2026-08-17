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
- En `Propuestos`, `gerente`, `comite` y `gerentegeneral` **aprueban** el candidato a `Aprobados` o lo
  **rechazan**. Al aprobar seleccionan Sucursal o Franquicia y se envia una notificacion con el ID
  y enlace directo a la proyeccion.
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

`viewergerente` no tiene restriccion por division o categoria de solicitante, pero solo recibe
locales de `En Estudio`, `Propuestos`, `Aprobados` y `Proyectos`.

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
| `gerente` | Ve todo; evalua Pendientes, Observacion y En Estudio, y aprueba o rechaza Propuestos. |
| `comite` | Aprueba o rechaza desde Propuestos; puede dar de baja Aprobados o Proyectos. |
| `gerentegeneral` | Mismas acciones que Comite sobre Propuestos, Aprobados y Proyectos (ademas puede omitir Propuestos). |
| `viewergerente` | Solo lectura global de divisiones en En Estudio, Propuestos, Aprobados y Proyectos; exporta Propuestos y descarga fichas listas. |
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
| `APPROVAL_NOTIFICATION_FROM` | Remitente de la notificacion de aprobacion; usa `mbustos@farmaciasdoctorsimi.cl` por defecto. |
| `APPROVAL_NOTIFICATION_TO` / `APPROVAL_NOTIFICATION_CC` | Destinatarios Para y CC de la notificacion, separados por coma o punto y coma. |
| `APPROVAL_NOTIFICATION_BASE_URL` | Base del enlace directo enviado al aprobar; por defecto `http://172.23.1.128:8002`. |
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
| `POSTGRES_CANDIDATE_SYNC_INTERVAL_SECONDS` | Intervalo de candidatos; `10` permite detectar nuevos registros casi al instante. |
| `POSTGRES_SYNC_INTERVAL_SECONDS` | Intervalo de capas comerciales; `1800` equivale a 30 minutos. |
| `POSTGRES_SYNC_PROJECT_NAME` | Nombre del proyecto utilizado por la sincronizacion. |

La seleccion de base de datos sigue este orden:

1. `DATABASE_URL`.
2. `SITE_SWIPER_DATABASE_URL`.
3. `SITE_SWIPER_DB`, que fuerza SQLite.
4. Variables `POSTGRES_*` cuando `SITE_SWIPER_USE_POSTGRES=true`.
5. `data/site_swiper.db` como respaldo local.

## Sincronizacion Postgres

El endpoint protegido `POST /admin/import-postgres` permite importar candidatos y puntos de
interes de forma controlada. Cuando `POSTGRES_AUTO_SYNC=true`, los candidatos se sincronizan
en un ciclo rapido independiente y las capas comerciales conservan un ciclo menos frecuente.

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
- La URL `/ID=<id_proyeccion>` abre directamente un candidato visible para el usuario en
  cualquiera de sus estados y prepara su pestaña actual. La URL vuelve a `/` al navegar a otra vista o local.
- Después del login se presenta un selector entre `Gestor de Proyecciones` y `Factibilidad`.
  El Gestor conserva el flujo histórico sin accesos internos al checklist.
- Los puntos de interes usan iconos de marca y muestran sus atributos en el mapa.

### Vista de tablas

- Pestañas para Pendientes, Observación, Rechazados, En Estudio, Propuestos, Aprobados y Proyectos.
- Busqueda por ID, direccion, comuna, region y solicitante.
- Filtros de fecha, orden ascendente/descendente y columnas ajustables.
- La fila correspondiente al candidato abierto en el panel queda destacada.
- Exportacion de la vista actual o de todas las vistas; `Exportar todo` consolida las pestañas en
  una sola hoja de Excel, agrupadas por estado.
- Exportacion de la sesion de Comite o Gerente General.
- El sidebar muestra la antigüedad del local: Pendientes y Observación cuentan desde `FECHA`;
  En Estudio, Propuestos y Aprobados cuentan desde la última entrada a la etapa. El indicador
  usa verde entre 0 y 2 días, amarillo entre 3 y 6, y rojo desde 7 días.
- En Propuestos, Aprobados y Proyectos, todos los roles pueden abrir una vista previa de la ficha
  progresiva y descargarla desde esa vista. En Propuestos muestra los antecedentes disponibles,
  Comuna, Región,
  MT2 y Valor de Arriendo; en Aprobados incorpora las Variables registradas; y en Proyectos exige
  `CveUnidad` y `Unidad` para generar la versión final. Comuna, Región, MT2 y Valor de Arriendo se
  precargan desde el candidato al abrir Variables. En las fichas de Propuestos y Aprobados, `MT2` y
  `ValorArriendo` priorizan las columnas homónimas de `CANDIDATE_DISPLAY_COLUMNS`; en Proyectos se
  conservan los valores registrados en Variables. La ficha identifica si corresponde a Sucursal o
  Franquicia, presenta
  horizontalmente las unidades cercanas y probabilidades por rango, adapta los datos del
  franquiciado según la división e incorpora el visto bueno de Hugo Silva. El endpoint también
  valida la visibilidad, la etapa y las variables obligatorias antes de generar el documento.

### Módulo Factibilidad

- Se abre desde el selector posterior al login como una vista independiente. No carga mapa,
  Street View, tablas, dashboard ni controles del Gestor; conserva solo un sidebar contextual.
- Cada local de `Proyectos` se expande de manera independiente y presenta tres tareas principales:
  Evaluación técnica, Permisos y normativa, y Preparación para apertura.
- El encabezado usa `ID XXX` y debajo muestra `CveUnidad, Unidad`. Al seleccionar el local, el
  sidebar presenta estos datos, la decisión y el avance de sus tres tareas principales.
- Cada tarea principal contiene cinco subtareas con estado `Realizado`, `En Proceso`,
  `No Realizado` o `No Aplica`, además de un comentario libre.
- La barra de cada tarea principal considera terminadas las subtareas `Realizado` y `No Aplica`.
- Cada local también muestra el avance total de sus 15 subtareas. Los porcentajes transitan de
  rojo intenso en 0% a verde intenso en 100%.
- Las decisiones `Rechazado` y `Completado` se guardan exclusivamente en tablas de Factibilidad.
  No actualizan `candidato_ubicacion`, `revision` ni el estado productivo del local.
- Las tablas de este módulo no tienen claves foráneas hacia las tablas productivas, para que puedan
  limpiarse posteriormente sin producir eliminaciones en cascada.

### Archivos de la proyección

- En `Propuestos`, los usuarios con visibilidad sobre el local pueden adjuntar imágenes y
  documentos PDF, Word, PowerPoint, Excel, OpenDocument, texto o CSV desde el sidebar.
- Los archivos se almacenan en `DocumentosProyeccion/ProyeccionXXX`, donde `XXX` es el ID de
  proyección. El directorio se configura con `PROJECTION_DOCUMENTS_DIR`.
- Los adjuntos continúan disponibles para consulta después de que el local cambie de estado.
  Las imágenes tienen vista previa y los documentos se pueden abrir o descargar.
- Cada adjunto puede eliminarse posteriormente y, al hacerlo, se borra del servidor. Tanto las
  cargas como las eliminaciones quedan registradas en la bitácora.
- Por defecto se aceptan hasta 12 archivos por carga y 15 MB por archivo; ambos límites pueden
  configurarse con `PROJECTION_ATTACHMENT_MAX_FILES` y `PROJECTION_ATTACHMENT_MAX_BYTES`.

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
| `GET` | `/factibilidad/locations` | Listar los locales de Proyectos con checklist y decisión de Factibilidad. |
| `PUT` | `/factibilidad/locations/{id}/tasks/{tarea}` | Guardar estado y comentario de una subtarea. |
| `PUT` | `/factibilidad/locations/{id}/decision` | Guardar Rechazado o Completado sin modificar el workflow productivo. |
| `GET` | `/candidates/by-projection/{id}` | Buscar una proyeccion visible por su ID externo, sin limitar su estado. |
| `GET` | `/candidates/by-projection/{id}/audit` | Consultar estado e historial por ID de proyeccion. |
| `GET` | `/candidates/{id}` | Obtener un candidato. |
| `POST` | `/candidates/{id}/review` | Registrar una accion de workflow. |
| `POST` | `/candidates/{id}/status` | Cambiar grupo mediante la vista de tablas. |
| `POST` | `/candidates/{id}/comment` | Guardar un comentario sin cambiar el estado. |
| `GET/POST` | `/candidates/{id}/attachments` | Consultar o adjuntar archivos de la proyección. |
| `GET/DELETE` | `/candidates/{id}/attachments/{filename}` | Abrir, descargar o eliminar un adjunto. |
| `GET` | `/candidates/{id}/project-sheet.pdf` | Generar la vista previa y descarga de la ficha PDF progresiva de un local visible en Propuestos, Aprobados o Proyectos. |
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
- `factibilidad_tarea_local`: estados y comentarios del checklist, sin clave foránea productiva.
- `factibilidad_decision_local`: resultado Rechazado o Completado del módulo, sin alterar el local.
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
