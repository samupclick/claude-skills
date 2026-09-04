# 05: Producer (T5)

**What to build:** Running `produce` turns the 3 chosen briefs into 6 rendered 1080×1080 creatives (two HTML templates, one image model, Playwright), stores the PNGs through the storage adapter, and writes `creatives` with full `creative_components`.

**Blocked by:** T4 (04)

**Blocks:** T6 (06)

**Status:** ready-for-agent

**Done:** no

**Stop point:** none

**FR ids:** FR-21, FR-22, FR-23, FR-24, FR-25

## Deliverable

`scripts/render_creatives.py`: copy per `references/direct-response-copy.md` (write that reference if missing, ≤ 60 lines); two HTML templates in `assets/creative-templates/` (`job-photo-bubble.html`, `screenshot-ad.html`); Gemini image generation with a no-text instruction; Playwright render 1080×1080 → Storage; `creatives` + full `creative_components` (family, variant, hook, angle, template, renderer, image_model, voc_phrase, cta, landing_page, offer)

## Acceptance

- [ ] FR-21 to FR-25; 6 creatives for 3 chosen briefs; a creative missing any component is refused by the script's validator; nothing binary committed
- [ ] FR-24: every image prompt contains the no-text instruction; a vision check (model adapter) flags rendered text in generated images
- [ ] FR-25: `creatives.asset_urls` and `sizes` are set (`1080x1080`), assets live under the storage adapter, and `git status` shows no image files

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
