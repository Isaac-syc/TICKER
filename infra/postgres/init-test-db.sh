#!/bin/sh
# Solo desarrollo: BD desechable para las pruebas de API (se recrea el esquema en cada corrida).
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE DATABASE helpdesk_test OWNER "$POSTGRES_USER";
EOSQL
