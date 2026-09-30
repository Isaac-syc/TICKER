#!/usr/bin/env bash
# Operaciones sobre la VM de demo (preparada con bootstrap-vm.sh; ver docs/deploy-oracle.md).
#   deploy.sh deploy → copia compose + infra, baja la imagen TAG, migra y levanta el stack
#   deploy.sh reset  → borra los datos y vuelve a sembrar la demo (workflow nocturno)
# Variables: SSH_KEY, SSH_HOST (usuario@host), TAG (deploy), REGISTRY (opcional).
set -euo pipefail

action="${1:-deploy}"
: "${SSH_KEY:?}" "${SSH_HOST:?}"
REGISTRY="${REGISTRY:-ghcr.io/${GITHUB_REPOSITORY_OWNER:-helpdesk}}"
REGISTRY="${REGISTRY,,}" # los nombres de imagen en GHCR van en minúsculas
APP_DIR=/opt/helpdesk

key_file="$(mktemp)"
trap 'rm -f "$key_file"' EXIT
printf '%s\n' "$SSH_KEY" > "$key_file"
chmod 600 "$key_file"
remote() {
  ssh -i "$key_file" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 "$SSH_HOST" "$@"
}
# Los scripts remotos llegan por stdin (bash -s): cada comando docker lee de /dev/null para no
# consumir el resto del script (docker compose run/exec leen stdin y cortarían la ejecución).

case "$action" in
  deploy)
    : "${TAG:?}"
    # La VM no clona el repo: solo recibe lo necesario para correr el stack.
    tar -czf - compose.yaml compose.prod.yaml infra/nginx infra/caddy | remote "tar -xzf - -C $APP_DIR"
    remote bash -s <<EOF
set -euo pipefail
cd $APP_DIR
sed -i -e 's|^REGISTRY=.*|REGISTRY=$REGISTRY|' -e 's|^TAG=.*|TAG=$TAG|' .env
docker compose pull --quiet api web </dev/null
# Migraciones primero: si fallan, la versión anterior sigue sirviendo.
docker compose run --rm migrate </dev/null
docker compose up -d --no-build --wait --remove-orphans </dev/null
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile </dev/null
docker image prune -f </dev/null
EOF
    ;;
  reset)
    remote bash -s <<EOF
set -euo pipefail
cd $APP_DIR
# La API se detiene para que nadie escriba mientras se borran las tablas (~30 s sin servicio).
docker compose stop api </dev/null
docker compose run --rm migrate alembic downgrade base </dev/null
docker compose run --rm migrate </dev/null
# Sesiones, leases de pestaña y bloqueos de login viven en Redis.
docker compose exec -T redis redis-cli FLUSHALL </dev/null
docker compose up -d --no-build --wait </dev/null
EOF
    ;;
  *)
    echo "Uso: deploy.sh deploy|reset" >&2
    exit 2
    ;;
esac
