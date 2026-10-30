"""A second client that sells on its own product page (hand-off Step 6, Circadian).

The gate's rule-based brand check catches the client's banned terms whatever their case, hyphen or spacing. A product
page passes the landing check. The planner, producer and gate prompts name that page and the client's banned words
instead of the upClickLabs quiz and call. The upClickLabs prompts are unchanged."""
import importlib.util
import sys
from pathlib import Path

ME_DIR = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod   # dataclasses look their module up by name
    spec.loader.exec_module(mod)
    return mod


gt = _load("gate_for_second_client", ME_DIR / "scripts" / "gate.py")
rc = _load("render_creatives_for_second_client", ME_DIR / "scripts" / "render_creatives.py")
pb = _load("plan_batch_for_second_client", ME_DIR / "scripts" / "plan_batch.py")

PRODUCT = "https://shop.example/products/pillow"
QUIZ = "http://localhost:8788/quiz"
SHOP_OFFER = {"name": "pillow", "landing_url": PRODUCT, "funnel_host": None, "terminal_metric": "purchase",
              "offer_layer": {"cta_mechanic": "shop_now"}}
FUNNEL_OFFER = {"name": "audit", "landing_url": None, "funnel_host": "http://localhost:8788", "terminal_metric": "booked_call",
                "offer_layer": {"cta_mechanic": "book_15_min"}}
BANNED = ["Talalay", "OEKO-TEX", "knife edge", "Circadian Rest", "—"]
SHOP_CONFIG = {"brand": {"hard_blocks": ["no pricing"], "banned_terms": BANNED}}
FUNNEL_CONFIG = {"brand": {"hard_blocks": ["no pricing"]}}
BANNED_LINE = "- banned words (never write them, in any spelling): Talalay, OEKO-TEX, knife edge, Circadian Rest, —"


def _producer(offer, config, landing_page):
    return rc.producer_instructions("BASE", offer=offer, icp=None, config=config, template="screenshot-ad", executions=2,
                                    landing_page=landing_page, rules="RULES")


def test_banned_terms_are_caught_whatever_the_case_hyphen_or_spacing():
    words = "Slow-pour talalay latex, oeko tex tested — sewn with a knife-edge seam by Circadian Rest"
    assert gt.brand_rule_hits(words, [], banned_terms=BANNED) == [
        "banned term: 'talalay'", "banned term: 'oeko tex'", "banned term: 'knife-edge'",
        "banned term: 'Circadian Rest'", "banned term: '—'"]


def test_banned_terms_match_whole_words_only():
    assert gt.brand_rule_hits("Circadian restores deep sleep at the edge of the bed", [],
                              banned_terms=["Circadian Rest", "knife edge"]) == []


def test_without_banned_terms_the_brand_rules_are_as_before():
    assert gt.brand_rule_hits("Talalay — from €99", ["no pricing"]) == ["pricing: '€99'"]


def test_a_product_page_passes_the_landing_check():
    assert gt.landing_page_for(SHOP_OFFER) == rc.landing_page_for(SHOP_OFFER) == PRODUCT
    comps = [{"component_type": "landing_page", "component_ref": PRODUCT},
             {"component_type": "cta", "component_ref": "shop_now"}, {"component_type": "offer", "component_ref": "o1"}]
    assert gt.landing_check(comps, landing_page=PRODUCT, cta_mechanic="shop_now", offer_id="o1") == []


def test_prompts_name_the_product_page_not_the_quiz():
    for text in (gt.trusted_context(SHOP_OFFER, None, SHOP_CONFIG, PRODUCT), _producer(SHOP_OFFER, SHOP_CONFIG, PRODUCT)):
        assert f"landing page: {PRODUCT}, the offer's own page (terminal metric: purchase)" in text
        assert "quiz" not in text and "15-minute call" not in text


def test_every_prompt_lists_the_banned_words():
    assert BANNED_LINE in gt.trusted_context(SHOP_OFFER, None, SHOP_CONFIG, PRODUCT)
    assert BANNED_LINE in _producer(SHOP_OFFER, SHOP_CONFIG, PRODUCT)
    assert BANNED_LINE in pb.offer_instructions(SHOP_OFFER, None, SHOP_CONFIG)


