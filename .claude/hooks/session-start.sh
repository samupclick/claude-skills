#!/bin/bash
# SessionStart hook (T11, PRD FR-48, CRUCIBLE A23): prepare a fresh session so the marketing-engineer
# routines (marketing-engineer/config/routines.json, SKILL.md §8) and the test suite can run at once.
#
#   1. mattpocock-skills plugin (every environment; the tracker/triage skills come from it)
#   2. Python deps from marketing-engineer/requirements.txt          (remote sessions only)
#   3. Chromium for Playwright (node `playwright` + the browser build)  (remote sessions only)
#   4. secrets: marketing-engineer/.env from .env.example when absent; report which live-backend variables the
#      host store provided and which adapter selectors pick a live backend, BY NAME ONLY — no value is ever
#      printed or written by this script
#   5. local Postgres for dev mode (remote sessions only): scripts/dev_db.sh (idempotent; it refreshes the apt
#      index itself when pgvector is missing in a fresh container), then `dev_db.sh --verify` (the five roles
#      connect), then the DRAFT seed when the client row is missing and nothing live is configured, so a live
#      container never gets a seeded stand-in warehouse to fall back on
#
#   session-start.sh --report-env    step 4's name-only report and nothing else (any environment)
#
# Synchronous: the session starts once this finishes, so nothing below races the first tool call.
# Every step reports and continues; a failed step never aborts the session. Idempotent; non-interactive.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ME="$ROOT/marketing-engineer"
LOG="${TMPDIR:-/tmp}/session-start-dev_db.log"
export DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1

say() { echo "session-start: $*"; }

# Live-backend variables (SKILL.md §1 and the live adapters) by exact name, plus every exported variable under a
# vendor prefix so one a later adapter adds is reported without editing this list. META_FAKE_* are dev knobs;
# *_BACKEND selectors have their own line.
LIVE_VARS="WAREHOUSE_URL_WORKER WAREHOUSE_URL_EXECUTOR WAREHOUSE_URL_SAM_ADMIN WAREHOUSE_URL_APP WAREHOUSE_URL_MCP_RO
  ANTHROPIC_API_KEY MODEL_ID SUPABASE_URL SUPABASE_STORAGE_BUCKET SUPABASE_PUBLISHABLE_KEY SUPABASE_STORAGE_EMAIL
  SUPABASE_STORAGE_PASSWORD SCRAPECREATORS_API_KEY REDDIT_CLIENT_ID REDDIT_CLIENT_SECRET GEMINI_API_KEY IMAGE_MODEL
  META_ACCESS_TOKEN META_READ_TOKEN META_AD_ACCOUNT_ID META_PIXEL_ID META_PAGE_ID META_CAPI_TOKEN META_TEST_EVENT_CODE
  CAL_WEBHOOK_SECRET TURNSTILE_SECRET_KEY TURNSTILE_SITE_KEY FUNNEL_HOST CHECKIN_TO EMAIL_QUEUE_DIR"
LIVE_PREFIX='^(WAREHOUSE_URL_|SUPABASE_|SCRAPECREATORS_|REDDIT_|GEMINI_|META_|CAL_|TURNSTILE_|CHECKIN_)'
# selector=its dev value (references/dev-mode.md); any other value selects a live backend
SELECTORS="STORAGE_BACKEND=local META_BACKEND=fake CAPI_BACKEND=fake INSPO_BACKEND=fixture VOC_BACKEND=fixture
  IMAGE_BACKEND=placeholder MODEL_BACKEND=fixture EMAIL_BACKEND=file TURNSTILE_BACKEND=pass"
DEV_ONLY=0

report_env() {
  local name sel dev present="" absent="" live=""
  for name in $( { printf '%s\n' $LIVE_VARS; compgen -e | grep -E "$LIVE_PREFIX" | grep -vE '^META_FAKE_|_BACKEND$'; } | sort -u); do
    if [ -n "${!name:-}" ]; then present="$present $name"; else absent="$absent $name"; fi
  done
  for sel in $SELECTORS; do
    name="${sel%%=*}"; dev="${sel#*=}"
    if [ -n "${!name:-}" ] && [ "${!name}" != "$dev" ]; then live="$live $name"; fi
  done
  say "secrets from the host store:${present:- none}"
  say "live backends selected:${live:- none}"
  say "not provided (dev defaults or unset):${absent:- none}"
  if [ -z "$present" ] && [ -z "$live" ]; then
    DEV_ONLY=1
    say "dev database: local only (no live variable in the environment)"
  fi
}

