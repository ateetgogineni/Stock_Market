"""Trade decision engine: NO TRADE logic, gates, sizing, exclusions and the desk API."""

import copy
from datetime import date, datetime, timezone

import numpy as np
import pytest

from app.options import contracts, decision, direction, service
from tests.test_options_direction import bars, trend
from tests.test_options_engine import NOW, ScaledFixture

OPEN = {"status": "open"}


@pytest.fixture(scope="module")
def chain():
    snap = service.build_snapshot("NIFTY", ScaledFixture(25030.35), now=NOW)
    # Use the 2026-11-17 expiry (11 days) so time-to-expiry rules don't dominate.
    return service.chain_view(snap, "2026-11-17")


def master(chain):
    spec = contracts.expiry_spec("NIFTY", chain["expiry"])
    return set(spec["strikes"]), spec["lot_size"]


def bullish():
    d = direction.analyse(bars([25030.35 / 1.004 ** (259 - i) for i in range(260)]), bars([14.0] * 30), {}, None, positioning_real=False)
    assert d["label"] in ("Bullish", "Strong Bullish")
    return d


def as_live(chain):
    """Pretend the chain came from a licensed feed during market hours, to exercise the post-gate logic."""
    live = copy.deepcopy(chain)
    live["data_type"] = "licensed"
    return live, datetime.fromisoformat(live["created_at"])


def test_synthetic_chain_is_always_no_trade_with_a_dry_run(chain):
    strikes, lot = master(chain)
    out = decision.decide(chain, bullish(), 50000, strikes, lot, OPEN, datetime.fromisoformat(chain["created_at"]))
    assert out["status"] == "NO TRADE"
    assert "synthetic" in out["status_reason"]
    assert out["dry_run"] is True and out["best"] is not None
    assert not next(g for g in out["data_gates"] if g["check"] == "Live option prices")["passed"]


def test_market_closed_blocks_a_fresh_signal(chain):
    strikes, lot = master(chain)
    live, now = as_live(chain)
    out = decision.decide(live, bullish(), 50000, strikes, lot, {"status": "closed_weekend"}, now)
    assert out["status"] == "NO TRADE" and "closed" in out["status_reason"]


def test_stale_quotes_block_the_signal(chain):
    strikes, lot = master(chain)
    live, now = as_live(chain)
    later = datetime.fromtimestamp(now.timestamp() + 600, tz=timezone.utc)
    out = decision.decide(live, bullish(), 50000, strikes, lot, OPEN, later)
    assert out["status"] == "NO TRADE"
    assert not next(g for g in out["data_gates"] if g["check"] == "Quote freshness")["passed"]


def test_live_bullish_desk_only_recommends_long_premium_within_budget(chain):
    strikes, lot = master(chain)
    live, now = as_live(chain)
    budget = 50000
    out = decision.decide(live, bullish(), budget, strikes, lot, OPEN, now)
    assert out["status"] in decision.RULES["statuses"]
    for c in out["candidates"]:
        if any(l["side"] == "sell" for l in c["legs"]):
            assert not c["eligible"] and any("Margin requirement unavailable" in e for e in c["exclusions"])
    best = out["best"]
    if out["status"] not in ("NO TRADE",):
        assert best["strategy"] == "BUY_CE"
        sz = best["sizing"]
        assert sz["lots"] >= 1 and sz["max_loss_total"] <= budget
        assert best["verification"]["consistent"]
        assert best["stop"]["pnl_per_lot"] < 0 < best["targets"][0]["pnl_per_lot"] < best["targets"][1]["pnl_per_lot"]
        assert best["entry"]["zone"][0] <= best["entry"]["zone"][1]


def test_budget_below_one_lot_is_no_trade(chain):
    strikes, lot = master(chain)
    live, now = as_live(chain)
    out = decision.decide(live, bullish(), 500, strikes, lot, OPEN, now)
    assert out["status"] == "NO TRADE"
    assert all(not c["eligible"] for c in out["candidates"])
    assert any("Risk budget" in e for c in out["candidates"] for e in c["exclusions"])


def test_uncertain_market_waits(chain):
    strikes, lot = master(chain)
    live, now = as_live(chain)
    d = {**bullish(), "label": "High Volatility / Uncertain"}
    out = decision.decide(live, d, 50000, strikes, lot, OPEN, now)
    assert out["status"] == "WAIT FOR CONFIRMATION" and out["candidates"] == []


def test_insufficient_direction_is_no_trade(chain):
    strikes, lot = master(chain)
    d = direction.analyse(bars(trend(n=50)), None, {}, None, positioning_real=False)
    out = decision.decide(chain, d, 50000, strikes, lot, OPEN)
    assert out["status"] == "NO TRADE" and out["best"] is None


def test_unlimited_loss_never_eligible(chain):
    strikes, lot = master(chain)
    live, now = as_live(chain)
    d = {**bullish(), "label": "Strong Bearish"}
    out = decision.decide(live, d, 10_000_000, strikes, lot, OPEN, now)
    sell_ce = next(c for c in out["candidates"] if c["strategy"] == "SELL_CE")
    assert sell_ce["unlimited_loss"] and not sell_ce["eligible"]


def test_strike_comparison_respects_delta_band(chain):
    ranked = decision.strike_comparison(chain["rows"], "CE", True, 300.0, chain["summary"]["atm_iv"])
    assert ranked and all(0.30 <= abs(r["delta"]) <= 0.70 for r in ranked)
    assert [r["score"] for r in ranked] == sorted((r["score"] for r in ranked), reverse=True)
    assert decision.why_selected(ranked).startswith(f"{ranked[0]['strike']:,.0f} CE")


def test_desk_api_runs_and_logs_signals(tmp_path):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app import main
    from app.db import Database
    from app.services.orchestrator import Orchestrator

    db = Database(f"sqlite:///{tmp_path / 'd.db'}")
    db.create_all()
    settings = SimpleNamespace(data_dir=tmp_path, agents_enabled=False, agent_timeout_seconds=5, agent_max_tokens=10, agent_model="x")
    main.app.state.orchestrator = Orchestrator(db, settings, provider_factory=lambda: ScaledFixture(25030.35), llm_factory=lambda: None)
    with TestClient(main.app) as client:
        idx = client.get("/api/options/desk/indices").json()["indices"]
        assert idx[0]["symbol"] == "NIFTY" and idx[0]["supported"]
        assert any(not i["supported"] for i in idx)  # FINNIFTY etc. listed but unavailable
        out = client.post("/api/options/desk", json={"symbol": "NIFTY", "budget": 40000}).json()
        assert out["decision"]["status"] == "NO TRADE" and out["header"]["data_type"] == "synthetic"
        assert out["chain"]["rows"] and out["direction"]["components"]
        assert client.post("/api/options/desk", json={"symbol": "RELIANCE"}).status_code == 404
        assert client.post("/api/options/desk", json={"symbol": "FINNIFTY"}).status_code == 422
        sig = client.get("/api/options/signals").json()
        assert sig["signals"][0]["signal_id"] == out["signal_id"] and sig["signals"][0]["mode"] == "dry_run"
        assert sig["counts"]["NO TRADE"] == 1
    del main.app.state.orchestrator
