---
name: crucible
description: |
  Adversarial design review before a build. Three independent single-lens reviewers (economics and
  measurement, safety and money, feasibility) attack a design set; findings are consolidated into
  amendments applied to the documents and veto items the owner decides. Use when the user says
  "crucible", "put this through the crucible", "stress-test the design", or "adversarial review".
---

# Crucible

Run the design through three hostile reviewers, then fold what survives back into the documents. The output is a `CRUCIBLE.md` report next to the design set plus the amended documents, never a review that sits beside an unchanged design.

## 1. Gather the design set

Collect every document the build would be implemented from (architecture, decisions, plan, schema, data model). Note their versions. If the set is a conversation rather than files, write the design down first and review that; the crucible reviews artefacts, not intentions.

## 2. Three reviewers, one lens each, in isolation

Run each reviewer separately with only its lens, the design set, and the schema below. Use subagents when available; otherwise run them sequentially and do not let one see another's findings.

| Lens | Asks |
|------|------|
| **E — economics, statistics, attribution** | Will the numbers mean anything? Sample sizes, budgets against unit costs, benchmarks that are assumed rather than measured, attribution that cannot be computed from the stored data, cadences that never reach signal. |
| **S — safety, money, security, compliance** | What can spend money, leak data, or be forged? Side effects without a single enforced path, keys held by the wrong process, signals an outsider can fake, approvals a bot can cast, missing consent or retention rules, platform policy risk. |
| **F — feasibility, complexity, dependencies** | Does it ship in the time claimed? Hours against scope, unbuilt items on the critical path, human inputs that serialise the build, schema that cannot store what the plan says happens first, external dependencies with silent lead times. |

Each reviewer returns, in order of severity, findings with a fixed shape: `id` (E1, S1, F1 …), `severity` (blocks / degrades / cosmetic), `claim` (one sentence), `evidence` (where in the design set), `proposed change` (concrete, minimal). Each reviewer ends with a one-line verdict on whether the design meets its own goal.

## 3. Consolidate

Merge the findings into amendments. One amendment may resolve several findings; cite them. Sort every amendment into exactly one bucket:

- **Applied**: no earlier decision is reversed. Edit the documents now and record where.
- **Veto item**: the amendment reverses a decision the owner made on purpose. Do not apply. State "was", "now", and a one-line "why", numbered V1, V2 …
- **Not adopted**: the finding is wrong, out of scope, or superseded by another amendment. Keep it in the report with the reason.

Apply the amendments to the documents, bump their versions, and keep any schedule-only document consistent with the cut line. If scope was the failure, write the minimum cut line that still meets the goal.

## 4. Write `CRUCIBLE.md`

Fixed sections, in this order:

1. Header: date, method (the three lenses and what each read), counts (findings raised, amendments), the three verdicts quoted as delivered.
2. **Decisions the crucible reversed**: the veto table, marked as awaiting the owner.
3. **Amendments applied**: table of amendment, source finding ids, and where it was applied.
4. **Cut line**: the minimum that meets the goal, and what is cut entirely with a slot for each cut item.
5. **Corrected checklist**: prerequisites the owner must do before the build, blockers marked.
6. **Findings not adopted**: each with its reason.

## 5. Stop for the owner

Present the veto items only, one line each, and wait. When the owner rules, record each ruling in the report header and in the design's decision log, then apply the accepted ones. Do not start the build inside the crucible; the owner kicks that off separately.

## Rules

- Reviewers see the design, never each other; independence is what makes the findings worth reading.
- Every amendment is applied or explicitly refused. There is no "noted".
- Findings must point at a location in the design set. A finding without evidence is dropped.
- Never soften a veto item into an "applied" amendment because it is inconvenient; the owner reverses their own decisions.
