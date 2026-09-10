#!/bin/bash
# SessionStart hook (T11, PRD FR-48, CRUCIBLE A23): prepare a fresh session so the marketing-engineer
# routines (marketing-engineer/config/routines.json, SKILL.md §8) and the test suite can run at once.
#
#   1. mattpocock-skills plugin (every environment; the tracker/triage skills come from it)
#   2. Python deps from marketing-engineer/requirements.txt          (remote sessions only)
#   3. Chromium for Playwright (node `playwright` + the browser build)  (remote sessions only)
#   4. secrets: marketing-engineer/.env from .env.example when absent; report which live variables the
#      host store provided, BY NAME ONLY — no value is ever printed or written by this script
#   5. local Postgres for dev mode (scripts/dev_db.sh, idempotent)      (remote sessions only)
#
# Synchronous: the session starts once this finishes, so nothing below races the first tool call.
# Every step reports and continues; a failed step never aborts the session. Idempotent; non-interactive.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ME="$ROOT/marketing-engineer"
export DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1

say() { echo "session-start: $*"; }

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
present=""; absent=""
for name in ANTHROPIC_API_KEY GEMINI_API_KEY SCRAPECREATORS_API_KEY SUPABASE_URL META_ACCESS_TOKEN META_CAPI_TOKEN CAL_WEBHOOK_SECRET CHECKIN_TO; do
  if [ -n "${!name:-}" ]; then present="$present $name"; else absent="$absent $name"; fi
done
say "secrets from the host store:${present:- none}"
say "not provided (dev defaults or unset):${absent:- none}"

# 5. dev database (idempotent: starts the cluster, applies new migrations, roles LOGIN)
if [ -x "$ME/scripts/dev_db.sh" ]; then
  if "$ME/scripts/dev_db.sh" >/tmp/session-start-dev_db.log 2>&1; then
    say "dev database ready ($(grep -c 'applying' /tmp/session-start-dev_db.log) migration(s) applied now)"
  else
    say "scripts/dev_db.sh failed; see /tmp/session-start-dev_db.log and run it by hand before pytest"
  fi
fi
say "done"
exit 0
