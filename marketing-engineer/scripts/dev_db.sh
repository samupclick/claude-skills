#!/usr/bin/env bash
# scripts/dev_db.sh — local Postgres 16 for phase 0 dev mode (references/dev-mode.md). Idempotent.
#
#   scripts/dev_db.sh            start cluster, install pgvector, create db gw, apply migrations, roles LOGIN
#   scripts/dev_db.sh --verify   connect as each of the five roles from .env and print the role + families count
#   scripts/dev_db.sh --seed     load families, client, offer, icp from the DRAFT config (scripts/seed.py)
#
# Migrations: every numbered file in warehouse/ (schema.sql is 0001) is applied once, in order; the
# bookkeeping table dev_migrations exists only in the local cluster (Supabase is applied by hand, T13).
# Passwords are never printed; they are read from the WAREHOUSE_URL_* strings in .env and reach psql on
# stdin, never on a command line. Debian/Ubuntu tooling (pg_ctlcluster, apt-get); root or sudo.
set -euo pipefail

ME_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_VERSION=16
CLUSTER=main
DB=gw
ENV_FILE="$ME_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ME_DIR/.env.example" "$ENV_FILE"
  echo "dev_db: created .env from .env.example"
fi

as_postgres() {
  if [[ "$(id -un)" == "postgres" ]]; then "$@"
  elif [[ "$(id -u)" == "0" ]]; then runuser -u postgres -- "$@"
  else sudo -u postgres "$@"; fi
}
pg() { PGOPTIONS="-c client_min_messages=warning" as_postgres psql -X -q -v ON_ERROR_STOP=1 "$@"; }

url_for() {  # url_for WORKER -> value of WAREHOUSE_URL_WORKER in .env
  local v; v="$( { grep -E "^WAREHOUSE_URL_$1=" "$ENV_FILE" || true; } | tail -n1 | cut -d= -f2-)"
  [[ -n "$v" ]] || { echo "dev_db: WAREHOUSE_URL_$1 missing from .env" >&2; exit 1; }
  printf '%s' "$v"
}
password_of() {  # password_of <url> <label>; a URL without a password is an error, never a password
  [[ "$1" =~ ^[a-z]+://[^:/@]+:([^@]+)@ ]] || { echo "dev_db: WAREHOUSE_URL_$2 has no password (dev mode needs one)" >&2; exit 1; }
  printf '%s' "${BASH_REMATCH[1]}"
}
SUDO=""; [[ "$(id -u)" == "0" ]] || SUDO="sudo"

ensure_cluster() {
  if ! dpkg -s "postgresql-${PG_VERSION}-pgvector" >/dev/null 2>&1; then
    echo "dev_db: installing postgresql-${PG_VERSION}-pgvector"
    $SUDO apt-get install -y -q "postgresql-${PG_VERSION}-pgvector" >/dev/null
  fi
  local status; status="$(pg_lsclusters -h | awk -v v="$PG_VERSION" -v c="$CLUSTER" '$1==v && $2==c {print $4}')"
  case "$status" in
    online*) ;;
    "") echo "dev_db: cluster $PG_VERSION/$CLUSTER not found" >&2; exit 1 ;;
    *) echo "dev_db: starting cluster $PG_VERSION/$CLUSTER"; as_postgres pg_ctlcluster "$PG_VERSION" "$CLUSTER" start ;;
  esac
  local i
  for i in $(seq 1 30); do
    as_postgres pg_isready -q && return 0
    sleep 0.5
  done
  echo "dev_db: cluster $PG_VERSION/$CLUSTER did not become ready" >&2; exit 1
}

ensure_database() {
  if [[ "$(pg -tAc "select 1 from pg_database where datname='$DB'")" != "1" ]]; then
    echo "dev_db: creating database $DB"
    pg -c "create database $DB"
  fi
  pg -d "$DB" -c "create extension if not exists vector"
  pg -d "$DB" -c "create table if not exists dev_migrations (name text primary key, applied_at timestamptz not null default now())"
}

apply_migrations() {
  local applied=0 f name
  # schema.sql is migration 0001; later files are NNNN_<slug>.sql. Sorted by their 4-digit prefix.
  while IFS= read -r f; do
    name="$(basename "$f")"
    if [[ "$(pg -d "$DB" -tAc "select 1 from dev_migrations where name='$name'")" == "1" ]]; then continue; fi
    echo "dev_db: applying $name"
    # the file is read by this user and piped in, so the postgres OS user needs no access to the checkout
    pg -d "$DB" -1 -f - -c "insert into dev_migrations (name) values ('$name')" < "$f"
    applied=$((applied + 1))
  done < <( { echo "0001 $ME_DIR/warehouse/schema.sql"; for f in "$ME_DIR"/warehouse/[0-9][0-9][0-9][0-9]_*.sql; do [[ -e "$f" ]] && echo "$(basename "$f" | cut -c1-4) $f"; done; } | sort -k1,1 -s | cut -d' ' -f2- )
  echo "dev_db: migrations applied now: $applied"
}

ensure_logins() {
  # Each role gets LOGIN + the dev password from its URL. Skipped when the URL already connects, so a
  # second run leaves pg_authid untouched. `pg` runs as the postgres OS user over the unix socket (peer
  # auth); `psql "$url"` connects over TCP with the role's password, the way the workers do.
  local key role url changed=0
  for key in ADMIN:postgres WORKER:worker_rw EXECUTOR:executor SAM_ADMIN:sam_admin APP:app MCP_RO:mcp_ro; do
    role="${key#*:}"; url="$(url_for "${key%%:*}")"
    if psql -X -q "$url" -tAc "select 1" >/dev/null 2>&1; then continue; fi
    pw="$(password_of "$url" "${key%%:*}")"
    pg -d "$DB" -v role="$role" <<EOSQL
\set pw '${pw//\'/\'\'}'
alter role :"role" login password :'pw';
EOSQL
    changed=$((changed + 1))
  done
  echo "dev_db: roles updated now: $changed"
}

verify() {
  local key role url rc
  for key in WORKER:worker_rw EXECUTOR:executor SAM_ADMIN:sam_admin APP:app MCP_RO:mcp_ro; do
    role="${key#*:}"; url="$(url_for "${key%%:*}")"
    psql -X -q "$url" -tAc "select current_user" >/dev/null || { echo "verify: $role cannot connect"; exit 1; }
    if rc="$(psql -X -q "$url" -tAc "select current_user || ' families=' || count(*) from families" 2>/dev/null)"; then
      echo "verify: $rc"
    else
      echo "verify: $role connected; no select on families (0002 grants none to $role)"
    fi
  done
}

MODE="${1:-}"
case "$MODE" in
  "") ensure_cluster; ensure_database; apply_migrations; ensure_logins ;;
  --verify) ensure_cluster; verify ;;
  --seed) ensure_cluster; python3 "$ME_DIR/scripts/seed.py" ;;
  *) echo "usage: $0 [--verify|--seed]" >&2; exit 2 ;;
esac
