#!/usr/bin/env python3
"""`produce` (T5): the creative producer. SKILL.md §3, §4 rules 4, 5, 7; PRD FR-21 to FR-25; ARCHITECTURE §4.

    python3 scripts/render_creatives.py [--client upclicklabs] [--experiment batch-001] [--rerender]
    python3 scripts/render_creatives.py --reupload        # go-live step 2: push every asset through the current storage backend

For the latest `selections` row of the client (or the named experiment) the producer takes each chosen brief and
writes `config.batch.executions_per_recipe` creatives (batch one: 3 briefs -> 6 creatives):

  1. opens a `runs` row (worker `producer`), prints "where are we", refuses when paused or when an action is `applying`;
  2. refuses the whole batch before rendering anything when a chosen brief is in a family without an HTML template
     (`assets/creative-templates/<family with dashes>.html`) or in a testimonial / quote family without an applied
     `quote_release` (FR-23); a brief that already has its creatives is skipped unless `--rerender`;
  3. copy through the model adapter (task `write_copy`, prompts in `references/prompts/producer.md`, rules in
     `references/direct-response-copy.md`): primary text at three lengths, five headlines, ten hook lines, a
     description, the CTA text, and per execution the overlay words for the template's slots. The brief's content is
     untrusted and enters the prompt only inside the data block; the offer, ICP, brand rules and slots are trusted;
  4. one text-free image per execution through the image adapter: every prompt ends with `NO_TEXT_INSTRUCTION`
     (FR-24) and a vision check (task `image_text_check`) flags readable text; a flagged image is regenerated, at
     most `MAX_IMAGE_ATTEMPTS`, then the execution is dropped and logged (FR-29's shape);
  5. the template is filled in HTML (every word is ours, escaped) and rendered with Playwright at 1080x1080; the
     generated image and the render go to the storage adapter under `creatives/<client>/<batch>/<creative id>/`;
  6. `creatives` (`renderer='html_template'`, `template`, `image_model` from config, `image_prompt`, `asset_urls`,
     `sizes=['1080x1080']`) and the full `creative_components` (family, variant, hook, angle, template, renderer,
     image_model, voc_phrase per phrase, cta, landing_page, offer, plus hook_type, proof_type, copy_length) are
     written together; a creative that fails `validate_creative` or `validate_components` does not exist (FR-21).

An execution is one rendering of the recipe: executions differ only in hook line (the first uses the brief's own,
the second a hook from the bank the copy task wrote, stored as its own `hooks` row) and in the image; the format
layer, copy length, CTA and landing page are identical. Worker role only; no side effect anywhere (SKILL.md §4 rule 1).
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.env import ME_DIR, load_env, require  # noqa: E402
from adapters.image import get_image  # noqa: E402
from adapters.model import Model, get_model  # noqa: E402
from adapters.storage import get_storage  # noqa: E402
from warehouse import client as wh  # noqa: E402

WORKER = "producer"
TASK_COPY = "write_copy"
TASK_VISION = "image_text_check"
PROMPTS = ME_DIR / "references" / "prompts" / "producer.md"
COPY_RULES = ME_DIR / "references" / "direct-response-copy.md"
TEMPLATE_DIR = ME_DIR / "assets" / "creative-templates"
RENDERER = "html_template"                                                     # FR-22: phase 0 renderer
SIZE = (1080, 1080)                                                            # FR-25: the only phase 0 size
SIZE_LABEL = "1080x1080"
MAX_IMAGE_ATTEMPTS = 3                                                         # FR-24 regenerate, FR-29 shape
NO_TEXT_INSTRUCTION = ("The image must contain no text of any kind: no words, letters, numerals, logos, wordmarks, "
                       "captions, labels, signs, screens with writing, or watermarks. All words are added separately.")
REQUIRED_COMPONENTS = ("family", "variant", "hook", "angle", "template", "renderer", "image_model", "cta", "landing_page", "offer")
EXTRA_COMPONENTS = ("hook_type", "proof_type", "copy_length", "voc_phrase")
COMPONENT_TYPES = REQUIRED_COMPONENTS + EXTRA_COMPONENTS                      # subset of the schema's check constraint
TEMPLATE_SLOTS: dict[str, tuple[str, ...]] = {                                 # overlay words the copy task must supply
    "job-photo-bubble": ("bubble_text", "caption"),
    "screenshot-ad": ("app", "title", "lines"),
}
SCREENSHOT_APPS = ("notes", "imessage", "email")
QUOTE_FAMILIES = ("testimonial_card", "press_quote")                           # FR-23: blocked without quote_release
COPY_LENGTHS = ("short", "medium", "long")
FALLBACK_CHROMIUM = Path("/opt/pw-browsers/chromium")                          # the container's pre-installed browser
REQUIRED_CONFIG = (("targets", "ctr_floor"), ("targets", "kill_impressions"), ("daily_cap",), ("currency",),
                   ("renderer",), ("image_model",), ("batch", "executions_per_recipe"), ("brand", "colors"), ("brand", "font"))


class ProducerRefused(RuntimeError):
    """`produce` refused; the message says why. The runs row closes `failed` with it."""


class PipelinePaused(ProducerRefused):
    pass


class ConfigMissing(ProducerRefused):
    pass


class NoSelection(ProducerRefused):
    """No `selections` row: nothing has been picked yet (SKILL.md §5.1)."""


class NoTemplate(ProducerRefused):
    """A chosen brief's family has no HTML template in assets/creative-templates/."""


