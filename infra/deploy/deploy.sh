#!/usr/bin/env bash
# Despliegue simple en una VM con Docker (fase 2 del roadmap de CD).
# La VM tiene en /opt/helpdesk: compose.yaml, infra/nginx y un .env con secretos reales.
# Variables: SSH_KEY, SSH_HOST (usuario@host), TAG, REGISTRY (opcional).
set -euo pipefail

: "${SSH_KEY:?}" "${SSH_HOST:?}" "${TAG:?}"
REGISTRY="${REGISTRY:-ghcr.io/${GITHUB_REPOSITORY_OWNER:-helpdesk}}"

key_file="$(mktemp)"
trap 'rm -f "$key_file"' EXIT
printf '%s\n' "$SSH_KEY" > "$key_file"
chmod 600 "$key_file"

ssh -i "$key_file" -o StrictHostKeyChecking=accept-new "$SSH_HOST" bash -s <<EOF
set -euo pipefail
cd /opt/helpdesk
export REGISTRY="$REGISTRY" TAG="$TAG"
docker compose pull api web
# Migraciones primero: si fallan, la versión anterior sigue sirviendo.
docker compose run --rm migrate
docker compose up -d --no-build --wait api web proxy
docker image prune -f
EOF
