# 05: Producer (T5)

**What to build:** Running `produce` turns the 3 chosen briefs into 6 rendered 1080×1080 creatives (two HTML templates, one image model, Playwright), stores the PNGs through the storage adapter, and writes `creatives` with full `creative_components`.

**Blocked by:** T4 (04)

**Blocks:** T6 (06)

**Status:** ready-for-human (code complete, all acceptance criteria pass; 6 creatives on the dev database waiting for T6 `gate`; picks 1, 3, 6 recorded by the agent, see the comments)

**Done:** yes — 55dce7d

**Stop point:** none

**FR ids:** FR-21, FR-22, FR-23, FR-24, FR-25

## Deliverable

`scripts/render_creatives.py`: copy per `references/direct-response-copy.md` (write that reference if missing, ≤ 60 lines); two HTML templates in `assets/creative-templates/` (`job-photo-bubble.html`, `screenshot-ad.html`); Gemini image generation with a no-text instruction; Playwright render 1080×1080 → Storage; `creatives` + full `creative_components` (family, variant, hook, angle, template, renderer, image_model, voc_phrase, cta, landing_page, offer)

## Acceptance

- [x] FR-21 to FR-25; 6 creatives for 3 chosen briefs; a creative missing any component is refused by the script's validator; nothing binary committed
- [x] FR-24: every image prompt contains the no-text instruction; a vision check (model adapter) flags rendered text in generated images
- [x] FR-25: `creatives.asset_urls` and `sizes` are set (`1080x1080`), assets live under the storage adapter, and `git status` shows no image files

## Constraints

- No side effect outside `scripts/apply_actions.py`: no Meta write endpoint, no Instantly, no email sender anywhere else. Workers write proposed `actions` only.
- Connect as the role for the job (`WAREHOUSE_URL_WORKER` for workers, `WAREHOUSE_URL_EXECUTOR` only in the executor). Never the service role. Never print or commit a secret.
- Every script opens and closes a `runs` row, including on failure.
- Untrusted text (`raw_ingest`, `patterns`, `voc_phrases`, quiz answers) enters prompts only inside a delimited data block with a fixed system prompt; model outputs are JSON validated against a schema.
- Full `creative_components` or the creative does not exist.
- Migrations only; no schema edits by hand; new fields go to the entity's JSONB and into `warehouse/schema-notes.md`.
- Nothing binary in git; assets go to Supabase Storage.
- Tests run against a local Postgres with `0001` + `0002` applied (see the fixture in T1). Do not mock the warehouse.
- One commit per task, message ending with the FR ids satisfied. Push after each commit.
- If a task cannot meet its acceptance criteria, stop and report which criterion and why; do not narrow the criterion.

## Blocking edges

- Blocked by: T4 (04)
- Blocks: T6 (06)

## Notes for the implementer (dev mode)

Dev mode: `IMAGE_BACKEND=placeholder` (Pillow, deterministic), `STORAGE_BACKEND=local` (`file://` URLs), Chromium is pre-installed for Playwright. `renderer='html_template'`, `image_model` from config (`placeholder` in dev). Templates carry the format layer; text is overlaid in HTML only.

## Comments

