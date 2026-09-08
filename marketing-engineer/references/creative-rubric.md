# Creative rubric (gate, `scripts/gate.py`)

The taste rubric the agent scores on every creative, in **shadow mode** until promoted (PRD FR-27; DECISIONS
component 5). Facts block automatically (the hard checks below); taste is Sam's verdict. The agent's shadow
verdict is stored next to Sam's so the agreement rate can be measured; the rubric becomes blocking only when
agent verdicts agree with Sam's at the configured rate over a window of human-channel decisions (default 85%
over 40 creatives, ARCHITECTURE §7), and never in phase 0.

## Dimensions (1 = poor, 5 = excellent)

| key | question |
|-----|----------|
| `hook_strength` | Does the first line stop the scroll on its own, in the brief's hook type? |
| `clarity_3s` | In three seconds, is it clear what is offered and for whom? |
| `icp_specificity` | Does it speak to the ICP's role, company type, and situation, not to everyone? |
| `voc_language` | Is the buyer's own language present (meaning, not verbatim)? |
| `single_cta` | One ask, matching the landing page (the quiz, then the call)? |
| `mobile_legibility` | At feed size on a phone, is every word readable and the layout intact? |
| `layout_fidelity` | Does the render carry the source recipe's visual structure (format layer)? |

`avg_score` is the plain mean, two decimals. The agent's `verdict` is `approve` when no dimension is below 3
and the mean is at least 3.5, else `reject`; the reason is one line in `scores.reason`. Shadow means: written,
never acted on.

## Hard checks (facts; any `fail` blocks, `gate_scores.hard_checks`)

| key | fails when | routes to |
|-----|-----------|-----------|
| `policy` | the copy trips Meta ad policy: personal attributes ("your failing agency"), before/after or results claims, misleading or sensational claims, ALL-CAPS shouting | producer |
| `brand` | a `clients.config.brand.hard_blocks` rule is broken: pricing, income claims, client names without a release (rule-based scan plus the model's reading) | producer |
| `likeness` | the image resembles a real, identifiable person (generated people are fine) or carries logos / wordmarks | producer |
| `testimonial` | a testimonial / quote family without an applied `quote_release`, a depicted person in such a family, or a fabricated quote in the copy | producer |
| `coherence` | the translated recipe no longer makes sense with the swapped nouns ("home grown smartphones") | **planner** |
| `components` | any of the ten FR-21 components is missing, or the `voc_phrase` rows disagree with the brief | producer |
| `landing` | the `landing_page` component is not the offer's page, or the `cta` component is not the offer's CTA mechanic, or the `offer` component is another offer | producer |
| `verbatim` | an `internal` phrase without an applied `quote_release`, or any `public` / `inbound` phrase, appears verbatim (the whole phrase, or a run of eight or more of its words) in the rendered words | producer |

## Retry loop (FR-29)

A failed creative carries a feedback object in `gate_scores.feedback` (route, failures with fix guidance, what
to preserve). The producer's `--rerender` writes the next version; `creatives.version` is the attempt number.
Attempt 4 is impossible: the producer refuses to render it and the gate archives it, counted and logged.
