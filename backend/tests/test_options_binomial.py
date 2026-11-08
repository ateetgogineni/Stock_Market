"""Independent pricing check: our CRR lattice vs our Black-Scholes, and both vs Quantsbin (a third-party library)."""

import os

import pytest

from app.options import pricing


@pytest.mark.parametrize("kind", ["CE", "PE"])
@pytest.mark.parametrize("S,K,T,r,sigma,q", [(100, 100, 1.0, 0.06, 0.2, 0.0), (24000, 24500, 30 / 365, 0.06, 0.13, 0.012),
                                               (52000, 50000, 7 / 365, 0.065, 0.18, 0.0), (1500, 1800, 0.5, 0.06, 0.35, 0.0)])
def test_binomial_converges_to_black_scholes(kind, S, K, T, r, sigma, q):
    bsm = pricing.price(kind, S, K, T, r, sigma, q)
    lat = pricing.binomial_price(kind, S, K, T, r, sigma, q, steps=800)
    assert lat == pytest.approx(bsm, rel=2e-3, abs=0.02)


def test_american_put_is_worth_at_least_the_european():
    eu = pricing.binomial_price("PE", 100, 110, 1.0, 0.08, 0.25)
    am = pricing.binomial_price("PE", 100, 110, 1.0, 0.08, 0.25, american=True)
    assert am > eu


def test_put_call_parity_gap_is_zero_for_bsm():
    c, p = pricing.price("CE", 24000, 24100, 0.1, 0.06, 0.14, 0.01), pricing.price("PE", 24000, 24100, 0.1, 0.06, 0.14, 0.01)
    assert abs(pricing.parity_gap(c, p, 24000, 24100, 0.1, 0.06, 0.01)) < 1e-8


def test_cross_check_against_quantsbin():
    os.environ.setdefault("MPLBACKEND", "Agg")
    qbdp = pytest.importorskip("quantsbin.derivativepricing")
    cases = [("Call", "CE", 100, 100, 0.2), ("Put", "PE", 100, 95, 0.3), ("Call", "CE", 24000, 24500, 0.14)]
    for qb_kind, kind, S, K, vol in cases:
        opt = qbdp.EqOption(option_type=qb_kind, strike=K, expiry_date="20271108", expiry_type="European")
        theirs_bsm = opt.engine(model="BSM", pricing_date="20261108", spot0=S, rf_rate=0.06, volatility=vol).valuation()
        theirs_lat = opt.engine(model="Binomial", pricing_date="20261108", spot0=S, rf_rate=0.06, volatility=vol,
                                no_of_steps=500).valuation()
        assert pricing.price(kind, S, K, 1.0, 0.06, vol) == pytest.approx(theirs_bsm, rel=1e-6)
        assert pricing.binomial_price(kind, S, K, 1.0, 0.06, vol) == pytest.approx(theirs_lat, rel=2e-3)
