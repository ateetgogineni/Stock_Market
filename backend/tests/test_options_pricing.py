"""Black-Scholes-Merton prices, Greeks and implied volatility.

Reference values: Hull, "Options, Futures, and Other Derivatives", worked examples
(European call/put pricing and the Greeks example). Greeks are also checked against
independent finite differences of the price function.
"""

import math

import pytest

from app.options.pricing import greeks, implied_vol, no_arbitrage_bounds, price


def test_hull_pricing_example():
    # S=42, K=40, r=10%, sigma=20%, T=0.5 -> c = 4.76, p = 0.81
    assert price("CE", 42, 40, 0.5, 0.10, 0.20) == pytest.approx(4.76, abs=0.005)
    assert price("PE", 42, 40, 0.5, 0.10, 0.20) == pytest.approx(0.81, abs=0.005)


def test_hull_greeks_example():
    # S=49, K=50, r=5%, sigma=20%, T=20 weeks: price 2.40, delta 0.522, gamma 0.066,
    # theta -4.31 per year, vega 12.1 per 1.00 vol, rho 8.91 per 1.00 rate
    g = greeks("CE", 49, 50, 0.3846, 0.05, 0.20)
    assert g.price == pytest.approx(2.40, abs=0.01)
    assert g.delta == pytest.approx(0.522, abs=0.001)
    assert g.gamma == pytest.approx(0.066, abs=0.001)
    assert g.theta * 365 == pytest.approx(-4.31, abs=0.01)
    assert g.vega * 100 == pytest.approx(12.1, abs=0.05)
    assert g.rho * 100 == pytest.approx(8.91, abs=0.01)


@pytest.mark.parametrize("S,K,T,r,sigma,q", [(25000, 25500, 0.05, 0.06, 0.14, 0.0), (1300, 1200, 0.3, 0.065, 0.28, 0.004),
                                              (59000, 52000, 0.9, 0.06, 0.18, 0.012), (100, 160, 0.02, 0.05, 0.9, 0.0)])
def test_put_call_parity(S, K, T, r, sigma, q):
    lhs = price("CE", S, K, T, r, sigma, q) - price("PE", S, K, T, r, sigma, q)
    assert lhs == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T), abs=1e-8 * S)


@pytest.mark.parametrize("kind", ["CE", "PE"])
@pytest.mark.parametrize("S,K,T,r,sigma,q", [(25000, 25500, 0.05, 0.06, 0.14, 0.0), (1300, 1200, 0.3, 0.065, 0.28, 0.004)])
def test_greeks_match_finite_differences(kind, S, K, T, r, sigma, q):
    g = greeks(kind, S, K, T, r, sigma, q)
    h = S * 1e-4
    p = lambda **kw: price(kind, kw.get("S", S), K, kw.get("T", T), kw.get("r", r), kw.get("sigma", sigma), q)
    assert g.delta == pytest.approx((p(S=S + h) - p(S=S - h)) / (2 * h), rel=1e-5, abs=1e-7)
    assert g.gamma == pytest.approx((p(S=S + h) - 2 * p() + p(S=S - h)) / h**2, rel=1e-3, abs=1e-8)
    assert g.vega == pytest.approx((p(sigma=sigma + 1e-4) - p(sigma=sigma - 1e-4)) / 2e-4 / 100, rel=1e-5)
    assert g.rho == pytest.approx((p(r=r + 1e-5) - p(r=r - 1e-5)) / 2e-5 / 100, rel=1e-5)
    dt = 1 / 365
    assert g.theta == pytest.approx(p(T=T - dt) - p(), rel=2e-2)  # one calendar day of decay


def test_expired_and_zero_vol_options_are_intrinsic():
    assert price("CE", 105, 100, 0, 0.06, 0.2) == 5
    assert price("PE", 105, 100, 0, 0.06, 0.2) == 0
    g = greeks("PE", 95, 100, 0, 0.06, 0.2)
    assert g.delta == -1.0 and g.gamma == 0.0 and g.vega == 0.0


@pytest.mark.parametrize("kind", ["CE", "PE"])
@pytest.mark.parametrize("K", [20000, 23500, 25000, 26500, 30000])
@pytest.mark.parametrize("sigma", [0.08, 0.15, 0.45])
def test_implied_vol_round_trip(kind, K, sigma):
    S, T, r, q = 25000, 30 / 365, 0.06, 0.0
    target = price(kind, S, K, T, r, sigma, q)
    lower, _ = no_arbitrage_bounds(kind, S, K, T, r, q)
    if target - lower < 1e-6:
        pytest.skip("no time value at this strike and volatility")
    iv, reason = implied_vol(kind, target, S, K, T, r, q)
    assert reason is None
    assert iv == pytest.approx(sigma, abs=1e-6)


def test_implied_vol_rejects_arbitrage_prices():
    S, K, T, r = 100, 90, 0.25, 0.05
    lower, upper = no_arbitrage_bounds("CE", S, K, T, r)
    iv, reason = implied_vol("CE", lower - 0.5, S, K, T, r)
    assert iv is None and "intrinsic" in reason
    iv, reason = implied_vol("CE", upper + 1, S, K, T, r)
    assert iv is None and "upper bound" in reason
    iv, reason = implied_vol("CE", 5, S, K, 0, r)
    assert iv is None and "expired" in reason
