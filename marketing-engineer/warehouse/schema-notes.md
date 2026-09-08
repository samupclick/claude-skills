# Warehouse schema notes

Migrations are the only way the schema changes (PRD DR-1, SKILL.md §4 rule 9). New fields go into
the owning entity's JSONB column and are listed here, never added as ad-hoc columns.

## Migrations (apply in order; `scripts/dev_db.sh` applies every numbered file once)

| File | Purpose |
|------|---------|
| `schema.sql` (0001) | Tables, views, marts, RLS scaffold |
| `0002_roles.sql` | Roles `worker_rw`, `executor`, `sam_admin`, `app`, `mcp_ro`; grants; `actions_guard` trigger; `check_daily_cap()`; baseline RLS policies |
| `0003_phase0_grants.sql` | Column grants only, for phase 0 workers: `worker_rw` may update `creatives (status, asset_urls, sizes, version)`, `briefs (spec)`, `campaigns (active_lever, active_lever_reason, active_lever_since)` |
| `0004_quiz_rpc.sql` | Quiz funnel RPC (T7): `quiz_start`, `quiz_complete`, `lead_booked`, `quiz_config` as SECURITY DEFINER, execute granted to `app`; the direct `insert on leads, lead_contacts` 0002 gave `app` is revoked, so `app` writes leads through the RPCs only. No new tables or columns |
| `0005_mcp_ro_leads_columns.sql` | DR-4 fix found by T7: 0002's column revoke on `leads (quiz_answers, consent, fbclid_hash)` for `mcp_ro` was a no-op under its table-level grant; replaced by a column-list grant that omits the three |
| `0006_executor_runs.sql` | Column grants only: `executor` may update `runs (status, finished_at, counts, tokens_used, api_calls, error)` so `scripts/apply_actions.py` closes its own runs row (0002 granted that to `worker_rw` only) |

## JSONB keys in use