class QuoteBlocked(ProducerRefused):
    """FR-23: a testimonial / quote family without an applied `quote_release`."""


class BudgetExceeded(ProducerRefused):
    """`clients.config.worker_budgets.producer` (tokens or images) spent before the batch was complete."""


class CreativeInvalid(ValueError):
    """The producer's validator refused a creative: a component is missing, the render is not 1080x1080, ..."""


class ImageHasText(RuntimeError):
    """FR-24: the vision check still saw text after MAX_IMAGE_ATTEMPTS generations; the execution is dropped."""


# ---------- pure rules (unit-tested) ----------

def available_templates(template_dir: Path = TEMPLATE_DIR) -> dict[str, Path]:
    """Template name (file stem, dashes) -> file. The family `job_photo_bubble` uses `job-photo-bubble.html`."""
    return {p.stem: p for p in sorted(template_dir.glob("*.html"))}


def template_for_family(family: str, templates: dict[str, Path]) -> str:
    """The family's template name, or NoTemplate naming the family and the file that would fix it."""
    name = family.replace("_", "-")
    if name not in templates:
        raise NoTemplate(f"family {family!r} has no HTML template (needs {TEMPLATE_DIR.relative_to(ME_DIR)}/{name}.html); "
                         f"templates available: {', '.join(sorted(templates)) or 'none'}. Pick a brief in a family with "
                         f"a template or add the template (references/families.md, weekend template column)")
    return name


def image_prompt(subject: str, variation: str = "") -> str:
    """The image model's prompt: the brief's imagery subject, the execution's variation, then the no-text instruction
    last, always (FR-24). Untrusted words in `subject` are scene description only; the instruction wins by position."""
    scene = " ".join(part.strip() for part in (subject, variation) if part and part.strip())
    return f"Photograph, natural light, realistic: {scene} {NO_TEXT_INSTRUCTION}".strip()


def retry_prompt(base: str, found: list[str], attempt: int) -> str:
    """The prompt for a regeneration after the vision check flagged text; still ends with the no-text instruction."""
    note = f"Attempt {attempt}: the previous image showed writing ({'; '.join(found)[:200] or 'unreadable marks'}); remove every surface that could carry text."
    return base.replace(NO_TEXT_INSTRUCTION, f"{note} {NO_TEXT_INSTRUCTION}")


_SLOT_RE = re.compile(r"\{\{\{(\w+)\}\}\}|\{\{(\w+)\}\}")


def render_template(name: str, slots: dict[str, Any], template_dir: Path = TEMPLATE_DIR) -> str:
    """Fill `{{slot}}` (HTML-escaped) and `{{{slot}}}` (raw, only for HTML the script built from escaped parts) in the
    template file. A slot the template needs and the caller did not give is refused, never left blank."""
    path = template_dir / f"{name}.html"
    if not path.exists():
        raise NoTemplate(f"template {name!r} not found in {template_dir}")
    text = path.read_text()
    missing: list[str] = []

    def fill(m: re.Match) -> str:
        raw, escaped = m.group(1), m.group(2)
        key = raw or escaped
        if key not in slots or slots[key] is None:
            missing.append(key)
            return ""
        return str(slots[key]) if raw else html.escape(str(slots[key]), quote=True)

    out = _SLOT_RE.sub(fill, text)
    if missing:
        raise CreativeInvalid(f"template {name!r} is missing slot(s) {sorted(set(missing))}")
    return out


def lines_html(lines: list[str]) -> str:
    return "".join(f'<div class="line">{html.escape(str(line), quote=True)}</div>' for line in lines)


def validate_overlay(template: str, overlay: dict[str, Any]) -> dict[str, Any]:
    """The copy task filled every slot the template needs (character limits are in the schema)."""
    needed = TEMPLATE_SLOTS.get(template)
    if needed is None:
        raise NoTemplate(f"template {template!r} has no slot definition in TEMPLATE_SLOTS")
    empty = [s for s in needed if not overlay.get(s)]
    if empty:
        raise CreativeInvalid(f"overlay for template {template!r} is missing {empty}")
    if template == "screenshot-ad" and overlay["app"] not in SCREENSHOT_APPS:
        raise CreativeInvalid(f"overlay.app {overlay['app']!r} is not one of {list(SCREENSHOT_APPS)}")
    return overlay


