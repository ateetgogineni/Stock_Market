"""Quality gates and rating rules: abstention, horizon blocking, HOLD vs INSUFFICIENT DATA."""

import copy
from datetime import datetime, timezone

import pytest

from app.services.analysis import compute_deterministic
from app.services.recommendation import INSUFFICIENT, component_score, load_rules, rate
from tests.conftest import AS_OF, make_snapshot


def gate(det, gid):
    return next(g for g in det["gates"] if g["id"] == gid)


def test_component_score_mapping():
    band = {"bad": 0.08, "good": 0.20}
    assert component_score(0.08, band) == -1.0
    assert component_score(0.20, band) == 1.0
    assert component_score(0.14, band) == pytest.approx(0.0)
    assert component_score(0.50, band) == 1.0  # clipped
    assert component_score(None, band) is None
    lower_better = {"bad": 2.0, "good": 0.3}
    assert component_score(0.3, lower_better) == 1.0 and component_score(2.0, lower_better) == -1.0


def test_healthy_fixture_gates(snapshot):
    det = compute_deterministic(snapshot)
    assert det["price"]["data_status"] == "end_of_day"
    assert det["data_quality"]["critical_failures"] == []
    assert gate(det, "cross_listing_consistency")["passed"]
    # Development data is always flagged, never presented as licensed.
    assert not gate(det, "provider_entitlement")["passed"]
    assert not gate(det, "official_filings")["passed"]


def test_short_horizon_always_abstains(snapshot):
    r = rate(compute_deterministic(snapshot), [])
    short = r["horizons"]["short"]
    assert short["rating"] == INSUFFICIENT
    assert "No validated short-horizon" in short["abstention_reasons"][0]


def test_ratings_have_horizon_and_evidence(snapshot):
    det = compute_deterministic(snapshot)
    r = rate(det, [])
    for h in ("medium", "long"):
        out = r["horizons"][h]
        assert out["rating"] in ("BUY", "HOLD", "SELL")
        assert out["window"]
        assert out["key_reasons"], "a rating must explain itself"
        for reason in out["key_reasons"]:
            for eid in reason["evidence_ids"]:
                assert eid in det["evidence"]
        assert out["invalidation"]


def test_stale_prices_force_insufficient_data():
    snap = make_snapshot(end_date=datetime(2026, 10, 23).date())  # two weeks old
    det = compute_deterministic(snap)
    assert det["price"]["data_status"] == "stale"
    assert not gate(det, "price_freshness")["passed"]
    assert det["data_quality"]["status"] == "insufficient"
    r = rate(det, [])
    assert all(h["rating"] == INSUFFICIENT for h in r["horizons"].values())
    assert any("Price freshness" in s for s in r["horizons"]["medium"]["abstention_reasons"])


def test_holiday_like_lag_is_only_a_warning():
    snap = make_snapshot(end_date=datetime(2026, 11, 4).date())  # 2 sessions behind
    det = compute_deterministic(snap)
    g = gate(det, "price_freshness")
    assert g["severity"] == "warning" and not g["passed"]
    assert rate(det, [])["horizons"]["medium"]["rating"] != INSUFFICIENT


def test_missing_statements_block_long_horizon_only():
    det = compute_deterministic(make_snapshot(missing=frozenset({"statements"})))
    assert not gate(det, "annual_statements")["passed"]
    labels = [{"evidence_id": i["evidence_id"], "label": "neutral"} for i in det["news"]["items"]]
    r = rate(det, labels)
    assert r["horizons"]["long"]["rating"] == INSUFFICIENT
    assert any("Two or more annual statements" in s for s in r["horizons"]["long"]["abstention_reasons"])
    # Medium term keeps 70% coverage (technical, momentum, risk, news) and can still be rated.
    assert r["horizons"]["medium"]["rating"] in ("BUY", "HOLD", "SELL")
    assert r["horizons"]["medium"]["coverage"] == pytest.approx(0.70)
    # Without news labels coverage drops to 65%: abstain rather than fall back to HOLD.
    bare = rate(det, [])["horizons"]["medium"]
    assert bare["rating"] == INSUFFICIENT
    assert any("coverage" in s for s in bare["abstention_reasons"])


def test_missing_prices_block_everything():
    det = compute_deterministic(make_snapshot(missing=frozenset({"history"})))
    assert det["price"]["data_status"] == "unavailable"
    r = rate(det, [])
    assert {h["rating"] for h in r["horizons"].values()} == {INSUFFICIENT}