local_psql() {  # the postgres OS user over the unix socket, as dev_db.sh does; no password involved
  if [ "$(id -u)" = 0 ]; then runuser -u postgres -- psql -X -q -d gw -tAc "$1" 2>/dev/null
  else sudo -n -u postgres psql -X -q -d gw -tAc "$1" 2>/dev/null; fi
}

seed_dev_db() {
  if [ "$DEV_ONLY" != 1 ]; then
    say "seed skipped: live variables are configured, so the local database stays unseeded (a missing WAREHOUSE_URL_* fails loudly)"
  elif local_psql "select 1 from clients where slug='upclicklabs'" | grep -qx 1; then
    say "dev database already seeded (client upclicklabs)"
  elif "$ME/scripts/dev_db.sh" --seed >>"$LOG" 2>&1; then
    say "dev database seeded from the DRAFT config (scripts/dev_db.sh --seed)"
  else
    say "scripts/dev_db.sh --seed failed; see $LOG"
  fi
}

if [ "${1:-}" = "--report-env" ]; then
  report_env
  exit 0
fi

# 1. plugin
if command -v claude >/dev/null 2>&1; then
  claude plugin list 2>/dev/null | grep -q 'mattpocock-skills@claude-plugins-official' \
    || claude plugin install mattpocock-skills@claude-plugins-official >/dev/null 2>&1 \
    || say "mattpocock-skills plugin install failed; fetch skills from https://github.com/mattpocock/skills manually"
fi

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  say "not a remote session; deps, Chromium, and the dev database are left to the developer (see marketing-engineer/references/dev-mode.md)"
  exit 0
fi

# 2. python deps
if python3 -m pip install -q -r "$ME/requirements.txt" >/dev/null 2>&1; then
  say "python deps installed (marketing-engineer/requirements.txt)"
else
  say "pip install -r marketing-engineer/requirements.txt failed; run it by hand before scripts/dev_db.sh"
fi

# 3. chromium for playwright (tests/browser_quiz.mjs today; render_creatives.py from T5)
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="${PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD:-1}"
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  { echo "export PLAYWRIGHT_BROWSERS_PATH=\"$PLAYWRIGHT_BROWSERS_PATH\""; echo "export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=\"$PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD\""; } >> "$CLAUDE_ENV_FILE"
fi
NODE_ROOT="$(npm root -g 2>/dev/null || true)"
if [ -z "$NODE_ROOT" ] || [ ! -d "$NODE_ROOT/playwright" ]; then
  if npm install -g playwright >/dev/null 2>&1; then say "node playwright installed globally"; else say "npm install -g playwright failed; browser tests will be skipped"; fi
fi
if ls -d "$PLAYWRIGHT_BROWSERS_PATH"/chromium* >/dev/null 2>&1; then
  say "chromium present under $PLAYWRIGHT_BROWSERS_PATH"
elif PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0 npx --yes playwright install chromium >/dev/null 2>&1; then
  say "chromium installed under $PLAYWRIGHT_BROWSERS_PATH"
else
  say "chromium missing and the download failed; renders and browser tests will be skipped"
fi

# 4. secrets: names only, never values
if [ ! -f "$ME/.env" ] && [ -f "$ME/.env.example" ]; then
  cp "$ME/.env.example" "$ME/.env" && say "created marketing-engineer/.env from .env.example (dev defaults)"
fi
report_env

# 5. dev database (idempotent: starts the cluster, installs pgvector, applies new migrations, roles LOGIN)
if [ -x "$ME/scripts/dev_db.sh" ]; then
  if "$ME/scripts/dev_db.sh" >"$LOG" 2>&1; then
    applied="$(grep -c 'applying' "$LOG")"
    if "$ME/scripts/dev_db.sh" --verify >>"$LOG" 2>&1; then
      say "dev database ready ($applied migration(s) applied now; five roles connect)"
      seed_dev_db
    else
      say "dev database started but scripts/dev_db.sh --verify failed; see $LOG"
    fi
  else
    say "scripts/dev_db.sh failed; see $LOG and run it by hand before pytest"
  fi
fi
say "done"
exit 0
