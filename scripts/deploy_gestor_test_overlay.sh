#!/usr/bin/env bash
set -euo pipefail

root_dir="${FACTIBILIDAD_ROOT:-/home/mbustos/FactibilidadGDP}"
container_name="${POSTGRES_CONTAINER:-postgres_tinder_locales}"
backup_dir="${FACTIBILIDAD_BACKUP_DIR:-/home/mbustos/backups/FactibilidadGDP}"
service_name="${FACTIBILIDAD_SERVICE:-factibilidad-gdp.service}"
cd "$root_dir"

.venv/bin/python -c '
import os
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
load_dotenv(".env")
assert make_url(os.environ["DATABASE_URL"]).database == "FactibilidadGDP"
'

mkdir -p "$backup_dir"
backup_file="$backup_dir/FactibilidadGDP_pre_gestor_overlay_$(date -u +%Y%m%dT%H%M%SZ).dump"
docker exec "$container_name" sh -c \
  'pg_dump -U "$POSTGRES_USER" -d FactibilidadGDP -Fc' > "$backup_file"
chmod 600 "$backup_file"

.venv/bin/python -m app.replication.cli migrate

env_backup="$root_dir/.env.before_gestor_overlay_$(date -u +%Y%m%dT%H%M%SZ)"
cp .env "$env_backup"
chmod 600 "$env_backup"

set_env_value() {
  local key="$1"
  local value="$2"
  local temp_file
  temp_file="$(mktemp "$root_dir/.env.update.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { found=0 }
    $0 ~ "^" key "=" { print key "=" value; found=1; next }
    { print }
    END { if (!found) print key "=" value }
  ' .env > "$temp_file"
  chmod 600 "$temp_file"
  mv "$temp_file" .env
}

set_env_value GESTOR_TEST_MODE true
set_env_value TARGET_SEARCH_PATH pruebas_gestor,factibilidad,gestor,integracion,public

main_pid="$(systemctl show "$service_name" --property MainPID --value)"
if [[ ! "$main_pid" =~ ^[1-9][0-9]*$ ]]; then
  echo "The 8003 service has no valid MainPID" >&2
  exit 1
fi
kill "$main_pid"

for _ in {1..20}; do
  new_pid="$(systemctl show "$service_name" --property MainPID --value)"
  if [[ "$new_pid" =~ ^[1-9][0-9]*$ ]] \
     && [[ "$new_pid" != "$main_pid" ]] \
     && curl --fail --silent http://127.0.0.1:8003/health >/dev/null; then
    echo "DEPLOY_OK backup=$backup_file env_backup=$env_backup"
    exit 0
  fi
  sleep 1
done

echo "The 8003 service did not become healthy" >&2
exit 1
