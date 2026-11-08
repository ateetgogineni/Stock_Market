"""Options pricing and Greeks (options spec section 4).

Black-Scholes-Merton for European options with a continuous dividend yield.
NSE index and stock options are European, so the model fits their exercise
style; its assumptions (constant volatility and rate, lognormal prices, no
jumps) are stored with every result because Greeks are estimates, not guarantees.

Units used everywhere:
* time T in years, ACT/365 calendar days;
* theta per calendar day;
* vega per 1 volatility point (0.01);
* rho per 1 percentage point of interest rate (0.01).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

MODEL = {
    "id": "black-scholes-merton",
    "version": "1.0",
    "assumptions": "European exercise; lognormal underlying; constant volatility, rate and continuous dividend "
                   "yield over the option's life; ACT/365 calendar time; no transaction costs.",
    "units": {"theta": "per calendar day", "vega": "per 1 vol point", "rho": "per 1% rate"},
}

SQRT_2PI = math.sqrt(2 * math.pi)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    theta: float  # per calendar day
    vega: float  # per vol point
    rho: float  # per 1% rate

    def as_dict(self) -> dict:
        return asdict(self)


def _check(kind: str, S: float, K: float) -> None:
    if kind not in ("CE", "PE"):
        raise ValueError("kind must be CE or PE")
    if S <= 0 or K <= 0:
        raise ValueError("spot and strike must be positive")


def intrinsic(kind: str, S: float, K: float) -> float:
    return max(S - K, 0.0) if kind == "CE" else max(K - S, 0.0)


def price(kind: str, S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    _check(kind, S, K)
    if T <= 0 or sigma <= 0:
        # At expiry (or with zero volatility) the option is worth its discounted forward intrinsic value.
        if T <= 0:
            return intrinsic(kind, S, K)
        fwd = S * math.exp(-q * T) - K * math.exp(-r * T)
        return max(fwd, 0.0) if kind == "CE" else max(-fwd, 0.0)
    vs = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vs
    d2 = d1 - vs
    df_q, df_r = math.exp(-q * T), math.exp(-r * T)
    if kind == "CE":
        return S * df_q * norm_cdf(d1) - K * df_r * norm_cdf(d2)
    return K * df_r * norm_cdf(-d2) - S * df_q * norm_cdf(-d1)


def greeks(kind: str, S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> Greeks:
    _check(kind, S, K)
    if T <= 0 or sigma <= 0:
        p = price(kind, S, K, T, r, sigma, q)
        itm = (S > K) if kind == "CE" else (S < K)
        delta = (1.0 if kind == "CE" else -1.0) if itm else 0.0
        return Greeks(p, delta, 0.0, 0.0, 0.0, 0.0)
    sqrt_t = math.sqrt(T)
    vs = sigma * sqrt_t
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vs
    d2 = d1 - vs
    df_q, df_r = math.exp(-q * T), math.exp(-r * T)
    pdf = norm_pdf(d1)
    gamma = df_q * pdf / (S * vs)
    vega = S * df_q * pdf * sqrt_t
    decay = -S * df_q * pdf * sigma / (2 * sqrt_t)
    if kind == "CE":
        p = S * df_q * norm_cdf(d1) - K * df_r * norm_cdf(d2)
        delta = df_q * norm_cdf(d1)
        theta = decay - r * K * df_r * norm_cdf(d2) + q * S * df_q * norm_cdf(d1)
        rho = K * T * df_r * norm_cdf(d2)
    else:
        p = K * df_r * norm_cdf(-d2) - S * df_q * norm_cdf(-d1)
        delta = df_q * (norm_cdf(d1) - 1.0)
        theta = decay + r * K * df_r * norm_cdf(-d2) - q * S * df_q * norm_cdf(-d1)
        rho = -K * T * df_r * norm_cdf(-d2)
    return Greeks(p, delta, gamma, theta / 365.0, vega / 100.0, rho / 100.0)


def no_arbitrage_bounds(kind: str, S: float, K: float, T: float, r: float, q: float = 0.0) -> tuple[float, float]:
    df_q, df_r = math.exp(-q * T), math.exp(-r * T)
    if kind == "CE":
        return max(S * df_q - K * df_r, 0.0), S * df_q
    return max(K * df_r - S * df_q, 0.0), K * df_r


def implied_vol(kind: str, market_price: float, S: float, K: float, T: float, r: float, q: float = 0.0,
                lo: float = 1e-4, hi: float = 5.0, tol: float = 1e-10, max_iter: int = 300) -> tuple[float | None, str | None]:
    """Volatility that reproduces `market_price`. Returns (iv, None) or (None, reason).

    Safeguarded Newton: a Newton step is taken when it stays inside the current bracket,
    otherwise the bracket is bisected, so the solver always converges for prices inside
    the no-arbitrage bounds.
    """
    _check(kind, S, K)
    if T <= 0:
        return None, "option has expired"
    if market_price is None or market_price <= 0:
        return None, "no positive price"
    lower, upper = no_arbitrage_bounds(kind, S, K, T, r, q)
    if market_price <= lower + 1e-9:
        return None, "price at or below intrinsic value: no time value to imply a volatility from"
    if market_price >= upper:
        return None, "price above the no-arbitrage upper bound"
    f_lo = price(kind, S, K, T, r, lo, q) - market_price
    f_hi = price(kind, S, K, T, r, hi, q) - market_price
    if f_lo > 0:
        return None, f"price implies volatility below {lo:.4f}"
    if f_hi < 0:
        return None, f"price implies volatility above {hi:.0%}"
    sigma = 0.3
    for _ in range(max_iter):
        diff = price(kind, S, K, T, r, sigma, q) - market_price
        # Absolute price tolerance plus a bracket-width stop: deep in-the-money options have
        # almost no vega, so a relative price test would stop far from the true volatility.
        if abs(diff) < tol or hi - lo < 1e-12:
            return sigma, None
        if diff > 0:
            hi = sigma
        else:
            lo = sigma
        v = greeks(kind, S, K, T, r, sigma, q).vega * 100.0
        step = sigma - diff / v if v > 1e-12 else None
        sigma = step if step is not None and lo < step < hi else 0.5 * (lo + hi)
    return sigma, None


BINOMIAL_MODEL = {"id": "cox-ross-rubinstein", "version": "1.0", "steps": 500,
                  "use": "Independent cross-check of Black-Scholes prices; never used to quote or size trades."}


def binomial_price(kind: str, S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
                   steps: int = 500, american: bool = False) -> float:
    """Cox-Ross-Rubinstein lattice. For European options it converges to Black-Scholes as steps grow,
    so a large gap between the two flags a pricing or input error. Written independently of `price`."""
    _check(kind, S, K)
    if T <= 0 or sigma <= 0:
        return price(kind, S, K, T, r, sigma, q)
    dt = T / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not 0 < p < 1:
        raise ValueError("binomial step too coarse for these inputs")
    disc = math.exp(-r * dt)
    sign = 1 if kind == "CE" else -1
    values = [max(sign * (S * u ** (steps - 2 * j) - K), 0.0) for j in range(steps + 1)]
    for n in range(steps - 1, -1, -1):
        for j in range(n + 1):
            v = disc * (p * values[j] + (1 - p) * values[j + 1])
            if american:
                v = max(v, sign * (S * u ** (n - 2 * j) - K))
            values[j] = v
    return values[0]


def parity_gap(call: float, put: float, S: float, K: float, T: float, r: float, q: float = 0.0) -> float:
    """C - P - (S e^-qT - K e^-rT); zero for consistent European prices."""
    return call - put - (S * math.exp(-q * T) - K * math.exp(-r * T))