def copy_for_length(primary_text: dict[str, str], copy_length: str) -> tuple[str, str]:
    """The primary text at the brief's copy length (format layer, carried verbatim); unknown lengths ship `medium`."""
    length = copy_length if copy_length in COPY_LENGTHS else "medium"
    return primary_text[length], length


def validate_components(components: list[tuple[str, str]], *, voc_phrase_ids: list[Any]) -> list[tuple[str, str]]:
    """FR-21 / SKILL.md §4 rule 4: every required component exactly once, one `voc_phrase` per phrase the brief used,
    only known types, no empty refs. Anything else and the creative does not exist."""
    types = [t for t, _ in components]
    unknown = sorted(set(types) - set(COMPONENT_TYPES))
    if unknown:
        raise CreativeInvalid(f"unknown component type(s) {unknown}")
    for t in REQUIRED_COMPONENTS:
        n = types.count(t)
        if n != 1:
            raise CreativeInvalid(f"component {t!r} appears {n} times; exactly one is required (FR-21)")
    empty = [t for t, ref in components if not str(ref or "").strip()]
    if empty:
        raise CreativeInvalid(f"component(s) {empty} have an empty ref")
    voc = sorted(ref for t, ref in components if t == "voc_phrase")
    if voc != sorted(str(v) for v in voc_phrase_ids):
        raise CreativeInvalid(f"voc_phrase components {voc} do not match the brief's phrases {[str(v) for v in voc_phrase_ids]}")
    if len(set(components)) != len(components):
        raise CreativeInvalid("duplicate component rows")
    return components


def validate_creative(values: dict[str, Any], png: bytes) -> dict[str, Any]:
    """FR-22, FR-24, FR-25 on the row about to be written: the phase-0 renderer and size, a stored asset, a prompt that
    carries the no-text instruction, copy present. Refused before the insert."""
    from PIL import Image

    if values.get("renderer") != RENDERER:
        raise CreativeInvalid(f"renderer {values.get('renderer')!r} is not {RENDERER!r} (FR-22)")
    for key in ("brief_id", "template", "image_model", "primary_text", "headline", "image_prompt"):
        if not values.get(key):
            raise CreativeInvalid(f"creatives.{key} is empty")
    if not values["image_prompt"].endswith(NO_TEXT_INSTRUCTION):
        raise CreativeInvalid("image_prompt does not end with the no-text instruction (FR-24)")
    if list(values.get("sizes") or []) != [SIZE_LABEL]:
        raise CreativeInvalid(f"sizes {values.get('sizes')} is not [{SIZE_LABEL!r}] (FR-25)")
    urls = list(values.get("asset_urls") or [])
    if len(urls) != 1 or not urls[0]:
        raise CreativeInvalid("asset_urls must hold exactly the rendered 1080x1080 asset (FR-25)")
    img = Image.open(io.BytesIO(png))
    if img.format != "PNG" or img.size != SIZE:
        raise CreativeInvalid(f"render is {img.format} {img.size}, not PNG {SIZE}")
    return values


