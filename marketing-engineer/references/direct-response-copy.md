# Direct-response copy rules (producer, `scripts/render_creatives.py`)

Read by the producer and sent to the copy model as trusted instructions. Sixty lines or fewer, on purpose:
the rules are the ones that survive ablation, not a style guide. DECISIONS.md component 4; SKILL.md §4 rule 5.

## The five rules

1. **One idea per ad.** One promise, one proof, one ask. A second idea is a second creative.
2. **The first line is the hook.** It carries the whole ad; it must survive alone in the feed. Use the
   hook type the format layer prescribes (pain, outcome, proof, contrarian, identity, question, number).
3. **Specificity over adjectives.** A number, a moment, a named situation beats "better", "faster", "smart".
   Never invent a number: only figures given in the offer's proof points may appear.
4. **The CTA matches the landing page.** The CTA names what happens next on the page (the quiz, then the
   15-minute call), nothing else. No "buy", no "sign up" when the page offers a quiz.
5. **The reader's words, not ours.** Where a customer phrase (VOC) fits the hook type, use its meaning, in
   the buyer's register. Verbatim `public` or `inbound` phrases are never quoted (gate hard check).

## Translation discipline (component 3, unchanged here)

The format layer (family, visual structure, copy structure, copy length, hook type) is fixed by the brief.
The producer may change only the offer, the product nouns, the VOC phrases, and the imagery subject.
Copy length follows the brief: `short` is one line plus the CTA; `medium` three lines; `long` a paragraph
of five to seven lines with a line break before the CTA.

## What the producer writes per brief

| Field | Count | Rule |
|-------|-------|------|
| primary text | 3 (short, medium, long) | same idea at three lengths; the brief's `copy_length` is the one shipped |
| headlines | 5 | ≤ 40 characters, no punctuation at the end, the promise or the proof, never a pun |
| hook lines | 10 | ≤ 90 characters, same hook type, the first one is the brief's own hook line verbatim |
| description | 1 | ≤ 30 characters, the mechanism ("free 15-minute call") |
| CTA text | 1 | ≤ 4 words, matches `offer_layer.cta_mechanic` and the landing page |
| overlay | per execution | the words on the image, composed by us and rendered in HTML; never asked of the image model |

## Hard blocks (config `brand.hard_blocks` plus Meta policy)

- No pricing, no income or results claims, no client names without an applied `quote_release`.
- No "you" statements about personal attributes (Meta personal-attributes policy): not "your failing
  agency", but "an agency report that never had this line".
- No real person, no brand logos, no competitor names in copy or imagery.
- No sensational punctuation ("!!!"), no ALL CAPS words except acronyms (AI, SEO, B2B).

## Images (FR-24)

Every image prompt ends with the no-text instruction the script appends. The image model paints a scene; the
words come from the template. A generated image that contains readable text is regenerated, at most three
attempts, then the execution is dropped and logged.
