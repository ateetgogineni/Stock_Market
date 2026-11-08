"""Options contracts, chain analytics, payoff engine and risk verification."""

import math
from datetime import date, datetime, timezone

import pytest

from app.options import chain, contracts, risk, service
from app.options import strategies as st
from app.providers.fixture import FixtureProvider

NOW = datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc)


class ScaledFixture:
    """Synthetic underlying history rescaled so its last close sits at a realistic level."""

    name = "fixture"

    def __init__(self, target: float):
        self.p, self.target = FixtureProvider(end_date=date(2026, 11, 6)), target

    def history(self, symbol, years):
        bars = self.p.history(symbol, years)
        f = self.target / bars[-1]["close"]
        return [{**b, **{k: b[k] * f for k in ("open", "high", "low", "close", "adj_close")}} for b in bars]


@pytest.fixture(scope="module")
def nifty():
    return service.build_snapshot("NIFTY", ScaledFixture(25030.35), now=NOW)


@pytest.fixture(scope="module")
def reliance():
    return service.build_snapshot("RELIANCE", ScaledFixture(1320.0), now=NOW)


def leg(side, kind, strike, fill):
    return {"side": side, "type": kind, "strike": strike, "fill": fill, "quote": None}


# ---------------------------------------------------------------- contracts

def test_contract_master_identifies_real_contracts():
    n = contracts.underlying_view("NIFTY")
    assert n["type"] == "index" and n["settlement"] == "cash" and n["exercise"] == "european"
    assert n["price_symbol"] == "^NSEI"
    assert n["expiries"][0]["lot_size"] == 65
    r = contracts.underlying_view("RELIANCE")
    assert r["type"] == "stock" and r["settlement"] == "physical" and r["instrument_id"] == "IN:INE002A01018"
    with pytest.raises(contracts.ContractError):
        contracts.underlying_view("CUPID")  # not in the F&O segment
    assert contracts.search("bank")[0]["symbol"] == "BANKNIFTY"


def test_index_without_verified_price_source_is_insufficient_data():
    assert contracts.underlying_view("FINNIFTY")["price_symbol"] is None
    with pytest.raises(service.OptionsDataError, match="INSUFFICIENT DATA"):
        service.build_snapshot("FINNIFTY", ScaledFixture(27000), now=NOW)


def test_no_strikes_near_spot_is_insufficient_data():
    with pytest.raises(service.OptionsDataError, match="INSUFFICIENT DATA"):
        service.build_snapshot("NIFTY", ScaledFixture(1500), now=NOW)


def test_snapshot_round_trip_and_tamper_detection(nifty, tmp_path):
    service.save(nifty, tmp_path)
    assert service.load(nifty["chain_id"], tmp_path) == nifty
    path = tmp_path / "options" / f"{nifty['chain_id']}.json"
    path.write_text(path.read_text().replace('"oi":', '"oi": 1', 1))
    with pytest.raises(Exception):
        service.load(nifty["chain_id"], tmp_path)


def test_expiries_use_contract_master_dates_and_days(nifty):
    first = nifty["expiries"][0]
    assert first["expiry"] == "2026-11-09"  # holiday-shifted Monday expiry from the master
    assert first["T"] * 365 == pytest.approx(3.0)


# ---------------------------------------------------------------- chain analytics

def test_max_pain_hand_example():
    rows = [
        {"strike": 90, "CE": {"oi": 100}, "PE": {"oi": 500}},
        {"strike": 100, "CE": {"oi": 300}, "PE": {"oi": 300}},
        {"strike": 110, "CE": {"oi": 500}, "PE": {"oi": 100}},
    ]
    # Payout to holders: at 90 -> 300*10+100*20... evaluated at each strike; 100 is the minimum.
    assert chain.max_pain(rows) == 100


def test_chain_view_summary(nifty):
    view = service.chain_view(nifty)
    s = view["summary"]
    assert view["data_type"] == "synthetic"
    assert not next(g for g in view["quality"] if g["id"] == "data_source")["passed"]
    assert s["atm_strike"] % 50 == 0 and abs(s["atm_strike"] - 25030) <= 50
    assert 0.1 < s["atm_iv"] < 0.5
    assert s["pcr_oi"] == pytest.approx(s["total_oi"]["PE"] / s["total_oi"]["CE"])
    assert all(x["strike"] >= 25030.35 for x in s["oi_resistance"])
    assert all(x["strike"] <= 25030.35 for x in s["oi_support"])
    assert s["unusual_volume"], "planted volume spikes should be detected"
    assert "not proof" in s["positioning"]["caveat"]
    mc = view["model_check"]
    assert mc["status"] == "ok" and mc["passed"] and mc["strike"] == s["atm_strike"]
    assert {c["contract"].split()[-1] for c in mc["checks"]} == {"CE", "PE"}
    for row in view["rows"]:
        for k in ("CE", "PE"):
            q = row[k]
            assert (q["iv"] is None) == (q["greeks"] is None)


