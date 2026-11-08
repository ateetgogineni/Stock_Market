"""Strategy builder and payoff engine (options spec sections 2.2, 3 and 5).

Payoffs at expiry are piecewise linear in the underlying price with kinks only
at strikes, so maximum profit, maximum loss and break-evens are found exactly:
evaluate the kinks, then use the slope beyond the highest strike to detect
unlimited profit or loss. The risk module re-checks every figure independently.
"""

from __future__ import annotations

import math

from . import pricing

TEMPLATES = {
    "long_call": {"label": "Long Call", "outlook": "bullish", "legs": [("buy", "CE", 0)],
                  "explain": "Buy a call. Profits if the underlying rises above strike plus premium; loss limited to the premium."},
    "bull_call_spread": {"label": "Bull Call Spread", "outlook": "bullish", "legs": [("buy", "CE", 0), ("sell", "CE", 1)],
                         "explain": "Buy a call and sell a higher call. Cheaper than a long call; profit and loss both capped."},
    "bull_put_spread": {"label": "Bull Put Spread", "outlook": "bullish", "legs": [("sell", "PE", 0), ("buy", "PE", -1)],
                        "explain": "Sell a put and buy a lower put for a net credit. Keeps the credit if the price stays above the short strike."},
    "covered_call": {"label": "Covered Call", "outlook": "mildly bullish", "legs": [("buy", "STOCK", 0), ("sell", "CE", 1)],
                     "explain": "Hold the shares and sell a call above the price. Earns premium but caps upside; downside is the stock's.",
                     "stock_only": True},
    "long_put": {"label": "Long Put", "outlook": "bearish", "legs": [("buy", "PE", 0)],
                 "explain": "Buy a put. Profits if the underlying falls below strike minus premium; loss limited to the premium."},
    "bear_put_spread": {"label": "Bear Put Spread", "outlook": "bearish", "legs": [("buy", "PE", 0), ("sell", "PE", -1)],
                        "explain": "Buy a put and sell a lower put. Cheaper than a long put; profit and loss both capped."},
    "bear_call_spread": {"label": "Bear Call Spread", "outlook": "bearish", "legs": [("sell", "CE", 0), ("buy", "CE", 1)],
                         "explain": "Sell a call and buy a higher call for a net credit. Keeps the credit if the price stays below the short strike."},
    "long_straddle": {"label": "Long Straddle", "outlook": "big move either way", "legs": [("buy", "CE", 0), ("buy", "PE", 0)],
                      "explain": "Buy a call and a put at the same strike. Needs a large move or a rise in volatility; loses to time decay."},
    "long_strangle": {"label": "Long Strangle", "outlook": "big move either way", "legs": [("buy", "CE", 1), ("buy", "PE", -1)],
                      "explain": "Buy an out-of-the-money call and put. Cheaper than a straddle but needs an even larger move."},
    "short_straddle": {"label": "Short Straddle", "outlook": "range-bound", "legs": [("sell", "CE", 0), ("sell", "PE", 0)],
                       "explain": "Sell a call and a put at the same strike. Earns time decay if the price stays near the strike. UNLIMITED LOSS on the upside."},
    "short_strangle": {"label": "Short Strangle", "outlook": "range-bound", "legs": [("sell", "CE", 1), ("sell", "PE", -1)],
                       "explain": "Sell an out-of-the-money call and put. Wider profit zone than a straddle. UNLIMITED LOSS on the upside."},
    "iron_condor": {"label": "Iron Condor", "outlook": "range-bound", "legs": [("sell", "PE", -1), ("buy", "PE", -2), ("sell", "CE", 1), ("buy", "CE", 2)],
                    "explain": "A short strangle with protective wings. Earns the credit inside the range; loss capped by the wings."},
    "iron_butterfly": {"label": "Iron Butterfly", "outlook": "range-bound", "legs": [("sell", "PE", 0), ("sell", "CE", 0), ("buy", "PE", -1), ("buy", "CE", 1)],
                       "explain": "A short straddle with protective wings. Higher credit than a condor, narrower profit zone, capped loss."},
}


