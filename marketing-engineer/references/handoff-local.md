# Hand-off: prepare a live run of the Marketing Engineer Pipeline locally

You are on Sam's Mac, in the local clone of `samupclick/claude-skills`. Until now the pipeline was built in a cloud session that had no credentials. Sam wants to continue locally, where the API keys sit in the macOS keychain. Work through the steps in order. Stop at each **STOP** and wait for Sam.

## Where things stand (as of 2026-10-29)

- Branch `claude/sleepy-brahmagupta-jng3kp` is open as PR samupclick/claude-skills#4 against `main`, not merged. It holds:
  - the whole phase 0 loop in dev mode
  - all eight live adapters (Supabase storage, Meta Marketing API, Meta CAPI, Turnstile, scrapecreators, Reddit, Gemini image, Gmail connector), contract-tested against **assumed** vendor response shapes, never called with a real key
  - `scripts/apply_migrations.py` for Supabase, the funnel packaged for Vercel from this repo, the Monday memo, the FR-29 retry loop and the FR-37 review sync
- 497 tests pass on a Linux container with Postgres 16 + pgvector.
- Read first: `CLAUDE.md`, `marketing-engineer/SKILL.md` (§1 env vars, §3 run modes, §8 routines, §11 Friday checklist), `marketing-engineer/references/dev-mode.md` (adapter table and "Go-live swap checklist"), `marketing-engineer/CHANGELOG.md` section "Phase 0 completion - 2026-10-28" (decisions and 20 open questions for Sam), `marketing-engineer/.env.example`. Source-of-truth order: `warehouse/schema.sql` + `0002_roles.sql` → `PRD.md` → `ARCHITECTURE.md` → `CRUCIBLE.md` → `DECISIONS.md`.
- The repo's rules are binding:
  - Meta write calls only in `scripts/apply_actions.py`.
  - Workers connect as `worker_rw`, never the service role.
  - Every script opens and closes a `runs` row.
  - Untrusted text goes only inside `data_block()`.
  - Migrations only; nothing binary in git.
  - Tests use a real Postgres, never a mocked warehouse.

## Secrets rules (hard)

- Never print, echo, log, paste or commit a secret value: not in chat, output, files or commit messages.
- Read values into a process environment only. List keychain items by label/service name only, never with `-w` or `-d` output shown.
- The Meta **write** token (`META_ACCESS_TOKEN`) is loaded only for `scripts/apply_actions.py`, never for workers.
- Make no Meta writes, no ad creation and no emails without Sam's explicit approval at a stop point.

## Step 1. Local environment (macOS)

1. `git fetch origin claude/sleepy-brahmagupta-jng3kp && git checkout claude/sleepy-brahmagupta-jng3kp`
2. Python 3.13: `cd marketing-engineer && python3 -m pip install -r requirements.txt`, then `python3 -m playwright install chromium`. Leave `CHROMIUM_PATH` unset; `/opt/pw-browsers` is the cloud path.
3. **Postgres: `scripts/dev_db.sh` is Debian-only** (`apt-get`, `pg_ctlcluster`, `runuser`). Pick one, preferring the first:
   - (a) Docker: `pgvector/pgvector:pg16` on port 5432. Teach `dev_db.sh` a macOS path, or add `scripts/dev_db_docker.sh`, that applies every numbered migration in `warehouse/` once each and gives the five roles LOGIN from the `WAREHOUSE_URL_*` strings in `.env`, like `dev_db.sh` does.
   - (b) Homebrew: `postgresql@16` plus `pgvector`.
   Keep the existing Linux path working. Run the full suite: `python3 -m pytest -q -o addopts=""`. It must pass before going further.

## Step 2. Keychain → environment

1. Inventory the login keychain for the variables in `.env.example` (Anthropic, Gemini, scrapecreators, Meta ×6, Supabase, Turnstile, Reddit, Cal.com). Record which keychain item matches each variable, or "not found". **STOP** to confirm any ambiguous match with Sam.
2. Write `marketing-engineer/scripts/env_from_keychain.sh`. It holds only a `VAR=<keychain service>` mapping, so it's committable. It exports values at run time via `security find-generic-password -s ... -w` and prints only the names it loaded. `META_ACCESS_TOKEN` loads only with `--with-meta-write`. Usage: `source scripts/env_from_keychain.sh`. Values never go into `.env` or any file.

