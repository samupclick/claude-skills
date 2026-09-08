# Dev mode — building before the Friday checklist is done

Every external dependency sits behind an adapter selected by an environment variable. Phase 0 is built and tested entirely in dev mode; going live is one variable change per service plus the real credentials. The code paths, schema, and tests are identical in both modes.

| Service | Env var | Dev value | Live value | What the fake does |
|---------|---------|-----------|------------|--------------------|
| Warehouse | `WAREHOUSE_URL_WORKER` / `_EXECUTOR` / `_ADMIN` | local Postgres (`postgresql://…@localhost:5432/gw` per role) | Supabase EU pooler strings | Nothing to fake; same schema (`0001` + `0002`) applied locally by `scripts/dev_db.sh` |
| Object storage | `STORAGE_BACKEND` | `local` (writes under `.dev/storage/`, returns `file://` URLs) | `supabase` | Same interface: `put(bytes, key) -> url`, `get(url)` |
| Meta Marketing API | `META_BACKEND` | `fake` | `live` | In-memory account: creates campaigns/ad sets/ads with ids, name lookup, `effective_status`, `ad_review_feedback`, insights that synthesise impressions/clicks from a seed, throttle header simulation, failure injection via `META_FAKE_FAIL=<step>` |
| Meta CAPI | `CAPI_BACKEND` | `fake` (logs events to `.dev/capi.jsonl`) | `live` | Records `event_id` for dedup tests |
| scrapecreators | `INSPO_BACKEND` | `fixture` (reads `fixtures/ad_library/*.json`) | `scrapecreators` | Fixture shape is an **assumption** until one real call is saved (`CRUCIBLE.md` §4); the adapter normalises whatever the real shape turns out to be |
| Public VOC threads (Reddit) | `VOC_BACKEND` | `fixture` (reads `fixtures/voc/*.json`, matched to `voc.public_sources` by URL) | `reddit` | Fixture threads are **synthetic**; the shape is ours (`url`, `title`, `comments[{id,text,score}]`, no authors) and the live backend normalises Reddit's JSON into it |
| Image generation | `IMAGE_BACKEND` | `placeholder` (Pillow: solid colour + a small hash label) | `gemini` | Deterministic bytes per prompt hash so renders are reproducible; the label is the adapter's dev marker, so the FR-24 vision check runs on the `image_text_check` fixture ("no text") in dev mode |
| Vision decomposition, copy, gate, planner reasoning | `MODEL_BACKEND` | `claude` (real; cheap) or `fixture` for CI | `claude` | Fixture mode replays recorded JSON outputs from `fixtures/model/` |
| Email (check-in) | `EMAIL_BACKEND` | `file` (writes `.dev/outbox/*.eml`) | `gmail` | Golden-file tests read the outbox |
| Calendar webhook | `CAL_WEBHOOK_SECRET` | `dev-secret` | real secret | Signature check identical; tests sign with the dev secret |
| Quiz page host | `FUNNEL_HOST` | `http://localhost:8788` | `https://go.upclicklabs.com` | Local static server + local Edge Function emulation |
| Turnstile | `TURNSTILE_BACKEND` | `pass` | `live` | Always passes; rate limits still enforced |

## Running locally (T0 dev harness)

```
pip install -r requirements.txt          # the SessionStart hook does this in remote sessions
scripts/dev_db.sh                        # start Postgres 16, pgvector, db gw, migrations, roles LOGIN; writes .env from .env.example
scripts/dev_db.sh --verify               # connect as the five roles
scripts/dev_db.sh --seed                 # families + upclicklabs client/offer/icp from the DRAFT files, as-is
python3 -m pytest                        # tests run against the local warehouse, never a mock
```