class StrategyError(ValueError):
    pass


def build_legs(template: str, rows: list[dict], atm_strike: float, width: int, underlying_type: str,
               strikes: dict | None = None) -> list[dict]:
    """Choose strikes: offset n means n*width strikes away from ATM. `strikes` overrides by leg index."""
    spec = TEMPLATES.get(template)
    if spec is None:
        raise StrategyError(f"Unknown strategy {template!r}.")
    if spec.get("stock_only") and underlying_type != "stock":
        raise StrategyError(f"{spec['label']} needs the underlying shares; it is not available on an index.")
    if width < 1:
        raise StrategyError("Width must be at least one strike.")
    grid = [r["strike"] for r in rows]
    atm_i = grid.index(atm_strike)
    legs = []
    for i, (side, kind, offset) in enumerate(spec["legs"]):
        if kind == "STOCK":
            legs.append({"leg": i, "side": side, "type": "STOCK", "strike": None})
            continue
        chosen = (strikes or {}).get(str(i)) or (strikes or {}).get(i)
        if chosen is None:
            j = atm_i + offset * width
            if not 0 <= j < len(grid):
                raise StrategyError(f"Not enough strikes {'above' if offset > 0 else 'below'} the money for width {width}.")
            chosen = grid[j]
        if chosen not in grid:
            raise StrategyError(f"Strike {chosen} is not listed for this expiry.")
        legs.append({"leg": i, "side": side, "type": kind, "strike": chosen})
    return legs


def price_legs(legs: list[dict], rows: list[dict], spot: float) -> list[dict]:
    """Attach quotes and conservative fills: buy at the ask, sell at the bid."""
    by_strike = {r["strike"]: r for r in rows}
    out = []
    for leg in legs:
        if leg["type"] == "STOCK":
            out.append({**leg, "fill": spot, "fill_basis": "last close", "quote": None})
            continue
        quote = by_strike[leg["strike"]][leg["type"]]
        fill = quote["ask"] if leg["side"] == "buy" else quote["bid"]
        out.append({**leg, "quote": quote, "fill": fill if fill and fill > 0 else None,
                    "fill_basis": "ask" if leg["side"] == "buy" else "bid"})
    return out


def leg_payoff(leg: dict, S: float) -> float:
    """Per-unit P&L of one leg at expiry, including its entry price."""
    sign = 1 if leg["side"] == "buy" else -1
    if leg["type"] == "STOCK":
        value = S
    elif leg["type"] == "CE":
        value = max(S - leg["strike"], 0.0)
    else:
        value = max(leg["strike"] - S, 0.0)
    return sign * (value - leg["fill"])


def payoff(legs: list[dict], S: float, units: int) -> float:
    return units * sum(leg_payoff(l, S) for l in legs)


def analyse_payoff(legs: list[dict], units: int) -> dict:
    """Exact max profit, max loss and break-evens of a piecewise-linear expiry payoff."""
    kinks = sorted({0.0} | {l["strike"] for l in legs if l["strike"] is not None})
    values = [payoff(legs, k, units) for k in kinks]
    # Slope (per unit of underlying) beyond the highest strike: calls and stock keep their exposure.
    slope = units * sum((1 if l["side"] == "buy" else -1) for l in legs if l["type"] in ("CE", "STOCK"))
    upside_unbounded = slope != 0
    max_profit = math.inf if slope > 0 else max(values)
    max_loss = -math.inf if slope < 0 else min(values)
    breakevens = []
    for (a, va), (b, vb) in zip(zip(kinks, values), zip(kinks[1:], values[1:])):
        if va == 0:
            breakevens.append(a)
        elif va * vb < 0:
            breakevens.append(a + (b - a) * (-va) / (vb - va))
    last, vlast = kinks[-1], values[-1]
    if vlast == 0 and last not in breakevens:
        breakevens.append(last)
    elif slope != 0 and vlast * slope < 0:
        breakevens.append(last - vlast / slope)
    return {
        "max_profit": max_profit,
        "max_loss": max_loss,
        "unlimited_profit": max_profit == math.inf,
        "unlimited_loss": max_loss == -math.inf,
        "breakevens": sorted(round(b, 2) for b in breakevens),
        "slope_above_highest_strike": slope,
        "upside_unbounded": upside_unbounded,
        "kink_values": [{"price": k, "pnl": v} for k, v in zip(kinks, values)],
    }


