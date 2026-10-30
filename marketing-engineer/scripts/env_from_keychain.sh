# scripts/env_from_keychain.sh — export pipeline credentials from Sam's macOS login keychain into THIS shell.
# Source it (bash or zsh); running it in a child shell would export into nothing:
#
#   source scripts/env_from_keychain.sh                          every mapped variable except the Meta write token
#   source scripts/env_from_keychain.sh ANTHROPIC_API_KEY GEMINI_API_KEY    only these (least privilege per job)
#   ( source scripts/env_from_keychain.sh --with-meta-write META_ACCESS_TOKEN META_AD_ACCOUNT_ID META_PAGE_ID \
#       META_PIXEL_ID && python3 scripts/apply_actions.py --client upclicklabs )      executor: write token in a subshell
#
# This file holds only VAR -> keychain service/account names, never a value. Values are read at run time with
# `security find-generic-password -s <service> -a <account> -w` straight into the environment; they never go into
# .env, a file, the warehouse or git, and this script prints only the variable names it loaded or could not find.
# META_ACCESS_TOKEN (the Meta write token) loads only with --with-meta-write, and only scripts/apply_actions.py may
# hold it (SKILL.md §1, §8): use the subshell form above so the rest of the shell never inherits it.
#
# Add a missing credential (the value is typed at the prompt, never on the command line):
#   security add-generic-password -s marketing-engineer -a SCRAPECREATORS_API_KEY -w
# Mapping decided with Sam 2026-10-29: Anthropic and Gemini come from the live aeo-pipeline-v3 items; every other
# variable is service `marketing-engineer`, account = the variable name. The circadian-supabase-* items are
# Circadian's project, not the Growth Warehouse, and are not mapped.
# APIFY_TOKEN (INSPO_BACKEND=apify) comes from the aeo-discovery-pipeline item: Sam chose Apify on 2026-10-31.

_me_kc_map() {
  cat <<'MAP'
ANTHROPIC_API_KEY            aeo-pipeline-v3      anthropic
GEMINI_API_KEY               aeo-pipeline-v3      gemini
APIFY_TOKEN                  aeo-discovery-pipeline apify
SCRAPECREATORS_API_KEY       marketing-engineer   SCRAPECREATORS_API_KEY
META_ACCESS_TOKEN            marketing-engineer   META_ACCESS_TOKEN
META_READ_TOKEN              marketing-engineer   META_READ_TOKEN
META_AD_ACCOUNT_ID           marketing-engineer   META_AD_ACCOUNT_ID
META_PAGE_ID                 marketing-engineer   META_PAGE_ID
META_PIXEL_ID                marketing-engineer   META_PIXEL_ID
META_CUSTOM_CONVERSIONS      marketing-engineer   META_CUSTOM_CONVERSIONS
META_CAPI_TOKEN              marketing-engineer   META_CAPI_TOKEN
META_TEST_EVENT_CODE         marketing-engineer   META_TEST_EVENT_CODE
SUPABASE_URL                 marketing-engineer   SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY     marketing-engineer   SUPABASE_PUBLISHABLE_KEY
SUPABASE_STORAGE_EMAIL       marketing-engineer   SUPABASE_STORAGE_EMAIL
SUPABASE_STORAGE_PASSWORD    marketing-engineer   SUPABASE_STORAGE_PASSWORD
TURNSTILE_SECRET_KEY         marketing-engineer   TURNSTILE_SECRET_KEY
REDDIT_CLIENT_ID             marketing-engineer   REDDIT_CLIENT_ID
REDDIT_CLIENT_SECRET         marketing-engineer   REDDIT_CLIENT_SECRET
CAL_WEBHOOK_SECRET           marketing-engineer   CAL_WEBHOOK_SECRET
MAP
}

_me_kc_main() {
  local with_write=0 want=" " arg var svc acct val loaded="" missing="" skipped="" unknown=""
  for arg in "$@"; do
    case "$arg" in
      --with-meta-write) with_write=1 ;;
      -h|--help) echo "usage: source scripts/env_from_keychain.sh [--with-meta-write] [VAR ...]"; return 0 ;;
      -*) echo "env_from_keychain: unknown option $arg" >&2; return 2 ;;
      *) _me_kc_map | grep -qE "^${arg}[[:space:]]" || unknown="$unknown $arg"; want="$want$arg " ;;
    esac
  done
  if [ -n "$unknown" ]; then
    echo "env_from_keychain: not a mapped variable:$unknown" >&2
    return 2
  fi
  while read -r var svc acct; do
    [ -n "$var" ] || continue
    if [ "$want" != " " ]; then
      case "$want" in *" $var "*) ;; *) continue ;; esac
    fi
    if [ "$var" = META_ACCESS_TOKEN ] && [ "$with_write" != 1 ]; then
      skipped="$skipped $var"
      continue
    fi
    if val="$(security find-generic-password -s "$svc" -a "$acct" -w 2>/dev/null)" && [ -n "$val" ]; then
      export "$var=$val"
      loaded="$loaded $var"
    else
      missing="$missing $var"
    fi
  done <<EOF
$(_me_kc_map)
EOF
  val=""
  echo "env_from_keychain: loaded:${loaded:- none}"
  [ -z "$missing" ] || echo "env_from_keychain: not in keychain:$missing"
  [ -z "$skipped" ] || echo "env_from_keychain: skipped (Meta write token, executor only; pass --with-meta-write):$skipped"
  return 0
}

_me_kc_sourced=0
if [ -n "${ZSH_VERSION:-}" ]; then
  case "${ZSH_EVAL_CONTEXT:-}" in *:file*) _me_kc_sourced=1 ;; esac
elif [ -n "${BASH_VERSION:-}" ]; then
  [ "${BASH_SOURCE[0]}" != "$0" ] && _me_kc_sourced=1
fi
if [ "$_me_kc_sourced" != 1 ]; then
  unset _me_kc_sourced
  echo "env_from_keychain: source this file (source scripts/env_from_keychain.sh); run as a program it exports nothing" >&2
  exit 2
fi
_me_kc_main "$@"
_me_kc_rc=$?
unset -f _me_kc_main _me_kc_map
unset _me_kc_sourced
eval "unset _me_kc_rc; return $_me_kc_rc"
