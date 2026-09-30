#!/bin/sh
# Un solo artefacto (imagen) para varios roles: la API y el job de migraciones.
set -eu

case "${1:-api}" in
  api)
    exec uvicorn helpdesk.main:app \
      --host 0.0.0.0 --port 8000 \
      --workers "${API_WORKERS:-2}" \
      --proxy-headers --forwarded-allow-ips "*" \
      --no-access-log
    ;;
  api-dev)
    exec uvicorn helpdesk.main:app --host 0.0.0.0 --port 8000 \
      --reload --reload-dir /app/src --no-access-log
    ;;
  migrate)
    echo "==> alembic upgrade head"
    alembic upgrade head
    echo "==> seed"
    python -m helpdesk seed
    ;;
  *)
    exec "$@"
    ;;
esac
