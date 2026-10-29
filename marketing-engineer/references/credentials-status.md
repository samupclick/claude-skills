# Credentials status

Names and status only, written by `scripts/preflight.py --write-status` on 2026-10-29. Each set credential was proven
with one read-only call; no value is recorded here or anywhere in git. The keychain item behind each variable is in
`scripts/env_from_keychain.sh`.

| Service | Variables | Status | Detail |
|---------|-----------|--------|--------|
| anthropic | `ANTHROPIC_API_KEY` | ok | claude-opus-5-5 listed |
| gemini | `GEMINI_API_KEY` | ok | gemini-nano-banana-2.1 listed |
| scrapecreators | `SCRAPECREATORS_API_KEY` | not set |  |
| meta write token | `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID` | not set |  |
| meta read token | `META_READ_TOKEN`, `META_AD_ACCOUNT_ID` | not set |  |
| meta capi token | `META_CAPI_TOKEN`, `META_PIXEL_ID` | not set |  |
| supabase | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | not set |  |
| warehouse | `WAREHOUSE_URL_WORKER` | not set | no Supabase pooler strings yet: the role strings are the local dev cluster |
| turnstile | `TURNSTILE_SECRET_KEY` | not set |  |
| reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | not set |  |
| cal.com | `CAL_WEBHOOK_SECRET` | not set |  |