`.env` is git-ignored and holds the dev passwords inside the `WAREHOUSE_URL_*` strings. Dev backends keep
their state under `DEV_ROOT` (default `.dev/`, git-ignored): `storage/`, `meta/account.json`,
`capi.jsonl`, `outbox/*.eml`. Workers get a backend with `from adapters.meta import get_meta` (likewise
`storage`, `capi`, `inspo`, `voc`, `image`, `model`, `email`, `turnstile`); an unknown env value raises naming the
variable, a live value raises naming T13. `adapters.env.require(job, *names)` refuses to start a job whose
variables are unset and never prints a value. Fake Meta knobs: `META_FAKE_SEED`, `META_FAKE_FAIL=<step>[:after]`
(`:after` performs the step, persists it, then fails, for orphan tests), `META_FAKE_THROTTLE_AFTER=<n>`.
The model adapter takes untrusted text through `untrusted=` only and wraps it in a delimited data block; `images=`
attaches PNG/JPEG bytes for vision tasks (the fixture backend ignores them). Fixture ad library knob:
`INSPO_FIXTURE_FAIL=<brand-slug>[,…]` makes those sources fail on every attempt (FR-8 tests).

`pull inspo` in dev mode: `python3 scripts/pull_inspo.py` (add `MODEL_BACKEND=fixture` when there is no
`ANTHROPIC_API_KEY`; `fixtures/model/decompose_ad.json` is a synthetic decomposition aligned to the fixture ads).
Images land under `.dev/storage/inspo/<brand>/<ad_id>/`. `--today YYYY-MM-DD` fixes the FR-6 reference date;
`--acknowledge <source>` is Sam's `acknowledge <source>` (SKILL.md §7).

`plan batch` in dev mode: `python3 scripts/plan_batch.py` (again `MODEL_BACKEND=fixture` without a key;
`fixtures/model/translate_brief.json` holds twelve synthetic translations) after `pull inspo` and `pull voc`; it
prints the §5.1 table and stops. `--select "2, 5, 9"` records Sam's picks, `--select default` the ranker's top three.
`--daily-budget` and `--cpm` override the capacity inputs for the FR-15 check; `--today` fixes the 7-day CPM window.

`produce` in dev mode: `python3 scripts/render_creatives.py` (`MODEL_BACKEND=fixture` without a key; `fixtures/model/write_copy.json`
holds three synthetic copy outputs, `image_text_check.json` the vision check) after `my picks`; it renders two creatives per
chosen brief through `assets/creative-templates/<family>.html` (`job-photo-bubble`, `screenshot-ad`; a pick in another family
is refused naming the family) with Playwright and writes them under `.dev/storage/creatives/<client>/<batch>/<creative id>/`.
Playwright needs a Chromium: its own download, or the container's `/opt/pw-browsers/chromium` (used when the download is
absent), or `CHROMIUM_PATH=<binary>`. `--rerender` archives a brief's creatives and writes the next version; `--reupload` is
go-live step 2.

`gate` in dev mode: `python3 scripts/gate.py` (`MODEL_BACKEND=fixture`; `fixtures/model/gate_checks.json`, `gate_vision.json`,
`gate_rubric.json` are clean / shadow answers) after `produce`; it writes one agent `gate_scores` row per draft creative
(hard checks + shadow rubric), prints the §5.2 table and stops for `verdicts: approve 1,3; reject 2: reason`
(`--verdicts "…"`; `--verdicts default` ships nothing). `components`, `landing`, `verbatim` and the rule-based part of
`brand` are computed from the warehouse and the rendered HTML, so they fail for real in dev mode; the model-judged
checks (policy, likeness, coherence, fabricated testimonial) only fail with a recorded or hand-written fixture.
`--rescore` scores gated creatives again (same attempt).

## Placeholders that need Sam's replacement before go-live

| File | Status | Replace with |
|------|--------|--------------|
| `config/clients/upclicklabs.json` | **DRAFT** — offer, ICP, quiz questions, floors are my guesses | Sam's real values (30 minutes) |
| `references/families.md` | **DRAFT** — 15 families + 7 hook types + 5 angles, DTC seed list | Sam's approval; edit names freely |
| `config/clients/upclicklabs/voc-seed/*.md` | **SYNTHETIC** — invented notes with fake names, for testing anonymisation | 5–10 real vault notes copied from `/Users/Sam/Documents/ucl-brain` |
| `fixtures/ad_library/*.json` | **ASSUMED SHAPE** | one real scrapecreators response |
| `fixtures/voc/*.json` | **SYNTHETIC** — invented threads matching the placeholder URLs | nothing; set real thread URLs in `voc.public_sources` and `VOC_BACKEND=reddit` |

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
