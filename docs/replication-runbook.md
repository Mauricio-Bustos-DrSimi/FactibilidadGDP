# Runbook de réplica 8002 → 8003

## Reglas previas

No pegar credenciales en comandos, Git o tickets. Configurarlas en
`/home/mbustos/FactibilidadGDP/.env` con permiso `600`. Cada base debe tener un usuario distinto:

- `DATABASE_URL`: escritura solo en la base FactibilidadGDP.
- `LEGACY_DATABASE_URL`: `SELECT` sobre la base del 8002.
- `SOURCE_DATABASE_URL`: `SELECT` sobre `dw_simi.SolicitudesProyecciones`.
- `CDC_DATABASE_URL`: LOGIN/REPLICATION limitado a captura lógica.

Los directorios, cookie, servicios y journal del 8003 son independientes del 8002.

## Preflight sin cambios

```bash
cd /home/mbustos/FactibilidadGDP
source .venv/bin/activate
python -m app.replication.cli preflight
```

El comando solo consulta versión, `wal_level`, límites, privilegios, publicaciones y slots. No
crea objetos. Antes de ejecutarlo contra una base real se debe registrar host, base y usuario.

## Migración de destino

Primero generar y revisar SQL sin ejecutarlo:

```bash
python -m app.replication.cli migrate --dry-run
```

Después de aprobar el DDL y respaldar la base destino vacía:

```bash
python -m app.replication.cli migrate
```

La revisión usa `CREATE ... IF NOT EXISTS`, `CREATE OR REPLACE VIEW` y semillas con conflicto
controlado. PostgreSQL ejecuta el upgrade en una transacción. El downgrade destructivo está
bloqueado; el rollback consiste en restaurar/eliminar exclusivamente la base nueva, nunca la del
8002.

## Snapshot

Ensayo de solo lectura:

```bash
python -m app.replication.cli snapshot --dry-run
```

Snapshot fallback reanudable:

```bash
python -m app.replication.cli snapshot
python -m app.replication.cli apply
```

Si la instalación anterior de 8003 ya contiene avance de Factibilidad, copiar únicamente esas
tablas con:

```bash
python -m app.replication.cli factibility-snapshot --dry-run
python -m app.replication.cli factibility-snapshot
```

El comando hace upsert en `factibilidad.*`; no actualiza candidatos, revisiones ni tablas del 8002.

Este snapshot sin slot corresponde al fallback de consistencia eventual. Para CDC se debe usar el
snapshot exportado por el slot autorizado y comenzar a consumir desde su LSN.

## Polling eventual

```bash
python -m app.replication.cli poll --dry-run
python -m app.replication.cli poll
python -m app.replication.cli apply
```

El servicio `factibilidad-gdp-replication.service` repite ambos pasos y registra checkpoints con
fecha, ID y hash.

## Reconciliación y replay

```bash
python -m app.replication.cli reconcile --dry-run
python -m app.replication.cli reconcile
python -m app.replication.cli replay --dry-run
python -m app.replication.cli replay
```

Los reportes no versionados quedan en `data/reconciliation`. Revisar:

```bash
curl -fsS http://127.0.0.1:8003/health
curl -fsS http://127.0.0.1:8003/health/db
curl -fsS http://127.0.0.1:8003/health/legacy
curl -fsS http://127.0.0.1:8003/health/replication
```

## Instalación systemd

Copiar las tres unidades y el timer de `deploy/` a `/etc/systemd/system/`, revisar rutas y luego:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now factibilidad-gdp.service
sudo systemctl enable --now factibilidad-gdp-replication.service
sudo systemctl enable --now factibilidad-gdp-reconcile.timer
systemctl status factibilidad-gdp.service --no-pager
systemctl status factibilidad-gdp-replication.service --no-pager
```

Esto no instala ni reinicia el servicio del puerto 8002.

## Autorización CDC requerida

Antes de crear una publicación o slot se debe registrar y aprobar:

- host, puerto, base y usuario ejecutor;
- tablas exactas incluidas y su `REPLICA IDENTITY` actual;
- DDL exacto de publicación/slot;
- consumo WAL esperado y umbral de alerta;
- respaldo verificado de la base fuente;
- rollback: detener consumidor, eliminar únicamente el slot/publicación creados y comprobar WAL;
- impacto: retención de WAL, carga de decodificación y ausencia de cambios funcionales en 8002.

No ejecutar ese DDL usando este runbook sin dicha aprobación.
