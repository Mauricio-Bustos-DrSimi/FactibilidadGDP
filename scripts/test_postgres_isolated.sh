#!/usr/bin/env bash
set -euo pipefail

# Run the PostgreSQL suite against disposable factibilidad_test_* databases.
# Credentials are read inside the server and are never printed or persisted.
container_name="${POSTGRES_TEST_CONTAINER:-postgres_tinder_locales}"
admin_user="$(docker exec "$container_name" printenv POSTGRES_USER)"
admin_password="$(docker exec "$container_name" printenv POSTGRES_PASSWORD)"
export TEST_DATABASE_ADMIN_URL="postgresql+psycopg2://${admin_user}:${admin_password}@127.0.0.1:5433/postgres"

.venv/bin/python -m pytest tests -q