def test_upclicklabs_prompts_are_unchanged():
    ctx = gt.trusted_context(FUNNEL_OFFER, None, FUNNEL_CONFIG, QUIZ)
    producer = _producer(FUNNEL_OFFER, FUNNEL_CONFIG, QUIZ)
    assert f"- landing page: the quiz at {QUIZ}, then a 15-minute call" in ctx
    assert f"- CTA mechanic: book_15_min; landing page: the quiz at {QUIZ}, then a 15-minute call" in producer
    for text in (ctx, producer, pb.offer_instructions(FUNNEL_OFFER, None, FUNNEL_CONFIG)):
        assert "banned words" not in text


# ---------- config/clients/circadian.json: the DRAFT creative-only client ----------

import json  # noqa: E402

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

CIRCADIAN = ME_DIR / "config" / "clients" / "circadian.json"
seed = _load("seed_for_second_client", ME_DIR / "scripts" / "seed.py")
pv = _load("pull_voc_for_second_client", ME_DIR / "scripts" / "pull_voc.py")


def _circadian():
    return json.loads(CIRCADIAN.read_text())


def test_circadian_config_has_every_key_the_creative_workers_require():
    cfg = _circadian()
    for module in (pv, pb, rc, gt):
        for path in module.REQUIRED_CONFIG:
            node = cfg
            for key in path:
                node = node.get(key) if isinstance(node, dict) else None
            assert node is not None, f"{module.__name__} needs {'.'.join(path)}"
    pv.check_config(cfg)
    assert cfg["voc"]["seed_dir"] and (ME_DIR / cfg["voc"]["seed_dir"]).is_dir()


def test_circadian_sells_on_its_product_page_and_cannot_launch():
    cfg = _circadian()
    assert cfg["currency"] == "USD" and cfg["offer"]["terminal_metric"] == "purchase"
    assert cfg["offer"]["landing_url"].startswith("https://circadianrest.com/products/")
    assert not cfg["offer"].get("funnel_host") and not cfg["offer"].get("calendar_url")
    assert "campaign" not in cfg and "trust" not in cfg, "creative only: UpClick never launches on Circadian's Meta assets"
    assert gt.landing_page_for(cfg["offer"]) == cfg["offer"]["landing_url"]


def test_circadian_brand_blocks_carry_the_hand_off_rules():
    brand = _circadian()["brand"]
    banned = {t.lower() for t in brand["banned_terms"]}
    assert {"white lotus", "talalay", "oeko-tex", "circadian rest", "—"} <= banned
    assert any("pricing" in b for b in brand["hard_blocks"]), "turns on the gate's price pattern"
    assert any("GOTS" in b and "buckwheat" in b for b in brand["hard_blocks"])


def test_circadian_offer_text_passes_its_own_brand_rules():
    cfg = _circadian()
    o, brand = cfg["offer"], cfg["brand"]
    text = " ".join([o["name"], o["promise"], o["price_anchor"], *o["proof_points"], *cfg["icp"]["pains"], *cfg["icp"]["outcomes"]])
    assert gt.brand_rule_hits(text, brand["hard_blocks"], banned_terms=brand["banned_terms"]) == []
    assert "GOTS" not in text, "the buckwheat pillow is never GOTS"


def test_circadian_seeds_next_to_upclicklabs(db_env, capsys):
    try:
        assert seed.main(["--config", str(CIRCADIAN)]) == 0
        with psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"], row_factory=dict_row) as conn:
            slugs = {r["slug"] for r in conn.execute("select slug from clients")}
            offer = conn.execute("select o.terminal_metric, o.landing_url from offers o join clients c on c.id = o.client_id "
                                 "where c.slug = 'circadian'").fetchone()
        assert {"upclicklabs", "circadian"} <= slugs
        assert offer == {"terminal_metric": "purchase", "landing_url": "https://circadianrest.com/products/buckwheat-pillow"}
    finally:
        with psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"]) as conn:
            cid = conn.execute("select id from clients where slug = 'circadian'").fetchone()
            if cid:
                for table in ("runs", "offers", "icps"):
                    conn.execute(f"delete from {table} where client_id = %s", cid)
                conn.execute("delete from clients where id = %s", cid)
