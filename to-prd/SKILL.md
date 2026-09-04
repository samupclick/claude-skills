---
name: to-prd
description: |
  Turn an architecture, decision log, or design conversation into a build-ready Product Requirements
  Document. Use when the user says "to prd", "write the PRD", "turn this into requirements", or wants
  a spec an engineer or agent can implement and test against without reading the design history.
---

# To PRD

Convert design material into a PRD that a build agent can implement from and a reviewer can test against. The PRD states *what* and *why*; it points to design docs for *how* and never re-argues decisions.

## Inputs to gather first

- The architecture or design doc (source of truth for scope).
- The decision log, if any (source of truth for rejected options and open items).
- Any review or audit output (source of amendments and constraints).
- The schema or data model, if any (source of data requirements).

Read all of them before writing. If they disagree, the newest amendment wins; note the conflict in Open Questions.

## Structure (use these headings, in this order)

1. **Summary** — three sentences: what, for whom, why now.
2. **Problem** — the pain in the user's words, one paragraph.
3. **Users** — each persona with what they do and what they must never have to do.
4. **Goals / Non-goals** — bullets; non-goals are as important as goals.
5. **Success metrics** — a table with metric, baseline, target, when measured.
6. **Scope by phase** — what ships in each phase; the first phase is the definition of done.
7. **Functional requirements** — numbered `FR-n`, grouped by component. Each has: statement (MUST/SHOULD), rationale (one line), acceptance criteria (testable, with the query or observable output where possible).
8. **Data requirements** — numbered `DR-n`; point to the schema, list what must exist from day one and why.
9. **Non-functional requirements** — numbered `NFR-n`: security, privacy, reliability, cost, observability.
10. **Dependencies** — external services and accounts, with who owns each and when it is needed.
11. **Risks** — table: risk, likelihood, impact, mitigation.
12. **Open questions** — each with owner and deadline; decisions awaiting veto go here.
13. **Appendix** — map of requirement IDs to source documents.

## Rules

- Every requirement is testable. "Handles errors gracefully" is not a requirement; "a failed source is retried once and then written as a warning in `runs`" is.
- Use MUST / SHOULD / MAY consistently.
- No design rationale beyond one line; link to the decision log instead.
- Requirements reference IDs from other requirements, never prose paragraphs.
- Keep it under ~400 lines; split by component if longer.
- Write the PRD next to the architecture it derives from, named `PRD.md`.