def position_greeks(legs: list[dict], spot: float, T: float, r: float, q: float, units: int) -> dict:
    total = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    for l in legs:
        sign = 1 if l["side"] == "buy" else -1
        if l["type"] == "STOCK":
            total["delta"] += sign * units
            continue
        g = l["quote"]["greeks"]
        if not g:
            return {k: None for k in total} | {"note": f"No implied volatility for the {l['strike']} {l['type']} leg."}
        for k in total:
            total[k] += sign * units * g[k]
    return total


def value_before_expiry(legs: list[dict], S: float, T: float, r: float, q: float, units: int,
                        vol_shift: float = 0.0) -> float | None:
    """Theoretical P&L if the underlying were at S with T years left (each leg at its own IV + shift)."""
    total = 0.0
    for l in legs:
        sign = 1 if l["side"] == "buy" else -1
        if l["type"] == "STOCK":
            total += sign * (S - l["fill"])
            continue
        iv = l["quote"]["iv"]
        if iv is None:
            return None
        total += sign * (pricing.price(l["type"], S, l["strike"], max(T, 0.0), r, max(iv + vol_shift, 0.01), q) - l["fill"])
    return units * total


def curves(legs: list[dict], spot: float, T: float, r: float, q: float, units: int, points: int = 121) -> dict:
    """Payoff curves over a window sized by the expected move (about 3.5 standard deviations
    to expiry), always covering every strike, so short-dated payoffs stay readable."""
    strikes = [l["strike"] for l in legs if l["strike"] is not None] or [spot]
    ivs = [l["quote"]["iv"] for l in legs if l.get("quote") and l["quote"].get("iv")]
    sigma = sum(ivs) / len(ivs) if ivs else 0.25
    move = max(spot * sigma * math.sqrt(max(T, 1 / 365)) * 3.5, spot * 0.03)
    span = max(strikes) - min(strikes)
    lo = max(0.0, min(min(strikes) - 0.5 * span, spot - move))
    hi = max(max(strikes) + 0.5 * span, spot + move)
    xs = [lo + (hi - lo) * i / (points - 1) for i in range(points)]
    return {
        "prices": [round(x, 2) for x in xs],
        "expiry": [round(payoff(legs, x, units), 2) for x in xs],
        "today": [None if (v := value_before_expiry(legs, x, T, r, q, units)) is None else round(v, 2) for x in xs],
    }


def scenarios(legs: list[dict], spot: float, T: float, r: float, q: float, units: int) -> list[dict]:
    out = []
    days_left = T * 365
    for label, dt_days in (("today", 0), ("in 7 days", 7), ("at expiry", days_left)):
        if label == "in 7 days" and dt_days >= days_left:
            continue  # expiry comes first; the "at expiry" row covers it
        T2 = max(T - dt_days / 365, 0.0)
        for vol_shift in (-0.05, 0.0, 0.05):
            if T2 == 0 and vol_shift != 0:
                continue
            row = {"when": label, "vol_shift": vol_shift, "pnl": {}}
            for move in (-0.10, -0.05, 0.0, 0.05, 0.10):
                v = value_before_expiry(legs, spot * (1 + move), T2, r, q, units, vol_shift)
                row["pnl"][f"{move:+.0%}"] = None if v is None else round(v, 2)
            out.append(row)
    return out
