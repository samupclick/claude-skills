# What still blocks the upClickLabs live run

Sam's items, checked on Sam's Mac on 2026-10-30 against the repo, `references/credentials-status.md` (preflight) and
DNS. Nothing here was done for you; this is the list. Full wording: `SKILL.md` §11 and `CRUCIBLE.md` §4. When every
row is ticked, run the go-live swap in `references/dev-mode.md` § "Go-live swap checklist".

New credentials go in the keychain at service `marketing-engineer`, account `<VAR>`
(`security add-generic-password -s marketing-engineer -a <VAR> -w` prompts for the value). Then rerun
`source scripts/env_from_keychain.sh && python3 scripts/preflight.py --write-status references/credentials-status.md`.

★ = blocks go-live · ◆ = takes days, start early

## Already proven

- [x] Anthropic key works and lists `claude-opus-5-5` (preflight).
- [x] Gemini key works and lists `gemini-nano-banana-2.1` (preflight). The one test generation is still to do; the
      Circadian batch (hand-off Step 6) makes one if Gemini imagery is chosen.
- [x] `references/families.md` names settled (2026-10-28). Only its DTC seed list is open (below).

## Start first: these gate other items

- [ ] ★ **`go.upclicklabs.com`**: it does **not resolve** yet (no CNAME or A record). The root `upclicklabs.com` is
      already on Vercel.
  - Deploy the funnel from this repo to a Vercel project, Root Directory `marketing-engineer`
    (`funnel/README.md` § "Deploy on Vercel").
  - Set the function region to the Supabase EU project's region. It is unset, so it defaults to US East.
  - Add the CNAME `go` → Vercel and wait for SSL to go green.
  - Create a Turnstile widget (site key and secret) and a Protection Bypass for Automation secret.
  - Meta's domain verification and the Standard Access review below both need this page live.
- [ ] ★ **Cal.com**: an account, a booking link (it replaces the placeholder `offer.calendar_url`) and the webhook
      secret `CAL_WEBHOOK_SECRET`.

## Meta

- [ ] ★ **App and tokens**:
  - a Business-type app added to the Business Manager;
  - a system user on the **Advertiser** role (not Admin) with `ads_management` and `business_management`;
  - the page, pixel and ad account assigned to it;
  - a non-expiring write token (`META_ACCESS_TOKEN`, executor only) and a separate `ads_read` token
    (`META_READ_TOKEN`) for the workers.
  - Preflight: all Meta tokens not set.
- [ ] ★ **Ad account**: a payment method, prior spend, and the **account spending limit set by hand**.
- [ ] ★ **Events**:
  - domain verified;
  - `QuizStart` and `QuizComplete` created as custom conversions, with their ids in `META_CUSTOM_CONVERSIONS`;
  - `Schedule` created;
  - CAPI token (`META_CAPI_TOKEN`) and test event code (`META_TEST_EVENT_CODE`);
  - Data Processing Terms accepted.
- [ ] ◆ **Standard Access review** for Ads Management submitted, with the `go.` page as demo URL. Until it is
      granted, Limited access throttles building a batch to minutes.

## Supabase EU (the warehouse and Storage)

- [ ] ★ Project in an **EU region** with `vector` enabled.
- [ ] ★ A session-pooler string per role, then `scripts/apply_migrations.py` (`0001`–`0008`, role passwords, Data API
      revoke).
- [ ] ★ The `creatives` bucket, and a storage-writer Auth user (sign-ups off), then
      `scripts/apply_migrations.py --storage-writer <email>`.
- [ ] Postgres MCP connected as `mcp_ro`.
- Preflight: Supabase and warehouse not set; the role strings are still the local dev cluster.

## Vendors

- [ ] ★ **scrapecreators**: an account and key (`SCRAPECREATORS_API_KEY`, not in the keychain), then save one real
      response per endpoint:
  - company ads as `fixtures/ad_library/real-001.json`;
  - search companies and company ads over `fixtures/scrapecreators/`.
  - Every fixture is an assumed shape until then.
- [ ] ★ **Reddit**: an approved app (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and a `REDDIT_USER_AGENT` naming your
      Reddit user). Without it, `pull_voc.py` falls back to Reddit's anonymous `.json`. Reports from mid-2026 say
      Reddit now answers that with 403, so don't count on the fallback.
- [ ] ★ **Gmail connector** connected on the claude.ai account that owns the routines. The check-in and memo send as
      that account.

## Real config values

- [ ] ★ `config/clients/upclicklabs.json` is still **DRAFT**. These are `PLACEHOLDER`:
  - offer `promise`, `proof_points` and `calendar_url`;
  - the three quiz questions;
  - ICP `pains` and `outcomes`;
  - `voc.vault_path` and the three `voc.public_sources`.

  Floors, trust thresholds, brakes and `disapproval_pause_threshold` are guesses.
- [ ] ★ `config/clients/upclicklabs/voc-seed/` holds 3 **synthetic** notes. Copy in 5–10 real vault notes
      (anonymised as you copy) and delete the README.
- [ ] `references/families.md`: confirm or replace the DTC seed list (marked PLACEHOLDER).

## Admin

- [ ] DPAs: Supabase, Anthropic, Google, scrapecreators, Vercel, Cloudflare.
- [ ] `CHECKIN_TO`: set to your plain address. The local `.env` still has the dev placeholder `sam@example.invalid`.

## Scheduled runs (your decision; nothing registered)

`scripts/routines.py register --print` prints the four **cloud** routines: `me-executor` 05:45 UTC, `me-morning`
06:00, `me-evening` 18:00 and `me-monday` 07:00 on Mondays. They need two claude.ai environments: the executor's
holds the Meta write token and nothing else.

If you'd rather run them on this Mac, they become `launchd` jobs with the same steps:
- The executor job is the only one that loads `--with-meta-write`. It can run `scripts/apply_actions.py --reconcile`
  directly, with no model session holding the token.
- The other three run a Claude session for the Gmail send.
- The Mac has to be awake at those times.

Nothing is registered either way until you approve each one.
