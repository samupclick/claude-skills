#!/usr/bin/env bash
# scripts/dev_db.sh — local Postgres 16 for phase 0 dev mode (references/dev-mode.md). Idempotent.
#
#   scripts/dev_db.sh            start cluster, install pgvector, create db gw, apply migrations, roles LOGIN
#   scripts/dev_db.sh --verify   connect as each of the five roles and print the role + families count; the URLs come
#                                from the environment, else .env, and may be remote (Supabase): the local cluster is
#                                started only when all five point at localhost (scripts/apply_migrations.py --verify)
#   scripts/dev_db.sh --seed     load families, client, offer, icp from the DRAFT config (scripts/seed.py)
#
# Migrations: every numbered file in warehouse/ (schema.sql is 0001) is applied once, in order; the
# bookkeeping table dev_migrations exists only in the local cluster (a remote target gets scripts/apply_migrations.py).
# Passwords are never printed; they are read from the WAREHOUSE_URL_* strings in .env and reach psql on
# stdin, never on a command line.
#
# Linux: Debian/Ubuntu tooling (pg_ctlcluster, apt-get); root or sudo.
# macOS: Homebrew postgresql@16 (`brew install postgresql@16`), run as the current user, no sudo. Homebrew's pgvector
# bottle targets Postgres 17/18 only, so pgvector is built once from Homebrew's checksummed source tarball into the
# postgresql@16 keg. The cluster's superuser is the OS user over the unix socket (local trust, like Debian's peer);
# a `postgres` superuser role is created for WAREHOUSE_URL_ADMIN, and TCP lines in pg_hba.conf move from Homebrew's
# `trust` to `scram-sha-256` so a wrong role password fails here as it does on Debian and Supabase.
set -euo pipefail

ME_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_VERSION=16
CLUSTER=main
DB=gw
ENV_FILE="$ME_DIR/.env"
OS="$(uname -s)"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ME_DIR/.env.example" "$ENV_FILE"
  echo "dev_db: created .env from .env.example"
fi

as_postgres() {
  if [[ "$OS" == "Darwin" ]]; then "$@"   # Homebrew's cluster superuser is the OS user
  elif [[ "$(id -un)" == "postgres" ]]; then "$@"
  elif [[ "$(id -u)" == "0" ]]; then runuser -u postgres -- "$@"
  else sudo -u postgres "$@"; fi
}
if [[ "$OS" == "Darwin" ]]; then
  # unix socket in /tmp (Homebrew's default), database postgres unless -d names another
  pg() { PGOPTIONS="-c client_min_messages=warning" PGDATABASE=postgres psql -X -q -h /tmp -p 5432 -v ON_ERROR_STOP=1 "$@"; }
else
  pg() { PGOPTIONS="-c client_min_messages=warning" as_postgres psql -X -q -v ON_ERROR_STOP=1 "$@"; }
fi

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

ensure_pgvector_macos() {  # build pgvector into the postgresql@16 keg when its control file is missing
  local pgc="$1" work
  [[ -f "$("$pgc" --sharedir)/extension/vector.control" ]] && return 0
  echo "dev_db: building pgvector for postgresql@${PG_VERSION} from Homebrew's source tarball"
  brew fetch --quiet --build-from-source pgvector >/dev/null
  work="$(mktemp -d)"
  tar -xzf "$(brew --cache --build-from-source pgvector)" -C "$work"
  make -C "$work"/pgvector-* PG_CONFIG="$pgc" OPTFLAGS="" >/dev/null
  make -C "$work"/pgvector-* PG_CONFIG="$pgc" install >/dev/null
  rm -rf "$work"
}

