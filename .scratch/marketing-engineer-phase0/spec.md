# marketing-engineer-phase0 — spec pointer

**Source spec:** `marketing-engineer/PRD.md` §6 row "0 — Weekend": FR-1 to FR-49, DR-1 to DR-6, NFR-1 to NFR-7. Precedence when documents disagree: `warehouse/schema.sql` + `warehouse/0002_roles.sql` → `PRD.md` → `ARCHITECTURE.md` → `CRUCIBLE.md` → `DECISIONS.md`. `PLAN.md` is the schedule only.

**Goal:** close one honest loop for the `upclicklabs` client — ad live → metrics rows in the warehouse → one learning row — per `PLAN.md` §1 items 1–11. Sub-sample numbers are expected.

**Dev mode:** built before the Friday checklist per `marketing-engineer/references/dev-mode.md`. Every external service sits behind an adapter chosen by an env var; the fake backends and fixtures are part of the build. "Ad live" in dev mode means live in the fake Meta account with synthesised insights. The placeholder files (`config/clients/upclicklabs.json`, `references/families.md`, the voc-seed notes) are DRAFTS; build against them as they are and do not invent real-looking values.

**Draft breakdown:** the fourteen tickets in `issues/` (T0 dev harness, T1–T12 from the kickoff table, T13 go-live swap). Blocking edges are in each file. Stop points A (T4), B (T6), C (T9, and T13 at go-live), D (T10).

**Breakdown decisions (Sam, 2026-09-04, "approve all" with the recommended defaults):**

1. Capacity: DRAFT config set to `daily_cap` 45 and `campaign.adset_daily_budget` 15 so batch one (3 recipes × 2 = 6 creatives) fits capacity 6; the FR-15 test keeps €30/€25 → 4 with explicit inputs.
2. Grants: T1 adds `warehouse/0003_phase0_grants.sql` (column grants only) for worker updates to `creatives`, `briefs.spec`, `campaigns.active_lever*`.
3. T0 stays one ticket.
4. The quiz funnel is built under `marketing-engineer/funnel/` in dev mode; T13 moves it to `go-upclicklabs` on Vercel.
5. T0 and T13 acceptance criteria as drafted.
6. FR-7: T4 carries the "retired family cannot be briefed" guard only.
7. T11 checks routine definitions in and dry-runs the 08:00 prompt; real registration is T13.
8. Edges as drafted.

**Dependency order / frontier:** T0 → T1 → {T2, T3, T7, T8} → T4 (needs T2, T3) → T5 → T6 → T9 (needs T6, T7, T8) → T10 → T11 → T12 → T13 (blocked on Sam).