## Step 3. Fix the model adapter before any real Claude call (found 2026-10-29, not yet done)

`adapters/model/claude.py` sends no `thinking` parameter, so on Claude Opus 5 / 5.5 thinking is always on, and thinking tokens count against `max_tokens`. The callers pass small limits:
- `scripts/gate.py`: 1500, 500 and 800
- `scripts/render_creatives.py`: 512 for the image check
- `scripts/pull_voc.py`: 2048

Real calls will stop at `max_tokens`, the adapter raises `ModelOutputInvalid`, and every gate check fails. Fix it test-first:

- Treat the caller's `max_tokens` as the answer budget, and request it plus thinking headroom: about `max(caller + 12000, 16000)`, kept non-streaming at or below ~16–20k.
- Set `output_config.effort` explicitly from `MODEL_EFFORT`, default `"high"` (Opus 5.5 defaults to `medium`). Keep `output_config.format` json_schema as is.
- Change the default `MODEL_ID` to `claude-opus-5-5` in `adapters/model/__init__.py` (`get_model`) and `.env.example`. `claude-opus-5` still works but is the older model.
- Opt into server-side refusal fallback: `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`. The installed `anthropic` 2.3.0 has `fallbacks`. Keep the `stop_reason == "refusal"` check, since the fallback can refuse too. Do not send `thinking: {type: "disabled"}`, `budget_tokens`, forced `tool_choice`, `temperature`, `top_p` or `top_k`; each returns a 400.
- Add a unit test with a fake client that asserts the request kwargs and the truncation, refusal and JSON paths. Run the full suite and commit, with a message ending in the FR ids (FR-49, NFR-4).

## Step 4. Preflight: prove each key with one read-only call

Add `marketing-engineer/scripts/preflight.py`. Like `warehouse/client.py status` it is read-only and opens no `runs` row. For each backend whose variables are set, it makes one read-only call and prints `service: ok | auth failed | wrong scope | not set`. It never prints a value; scrub any key from error text. Test it with `httpx.MockTransport`, including a sentinel-secret-never-printed test.