ensure_cluster_macos() {
  local brew_prefix pg_prefix data log hba i
  command -v brew >/dev/null || { echo "dev_db: macOS needs Homebrew (https://brew.sh), then: brew install postgresql@${PG_VERSION}" >&2; exit 1; }
  brew_prefix="$(brew --prefix)"
  pg_prefix="${PG_PREFIX:-$brew_prefix/opt/postgresql@$PG_VERSION}"
  data="${PGDATA_DIR:-$brew_prefix/var/postgresql@$PG_VERSION}"
  log="$brew_prefix/var/log/postgresql@$PG_VERSION.log"
  [[ -x "$pg_prefix/bin/postgres" ]] || { echo "dev_db: postgresql@${PG_VERSION} not installed; run: brew install postgresql@${PG_VERSION}" >&2; exit 1; }
  export PATH="$pg_prefix/bin:$PATH"   # keg-only: psql, pg_ctl, pg_isready are not on PATH otherwise
  ensure_pgvector_macos "$pg_prefix/bin/pg_config"
  if [[ ! -f "$data/PG_VERSION" ]]; then
    echo "dev_db: initdb $data"
    LC_ALL=en_US.UTF-8 initdb --locale=en_US.UTF-8 -E UTF-8 -D "$data" >/dev/null
  fi
  hba="$data/pg_hba.conf"
  if grep -qE '^host[[:space:]].*[[:space:]]trust[[:space:]]*$' "$hba"; then
    echo "dev_db: pg_hba.conf TCP lines trust -> scram-sha-256"
    sed -i '' -E 's/^(host[[:space:]].*[[:space:]])trust[[:space:]]*$/\1scram-sha-256/' "$hba"
    if pg_isready -q -h /tmp -p 5432; then pg_ctl -D "$data" reload >/dev/null; fi
  fi
  if ! pg_isready -q -h /tmp -p 5432; then
    echo "dev_db: starting postgresql@${PG_VERSION} (log: $log)"
    mkdir -p "$(dirname "$log")"
    LC_ALL=en_US.UTF-8 pg_ctl -D "$data" -l "$log" -w start >/dev/null
  fi
  for i in $(seq 1 30); do
    pg_isready -q -h /tmp -p 5432 && break
    sleep 0.5
  done
  pg_isready -q -h /tmp -p 5432 || { echo "dev_db: postgresql@${PG_VERSION} did not become ready" >&2; exit 1; }
  if [[ "$(pg -tAc "select 1 from pg_roles where rolname='postgres'")" != "1" ]]; then
    echo "dev_db: creating superuser role postgres"
    pg -c "create role postgres superuser login"
  fi
  # TLS like Debian's snakeoil default, so sslmode=require URLs (the Supabase shape) work against localhost
  if [[ "$(pg -tAc "show ssl")" != "on" ]]; then
    if [[ ! -f "$data/server.crt" ]]; then
      echo "dev_db: self-signed TLS certificate for the local cluster"
      openssl req -new -x509 -days 3650 -nodes -subj "/CN=localhost" \
        -keyout "$data/server.key" -out "$data/server.crt" >/dev/null 2>&1
      chmod 600 "$data/server.key"
    fi
    echo "dev_db: ssl = on"
    pg -c "alter system set ssl = on"
    pg -tAc "select pg_reload_conf()" >/dev/null
    for i in $(seq 1 20); do [[ "$(pg -tAc "show ssl")" == "on" ]] && break; sleep 0.25; done
  fi
}

ensure_cluster() {
  if [[ "$OS" == "Darwin" ]]; then ensure_cluster_macos; return; fi
  if ! dpkg -s "postgresql-${PG_VERSION}-pgvector" >/dev/null 2>&1; then
    echo "dev_db: installing postgresql-${PG_VERSION}-pgvector"
    # A fresh container can have an empty apt index; refresh it once when the package is not found.
    $SUDO apt-get install -y -q "postgresql-${PG_VERSION}-pgvector" >/dev/null 2>&1 \
      || { $SUDO apt-get update -qq >/dev/null && $SUDO apt-get install -y -q "postgresql-${PG_VERSION}-pgvector" >/dev/null; }
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

all_role_urls_local() {  # true when the five role URLs (environment first, then .env) all name localhost or a socket
  local key var url
  for key in WORKER EXECUTOR SAM_ADMIN APP MCP_RO; do
    var="WAREHOUSE_URL_$key"; url="${!var:-}"
    [[ -n "$url" ]] || url="$( { grep -E "^$var=" "$ENV_FILE" || true; } | tail -n1 | cut -d= -f2-)"
    [[ "$url" =~ ^[a-z]+://([^@/]*@)?(localhost|127\.0\.0\.1|\[::1\])?(:[0-9]+)?(/|$) ]] || return 1
  done
}

MODE="${1:-}"
case "$MODE" in
  "") ensure_cluster; ensure_database; apply_migrations; ensure_logins ;;
  --verify) if all_role_urls_local; then ensure_cluster; fi; exec python3 "$ME_DIR/scripts/apply_migrations.py" --verify ;;
  --seed) ensure_cluster; python3 "$ME_DIR/scripts/seed.py" ;;
  *) echo "usage: $0 [--verify|--seed]" >&2; exit 2 ;;
esac