# ---------------------------------------------------------------- payoff engine (hand-calculated)

def test_bull_call_spread_hand_example():
    legs = [leg("buy", "CE", 100, 5.0), leg("sell", "CE", 110, 2.0)]
    out = st.analyse_payoff(legs, 10)
    assert out["max_loss"] == pytest.approx(-30.0)  # net debit 3 x 10
    assert out["max_profit"] == pytest.approx(70.0)  # (10 - 3) x 10
    assert out["breakevens"] == [103.0]
    assert not out["unlimited_loss"] and not out["unlimited_profit"]


def test_short_straddle_has_unlimited_loss():
    legs = [leg("sell", "CE", 100, 4.0), leg("sell", "PE", 100, 3.5)]
    out = st.analyse_payoff(legs, 1)
    assert out["unlimited_loss"] and out["max_loss"] == -math.inf
    assert out["max_profit"] == pytest.approx(7.5)
    assert out["breakevens"] == [92.5, 107.5]


def test_long_put_profit_is_capped_at_zero_price():
    out = st.analyse_payoff([leg("buy", "PE", 100, 4.0)], 1)
    assert out["max_profit"] == pytest.approx(96.0) and out["breakevens"] == [96.0]


def test_iron_condor_max_loss_is_wing_width_minus_credit():
    legs = [leg("buy", "PE", 80, 0.5), leg("sell", "PE", 90, 1.5), leg("sell", "CE", 110, 1.5), leg("buy", "CE", 120, 0.5)]
    out = st.analyse_payoff(legs, 1)
    assert out["max_profit"] == pytest.approx(2.0)
    assert out["max_loss"] == pytest.approx(-8.0)
    assert out["breakevens"] == [88.0, 112.0]


def test_covered_call_upside_is_capped_and_downside_is_the_stock():
    legs = [leg("buy", "STOCK", None, 100.0), leg("sell", "CE", 110, 2.0)]
    out = st.analyse_payoff(legs, 1)
    assert not out["unlimited_profit"] and out["max_profit"] == pytest.approx(12.0)
    assert out["max_loss"] == pytest.approx(-98.0)


@pytest.mark.parametrize("template", [t for t in st.TEMPLATES if t != "covered_call"])
def test_independent_verification_agrees_for_every_template(nifty, template):
    ev = service.evaluate(nifty, template, None, width=2)
    assert ev["verification"]["consistent"], ev["verification"]["problems"]
    p = ev["payoff"]
    assert p["max_loss"] is not None or p["unlimited_loss"]
    assert ev["risk"]["opportunity_status"] == "INSUFFICIENT_DATA"  # synthetic data never yields a trade call


def test_verification_catches_a_wrong_payoff():
    legs = [leg("buy", "CE", 100, 5.0), leg("sell", "CE", 110, 2.0)]
    exact = st.analyse_payoff(legs, 10)
    wrong = {**exact, "max_loss": -10.0}
    assert not risk.verify_payoff(legs, 10, wrong)["consistent"]


def test_covered_call_refused_on_an_index(nifty):
    with pytest.raises(st.StrategyError, match="index"):
        service.evaluate(nifty, "covered_call", None)


def test_stock_options_flag_physical_settlement(reliance):
    ev = service.evaluate(reliance, "covered_call", None, width=2)
    ids = [f["id"] for f in ev["risk"]["flags"]]
    assert "physical_settlement" in ids
    short = service.evaluate(reliance, "short_strangle", None)
    assert short["risk"]["flags"][0]["id"] == "unlimited_loss"  # most severe first, never hidden


def test_evaluation_is_deterministic(nifty):
    assert service.evaluate(nifty, "iron_condor", None, width=3) == service.evaluate(nifty, "iron_condor", None, width=3)


# ---------------------------------------------------------------- risk rules

