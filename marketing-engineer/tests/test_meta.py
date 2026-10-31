from datetime import date

import pytest

from adapters.env import UnknownBackend
from adapters.meta import MetaApiError, get_meta


@pytest.fixture
def meta(dev_root, monkeypatch):
    monkeypatch.setenv("META_BACKEND", "fake")
    monkeypatch.setenv("META_FAKE_SEED", "7")
    monkeypatch.delenv("META_FAKE_FAIL", raising=False)
    return get_meta()


def build(meta, name="ucl-new_recipes-b1"):
    camp = meta.create_campaign(name, objective="OUTCOME_LEADS")
    adset = meta.create_adset(f"{name}-as1", campaign_id=camp["id"], daily_budget=15.0,
                              optimization_event="QuizStart", targeting={"geo": ["GB"]})
    creative = meta.create_creative(f"{name}-cr1", image_url="file:///x.png", body="b", title="t",
                                    link_url="http://localhost:8788/quiz?utm_content=c1")
    ad = meta.create_ad(f"{name}-ad1", adset_id=adset["id"], creative_id=creative["id"])
    return camp, adset, creative, ad


def test_create_then_name_lookup_then_read_back(meta):
    camp, adset, creative, ad = build(meta)
    assert meta.find_by_name("campaign", "ucl-new_recipes-b1")["id"] == camp["id"]
    assert meta.find_by_name("ad", "does-not-exist") is None
    read = meta.get("ad", ad["id"])
    assert read["name"] == "ucl-new_recipes-b1-ad1"
    assert read["status"] == "PAUSED"
    assert read["effective_status"] == "PAUSED"
    assert read["ad_review_feedback"] == {}
    assert read["adset_id"] == adset["id"] and read["creative_id"] == creative["id"]


def test_effective_status_follows_parents(meta):
    camp, adset, _, ad = build(meta)
    meta.update("ad", ad["id"], status="ACTIVE")
    assert meta.get("ad", ad["id"])["effective_status"] == "ADSET_PAUSED"
    meta.update("adset", adset["id"], status="ACTIVE")
    assert meta.get("ad", ad["id"])["effective_status"] == "CAMPAIGN_PAUSED"
    meta.update("campaign", camp["id"], status="ACTIVE")
    assert meta.get("ad", ad["id"])["effective_status"] == "ACTIVE"


def test_insights_are_synthesised_deterministically_from_seed(meta, monkeypatch):
    camp, adset, _, ad = build(meta)
    for kind, obj in (("campaign", camp), ("adset", adset), ("ad", ad)):
        meta.update(kind, obj["id"], status="ACTIVE", on=date(2026, 9, 1))
    rows = meta.insights(level="ad", since=date(2026, 9, 1), until=date(2026, 9, 3))
    assert [r["date_start"] for r in rows] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    row = rows[0]
    assert row["ad_id"] == ad["id"] and row["adset_id"] == adset["id"] and row["campaign_id"] == camp["id"]
    assert row["impressions"] > 0 and 0 < row["spend"] <= 15.0 * 1.25
    assert row["link_clicks"] <= row["clicks"] <= row["impressions"]
    actions = {a["action_type"]: a["value"] for a in row["actions"]}
    assert set(actions) == {"QuizStart", "QuizComplete", "Schedule"}
    assert actions["Schedule"] <= actions["QuizComplete"] <= actions["QuizStart"] <= row["link_clicks"]
    again = get_meta().insights(level="ad", since=date(2026, 9, 1), until=date(2026, 9, 3))
    assert again == rows
    assert meta.insights(level="ad", since=date(2026, 8, 20), until=date(2026, 8, 31)) == []
    assert meta.account_spend_today(date(2026, 9, 2)) == row_spend(rows, "2026-09-02")


def row_spend(rows, day):
    return sum(r["spend"] for r in rows if r["date_start"] == day)


def test_pausing_stops_spend_and_parents_gate_delivery(meta):
    camp, adset, _, ad = build(meta)
    for kind, obj in (("campaign", camp), ("adset", adset), ("ad", ad)):
        meta.update(kind, obj["id"], status="ACTIVE", on=date(2026, 9, 1))
    meta.update("ad", ad["id"], status="PAUSED", on=date(2026, 9, 3))
    days = [r["date_start"] for r in meta.insights(level="ad", since=date(2026, 9, 1), until=date(2026, 9, 6))]
    assert days == ["2026-09-01", "2026-09-02"], "a killed ad spends nothing from the kill day on"
    assert meta.account_spend_today(date(2026, 9, 4)) == 0
    meta.update("ad", ad["id"], status="ACTIVE", on=date(2026, 9, 5))
    meta.update("adset", adset["id"], status="PAUSED", on=date(2026, 9, 6))
    days = [r["date_start"] for r in meta.insights(level="ad", since=date(2026, 9, 1), until=date(2026, 9, 8))]
    assert days == ["2026-09-01", "2026-09-02", "2026-09-05"], "a paused ad set stops its ads"
    assert meta.get("ad", ad["id"])["effective_status"] == "ADSET_PAUSED"


def test_state_persists_across_clients(meta):
    camp, *_ = build(meta)
    assert get_meta().find_by_name("campaign", "ucl-new_recipes-b1")["id"] == camp["id"]


def test_failure_injection_before_and_after_create(meta, monkeypatch):
    camp, adset, creative, _ = build(meta, "x")
    monkeypatch.setenv("META_FAKE_FAIL", "create_ad")
    with pytest.raises(MetaApiError, match="create_ad"):
        meta.create_ad("x-ad2", adset_id=adset["id"], creative_id=creative["id"])
    assert meta.find_by_name("ad", "x-ad2") is None
    monkeypatch.setenv("META_FAKE_FAIL", "create_ad:after")
    with pytest.raises(MetaApiError):
        meta.create_ad("x-ad3", adset_id=adset["id"], creative_id=creative["id"])
    assert meta.find_by_name("ad", "x-ad3") is not None, "object exists although the caller saw an error"


def test_throttle_header_and_injection(meta, monkeypatch):
    from adapters.meta import MetaThrottled
    meta.create_campaign("t", objective="OUTCOME_LEADS")
    assert "x-business-use-case-usage" in meta.last_headers
    monkeypatch.setenv("META_FAKE_THROTTLE_AFTER", "1")
    with pytest.raises(MetaThrottled):
        meta.create_campaign("t2", objective="OUTCOME_LEADS")


def test_unknown_backend_names_variable(monkeypatch):
    monkeypatch.setenv("META_BACKEND", "sandbox")
    with pytest.raises(UnknownBackend, match="META_BACKEND"):
        get_meta()
