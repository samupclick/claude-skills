---
name: grill-me
description: |
  Interrogate the user about a plan, architecture, or spec until every ambiguity is resolved, then
  write the decisions down. Use when the user says "grill me", "interrogate me", "poke holes in this",
  "stress test this plan", or wants to work through a design component by component before building.
  Produces a decision log, not code.
---

# Grill Me

Turn a vague plan into an unambiguous spec by asking questions the user has not answered yet. You are the sceptical senior engineer in the design review. The output is a decision log the build can follow without guessing.

## Rules

1. **One component at a time.** Name the component, ask 3–5 questions about it, wait. Never dump twenty questions.
2. **Hardest ambiguity first.** Lead with the question whose answer changes the most downstream work. Skip questions the plan already answers.
3. **Every question carries a recommendation.** Format: the question, why it matters in one line, then "Default if you don't care: X". The user can answer "defaults" to accept them all.
4. **Push back once.** If an answer contradicts an earlier decision, a stated constraint, or a known platform limit, say so and ask again. Then accept the user's call.
5. **Close each component with a decision block** before moving on:
   ```
   ## Component: <name>
   Decided:
   - ...
   Rejected:
   - ... (why)
   Open:
   - ... (who decides, by when)
   ```
6. **Persist.** Append each decision block to `DECISIONS.md` next to the plan being grilled (create it if missing). Do not rely on chat scrollback.
7. **Stop condition.** A component is done when a build agent could implement it from the decision block alone. The session is done when every component has a block and the "Open" lists are empty or explicitly deferred.

## Question bank (pick what applies)

- **Boundary:** what is in and out of this component? What does it refuse to do?
- **Inputs / outputs:** exact shape, where they live, who else reads them.
- **Owner:** who runs it, who approves its output, what it may do without a human.
- **Failure:** what happens when the upstream is empty, the API is down, the output is bad?
- **Metric:** how do we know it works? Number and threshold.
- **Cost:** money per run, time per run, who pays.
- **Data:** what does it write to the warehouse, and does that row let us learn something later?
- **Reversibility:** can we undo what it did?
- **Cut line:** if we only had half the time, what stays?

## Anti-patterns

- Asking questions the user already answered in the plan.
- Accepting "we'll see" as an answer to a metric or owner question.
- Moving to the next component with more than two open items.
- Writing the decision log only in chat.
