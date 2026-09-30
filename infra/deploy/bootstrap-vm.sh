#!/usr/bin/env bash
# Prepara una VM Ubuntu (Oracle Cloud Always Free, ARM o x86) para la demo. Se corre una vez:
#   curl -fsSL https://raw.githubusercontent.com/Isaac-syc/TICKER/main/infra/deploy/bootstrap-vm.sh \
#     | sudo bash -s -- tiker-isaac.duckdns.org
# Es idempotente: volver a correrlo no pisa el .env ni las contraseñas ya generadas.
# El primer despliegue lo hace GitHub Actions (workflow CD), que copia compose e infra a /opt/helpdesk.
set -euo pipefail

DOMAIN="${1:?Uso: bootstrap-vm.sh <dominio> [registry]}"
REGISTRY="${2:-ghcr.io/isaac-syc}"
APP_USER="${SUDO_USER:-ubuntu}"
APP_DIR=/opt/helpdesk

[[ $EUID -eq 0 ]] || { echo "Córrelo con sudo" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive

echo "==> Paquetes del sistema"
echo "iptables-persistent iptables-persistent/autosave_v4 boolean true" | debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v6 boolean true" | debconf-set-selections
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl openssl iptables-persistent

echo "==> Firewall de la VM (la imagen de Oracle rechaza todo salvo SSH)"
# Se guarda antes de instalar Docker para no persistir sus reglas dinámicas en rules.v4.
changed=0
for port in 80 443; do
  if ! iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null; then
    iptables -I INPUT 1 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
    changed=1
  fi
done
if [[ $changed -eq 1 ]] && ! command -v docker >/dev/null; then
  netfilter-persistent save
fi

echo "==> Docker Engine + Compose (repositorio oficial de Docker)"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck source=/dev/null
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
# Rotación de logs: en una VM pequeña los logs JSON de los contenedores no deben crecer sin límite.
if [[ ! -f /etc/docker/daemon.json ]]; then
  cat > /etc/docker/daemon.json <<'JSON'
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }
JSON
  systemctl restart docker
fi
systemctl enable --now docker
usermod -aG docker "$APP_USER"

echo "==> $APP_DIR y secretos"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
if [[ ! -f $APP_DIR/.env ]]; then
  # Cumple la política de contraseñas del dominio (≥10, mayúscula, minúscula, número, símbolo).
  demo_pw() { printf 'Demo-%s!' "$(openssl rand -hex 5)"; }
  db_pw="$(openssl rand -hex 24)"
  admin_pw="$(demo_pw)"
  user_pw="$(demo_pw)"
  observer_pw="$(demo_pw)"
  umask 077
  cat > "$APP_DIR/.env" <<EOF
# Generado por bootstrap-vm.sh el $(date -u +%F). Contiene secretos reales: no se versiona.
COMPOSE_FILE=compose.yaml:compose.prod.yaml
DOMAIN=$DOMAIN
# REGISTRY y TAG los actualiza el deploy (infra/deploy/deploy.sh).
REGISTRY=$REGISTRY
TAG=latest

APP_ENV=prod
APP_TIMEZONE=America/Mexico_City
LOG_LEVEL=INFO
LOG_JSON=true

POSTGRES_DB=helpdesk
POSTGRES_USER=helpdesk
POSTGRES_PASSWORD=$db_pw
DATABASE_URL=postgresql+asyncpg://helpdesk:$db_pw@db:5432/helpdesk
REDIS_URL=redis://redis:6379/0

JWT_SECRET=$(openssl rand -hex 48)
JWT_ISSUER=helpdesk-ti
ACCESS_TOKEN_TTL_MINUTES=15
REFRESH_TOKEN_TTL_DAYS=7
COOKIE_SECURE=true
LOGIN_MAX_ATTEMPTS=5
LOGIN_LOCK_MINUTES=15
TAB_LEASE_TTL_SECONDS=90

SLA_CRITICAL_HOURS=4
SLA_HIGH_HOURS=8
SLA_MEDIUM_HOURS=24
SLA_LOW_HOURS=72

SEED_ADMIN_EMAIL=admin@helpdesk.test
SEED_ADMIN_PASSWORD=$admin_pw
SEED_USER_EMAIL=usuario@helpdesk.test
SEED_USER_PASSWORD=$user_pw
SEED_OBSERVER_EMAIL=observador@helpdesk.test
SEED_OBSERVER_PASSWORD=$observer_pw
SEED_DEMO_DATA=true
EOF
  cat > "$APP_DIR/credenciales-demo.txt" <<EOF
https://$DOMAIN
admin       admin@helpdesk.test       $admin_pw
usuario     usuario@helpdesk.test     $user_pw
observador  observador@helpdesk.test  $observer_pw
EOF
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env" "$APP_DIR/credenciales-demo.txt"
  echo "    .env generado; credenciales demo en $APP_DIR/credenciales-demo.txt"
else
  echo "    .env ya existe: no se modifica"
fi

cat <<EOF

Listo. Siguientes pasos:
  1. Sal y vuelve a entrar por SSH para usar docker sin sudo.
  2. En GitHub: secrets STAGING_SSH_KEY / STAGING_HOST y variable STAGING_URL=https://$DOMAIN
  3. Actions → CD → Run workflow (o cualquier push a main) hace el primer despliegue.
  Credenciales demo: cat $APP_DIR/credenciales-demo.txt
EOF