| Column | Key | Written by | Meaning |
|--------|-----|-----------|---------|
| `clients.config` | whole file | `scripts/seed.py` | `config/clients/<slug>.json` copied as-is (`_status` marks it DRAFT) |
| `runs.counts` | `families`, `clients`, `offers`, `icps` | `scripts/seed.py` | rows inserted by the seed |
| `runs.counts` | `sources_vault`, `sources_public`, `sources_failed`, `source_retries`, `raw_ingest_inserted`, `raw_ingest_duplicates`, `phrases_extracted`, `phrases_inserted`, `phrases_duplicates`, `phrases_rejected_identifiers` | `scripts/pull_voc.py` | per-run counters of the language worker; `phrases_duplicates` is the `(source_ref, phrase_normalised)` constraint firing, `phrases_rejected_identifiers` the validator refusing a phrase that still carried an identifier |
| `raw_ingest.payload` | `kind='vault_note'`, `path`, `sha256`, `bytes` | `scripts/pull_voc.py` | a vault/seed note as a pointer and content hash only, never its text (FR-11) |
| `raw_ingest.payload` | `url`, `title`, `comments[{id, text, score}]` | `scripts/pull_voc.py` | a public thread as fetched through `adapters.voc`; no author fields exist in the shape; row has `purge_after` = fetched + 90 days |
| `runs.counts` | `<any>` | `warehouse.client.run()` | per-worker counters accumulated with `Run.count()`; each worker documents its keys in its ticket |
| `runs.counts` | `sources_ok`, `sources_failed`, `warnings` (lists) | `scripts/pull_inspo.py` | per-source outcome of one intel run (FR-8); `warnings` holds the retried-then-failed messages. Two consecutive `sources_failed` entries for one source block `plan batch` (`warehouse.client.blocked_sources`) |
| `runs.counts` | `acknowledged` (list) | `scripts/pull_inspo.py --acknowledge <source>` | Sam's acknowledgement (SKILL.md §7); clears the FR-8 block for that source |
| `runs.counts` | `ads_fetched`, `raw_ingest_new`, `raw_ingest_seen`, `images_stored`, `patterns_new`, `patterns_seen`, `patterns_promoted`, `patterns_proven`, `patterns_candidate`, `ads_skipped` | `scripts/pull_inspo.py` | intel run counters |
| `raw_ingest.payload` | `backend`, `brand`, `ad` | `scripts/pull_inspo.py` (`source='ad_library'`) | the normalised ad from the inspo adapter, `ad.raw` being the vendor row; `dedup_key = ad_library:<ad_id>:<sha256(raw)[:16]>` |
| `patterns.recipe` | `format_layer` {`family`, `visual_structure`, `copy_structure`, `copy_length`, `hook_type`} | `scripts/pull_inspo.py` | the format layer carried verbatim into replicas (ARCH §4); `family` equals `patterns.family` |
| `patterns.recipe` | `offer_layer` {} | `scripts/pull_inspo.py` (empty), planner (T4) | fixed per offer from `offers.offer_layer` |
| `patterns.recipe` | `decomposition` {`variant`, `angle`, `hook_text`, `confidence`, `backend`} | `scripts/pull_inspo.py` | the model output behind the row; `backend` is `claude` or `fixture` |
| `patterns.recipe` | `proven_by` [`days_running` \| `concurrent_variants`] | `scripts/pull_inspo.py` | which FR-6 branches held when the row was written (empty for candidates) |
| `patterns.recipe` | `source` {`backend`, `ad_id`, `brand`, `page_name`, `raw_ingest_id`, `dedup_key`, `display_format`, `is_active`, `end_date`, `images` [{`cdn_url`, `storage_url`}], `text` {`title`, `body`, `cta`}} | `scripts/pull_inspo.py` | provenance; `ad_id` is the re-run dedup key for patterns; every `storage_url` is our copy of the CDN image (FR-5); `text` is untrusted (SKILL.md §4 rule 7) |
| `leads.consent` | `tracking`, `marketing`, `verbatim_use` (bool), `notice_version`, `at` | `quiz_start()` via `funnel/app.py` | The consent the prospect gave on the notice version shown; CAPI fires only with `tracking` |
| `leads.utm` | `source`, `medium`, `campaign`, `content`, `term` | `quiz_start()` | `utm_*` from the ad URL; `content` is the `creative_id` (FR-32) and resolves `creative_id` / `ad_entity_id` |
| `leads.quiz_answers` | `<question_id>` → chosen option | `quiz_complete()` | Only option strings from `offers.quiz_config.questions[].options` (whitelisted by the funnel) |
| `offers.quiz_config` | `version`, `questions[] {id, text, options[]}`, `qualification {qid: {option: points}}`, `qualification_mode` (`hard` to enable, else soft), `qualification_threshold`, `consent_notice_version` (defaults to `version`) | `scripts/seed.py` from the client config; `funnel/` reads | FR-35: soft by default |
| `runs.counts` | `quiz_start`, `quiz_complete`, `schedule`, `forged_rejected`, `prospects` | `scripts/test_events.py` | one synthetic run of the funnel |
| `actions.proposal` | `adset_daily_budget` | loop (T10) proposes, executor (T8) applies | `scale`: the new daily budget of the target ad's ad set; the executor refuses steps over 20% (FR-31) and re-checks `check_daily_cap()` with it applied |
| `actions.proposal` | `paused`, `reason` | executor brakes (T8), `scripts/pause.py` (T11) | `set_pause_flag`: the value `clients.paused` takes when Sam applies it with `--role sam_admin` |
| `actions.proposal` | `level`, `backtest_accuracy` | Sam (chat) | `promote_trust`: `propose` or `execute`, written to `clients.config.trust.<target_id>.level` when applied as `sam_admin`; promoting `kill` to `execute` needs `backtest_accuracy >= clients.config.trust.kill.backtest_min_accuracy` (FR-46) |
| `actions.evidence` | `action_type`, `action_ids`, `errors` | executor (T8) | `set_pause_flag` proposed by the three-consecutive-failures brake: the failing type and the three rows |
| `actions.evidence` | `spend_today`, `daily_cap`, `observed_at` | executor (T8) | `set_pause_flag` proposed by the hourly-spend brake (latest `account_spend_hourly` row today above `clients.daily_cap`) |
| `clients.config` | `trust.<action_type>.level`, `.threshold` | `scripts/seed.py`, `promote_trust` applied as `sam_admin` | read by the `trust_streaks` view; the executor treats a type as autonomous only when `level='execute'`, `streak >= threshold`, and no `failed` action of that type exists since the last applied `promote_trust` (demotion is computed, never stored) |
| `clients.config` | `rate_limits.max_kills_per_day`, `.max_share_of_live_ads_killed_per_day`, `.scale_cooldown_hours` | `scripts/seed.py` | limits on autonomous rows (FR-46); a missing limit refuses the autonomous row, never a permissive default |
| `runs.counts` | `applied`, `applied_auto`, `failed`, `skipped_paused`, `skipped_trust`, `skipped_rate_limit`, `skipped_role`, `skipped_brake`, `reconciled_applied`, `reconciled_failed`, `applying_recent`, `brake_proposed` | `scripts/apply_actions.py` | executor outcomes per run; `skipped_*` rows were left exactly as found (reason on stdout) |
| `runs.counts` | `approved`, `rejected` | `scripts/decide.py` | Sam's chat decisions recorded in one invocation |
| `runs.counts` | `queries` (list of `<label>: <sql>`) | `scripts/plan_batch.py` | FR-14: every read the planner did before proposing, the two SKILL.md §4.2 queries verbatim among them |
| `runs.counts` | `capacity`, `batch_size`, `daily_budget`, `cpm`, `cpm_source` (`config` \| `observed_7d` \| `override`), `kill_impressions`, `in_flight_below_sample`, `batch_requested` (0/1), `reprinted`, `learnings_read`, `leaderboard_rows`, `voc_read`, `patterns_considered`, `patterns_skipped_retired`, `retired_families` (list), `proposals`, `proposals_short`, `briefs_written`, `briefs_refused` | `scripts/plan_batch.py` | one `plan batch` run (FR-15, FR-16, FR-17, FR-7); `batch_requested = 0` with `status='ok'` is the FR-16 threshold not met |
| `runs.counts` | `proposed`, `chosen`, `rejected`, `experiment`, `selected_by` | `scripts/plan_batch.py --select` | Sam's picks recorded (FR-17); `selected_by` is `sam` or `ranker_default` (Sam quiet 20 minutes, SKILL.md §5.1) |
| `briefs.spec` | `proposal_number`, `rank`, `format_layer` {5 keys, verbatim copy of the source `patterns.recipe.format_layer`}, `offer_layer` (from `offers.offer_layer`), `hook_line`, `product_nouns` [], `imagery_subject`, `voc_phrase_indexes` [], `coherence_note`, `translation_backend`, `source` {`brand`, `ad_id`, `source_url`, `source_image_url`, `source_strength`, `status`, `variant`, `hook_type`} | `scripts/plan_batch.py` | the translated replica brief (FR-18); `proposal_number` is the number Sam picks in the §5.1 table |
| `briefs.spec` | `chosen` (bool), `selection_id`, `selected_by`, `pick_reason` | `scripts/plan_batch.py --select` (0003 `briefs.spec` grant) | set on every brief of the proposal when the `selections` row is written; `chosen` is `null` while the proposal waits for picks |
| `runs.counts` | `experiment`, `briefs_chosen`, `briefs_skipped_existing`, `templates` (list), `creatives_written`, `creatives_archived`, `creatives_dropped_text`, `hooks_written`, `images_generated`, `image_attempts_total`, `vision_checks`, `vision_flags`, `renders` | `scripts/render_creatives.py` | one `produce` run (FR-21 to FR-25): `creatives_dropped_text` counts executions whose image still showed text after three generations (FR-24); `briefs_skipped_existing` are briefs that already had their creatives (`--rerender` archives them) |
| `runs.counts` | `creatives_reuploaded`, `assets_reuploaded` | `scripts/render_creatives.py --reupload` | go-live step 2: every asset pushed through the current `STORAGE_BACKEND`, `creatives.asset_urls` repointed (0003 grant) |
| `actions.proposal` | `icp_id` | `retire_family` proposer (T10+) | optional: scopes the retirement to one ICP; `plan_batch.py` treats an applied `retire_family` without it as retired for every ICP of the client (FR-7 guard) |

