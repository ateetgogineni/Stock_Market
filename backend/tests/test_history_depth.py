"""Short price histories: recent listings, provider gaps, and honest "1 year" labels."""

from app.services.analysis import compute_deterministic
from app.services.recommendation import INSUFFICIENT, rate
from tests.conftest import make_snapshot

SBIFUNDS = "IN:INE640G01020"  # listed on NSE on 2026-07-21 per the NSE master


def gate(det, gid):
    return next(g for g in det["gates"] if g["id"] == gid)


def test_recent_listing_is_explained_with_a_date():
    det = compute_deterministic(make_snapshot(instrument_id=SBIFUNDS, sessions=76))
    hist = det["price"]["history"]
    assert hist["listing_date"] == "2026-07-21" and hist["recently_listed"] is True
    assert hist["full_year_from"] > "2027-07-01"
    g = gate(det, "price_history_depth")
    assert not g["passed"] and g["affects"] == ["medium", "long"]
    assert "Listed on NSE on 2026-07-21" in g["message"] and hist["full_year_from"] in g["message"]

    r = rate(det, [])
    assert r["horizons"]["short"]["abstention_kind"] == "horizon_disabled"
    for h in ("medium", "long"):
        out = r["horizons"][h]
        assert out["rating"] == INSUFFICIENT and out["abstention_kind"] == "data"
        assert any("Listed on NSE on 2026-07-21" in s for s in out["abstention_reasons"])


def test_short_provider_history_for_an_old_listing_is_called_a_gap():
    det = compute_deterministic(make_snapshot(sessions=150))  # Reliance has been listed since 1995
    hist = det["price"]["history"]
    assert hist["recently_listed"] is False
    assert "price history is incomplete" in gate(det, "price_history_depth")["message"]
    assert "1995-11-29" in gate(det, "price_history_depth")["message"]


def test_one_year_risk_metrics_are_never_computed_on_a_shorter_window():
    det = compute_deterministic(make_snapshot(instrument_id=SBIFUNDS, sessions=76))
    ev = det["evidence"]
    assert ev["risk.max_drawdown_1y"]["status"] == "unavailable" and ev["risk.max_drawdown_1y"]["value"] is None
    assert "only 76 sessions" in ev["risk.max_drawdown_1y"]["display"]
    assert ev["risk.max_drawdown_full"]["status"] == "ok"  # labelled with its real start date
    assert det["metrics"]["max_drawdown_1y"]["value"] is None
    assert ev["risk.volatility_1y"]["value"] is None


def test_shorter_beta_and_var_windows_are_labelled_with_their_length():
    det = compute_deterministic(make_snapshot(sessions=180))
    assert det["evidence"]["risk.beta_1y"]["label"] == "Beta vs NIFTY 50, 179 sessions"
    assert det["evidence"]["risk.var95_1d"]["label"] == "1-day historical VaR (95%), 179 sessions"
    full = compute_deterministic(make_snapshot())
    assert full["evidence"]["risk.beta_1y"]["label"] == "Beta vs NIFTY 50, 1 year"
    assert full["price"]["history"]["full_year_from"] is None