def copy_schema(executions: int) -> dict[str, Any]:
    line = {"type": "string", "minLength": 1, "maxLength": 120}
    return {
        "type": "object",
        "properties": {
            "primary_text": {"type": "object", "properties": {k: {"type": "string", "minLength": 1} for k in COPY_LENGTHS},
                             "required": list(COPY_LENGTHS), "additionalProperties": False},
            "headlines": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 60}, "minItems": 5, "maxItems": 5},
            "hook_lines": {"type": "array", "items": line, "minItems": 10, "maxItems": 10},
            "description": {"type": "string", "minLength": 1, "maxLength": 60},
            "cta_text": {"type": "string", "minLength": 1, "maxLength": 30},
            "executions": {
                "type": "array", "minItems": executions, "maxItems": executions,
                "items": {
                    "type": "object",
                    "properties": {
                        "hook_line": line,
                        "imagery_variation": {"type": "string", "minLength": 1, "maxLength": 300},
                        "overlay": {
                            "type": "object",
                            "properties": {
                                "bubble_text": {"type": "string", "maxLength": 120},
                                "caption": {"type": "string", "maxLength": 140},
                                "app": {"type": "string", "enum": list(SCREENSHOT_APPS)},
                                "title": {"type": "string", "maxLength": 60},
                                "lines": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 90},
                                          "minItems": 2, "maxItems": 5},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "required": ["hook_line", "imagery_variation", "overlay"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["primary_text", "headlines", "hook_lines", "description", "cta_text", "executions"],
        "additionalProperties": False,
    }


def vision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"contains_text": {"type": "boolean"}, "text_found": {"type": "array", "items": {"type": "string"}},
                       "confidence": {"type": "number", "minimum": 0, "maximum": 1}},
        "required": ["contains_text", "text_found", "confidence"],
        "additionalProperties": False,
    }


def untrusted_brief_text(brief: dict[str, Any], hook_text: str, voc: list[dict[str, Any]]) -> str:
    """The brief as data: it descends from ingested ad text and customer words (SKILL.md §4 rule 7). No URLs."""
    spec = brief.get("spec") or {}
    src = spec.get("source") or {}
    payload = {
        "brief": {
            "hook_line": hook_text, "family": brief.get("family"), "angle": brief.get("angle"),
            "format_layer": spec.get("format_layer"), "visual_spec": brief.get("visual_spec"),
            "product_nouns": spec.get("product_nouns"), "imagery_subject": spec.get("imagery_subject"),
            "coherence_note": spec.get("coherence_note"), "changed_ingredients": brief.get("changed_ingredients"),
            "source_variant": src.get("variant"), "source_hook_type": src.get("hook_type"),
        },
        "customer_phrases": [{"n": i, "category": v["category"], "visibility": v["visibility"], "phrase": v["phrase"]}
                             for i, v in enumerate(voc)],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1, default=str)


def producer_instructions(base: str, *, offer: dict[str, Any], icp: dict[str, Any] | None, config: dict[str, Any],
                          template: str, executions: int, landing_page: str, rules: str) -> str:
    """The trusted half of the user turn: the prompt file's instructions, then the copy rules, offer, ICP, brand rules,
    template slots (DRAFT config values are copied as they are)."""
    brand = config.get("brand") or {}
    layer = offer.get("offer_layer") or {}
    slots = {
        "job-photo-bubble": "bubble_text (the hook as spoken in the bubble, <= 120 chars), caption (one line under the photo, <= 140 chars)",
        "screenshot-ad": "app (notes | imessage | email), title (the window title, <= 60 chars), lines (2 to 5 lines of the fake UI, <= 90 chars each; "
                         "for imessage alternate the buyer and us, ours last; for email the first line is the highlighted subject)",
    }.get(template) or ", ".join(TEMPLATE_SLOTS.get(template, ()))
    lines = [
        base, "", "Copy rules (references/direct-response-copy.md):", rules, "",
        "Offer (ours):", f"- name: {offer.get('name')}", f"- promise: {offer.get('promise')}",
        f"- price anchor: {offer.get('price_anchor')}", f"- proof points: {', '.join(offer.get('proof_points') or []) or '-'}",
        f"- offer layer (fixed): {json.dumps(layer, sort_keys=True)}",
        f"- CTA mechanic: {layer.get('cta_mechanic')}; landing page: the quiz at {landing_page}, then a 15-minute call",
        f"- brand hard blocks: {', '.join(brand.get('hard_blocks') or []) or '-'}",
    ]
    if icp:
        lines += ["Audience (ICP):", f"- {icp.get('label')}", f"- role: {icp.get('role')}; company: {icp.get('company_type')}; "
                  f"size: {icp.get('size_band')}; geo: {', '.join(icp.get('geo') or [])}",
                  f"- pains: {'; '.join(icp.get('pains') or []) or '-'}", f"- outcomes: {'; '.join(icp.get('outcomes') or []) or '-'}"]
    lines += ["", f"Executions requested: {executions}.", f"Template: {template}. Overlay slots: {slots}."]
    return "\n".join(lines)


def load_prompts(path: Path = PROMPTS) -> dict[str, str]:
    """`## System`, `## Instructions`, `## Vision system`, `## Vision instructions` -> lower-cased keys."""
    text = path.read_text()
    sections = re.split(r"^## ([\w ]+?)\s*$", text, flags=re.M)
    found = {sections[i].strip().lower(): sections[i + 1].strip() for i in range(1, len(sections) - 1, 2)}
    for key in ("system", "instructions", "vision system", "vision instructions"):
        if key not in found:
            raise RuntimeError(f"{path} needs a '## {key.title()}' section")
    return found


# ---------- rendering ----------

class PlaywrightRenderer:
    """One Chromium for the run; `render(html) -> PNG bytes` at 1080x1080. The browser is the container's
    pre-installed one when Playwright's own download is absent (CHROMIUM_PATH overrides both)."""

    def __init__(self, size: tuple[int, int] = SIZE):
        self.size = size
        self._pw: Any = None
        self._browser: Any = None
        self.renders = 0

    def _start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        explicit = os.environ.get("CHROMIUM_PATH")
        try:
            self._browser = self._pw.chromium.launch(executable_path=explicit or None)
        except Exception:
            if explicit or not FALLBACK_CHROMIUM.exists():
                raise
            self._browser = self._pw.chromium.launch(executable_path=str(FALLBACK_CHROMIUM))

    def render(self, page_html: str) -> bytes:
        if self._browser is None:
            self._start()
        w, h = self.size
        page = self._browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        try:
            page.set_content(page_html, wait_until="load")
            page.evaluate("document.fonts && document.fonts.ready")
            png = page.screenshot(type="png", clip={"x": 0, "y": 0, "width": w, "height": h})
        finally:
            page.close()
        self.renders += 1
        return png

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None


def data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


# ---------- config and state ----------

def check_config(config: dict[str, Any]) -> None:
    for path in REQUIRED_CONFIG:
        node: Any = config
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            raise ConfigMissing(f"config is missing {'.'.join(path)}")
    if config["renderer"] != RENDERER:
        raise ConfigMissing(f"config.renderer {config['renderer']!r} is not {RENDERER!r}; phase 0 renders HTML templates only (FR-22)")


def paused(client: dict[str, Any]) -> bool:
    return bool(client.get("paused")) or os.environ.get("PIPELINE_PAUSED", "").strip().lower() in ("1", "true", "yes")


SELECTION_SQL = """
select s.*, e.name as experiment_name from selections s join experiments e on e.id = s.experiment_id
 where s.client_id = %s and (%s::text is null or e.name = %s) order by s.created_at desc limit 1;
"""
CHOSEN_BRIEFS_SQL = """
select b.*, h.text as hook_text from briefs b left join hooks h on h.id = b.hook_id
 where b.id = any(%s::uuid[]) order by (b.spec->>'proposal_number')::int, b.created_at;
"""
VOC_SQL = "select id, phrase, category, visibility, trust_tier from voc_phrases where id = any(%s::uuid[]) order by id;"
EXISTING_SQL = "select id, version from creatives where brief_id = %s and status <> 'archived' order by version desc, created_at;"
QUOTE_RELEASE_SQL = """
select 1 from actions where client_id = %s and action_type = 'quote_release' and status = 'applied'
   and (target_id = %s or proposal->>'brief_id' = %s) limit 1;
"""


def landing_page_for(offer: dict[str, Any]) -> str:
    """FR-21 `landing_page`: the offer's landing URL, else the quiz on its funnel host (funnel/server.py serves /quiz).
    The launcher (T9) appends `utm_content=<creative_id>` (FR-32); the component holds the page, not the tracked URL."""
    if offer.get("landing_url"):
        return str(offer["landing_url"])
    if offer.get("funnel_host"):
        return f"{str(offer['funnel_host']).rstrip('/')}/quiz"
    raise ConfigMissing("offer has neither landing_url nor funnel_host; the landing_page component cannot be set")


# ---------- the batch ----------

def generate_checked_image(*, image: Any, model: Model, prompts: dict[str, str], base_prompt: str, r: wh.Run,
                           image_budget: int) -> tuple[bytes, str, int]:
    """One text-free image: generate, vision-check (FR-24), regenerate on a flag, at most MAX_IMAGE_ATTEMPTS.
    Returns (png, the prompt that produced it, attempts). Raises ImageHasText when every attempt showed text."""
    prompt, found = base_prompt, []
    for attempt in range(1, MAX_IMAGE_ATTEMPTS + 1):
        if image_budget and r.counts.get("images_generated", 0) >= image_budget:
            raise BudgetExceeded(f"producer image budget {image_budget} spent (worker_budgets.producer.images)")
        assert NO_TEXT_INSTRUCTION in prompt
        png = image.generate(prompt, size=SIZE)
        r.count("images_generated")
        result = model.generate_json(task=TASK_VISION, system=prompts["vision system"], instructions=prompts["vision instructions"],
                                     untrusted="(one generated image attached; no text data)", schema=vision_schema(),
                                     max_tokens=512, images=[png])
        r.count("vision_checks")
        r.api_calls = (r.api_calls or 0) + 1
        r.tokens_used = (r.tokens_used or 0) + result.tokens_used
        if not result.output["contains_text"]:
            return png, prompt, attempt
        found = [str(t) for t in result.output.get("text_found") or []]
        r.count("vision_flags")
        print(f"render_creatives: vision check flagged text on attempt {attempt}: {found or 'unreadable'}; regenerating", file=sys.stderr)
        prompt = retry_prompt(base_prompt, found, attempt + 1)
    raise ImageHasText(f"image still showed text after {MAX_IMAGE_ATTEMPTS} attempts ({found or 'unreadable'})")


def produce(conn: wh.Connection, r: wh.Run, *, client: dict[str, Any], config: dict[str, Any], model: Model, image: Any,
            storage: Any, renderer: PlaywrightRenderer, experiment_name: str | None = None, rerender: bool = False,
            template_dir: Path = TEMPLATE_DIR) -> list[dict[str, Any]]:
    """Render every chosen brief of the latest selection into `executions_per_recipe` creatives. Returns the rows written."""
    client_id = client["id"]
    for key in ("briefs_chosen", "briefs_skipped_existing", "creatives_written", "creatives_dropped_text", "images_generated",
                "vision_checks", "vision_flags", "renders", "hooks_written"):
        r.counts.setdefault(key, 0)
    executions = int(config["batch"]["executions_per_recipe"])
    budgets = (config.get("worker_budgets") or {}).get("producer") or {}
    token_budget, image_budget = int(budgets.get("tokens") or 0), int(budgets.get("images") or 0)

    sel = conn.execute(SELECTION_SQL, (client_id, experiment_name, experiment_name)).fetchone()
    if sel is None:
        raise NoSelection("no picks recorded for this client" + (f" on {experiment_name}" if experiment_name else "")
                          + "; run `plan batch` then `my picks: n, n, n` (scripts/plan_batch.py --select) first")
    r.counts["experiment"] = sel["experiment_name"]
    briefs = conn.execute(CHOSEN_BRIEFS_SQL, (list(sel["chosen"]),)).fetchall()
    r.counts["briefs_chosen"] = len(briefs)
    if not briefs:
        raise NoSelection(f"selection on {sel['experiment_name']} has no chosen briefs")
    offer = conn.execute("select * from offers where id = %s", (briefs[0]["offer_id"],)).fetchone() if briefs[0].get("offer_id") else None
    if offer is None:
        offer = conn.execute("select * from offers where client_id = %s order by created_at limit 1", (client_id,)).fetchone()
    if offer is None:
        raise ConfigMissing("no offers row for this client; run scripts/dev_db.sh --seed")
    icp = conn.execute("select * from icps where client_id = %s order by created_at limit 1", (client_id,)).fetchone()
    landing_page = landing_page_for(offer)
    cta = (offer.get("offer_layer") or {}).get("cta_mechanic")
    if not cta:
        raise ConfigMissing("offers.offer_layer.cta_mechanic is empty; the cta component cannot be set")

    # Refuse the whole batch before any render: FR-23 quote families, then a family without a template.
    templates = available_templates(template_dir)
    plan: list[tuple[dict[str, Any], str]] = []
    for b in briefs:
        n = (b.get("spec") or {}).get("proposal_number")
        if b["family"] in QUOTE_FAMILIES:
            released = conn.execute(QUOTE_RELEASE_SQL, (client_id, str(b["id"]), str(b["id"]))).fetchone()
            if not released:
                raise QuoteBlocked(f"brief #{n} is in family {b['family']!r}: testimonial / quote families are blocked without an "
                                   f"applied quote_release action (FR-23)")
        try:
            plan.append((b, template_for_family(b["family"], templates)))
        except NoTemplate as exc:
            raise NoTemplate(f"brief #{n}: {exc}") from exc
        if not b.get("hook_text"):
            raise CreativeInvalid(f"brief #{n} has no hook (hooks row missing); the planner writes one per brief")
    r.counts["templates"] = sorted({t for _, t in plan})

    prompts = load_prompts()
    rules = COPY_RULES.read_text()
    slug = client["slug"]
    written: list[dict[str, Any]] = []
    for b, template in plan:
        n = (b.get("spec") or {}).get("proposal_number")
        spec = b.get("spec") or {}
        existing = conn.execute(EXISTING_SQL, (b["id"],)).fetchall()
        version = 1
        if existing and not rerender:
            print(f"render_creatives: brief #{n} already has {len(existing)} creative(s); skipped (use --rerender to replace)")
            r.count("briefs_skipped_existing")
            continue
        if existing:
            version = int(existing[0]["version"]) + 1
            conn.execute("update creatives set status = 'archived' where brief_id = %s and status <> 'archived'", (b["id"],))
            r.count("creatives_archived", len(existing))
        voc = conn.execute(VOC_SQL, (list(b.get("voc_phrase_ids") or []),)).fetchall() if b.get("voc_phrase_ids") else []
        layer = spec.get("format_layer") or {}
        instructions = producer_instructions(prompts["instructions"], offer=offer, icp=icp, config=config, template=template,
                                             executions=executions, landing_page=landing_page, rules=rules)
        if token_budget and (r.tokens_used or 0) > token_budget:
            raise BudgetExceeded(f"producer token budget {token_budget} spent before brief #{n}")
        result = model.generate_json(task=TASK_COPY, system=prompts["system"], instructions=instructions,
                                     untrusted=untrusted_brief_text(b, b["hook_text"], voc), schema=copy_schema(executions),
                                     max_tokens=6000)
        r.api_calls = (r.api_calls or 0) + 1
        r.tokens_used = (r.tokens_used or 0) + result.tokens_used
        copy = result.output
        primary, length = copy_for_length(copy["primary_text"], str(layer.get("copy_length") or ""))
        hook_lines_used: set[str] = set()
        for k, ex in enumerate(copy["executions"]):
            hook_text = b["hook_text"] if k == 0 else str(ex["hook_line"]).strip()
            if hook_text in hook_lines_used:
                raise CreativeInvalid(f"brief #{n}: executions must differ in hook line; {hook_text!r} repeats")
            hook_lines_used.add(hook_text)
            overlay = validate_overlay(template, dict(ex["overlay"]))
            base_prompt = image_prompt(str(spec.get("imagery_subject") or b.get("visual_spec") or ""), str(ex["imagery_variation"]))
            try:
                png_image, prompt, attempts = generate_checked_image(image=image, model=model, prompts=prompts, base_prompt=base_prompt,
                                                                     r=r, image_budget=image_budget)
            except ImageHasText as exc:
                r.count("creatives_dropped_text")
                print(f"render_creatives: brief #{n} execution {k + 1} dropped: {exc} (FR-24)", file=sys.stderr)
                continue
            slots = {
                "image_data_uri": data_uri(png_image), "hook": hook_text, "cta_text": copy["cta_text"], "client_name": client.get("name") or slug,
                "brand_font": config["brand"]["font"], "brand_primary": config["brand"]["colors"].get("primary", "#111111"),
                "brand_accent": config["brand"]["colors"].get("accent", "#3B82F6"), "brand_bg": config["brand"]["colors"].get("bg", "#FFFFFF"),
                "bubble_text": overlay.get("bubble_text"), "caption": overlay.get("caption"),
                "app": overlay.get("app"), "title": overlay.get("title"), "lines_html": lines_html(overlay.get("lines") or []),
            }
            rendered = renderer.render(render_template(template, slots, template_dir))
            r.count("renders")
            creative_id = uuid4()
            key = f"creatives/{slug}/{sel['experiment_name']}/{creative_id}"
            storage.put(png_image, f"{key}/image.png")
            asset_url = storage.put(rendered, f"{key}/{SIZE_LABEL}.png")
            values = dict(
                id=creative_id, client_id=client_id, brief_id=b["id"], experiment_id=b.get("experiment_id"), status="draft",
                primary_text=primary, headline=copy["headlines"][0], description=copy["description"], renderer=RENDERER,
                template=template, image_model=str(config["image_model"]), image_prompt=prompt,
                source_reference_url=(spec.get("source") or {}).get("source_image_url"), asset_urls=[asset_url],
                sizes=[SIZE_LABEL], version=version,
            )
            validate_creative(values, rendered)
            if k == 0:
                hook_id = b["hook_id"]
            else:
                hook = wh.insert_hooks(conn, client_id=client_id, text=hook_text, hook_type=layer.get("hook_type"),
                                       pattern_id=b.get("source_pattern_id"), trust_tier="owned")
                hook_id = hook["id"]
                r.count("hooks_written")
            components = [
                ("family", b["family"]), ("variant", str((spec.get("source") or {}).get("variant") or "")), ("hook", str(hook_id)),
                ("hook_type", str(layer.get("hook_type") or "")), ("angle", b["angle"]), ("template", template), ("renderer", RENDERER),
                ("image_model", str(config["image_model"])), ("cta", str(cta)), ("landing_page", landing_page), ("offer", str(offer["id"])),
                ("proof_type", str((offer.get("offer_layer") or {}).get("proof_type") or "")), ("copy_length", length),
                *[("voc_phrase", str(v["id"])) for v in voc],
            ]
            components = [(t, ref) for t, ref in components if ref or t in REQUIRED_COMPONENTS]
            validate_components(components, voc_phrase_ids=[v["id"] for v in voc])
            row = wh.insert_creatives(conn, **values)
            for t, ref in components:
                wh.insert_creative_components(conn, creative_id=row["id"], component_type=t, component_ref=ref)
            row.update(proposal_number=n, hook_text=hook_text, execution=k + 1, image_attempts=attempts, components=len(components))
            written.append(row)
            r.count("creatives_written")
            r.counts["image_attempts_total"] = r.counts.get("image_attempts_total", 0) + attempts
    expected = (len(plan) - r.counts["briefs_skipped_existing"]) * executions
    if written or r.counts["briefs_skipped_existing"]:
        print(format_creatives(sel["experiment_name"], written))
    if r.counts["creatives_dropped_text"]:
        print(f"render_creatives: WARNING {r.counts['creatives_dropped_text']} execution(s) dropped after {MAX_IMAGE_ATTEMPTS} "
              f"text-bearing images; {len(written)} of {expected} creatives written", file=sys.stderr)
    return written


def format_creatives(experiment: str, rows: list[dict[str, Any]]) -> str:
    table = [("#", "brief", "family / template", "exec", "hook line", "components", "asset")]
    for i, c in enumerate(rows, start=1):
        table.append((str(i), f"#{c.get('proposal_number')}", f"{c.get('template')}", str(c.get("execution")),
                      (c.get("hook_text") or "")[:60], str(c.get("components")), (c.get("asset_urls") or [""])[0]))
    widths = [min(max(len(r[i]) for r in table), 100) for i in range(len(table[0]))]
    lines = [f"\n{experiment}: {len(rows)} creative(s) rendered ({RENDERER}, {SIZE_LABEL})"]
    for i, row in enumerate(table):
        lines.append("  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())
        if i == 0:
            lines.append("  ".join("-" * w for w in widths))
    lines.append("\nNext: `gate` (scripts/gate.py, T6).")
    return "\n".join(lines)


# ---------- --reupload (go-live step 2) ----------

def read_asset(url: str, storage: Any) -> bytes:
    """A `file://` URL written by the local backend is read from disk; anything else through the current backend."""
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(url2pathname(parsed.path)).read_bytes()
    return storage.get(url)


def reupload(conn: wh.Connection, r: wh.Run, *, client: dict[str, Any], storage: Any) -> int:
    """Push every non-archived creative's assets through the current storage backend and point `asset_urls` at the new
    copies (0003 grant). Keys keep the `creatives/<client>/<batch>/<id>/<size>.png` shape."""
    rows = conn.execute("select c.id, c.asset_urls, c.sizes, e.name as experiment from creatives c left join experiments e on e.id = c.experiment_id "
                        "where c.client_id = %s and c.status <> 'archived' and cardinality(c.asset_urls) > 0 order by c.created_at", (client["id"],)).fetchall()
    n = 0
    for c in rows:
        new_urls = []
        for url, size in zip(c["asset_urls"], c["sizes"] or [SIZE_LABEL] * len(c["asset_urls"])):
            new_urls.append(storage.put(read_asset(url, storage), f"creatives/{client['slug']}/{c['experiment'] or 'no-batch'}/{c['id']}/{size}.png"))
            n += 1
        conn.execute("update creatives set asset_urls = %s where id = %s", (new_urls, c["id"]))
    r.counts.update(creatives_reuploaded=len(rows), assets_reuploaded=n)
    print(f"render_creatives: re-uploaded {n} asset(s) of {len(rows)} creative(s) through STORAGE_BACKEND={os.environ.get('STORAGE_BACKEND')}")
    return n


# ---------- main ----------

def load_config(client: dict[str, Any]) -> dict[str, Any]:
    return dict(client.get("config") or {})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="produce: chosen briefs -> rendered 1080x1080 creatives with full creative_components")
    ap.add_argument("--client", default="upclicklabs")
    ap.add_argument("--experiment", default=None, help="batch name (default: the latest selection)")
    ap.add_argument("--rerender", action="store_true", help="archive a brief's existing creatives and render a new version")
    ap.add_argument("--reupload", action="store_true", help="go-live step 2: push every asset through the current storage backend")
    args = ap.parse_args(argv)

    load_env()
    if args.reupload:
        require(WORKER, "WAREHOUSE_URL_WORKER", "STORAGE_BACKEND")
    else:
        require(WORKER, "WAREHOUSE_URL_WORKER", "MODEL_BACKEND", "IMAGE_BACKEND", "STORAGE_BACKEND")
    r: wh.Run | None = None
    renderer = PlaywrightRenderer()
    try:
        with wh.connect("worker", job=WORKER) as conn:
            client = wh.client_by_slug(conn, args.client)
            if client is None:
                print(f"render_creatives: no client with slug {args.client!r}; run scripts/dev_db.sh --seed", file=sys.stderr)
                return 1
            config = load_config(client)
            try:
                with wh.run(conn, WORKER, client["id"]) as r:
                    status = wh.where_are_we(conn, args.client)
                    print(wh.format_where_are_we(status))
                    check_config(config)
                    if paused(client):
                        raise PipelinePaused("pipeline paused (clients.paused or PIPELINE_PAUSED); produce refused")
                    if status["actions_stuck"]:
                        raise ProducerRefused(f"{status['actions_stuck']} action(s) in `applying`; only the executor's reconcile mode may run (SKILL.md §2)")
                    if args.reupload:
                        reupload(conn, r, client=client, storage=get_storage())
                    else:
                        produce(conn, r, client=client, config=config, model=get_model(), image=get_image(), storage=get_storage(),
                                renderer=renderer, experiment_name=args.experiment, rerender=args.rerender)
            except (ProducerRefused, CreativeInvalid) as exc:
                print(f"render_creatives: refused: {exc} (runs row {r.id} closed as failed)", file=sys.stderr)
                return 2
    finally:
        renderer.close()
    assert r is not None
    print(f"\nrender_creatives: run {r.id} ok; counts {json.dumps(r.counts, sort_keys=True, default=str)}; "
          f"api_calls {r.api_calls}; tokens {r.tokens_used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