def _q(**kw):
    base = {"bid": 10.0, "ask": 10.5, "spread_pct": 0.05, "volume": 100, "oi": 1000, "iv": 0.2, "iv_note": None, "greeks": {}}
    return base | kw


def _ctx(**kw):
    return {"data_type": "licensed", "data_fresh": True, "days_to_expiry": 20.0, "settlement": "cash",
            "underlying_type": "index", "iv_to_realised": 1.0} | kw


def test_risk_rules_reject_unsafe_legs():
    legs = [{"side": "sell", "type": "CE", "strike": 110, "fill": None, "quote": _q(bid=0.0)},
            {"side": "buy", "type": "CE", "strike": 120, "fill": 3.0, "quote": _q(spread_pct=0.8)},
            {"side": "buy", "type": "PE", "strike": 90, "fill": 2.0, "quote": _q(volume=0, oi=10)}]
    out = risk.assess(legs, {"unlimited_loss": False, "max_loss": -5.0, "max_profit": 5.0}, {"consistent": True, "problems": []}, _ctx())
    assert out["verdict"] == "rejected"
    text = " ".join(out["rejections"])
    assert "no bid" in text and "extremely wide" in text and "illiquid" in text
    assert out["opportunity_status"] == "NO_SUITABLE_OPPORTUNITY"


def test_opportunity_status_rules():
    legs = [{"side": "buy", "type": "CE", "strike": 100, "fill": 5.0, "quote": _q()}]
    exact = {"unlimited_loss": False, "max_loss": -5.0, "max_profit": math.inf}
    ok = {"consistent": True, "problems": []}
    assert risk.assess(legs, exact, ok, _ctx(data_type="synthetic"))["opportunity_status"] == "INSUFFICIENT_DATA"
    assert risk.assess(legs, exact, ok, _ctx(data_fresh=False))["opportunity_status"] == "INSUFFICIENT_DATA"
    # Even clean, licensed data gets no opportunity call until a validated model exists.
    clean = risk.assess(legs, exact, ok, _ctx())
    assert clean["opportunity_status"] == "INSUFFICIENT_DATA" and "validated" in clean["opportunity_reason"]
    bad = risk.assess(legs, exact, {"consistent": False, "problems": ["x"]}, _ctx())
    assert bad["verdict"] == "rejected"


# ---------------------------------------------------------------- HTTP API

def test_options_http_flow(tmp_path):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app import main
    from app.db import Database
    from app.services.orchestrator import Orchestrator

    db = Database(f"sqlite:///{tmp_path / 'o.db'}")
    db.create_all()
    settings = SimpleNamespace(data_dir=tmp_path, agents_enabled=False, agent_timeout_seconds=5, agent_max_tokens=10, agent_model="x")
    main.app.state.orchestrator = Orchestrator(db, settings, provider_factory=lambda: ScaledFixture(25030.35),
                                               llm_factory=lambda: None)
    with TestClient(main.app) as client:
        found = client.get("/api/options/underlyings", params={"q": "nifty"}).json()["results"]
        assert found[0]["symbol"] == "NIFTY"
        assert client.get("/api/options/underlyings").json()["results"][0]["symbol"] == "NIFTY"
        assert len(client.get("/api/options/strategies").json()["templates"]) == len(st.TEMPLATES)
        assert client.post("/api/options/chains", json={"symbol": "CUPID"}).status_code == 404
        assert client.post("/api/options/chains", json={"symbol": "FINNIFTY"}).status_code == 422
        chain_id = client.post("/api/options/chains", json={"symbol": "nifty"}).json()["chain_id"]
        view = client.get(f"/api/options/chains/{chain_id}").json()
        assert view["data_type"] == "synthetic" and view["rows"]
        second = view["expiries"][1]["expiry"]
        assert client.get(f"/api/options/chains/{chain_id}", params={"expiry": second}).json()["expiry"] == second
        ev = client.post(f"/api/options/chains/{chain_id}/strategies", json={"template": "short_strangle", "width": 3}).json()
        assert ev["payoff"]["unlimited_loss"] is True and ev["payoff"]["max_loss"] is None
        assert ev["risk"]["opportunity_status"] == "INSUFFICIENT_DATA"
        bad = client.post(f"/api/options/chains/{chain_id}/strategies", json={"template": "covered_call"})
        assert bad.status_code == 422
        assert client.get("/api/options/chains").json()["chains"][0]["chain_id"] == chain_id
    del main.app.state.orchestrator
