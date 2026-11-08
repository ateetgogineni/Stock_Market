"""Options Risk Management engine (options spec sections 5 and 8, agent 19).

Risk analysis is mandatory before a strategy is shown. This module:
1. independently re-checks the payoff engine by brute-force evaluation on a dense
   price grid (a different method from the exact kink analysis);
2. applies explicit risk rules that can REJECT a strategy;
3. sets the opportunity status. On synthetic or stale data it is always
   INSUFFICIENT_DATA: the platform never calls a trade an opportunity on such data.
"""

from __future__ import annotations

import math

from . import strategies as st

MAX_SPREAD_REJECT = 0.50
MAX_SPREAD_WARN = 0.10
MIN_OI = 50


def verify_payoff(legs: list[dict], units: int, exact: dict) -> dict:
    """Re-derive max profit/loss and break-evens numerically and compare with the exact engine."""
    strikes = [l["strike"] for l in legs if l["strike"] is not None]
    top = max(strikes + [l["fill"] for l in legs if l["type"] == "STOCK"])
    hi = top * 4
    n = 40_000
    xs = sorted({hi * i / n for i in range(n + 1)} | set(strikes))
    ys = [st.payoff(legs, x, units) for x in xs]
    grid_max, grid_min = max(ys), min(ys)
    # Unbounded if P&L keeps moving the same way far beyond the grid.
    far1, far2 = st.payoff(legs, hi * 10, units), st.payoff(legs, hi * 20, units)
    unlimited_profit = far2 > far1 + 1e-6 and far2 > grid_max
    unlimited_loss = far2 < far1 - 1e-6 and far2 < grid_min
    crossings = [xs[i] for i in range(1, len(xs)) if (ys[i - 1] < 0) != (ys[i] < 0)]
    step = hi / n
    tol = max(1.0, 1e-6 * max(abs(grid_max), abs(grid_min)))
    problems = []
    if exact["unlimited_profit"] != unlimited_profit:
        problems.append("unlimited-profit flag differs")
    if exact["unlimited_loss"] != unlimited_loss:
        problems.append("unlimited-loss flag differs")
    if not exact["unlimited_profit"] and abs(exact["max_profit"] - grid_max) > tol:
        problems.append(f"max profit {exact['max_profit']:.2f} vs grid {grid_max:.2f}")
    if not exact["unlimited_loss"] and abs(exact["max_loss"] - grid_min) > tol:
        problems.append(f"max loss {exact['max_loss']:.2f} vs grid {grid_min:.2f}")
    be = exact["breakevens"]
    if len(be) != len(crossings) or any(abs(a - b) > 2 * step + 0.01 for a, b in zip(be, crossings)):
        problems.append(f"break-evens {be} vs grid {[round(c, 2) for c in crossings]}")
    return {"method": f"brute-force evaluation at {len(xs)} prices from 0 to {hi:,.0f}, plus far-tail checks",
            "consistent": not problems, "problems": problems}


def assess(legs: list[dict], exact: dict, verification: dict, ctx: dict) -> dict:
    """Apply risk rules. ctx: data_type, data_fresh, days_to_expiry, settlement, iv_to_realised, underlying_type."""
    flags, rejections = [], []

    def flag(fid, severity, text):
        flags.append({"id": fid, "severity": severity, "text": text})

    if not verification["consistent"]:
        rejections.append("Independent payoff verification failed: " + "; ".join(verification["problems"]))
    for l in legs:
        if l["type"] == "STOCK":
            continue
        name = f"{l['side']} {l['strike']:g} {l['type']}"
        q = l["quote"]
        if l["fill"] is None:
            rejections.append(f"{name}: no {'ask' if l['side'] == 'buy' else 'bid'} price to trade against.")
            continue
        if q["spread_pct"] is not None and q["spread_pct"] > MAX_SPREAD_REJECT:
            rejections.append(f"{name}: bid-ask spread is {q['spread_pct']:.0%} of the mid price (extremely wide).")
        elif q["spread_pct"] is not None and q["spread_pct"] > MAX_SPREAD_WARN:
            flag("wide_spread", "medium", f"{name}: bid-ask spread is {q['spread_pct']:.0%} of the mid price.")
        if q["volume"] == 0 and q["oi"] < MIN_OI:
            rejections.append(f"{name}: illiquid (no volume and open interest {q['oi']}).")
        elif q["volume"] == 0:
            flag("no_volume", "medium", f"{name}: no trades in the session.")
        if q["iv"] is None:
            flag("no_iv", "medium", f"{name}: implied volatility unavailable ({q['iv_note']}); Greeks for this leg are missing.")

    if exact["unlimited_loss"]:
        flag("unlimited_loss", "critical", "UNLIMITED LOSS: losses grow without limit if the underlying keeps rising. "
             "Short options also need exchange margin and can be assigned.")
    elif exact["max_loss"] < 0 and exact["max_profit"] not in (math.inf,) and exact["max_profit"] > 0:
        rr = exact["max_profit"] / abs(exact["max_loss"])
        if rr < 0.33:
            flag("poor_reward", "medium", f"Maximum profit is only {rr:.2f}x the maximum loss.")
    if any(l["side"] == "sell" and l["type"] != "STOCK" for l in legs):
        flag("margin", "medium", "Short option legs need SPAN plus exposure margin, which is not calculated here.")
    dte = ctx["days_to_expiry"]
    if dte <= 2:
        flag("expiry_risk", "high", f"Only {dte:.1f} days to expiry: gamma is very high and premiums can go to zero quickly.")
    elif dte <= 7:
        flag("expiry_risk", "medium", f"{dte:.1f} days to expiry: time decay accelerates in the final week.")
    if ctx["settlement"] == "physical":
        flag("physical_settlement", "high", "Stock options on NSE settle by physical delivery: an in-the-money position at "
             "expiry means delivering or taking delivery of the shares, not just a cash difference.")
    ratio = ctx.get("iv_to_realised")
    if ratio is not None and ratio > 1.5:
        flag("high_iv", "medium", f"Implied volatility is {ratio:.1f}x the 1-year realised volatility: options are expensive.")
    flag("gap_risk", "low", "Prices can gap overnight past strikes and stop levels; expiry payoffs assume no early exit.")

    if ctx["data_type"] == "synthetic":
        opportunity = "INSUFFICIENT_DATA"
        reason = "The option chain is synthetic (no licensed NSE options feed is configured), so no trade opportunity can be assessed."
    elif not ctx["data_fresh"]:
        opportunity = "INSUFFICIENT_DATA"
        reason = "The option chain is stale."
    elif rejections:
        opportunity = "NO_SUITABLE_OPPORTUNITY"
        reason = "The strategy fails the risk rules."
    else:
        opportunity = "INSUFFICIENT_DATA"
        reason = "No validated opportunity model exists yet (options spec phase 9)."

    return {
        "verdict": "rejected" if rejections else ("passed_with_warnings" if any(f["severity"] in ("critical", "high", "medium") for f in flags) else "passed"),
        "rejections": rejections,
        "flags": sorted(flags, key=lambda f: ["critical", "high", "medium", "low"].index(f["severity"])),
        "opportunity_status": opportunity,
        "opportunity_reason": reason,
        "probability_estimates": "Not shown: no statistically validated probability model.",
    }