- **Anthropic:** `GET https://api.anthropic.com/v1/models`; confirm `MODEL_ID` is listed.
- **Gemini:** `GET https://generativelanguage.googleapis.com/v1beta/models` with `x-goog-api-key`; confirm `IMAGE_MODEL` (default `gemini-nano-banana-2.1`, which is on Google's models page) is listed.
- **scrapecreators:** use a balance or credits endpoint if one exists. Otherwise skip unless `--allow-credit` is passed, in which case run one company search (about 1 credit).
- **Meta:** `GET https://graph.facebook.com/v26.0/me` per token (Bearer header), then `GET /act_<id>?fields=account_status,currency,timezone_name,spend_cap`.
- **Supabase:** `GET <SUPABASE_URL>/auth/v1/health` with `apikey`; if pooler strings exist, `scripts/dev_db.sh --verify`.
- **Turnstile:** siteverify with a dummy token. `invalid-input-response` means the secret is OK.
- **Reddit:** client-credentials token.

Write the results, names and status only, to `marketing-engineer/references/credentials-status.md`. **STOP**: show Sam the table.

## Step 5. What still blocks a live upClickLabs run (Sam's items; list them, don't do them)

These are from SKILL.md §11 and CRUCIBLE.md §4; tick whatever preflight proves:
- **Meta:** app, system user on the Advertiser role, token, ad account with spend history, spending limit set by hand; events `QuizStart`, `QuizComplete`, `Schedule`; CAPI token and test event code; Data Processing Terms; Standard Access review submitted.
- **`go.upclicklabs.com`:** on Vercel, plus a Cal.com account and booking link.
- **Supabase EU:** pgvector, `creatives` bucket, pooler strings, and a storage-writer Auth user for `apply_migrations.py --storage-writer`.
- **scrapecreators:** one real response saved to `fixtures/ad_library/real-001.json`.
- **Real config values:** `config/clients/upclicklabs.json` is still DRAFT, the voc-seed notes are synthetic, and `families.md` is approved except its DTC seed list.
- **Admin:** DPAs, and `CHECKIN_TO`.

Then follow the go-live swap in `references/dev-mode.md`.

Scheduled runs: `scripts/routines.py register --print` prints **cloud** Routine definitions. If Sam wants them local, propose `launchd` jobs with the same steps; the executor job is the only one that loads the Meta write token. Don't register anything without Sam's approval.

## Step 6. Circadian test creative: creative only, no Meta launch

Sam's rule: UpClick designs, Circadian publishes. UpClick never creates, owns or publishes on Circadian's Meta assets. Circadian's portfolio was mid-rebuild in September. The output is PNG creatives for Sam to review with Jacob Katz (Circadian / Dough Labs LLC). The run needs `ANTHROPIC_API_KEY` and `GEMINI_API_KEY`; `SCRAPECREATORS_API_KEY` is optional. Use local storage (`STORAGE_BACKEND=local`) and `META_BACKEND=fake`.

**Facts (vault-verified 2026-08-31, from branch `claude/meta-ads-syllabus-4nlkpv` and `research/circadian-meta-unlock/` on `claude/jacob-meta-facebook-unlock-8adlf1`):**
- circadianrest.com is a Shopify natural-sleep brand.
- Pillows in 6 fills from $79; duvet inserts $339–679.
- AOV $170–180, COGS plus shipping $60–70, returns 7%.
- Margin ~49–57%, break-even ROAS ~1.8–2.0, max cost per order ~$85–100.
- No Meta pixel on the site.
- Public product data: `https://circadianrest.com/products.json`.

**Brand hard blocks** (put them in the client config so `gate.py`'s brand check enforces them):
- Never name the manufacturer, White Lotus Home.
- GOTS wording only as the full label; no component claims; buckwheat is never GOTS.
- No OEKO-TEX or other certification claims until the renewal lands.
- Product facts only from Jacob's PDP Copy Master and Insider Knowledge Bank. These come from his Voice & Image Kit email to Sam: voice standard plus scoring script, PDP copy master, ~120 reference photos, and the rule "never describe a scene". Ask Sam for the kit, or search Gmail if the local session has it. **STOP** if the facts are missing; don't invent product claims.

**Pipeline gaps for a second client. Build the smallest version of each, test-first:**
1. `scripts/seed.py` hard-codes `config/clients/upclicklabs.json`. Add `--config <path>` so a second client seeds.
2. Write `config/clients/circadian.json`, marked DRAFT: offer and `offer_layer` for DTC (e.g. product page and shop CTA), ICP, floors, `daily_cap`, currency USD, brand hard blocks. Terminal metric `purchase`: `campaigns.terminal_metric` / `offers.terminal_metric` are free text with default `booked_call`, so check that nothing downstream assumes `booked_call` or a quiz. `landing_page` is the product page URL with `utm_content=creative_id`. Check `gate.py`'s `landing_check` against a non-funnel URL.
3. Templates: only `job-photo-bubble.html` and `screenshot-ad.html` exist (`assets/creative-templates/`). A bedding brand likely needs one or two more, such as a product-photo-with-caption template or `us_vs_them` / `stat_card`. **STOP**: ask Sam which.
4. **STOP**: ask Sam about imagery. Gemini-generated (FR-23: generated, no stock), Circadian's own product photos (they're the brand's, not stock, but this departs from FR-23), or both side by side?
5. Inspo: **STOP**: ask Sam for the DTC bedding seed brands for `pull_inspo.py`.
6. Run: `seed --config` → `pull_inspo.py` → `pull_voc.py` (Circadian sources) → `plan_batch.py --client circadian` → **STOP A**: Sam's picks → `render_creatives.py` → `gate.py` → **STOP B**: Sam's verdicts. Show the creatives with their gate results. Nothing goes to Meta.

## Done means

- The local suite is green.
- Keys are verified by preflight, and nothing secret was printed or committed.
- The model adapter fix is merged into the branch.
- Sam has a names-only credentials table and a short list of what still blocks the upClickLabs live run.
- A first Circadian batch is gated and waiting for Sam's verdicts, or stopped at a STOP with the question asked.

Commit per step on `claude/sleepy-brahmagupta-jng3kp` and push after each commit. Use `git pull --rebase` first; PR samupclick/claude-skills#4 tracks the branch.
