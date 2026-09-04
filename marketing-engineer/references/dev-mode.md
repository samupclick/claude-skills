# Dev mode — building before the Friday checklist is done

Every external dependency sits behind an adapter selected by an environment variable. Phase 0 is built and tested entirely in dev mode; going live is one variable change per service plus the real credentials. The code paths, schema, and tests are identical in both modes.

| Service | Env var | Dev value | Live value | What the fake does |
|---------|---------|-----------|------------|--------------------|
| Warehouse | `WAREHOUSE_URL_WORKER` / `_EXECUTOR` / `_ADMIN` | local Postgres (`postgresql://…@localhost:5432/gw` per role) | Supabase EU pooler strings | Nothing to fake; same schema (`0001` + `0002`) applied locally by `scripts/dev_db.sh` |
| Object storage | `STORAGE_BACKEND` | `local` (writes under `.dev/storage/`, returns `file://` URLs) | `supabase` | Same interface: `put(bytes, key) -> url`, `get(url)` |
| Meta Marketing API | `META_BACKEND` | `fake` | `live` | In-memory account: creates campaigns/ad sets/ads with ids, name lookup, `effective_status`, `ad_review_feedback`, insights that synthesise impressions/clicks from a seed, throttle header simulation, failure injection via `META_FAKE_FAIL=<step>` |
| Meta CAPI | `CAPI_BACKEND` | `fake` (logs events to `.dev/capi.jsonl`) | `live` | Records `event_id` for dedup tests |
| scrapecreators | `INSPO_BACKEND` | `fixture` (reads `fixtures/ad_library/*.json`) | `scrapecreators` | Fixture shape is an **assumption** until one real call is saved (`CRUCIBLE.md` §4); the adapter normalises whatever the real shape turns out to be |
| Image generation | `IMAGE_BACKEND` | `placeholder` (Pillow: solid colour + label, no text) | `gemini` | Deterministic bytes per prompt hash so renders are reproducible |
| Vision decomposition, copy, gate, planner reasoning | `MODEL_BACKEND` | `claude` (real; cheap) or `fixture` for CI | `claude` | Fixture mode replays recorded JSON outputs from `fixtures/model/` |
| Email (check-in) | `EMAIL_BACKEND` | `file` (writes `.dev/outbox/*.eml`) | `gmail` | Golden-file tests read the outbox |
| Calendar webhook | `CAL_WEBHOOK_SECRET` | `dev-secret` | real secret | Signature check identical; tests sign with the dev secret |
| Quiz page host | `FUNNEL_HOST` | `http://localhost:8788` | `https://go.upclicklabs.com` | Local static server + local Edge Function emulation |
| Turnstile | `TURNSTILE_BACKEND` | `pass` | `live` | Always passes; rate limits still enforced |

## Placeholders that need Sam's replacement before go-live

| File | Status | Replace with |
|------|--------|--------------|
| `config/clients/upclicklabs.json` | **DRAFT** — offer, ICP, quiz questions, floors are my guesses | Sam's real values (30 minutes) |
| `references/families.md` | **DRAFT** — 15 families + 7 hook types + 5 angles, DTC seed list | Sam's approval; edit names freely |
| `config/clients/upclicklabs/voc-seed/*.md` | **SYNTHETIC** — invented notes with fake names, for testing anonymisation | 5–10 real vault notes copied from `/Users/Sam/Documents/ucl-brain` |
| `fixtures/ad_library/*.json` | **ASSUMED SHAPE** | one real scrapecreators response |

## Go-live swap checklist (do after the Friday checklist)

1. Apply `0001` + `0002` on Supabase EU; set the three `WAREHOUSE_URL_*` strings; `scripts/dev_db.sh --verify` against it.
2. `STORAGE_BACKEND=supabase`; re-run `render_creatives.py --reupload` so `asset_urls` point at Storage.
3. Replace the three placeholder files above; re-run `pull_voc.py` and `plan_batch.py`.
4. Save one real scrapecreators call to `fixtures/ad_library/real-001.json`; fix the normaliser if the shape differs; `INSPO_BACKEND=scrapecreators`; re-run `pull_inspo.py`.
5. `IMAGE_BACKEND=gemini` with the key; re-render.
6. Meta: token in the executor's env only; `META_BACKEND=live`; `CAPI_BACKEND=live`; `FUNNEL_HOST=https://go.upclicklabs.com`; deploy the quiz app; `test_events.py` green.
7. `EMAIL_BACKEND=gmail`; send one check-in.
8. Only then: `launch` → stop point C → `apply actions`.

Nothing in steps 1–7 changes code. If it does, that is a bug in the adapter boundary and goes back to the ticket that owns it.