def test_trading_currency_mismatch_is_critical():
    det = compute_deterministic(make_snapshot(currency="USD"))
    g = gate(det, "currency_consistency")
    assert g["severity"] == "critical" and not g["passed"]
    assert {h["rating"] for h in rate(det, [])["horizons"].values()} == {INSUFFICIENT}


def test_foreign_reporting_currency_withholds_price_based_valuation():
    # e.g. Infosys: Yahoo reports its statements in USD while the NSE price is in INR.
    det = compute_deterministic(make_snapshot(financial_currency="USD"))
    g = gate(det, "reporting_currency")
    assert g["severity"] == "warning" and not g["passed"]
    m = det["fundamentals"]["metrics"]
    assert m["pe"]["status"] == "not_meaningful" and m["pe"]["value"] is None
    assert m["pb"]["status"] == "not_meaningful"
    assert m["roe"]["status"] == "ok"  # currency-neutral ratios survive
    assert det["evidence"]["stmt.a.revenue.2026-03-31"]["display"].startswith("USD ")
    assert det["evidence"]["calc.market_cap"]["display"].startswith("₹")
    assert det["fundamentals"]["annual_table"][0]["revenue"]["display"].startswith("USD ")
    r = rate(det, [])
    assert r["sub_scores"]["valuation"]["score"] is None
    assert r["horizons"]["long"]["coverage"] == pytest.approx(0.80)


def test_cross_listing_conflict_is_flagged():
    det = compute_deterministic(make_snapshot(cross_listing_skew=0.04))
    g = gate(det, "cross_listing_consistency")
    assert not g["passed"] and "apart" in g["message"]


def test_short_history_blocks_medium_and_long():
    det = compute_deterministic(make_snapshot(sessions=150))
    assert not gate(det, "price_history_depth")["passed"]
    r = rate(det, [])
    assert r["horizons"]["medium"]["rating"] == INSUFFICIENT
    assert r["horizons"]["long"]["rating"] == INSUFFICIENT


def test_financial_sector_excludes_leverage_components():
    det = compute_deterministic(make_snapshot(sector="Financial Services"))
    subs = rate(det, [])["sub_scores"]["fundamental_quality"]
    statuses = {c["name"]: c["status"] for c in subs["components"]}
    assert statuses["debt_to_equity"] == "excluded_for_sector"
    assert statuses["interest_coverage"] == "excluded_for_sector"
    assert subs["sector_note"]


def test_low_agreement_downgrades_to_hold():
    det = compute_deterministic(make_snapshot())
    rules = copy.deepcopy(load_rules())
    rules["thresholds"]["min_agreement"] = 1.01  # impossible to satisfy
    r = rate(det, [], rules)
    for h in ("medium", "long"):
        out = r["horizons"][h]
        assert out["rating"] == "HOLD"
        assert out["hold_reason"]


def test_news_tone_needs_enough_items(snapshot):
    det = compute_deterministic(snapshot)
    ids = [i["evidence_id"] for i in det["news"]["items"]]
    few = rate(det, [{"evidence_id": ids[0], "label": "positive"}])
    assert few["sub_scores"]["news_events"]["score"] is None
    many = rate(det, [{"evidence_id": i, "label": "negative"} for i in ids])
    assert many["sub_scores"]["news_events"]["score"] == -1.0


def test_news_dedupes_syndicated_headlines(snapshot):
    det = compute_deterministic(snapshot)
    assert det["news"]["duplicates_removed"] == 1
    titles = [i["title"] for i in det["news"]["items"]]
    assert len(titles) == len(set(titles))


def test_deterministic_core_is_reproducible(snapshot):
    a = compute_deterministic(snapshot)
    b = compute_deterministic(copy.deepcopy(snapshot))
    assert a == b


def test_in_progress_session_bar_is_excluded():
    # Wednesday 4 Nov 2026, 11:00 IST (market open); the provider's last bar is today's partial bar.
    at = datetime(2026, 11, 4, 5, 30, tzinfo=timezone.utc)
    det = compute_deterministic(make_snapshot(as_of=at, end_date=datetime(2026, 11, 4).date()))
    assert det["price"]["last_session"] == "2026-11-03"
    assert det["price"].get("partial_session_excluded")
    assert det["price"]["data_status"] in ("delayed", "end_of_day")
    assert det["price"]["data_status"] != "live"