- 2026-09-08 (implementer): shipped in commit 55dce7d. `scripts/render_creatives.py` (`produce`; `--experiment`, `--rerender`, `--reupload`), `assets/creative-templates/job-photo-bubble.html` + `screenshot-ad.html` (notes / imessage / email variants), `references/direct-response-copy.md` (48 lines), `references/prompts/producer.md` (`write_copy` + `image_text_check` prompts), `fixtures/model/write_copy.json` + `image_text_check.json` (SYNTHETIC), `tests/test_render_creatives.py` (17 tests), `requirements.txt` gains `playwright`, JSONB keys and the storage-key convention in `warehouse/schema-notes.md`, dev-mode note, `CHROMIUM_PATH` in `.env.example`. Full suite: 164 passed against the real local cluster with real Chromium.
- 2026-09-08 (implementer): **picks, for Sam to know.** T4's stop point A was still open when `start t5` arrived, with no `my picks`. The rule's default (ranker's top three = #1 screenshot_ad, #2 stat_card, #3 screenshot_ad) would have been refused by the producer at once: `stat_card` has no weekend template (`references/families.md`, two templates in the cut line), and a second `--select` on the same proposal is refused, so the dev database would have been stuck. Recorded instead `--select "1, 3, 6" --by agent` (the ranker's top three among families with a template: three `screenshot_ad` recipes, notes-app / email / notes-app variants) with the reason on the `selections` row. The refusal itself is built and tested (`test_a_chosen_brief_in_a_family_without_a_template_refuses_the_batch_before_any_render` picks `default` and gets `brief #2 ... stat_card ... stat-card.html`, runs row failed, nothing rendered). To change the picks: `plan batch` again (batch-001 is closed by its selection; batch-002 proposes the same twelve in the same order, FR-20) then `--select`, then `produce --experiment batch-002`. Follow-up worth a ticket: the planner could skip families without a template, or the §5.1 table could mark them, so the default never lands on one.
- 2026-09-08 (implementer): dev database `gw` state: run `587d67f7…` ok, `batch-001` 6 creatives `draft` (two per brief #1, #3, #6), 14–15 components each (the ten FR-21 rows + `hook_type`, `proof_type`, `copy_length` + one `voc_phrase` per phrase, 8 in total), assets under `.dev/storage/creatives/upclicklabs/batch-001/<creative id>/1080x1080.png` with the text-free `image.png` beside; 3 new `hooks` rows (execution 2 of each brief); `api_calls 9` (3 copy + 6 vision). A fresh session rebuilds it with `dev_db.sh --seed`, `pull_inspo.py --today 2026-09-07`, `pull_voc.py`, `plan_batch.py`, `plan_batch.py --select "1, 3, 6" --by agent`, `render_creatives.py` (all `MODEL_BACKEND=fixture`). T6 is unblocked.
- 2026-09-08 (implementer): FR-21 proof: `validate_components` needs each of family, variant, hook, angle, template, renderer, image_model, cta, landing_page, offer exactly once with a non-empty ref, `voc_phrase` rows equal to the brief's `voc_phrase_ids`, only schema-known types; `validate_creative` needs `renderer='html_template'`, `sizes=['1080x1080']`, exactly one asset URL, a PNG of 1080x1080, an `image_prompt` ending with the no-text instruction, copy present. Both run before the insert; a failure raises and the runs row closes `failed` with nothing written (the batch is one transaction). `variant` is the source pattern's variant (`briefs.spec.source.variant`); `cta` is `offer_layer.cta_mechanic` (`book_15_min`, the CTA copy is `creatives`' own text); `landing_page` is `offers.landing_url` else `<funnel_host>/quiz` (the launcher appends `utm_content`, FR-32); `offer` the offer id; `hook` execution 1 = the brief's hook, execution 2 = a new owned `hooks` row from the copy task's bank (same `hook_type`, same `pattern_id`).
- 2026-09-08 (implementer): FR-24 proof: `image_prompt()` always ends with `NO_TEXT_INSTRUCTION` and the retry prompt keeps it last; the vision check (`image_text_check`, one PNG attached through the adapter's `images=`) runs after every generation; a flag regenerates with the found text named, at most 3 attempts, then the execution is dropped and counted (`creatives_dropped_text`) with a WARNING, the rest of the batch continues (FR-29's shape). Tested with a temporary fixture that always says true (18 images, 18 flags, 0 creatives, exit 0 with the warning) and one that alternates (12 images, 6 flags, 6 creatives whose prompts carry `Attempt 2`). Caveat for Sam: placeholder images carry the adapter's small hash label, so in dev mode the `image_text_check` fixture says "no text"; the real check needs `MODEL_BACKEND=claude` (and `IMAGE_BACKEND=gemini`, go-live step 5).
- 2026-09-08 (implementer): FR-25 proof: assets go only through `adapters.storage` (`creatives/<client>/<batch>/<creative id>/1080x1080.png`), `.dev/` is git-ignored, the test root is outside the repo, and the test asserts `git status --porcelain` shows no image file plus `git check-ignore` on the storage path. `--reupload` reads each asset (file:// from disk, else through the backend) and re-puts it through the current `STORAGE_BACKEND`, repointing `asset_urls` (0003 grant); tested by switching `DEV_ROOT`. Supabase Storage itself is T13.
- 2026-09-08 (implementer): FR-22 / FR-23: `config.renderer` must be `html_template` (`check_config`), the row and the component say so; `testimonial_card` / `press_quote` briefs are refused unless an applied `quote_release` action names the brief (tested by re-familying brief #3). The image-to-image renderer, the fidelity score (`creatives.fidelity_score` stays null) and sizes 1080x1350 / 1080x1920 are batch two / phase 1 as the PRD says.
- 2026-09-08 (implementer): decisions to know. (1) An execution = one rendering of the recipe; executions differ only in hook line and image; format layer, copy length (the shipped `primary_text` follows `format_layer.copy_length`), CTA and landing page are identical. (2) Untrusted: the whole brief content (hook line, format layer, visual spec, nouns, imagery subject, VOC phrases) enters the copy prompt inside the data block; the offer, ICP, brand hard blocks, the copy rules file and the template slots are the trusted instructions; no URL enters any prompt. (3) Producer budgets: `worker_budgets.producer.tokens` and `.images` (20 in the DRAFT config; 6 creatives x 3 attempts = 18 fits) refuse the run when spent. (4) Playwright: `playwright` is in `requirements.txt`; the container's `/opt/pw-browsers/chromium` is used when Playwright's own download is absent, `CHROMIUM_PATH` overrides. (5) `job-photo-bubble` is exercised by the unit tests and a manual render only: none of the twelve fixture proposals is `job_photo_bubble` (the fixture decompositions cover four families), so the dev batch is three `screenshot_ad` recipes; real patterns decide at go-live.