## Action target conventions (T8)

`actions.target_id` is text in the schema; the executor reads it as: `ad_entity` → `ad_entities.id`, `campaign` →
`campaigns.id`, `client` → `clients.id`, `trust` → the action type being promoted. Meta object ids are looked up
from the target row (`ad_entities.ad_id`, `ad_entities.adset_id`, `campaigns.external_id`), never carried in
the proposal. `kill` sets the Meta ad to `ARCHIVED` (final); `pause` to `PAUSED`; both mirror `ad_entities.status`
from Meta's read-back.

## Storage keys (T5)

Rendered creatives live under `creatives/<client slug>/<experiment name>/<creative id>/<size>.png` in the storage
adapter (`.dev/storage/` locally, the `creatives` bucket on Supabase); `creatives.asset_urls` holds the rendered
asset(s), `creatives.sizes` the matching sizes (`1080x1080` only in phase 0). The text-free generated image sits
beside the render as `image.png` under the same key (for the fidelity check and the image-to-image renderer of batch
two); it is not listed in `asset_urls`. `creatives.image_prompt` always ends with the producer's no-text instruction
(FR-24). `creative_components` per creative (T5): the ten FR-21 rows (`family`, `variant`, `hook`, `angle`, `template`,
`renderer`, `image_model`, `cta`, `landing_page`, `offer`), one `voc_phrase` per phrase the brief used, plus
`hook_type`, `proof_type`, `copy_length` for the leaderboard. `landing_page` is the page (`offers.landing_url`, else
`<funnel_host>/quiz`); the launcher appends `utm_content=<creative_id>` (FR-32). `cta` is `offer_layer.cta_mechanic`.
