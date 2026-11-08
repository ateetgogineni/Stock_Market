"""Index options trade decision engine (module 2, sections 6-10; agents 23-27).

Pipeline: direction -> playbook of candidate trades -> strike selection ->
pricing at conservative fills -> exact payoff + independent re-verification ->
model-based stop-loss and targets -> budget-capped sizing -> draft quality grade
-> final verification gates -> one decision status.

The engine never forces a trade. Market-data gates (synthetic or stale quotes,
market closed) and missing margin data are hard stops, and the rule set is a
draft that runs in paper mode until historical evaluation approves it. On a
synthetic chain the result is NO TRADE; the best candidate is returned only as
a clearly labelled dry run.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

from . import pricing, risk
from . import strategies as st

RULES = {
    "version": "trade-rules-0.1-draft",
    "validation_status": "draft_unvalidated",
    "paper_mode": True,
    "buy_delta": {"strong": 0.55, "normal": 0.45, "min": 0.30, "max": 0.70},
    "short_delta": 0.30,
    "condor_delta": 0.20,
    "liquidity": {"max_spread_pct": 0.05, "good_spread_pct": 0.02, "min_oi": 500, "good_oi": 1000},
    "chain_max_age_minutes": 5,
    "levels_atr": {"stop": 1.0, "t1": 1.0, "t2": 2.0},
    "grade": {"high": 7, "moderate": 5, "low": 3},
    "statuses": ["HIGH-QUALITY SETUP", "MODERATE SETUP", "LOW-QUALITY SETUP", "WAIT FOR CONFIRMATION", "NO TRADE"],
}

PLAYBOOK = {
    "Strong Bullish": ["BUY_CE", "bull_call_spread", "bull_put_spread", "SELL_PE"],
    "Bullish": ["bull_call_spread", "BUY_CE", "bull_put_spread", "SELL_PE"],
    "Neutral": ["iron_condor", "bull_put_spread", "bear_call_spread"],
    "Bearish": ["bear_put_spread", "BUY_PE", "bear_call_spread", "SELL_CE"],
    "Strong Bearish": ["BUY_PE", "bear_put_spread", "bear_call_spread", "SELL_CE"],
    "High Volatility / Uncertain": [],
}
LABELS = {
    "BUY_CE": ("BUY CE", "bullish"), "BUY_PE": ("BUY PE", "bearish"), "SELL_CE": ("SELL CE", "bearish"),
    "SELL_PE": ("SELL PE", "bullish"), "bull_call_spread": ("Bull Call Spread", "bullish"),
    "bear_put_spread": ("Bear Put Spread", "bearish"), "bull_put_spread": ("Bull Put Spread", "bullish"),
    "bear_call_spread": ("Bear Call Spread", "bearish"), "iron_condor": ("Iron Condor", "neutral"),
}


# ---------------------------------------------------------------- strike selection (agent 23)

def strike_comparison(rows: list[dict], kind: str, strong: bool, atr: float, atm_iv: float | None) -> list[dict]:
    """Rank buyable strikes of one type. Higher score is better; every input is shown."""
    b = RULES["buy_delta"]
    target = b["strong"] if strong else b["normal"]
    out = []
    for r in rows:
        q = r[kind]
        g = q.get("greeks")
        if not g or q["bid"] <= 0 or q["ask"] <= 0 or not q.get("mid"):
            continue
        dlt = abs(g["delta"])
        if not b["min"] <= dlt <= b["max"]:
            continue
        gain = dlt * atr + 0.5 * g["gamma"] * atr * atr  # premium gain for a one-ATR move in our favour
        edge = gain / q["ask"]
        decay = abs(g["theta"]) / q["mid"]
        spread = q["spread_pct"] or 0.0
        iv_ratio = (q["iv"] / atm_iv) if q.get("iv") and atm_iv else 1.0
        score = (1.0 - 3 * abs(dlt - target) + min(edge, 0.8) - 4 * decay - 8 * spread
                 + 0.05 * math.log10(q["oi"] + 1) - 0.5 * max(iv_ratio - 1.1, 0))
        out.append({"strike": r["strike"], "type": kind, "delta": g["delta"], "gamma": g["gamma"], "theta": g["theta"],
                    "vega": g["vega"], "iv": q["iv"], "bid": q["bid"], "ask": q["ask"], "mid": q["mid"], "spread_pct": spread,
                    "oi": q["oi"], "volume": q["volume"], "one_atr_gain_pct": edge, "decay_pct_per_day": decay,
                    "iv_vs_atm": iv_ratio, "score": round(score, 4)})
    out.sort(key=lambda x: -x["score"])
    return out[:6]


def why_selected(ranked: list[dict]) -> str | None:
    if not ranked:
        return None
    best = ranked[0]
    text = (f"{best['strike']:,.0f} {best['type']}: delta {abs(best['delta']):.2f}, spread {best['spread_pct']:.1%}, "
            f"decay {best['decay_pct_per_day']:.1%} of premium a day, a one-ATR move adds about {best['one_atr_gain_pct']:.0%}.")
    if len(ranked) > 1:
        alt = ranked[1]
        reasons = []
        if alt["decay_pct_per_day"] > best["decay_pct_per_day"]:
            reasons.append("faster time decay")
        if alt["spread_pct"] > best["spread_pct"]:
            reasons.append("a wider spread")
        if alt["one_atr_gain_pct"] < best["one_atr_gain_pct"]:
            reasons.append("less upside per rupee")
        if abs(abs(alt["delta"]) - abs(best["delta"])) > 0.05:
            reasons.append("a delta further from the target")
        text += f" Runner-up {alt['strike']:,.0f} {alt['type']} has {', '.join(reasons) or 'a slightly lower combined score'}."
    return text


# ------------------------------------------------------------------ candidate building

def _grid(rows):
    return [r["strike"] for r in rows]


def _nearest(grid, value):
    return min(grid, key=lambda k: abs(k - value))


def _by_delta(rows, kind, target, side_of_spot, spot):
    cands = [r for r in rows if r[kind].get("greeks") and (r["strike"] < spot if side_of_spot == "below" else r["strike"] > spot)]
    if not cands:
        return None
    return min(cands, key=lambda r: abs(abs(r[kind]["greeks"]["delta"]) - target))["strike"]


def _offset(grid, strike, distance, direction):
    target = strike + direction * distance
    options = [k for k in grid if (k > strike if direction > 0 else k < strike)]
    return min(options, key=lambda k: abs(k - target)) if options else None


def build_legs(name: str, rows: list[dict], spot: float, atr: float, best: dict) -> list[dict] | None:
    grid = _grid(rows)
    L = lambda side, kind, k: {"side": side, "type": kind, "strike": k}  # noqa: E731
    ce, pe = best.get("CE"), best.get("PE")
    sd, cd = RULES["short_delta"], RULES["condor_delta"]
    if name == "BUY_CE":
        return [L("buy", "CE", ce)] if ce else None
    if name == "BUY_PE":
        return [L("buy", "PE", pe)] if pe else None
    if name == "SELL_PE":
        k = _by_delta(rows, "PE", sd, "below", spot)
        return [L("sell", "PE", k)] if k else None
    if name == "SELL_CE":
        k = _by_delta(rows, "CE", sd, "above", spot)
        return [L("sell", "CE", k)] if k else None
    if name == "bull_call_spread" and ce:
        short = _offset(grid, ce, 2 * atr, +1)
        return [L("buy", "CE", ce), L("sell", "CE", short)] if short else None
    if name == "bear_put_spread" and pe:
        short = _offset(grid, pe, 2 * atr, -1)
        return [L("buy", "PE", pe), L("sell", "PE", short)] if short else None
    if name == "bull_put_spread":
        short = _by_delta(rows, "PE", sd, "below", spot)
        long = _offset(grid, short, atr, -1) if short else None
        return [L("sell", "PE", short), L("buy", "PE", long)] if long else None
    if name == "bear_call_spread":
        short = _by_delta(rows, "CE", sd, "above", spot)
        long = _offset(grid, short, atr, +1) if short else None
        return [L("sell", "CE", short), L("buy", "CE", long)] if long else None
    if name == "iron_condor":
        sp, sc = _by_delta(rows, "PE", cd, "below", spot), _by_delta(rows, "CE", cd, "above", spot)
        lp = _offset(grid, sp, atr, -1) if sp else None
        lc = _offset(grid, sc, atr, +1) if sc else None
        if None in (sp, sc, lp, lc):
            return None
        return [L("sell", "PE", sp), L("buy", "PE", lp), L("sell", "CE", sc), L("buy", "CE", lc)]
    return None


def _value(legs, S, T, r, q):
    """Theoretical value per unit of the whole position (long legs positive, short legs negative)."""
    total = 0.0
    for l in legs:
        iv = l["quote"]["iv"]
        if iv is None:
            return None
        sign = 1 if l["side"] == "buy" else -1
        total += sign * pricing.price(l["type"], S, l["strike"], max(T, 0.0), r, iv, q)
    return total


def evaluate_candidate(name: str, rows: list[dict], ctx: dict, best_strikes: dict, budget: float) -> dict | None:
    spot, T, r, q, lot, atr = ctx["spot"], ctx["T"], ctx["r"], ctx["q"], ctx["lot"], ctx["atr"]
    legs = build_legs(name, rows, spot, atr, best_strikes)
    if not legs:
        return None
    label, bias = LABELS[name]
    priced = st.price_legs([{**l, "leg": i} for i, l in enumerate(legs)], rows, spot)
    exclusions = []
    if any(l["fill"] is None for l in priced):
        exclusions.append("A leg has no tradable bid/ask.")
        return {"strategy": name, "label": label, "bias": bias, "legs": _legs_out(priced), "eligible": False, "exclusions": exclusions}

    exact = st.analyse_payoff(priced, lot)
    verification = risk.verify_payoff(priced, lot, exact)
    assessment = risk.assess(priced, exact, verification, {**ctx["risk_ctx"], "data_type": "licensed", "data_fresh": True})
    entry = sum((1 if l["side"] == "buy" else -1) * l["fill"] for l in priced)  # >0 debit, <0 credit
    mid_entry = sum((1 if l["side"] == "buy" else -1) * (l["quote"]["mid"] or l["fill"]) for l in priced)
    kind = "debit" if entry > 0 else "credit"

    a = RULES["levels_atr"]
    T_hit = max(T - 1 / 365, T * 0.5)
    lv = ctx["levels"]
    if bias == "bullish":
        stop_lvl, t1_lvl, t2_lvl = spot - a["stop"] * atr, spot + a["t1"] * atr, spot + a["t2"] * atr
    elif bias == "bearish":
        stop_lvl, t1_lvl, t2_lvl = spot + a["stop"] * atr, spot - a["t1"] * atr, spot - a["t2"] * atr
    else:
        shorts = [l["strike"] for l in priced if l["side"] == "sell"]
        stop_lvl, t1_lvl, t2_lvl = (min(shorts), max(shorts)), None, None

    def pnl_at(level):
        v = _value(priced, level, T_hit, r, q)
        return None if v is None else (v - entry) * lot

    if bias == "neutral":
        sl_pnls = [pnl_at(x) for x in stop_lvl]
        sl_pnl = min(p for p in sl_pnls if p is not None) if all(p is not None for p in sl_pnls) else None
        t1_pnl, t2_pnl = abs(entry) * 0.5 * lot, abs(entry) * 0.75 * lot
        stop = {"index_level": list(stop_lvl), "pnl_per_lot": sl_pnl, "rule": "close if the index reaches either short strike"}
        targets = [{"index_level": None, "pnl_per_lot": t1_pnl, "rule": "buy back at 50% of the credit"},
                   {"index_level": None, "pnl_per_lot": t2_pnl, "rule": "buy back at 25% of the credit"}]
    else:
        sl_pnl, t1_pnl, t2_pnl = pnl_at(stop_lvl), pnl_at(t1_lvl), pnl_at(t2_lvl)
        stop = {"index_level": stop_lvl, "pnl_per_lot": sl_pnl, "value": None if sl_pnl is None else entry + sl_pnl / lot,
                "rule": f"index moves {a['stop']:g} ATR against the trade"}
        targets = [{"index_level": t1_lvl, "pnl_per_lot": t1_pnl, "value": None if t1_pnl is None else entry + t1_pnl / lot, "rule": "index moves 1 ATR in favour"},
                   {"index_level": t2_lvl, "pnl_per_lot": t2_pnl, "value": None if t2_pnl is None else entry + t2_pnl / lot, "rule": "index moves 2 ATR in favour"}]
    rr = (t1_pnl / abs(sl_pnl)) if t1_pnl is not None and sl_pnl not in (None, 0) and sl_pnl < 0 else None

    # Sizing (agent 26): size by the worst case, so a gap through the stop still stays inside the budget.
    max_loss_lot = exact["max_loss"]
    has_short = any(l["side"] == "sell" for l in priced)
    if exact["unlimited_loss"] or max_loss_lot == -math.inf:
        lots = 0
        exclusions.append("Unlimited loss: not eligible for a recommendation.")
    else:
        lots = int(budget // abs(max_loss_lot)) if max_loss_lot < 0 else 0
        if lots < 1:
            exclusions.append(f"Risk budget ₹{budget:,.0f} is below the maximum loss of one lot (₹{abs(max_loss_lot):,.0f}).")
    if has_short:
        exclusions.append("Margin requirement unavailable (exchange SPAN data not loaded): short-option legs cannot be recommended.")
    exclusions += assessment["rejections"]
    if not verification["consistent"]:
        exclusions.append("Independent payoff check failed.")
    liq = []
    for l in priced:
        qd = l["quote"]
        liq.append({"leg": f"{l['side']} {l['strike']:g} {l['type']}", "spread_pct": qd["spread_pct"], "oi": qd["oi"], "volume": qd["volume"]})
        if qd["spread_pct"] is not None and qd["spread_pct"] > RULES["liquidity"]["max_spread_pct"]:
            exclusions.append(f"{l['strike']:g} {l['type']}: spread {qd['spread_pct']:.1%} is above {RULES['liquidity']['max_spread_pct']:.0%}.")
        if qd["oi"] < RULES["liquidity"]["min_oi"]:
            exclusions.append(f"{l['strike']:g} {l['type']}: open interest {qd['oi']} is below {RULES['liquidity']['min_oi']}.")

    sizing = {
        "budget": budget, "lots": lots, "lot_size": lot, "units": lots * lot,
        "max_loss_total": None if exact["unlimited_loss"] else abs(max_loss_lot) * lots,
        "stop_loss_total": None if sl_pnl is None else abs(min(sl_pnl, 0)) * lots,
        "target1_total": None if t1_pnl is None else t1_pnl * lots,
        "capital": entry * lot * lots if kind == "debit" else None,
        "margin": "unavailable" if has_short else "not required (premium paid in full)",
        "rule": "Lots = floor(budget / maximum loss per lot); never above the budget even if the price gaps past the stop.",
    }

    # Draft quality grade (paper mode until validated against history).
    direction = ctx["direction"]
    strong = direction["label"].startswith("Strong")
    long_premium = kind == "debit"
    # (factor, points, met). A factor that is met adds its points; a missed one adds 0 or a penalty.
    rr_pts = 2 if rr and rr >= 2 else 1 if rr and rr >= 1.5 else 0
    ivr = ctx["iv_to_realised"]
    iv_ok = bool(ivr and ((long_premium and ivr <= 1.2) or (not long_premium and ivr >= 1.1)))
    liq_ok = all((x["spread_pct"] or 1) <= RULES["liquidity"]["good_spread_pct"] and x["oi"] >= RULES["liquidity"]["good_oi"] for x in liq)
    pts = [("Direction strength", 2 if strong else 1, strong),
           ("ADX trend ≥ 25", 1 if direction["adx"] >= 25 else 0, direction["adx"] >= 25),
           ("Reward/risk to T1 ≥ 2", rr_pts, rr_pts == 2),
           ("Volatility priced in our favour", 1 if iv_ok else 0, iv_ok),
           ("Tight spreads and deep open interest", 1 if liq_ok else 0, liq_ok)]
    em = ctx["expected_move"]
    be = exact["breakevens"]
    if long_premium and em and be:
        need = min(abs(b - spot) for b in be)
        pts.append(("Expected move covers break-even", 1 if em >= need else 0, em >= need))
    pts.append(("At least 2 days to expiry", 0 if ctx["days"] >= 2 else -1, ctx["days"] >= 2))
    score = sum(p for _, p, _ in pts)
    g = RULES["grade"]
    grade = "HIGH-QUALITY SETUP" if score >= g["high"] else "MODERATE SETUP" if score >= g["moderate"] else "LOW-QUALITY SETUP" if score >= g["low"] else "NO TRADE"

    aligned = [c for c in direction["components"] if c["score"] is not None and ((c["score"] > 0.1) if bias == "bullish" else (c["score"] < -0.1) if bias == "bearish" else abs(c["score"]) <= 0.25)]
    opposed = [c for c in direction["components"] if c["score"] is not None and ((c["score"] < -0.1) if bias == "bullish" else (c["score"] > 0.1) if bias == "bearish" else abs(c["score"]) > 0.5)]
    supporting = [f"{c['label']}: {c['reading']}" for c in aligned]
    if rr:
        supporting.append(f"Reward/risk to Target 1 is {rr:.2f}.")
    against = [f"{c['label']}: {c['reading']}" for c in opposed]
    against += [f["text"] for f in assessment["flags"] if f["severity"] in ("critical", "high", "medium")]
    against += [f"{name_}: not met" for name_, _, met in pts if not met]

    bull = bias == "bullish"
    if bias == "neutral":
        confirmation = [f"Index holds between {stop_lvl[0]:,.0f} and {stop_lvl[1]:,.0f}", "India VIX is not rising"]
        invalidation = [f"Index trades beyond a short strike ({stop_lvl[0]:,.0f} / {stop_lvl[1]:,.0f})", "India VIX jumps more than 15%", "Direction turns Strong Bullish or Strong Bearish"]
        exits = ["Buy back at 50% of the credit (Target 1) or 25% (Target 2)", "Exit the day before expiry to avoid pin and gamma risk"]
    else:
        trig = lv.get("vwap20") or lv.get("sma20")
        confirmation = [f"Index {'closes above' if bull else 'closes below'} {trig:,.0f} (VWAP20/SMA20)",
                        f"Index {'clears' if bull else 'breaks'} the previous session {'high' if bull else 'low'} {lv['prev_high' if bull else 'prev_low']:,.0f}"]
        invalidation = [f"Index {'closes below' if bull else 'closes above'} {stop_lvl:,.0f} (stop level)",
                        f"Direction turns {'Bearish' if bull else 'Bullish'} or High Volatility / Uncertain",
                        "Implied volatility falls sharply (premium crush)" if long_premium else "Implied volatility jumps (premium expands)"]
        exits = ["After Target 1, move the stop to the entry price", "After Target 2, trail the stop by 1 ATR on the index",
                 "Exit if Target 1 is not reached with one day left to expiry (time decay)"]

    confirmed = True
    if bias != "neutral":
        trig = lv.get("vwap20") or lv.get("sma20")
        last = direction["last"]
        confirmed = (last > trig and last > lv["sma20"]) if bull else (last < trig and last < lv["sma20"])

    return {
        "strategy": name, "label": label, "bias": bias, "kind": kind,
        "legs": _legs_out(priced),
        "entry": {"value": abs(entry), "kind": kind, "zone": sorted([abs(mid_entry), abs(entry)]), "per_lot": abs(entry) * lot,
                  "basis": "conservative fill: buy at ask, sell at bid; mid shown as the better end of the zone"},
        "stop": stop, "targets": targets,
        "breakevens": be, "max_loss_per_lot": None if exact["unlimited_loss"] else abs(max_loss_lot),
        "max_profit_per_lot": None if exact["unlimited_profit"] else exact["max_profit"],
        "unlimited_loss": exact["unlimited_loss"], "unlimited_profit": exact["unlimited_profit"],
        "risk_reward": rr, "liquidity": liq, "sizing": sizing,
        "grade": {"label": grade, "points": score, "breakdown": [{"factor": n, "points": p, "met": m} for n, p, m in pts],
                  "note": "Draft rules, not validated against historical performance (paper mode)."},
        "supporting": supporting, "against": against, "entry_confirmation": confirmation, "confirmed": confirmed,
        "invalidation": invalidation, "exit_signals": exits, "verification": verification, "risk": assessment,
        "eligible": not exclusions and grade != "NO TRADE", "exclusions": exclusions,
        "curves": st.curves(priced, spot, T, r, q, lot),
    }


def _legs_out(priced):
    return [{"side": l["side"], "type": l["type"], "strike": l["strike"], "fill": l["fill"], "fill_basis": l["fill_basis"],
             "bid": l["quote"]["bid"], "ask": l["quote"]["ask"], "mid": l["quote"]["mid"], "iv": l["quote"]["iv"],
             "delta": (l["quote"]["greeks"] or {}).get("delta"), "spread_pct": l["quote"]["spread_pct"],
             "oi": l["quote"]["oi"], "volume": l["quote"]["volume"]} for l in priced]


# ------------------------------------------------------------------ final verification (agent 27)

def data_gates(chain: dict, master_strikes: set, master_lot: int | None, market: dict, now: datetime) -> list[dict]:
    created = datetime.fromisoformat(chain["created_at"])
    age_min = (now - created).total_seconds() / 60
    expiry_ok = date.fromisoformat(chain["expiry"]) >= now.date() and chain["summary"]["days_to_expiry"] > 0
    synthetic = chain["data_type"] == "synthetic"
    return [
        {"check": "Live option prices", "passed": not synthetic,
         "detail": "Option prices are synthetic (no licensed NSE feed configured)." if synthetic else "Licensed option-chain feed."},
        {"check": "Market open", "passed": market["status"] == "open",
         "detail": f"Market is {market['status'].replace('_', ' ')}; a fresh signal needs live session quotes." if market["status"] != "open" else "Session in progress."},
        {"check": "Quote freshness", "passed": age_min <= RULES["chain_max_age_minutes"],
         "detail": f"Chain built {age_min:.1f} min ago (limit {RULES['chain_max_age_minutes']} min)."},
        {"check": "Expiry valid", "passed": expiry_ok, "detail": f"Expiry {chain['expiry']}, {chain['summary']['days_to_expiry']:.2f} days left."},
        {"check": "Contracts in NSE master", "passed": bool(master_strikes) and master_lot == chain["summary"]["lot_size"],
         "detail": f"Lot size {chain['summary']['lot_size']} matches the contract master." if master_lot == chain["summary"]["lot_size"] else "Lot size mismatch."},
    ]


def decide(chain: dict, direction: dict, budget: float, master_strikes: set, master_lot: int | None,
           market: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    s = chain["summary"]
    rows = chain["rows"]
    spot = chain["spot"]["price"]
    a = chain["assumptions"]
    gates = data_gates(chain, master_strikes, master_lot, market, now)
    base = {"rules": {k: RULES[k] for k in ("version", "validation_status", "paper_mode")}, "data_gates": gates,
            "generated_at": now.isoformat(timespec="seconds"), "chain_id": chain["chain_id"], "expiry": chain["expiry"]}

    if direction["label"] == "INSUFFICIENT DATA":
        return {**base, "status": "NO TRADE", "status_reason": direction.get("reason"), "best": None, "dry_run": False, "candidates": [], "strikes": {}}

    strong = direction["label"].startswith("Strong")
    atr = direction["atr"]
    ce_rank = strike_comparison(rows, "CE", strong, atr, s["atm_iv"])
    pe_rank = strike_comparison(rows, "PE", strong, atr, s["atm_iv"])
    best_strikes = {"CE": ce_rank[0]["strike"] if ce_rank else None, "PE": pe_rank[0]["strike"] if pe_rank else None}
    ctx = {
        "spot": spot, "T": s["days_to_expiry"] / 365, "days": s["days_to_expiry"], "r": a["risk_free_rate"], "q": a["dividend_yield"],
        "lot": s["lot_size"], "atr": atr, "levels": direction["levels"], "direction": direction,
        "iv_to_realised": s["iv_to_realised"], "expected_move": s["expected_move"]["straddle"],
        "risk_ctx": {"days_to_expiry": s["days_to_expiry"], "settlement": chain["underlying"]["settlement"],
                     "underlying_type": chain["underlying"]["type"], "iv_to_realised": s["iv_to_realised"], "spot": spot},
    }
    names = PLAYBOOK.get(direction["label"], [])
    candidates = [c for c in (evaluate_candidate(n, rows, ctx, best_strikes, budget) for n in names) if c]
    eligible = [c for c in candidates if c["eligible"]]
    ranked = sorted(eligible, key=lambda c: (-c["grade"]["points"], -(c["risk_reward"] or 0)))
    best = ranked[0] if ranked else None
    # For the dry run, show the strongest candidate even if a rule excluded it, so the analysis stays visible.
    showcase = best or (sorted(candidates, key=lambda c: (-(c.get("grade", {}).get("points", -9)), -(c.get("risk_reward") or 0)))[0] if candidates else None)

    data_ok = all(g["passed"] for g in gates)
    if direction["label"] == "High Volatility / Uncertain":
        status, reason = "WAIT FOR CONFIRMATION", "Market direction is uncertain with elevated volatility; no playbook applies."
    elif not data_ok:
        failed = [g["detail"] for g in gates if not g["passed"]]
        status, reason = "NO TRADE", " ".join(failed)
    elif best is None:
        status, reason = "NO TRADE", "No candidate passed the risk, liquidity, margin and budget rules."
    elif not best["confirmed"]:
        status, reason = "WAIT FOR CONFIRMATION", "Entry confirmation conditions are not met yet."
    else:
        status, reason = best["grade"]["label"], "Draft rules in paper mode: record as a paper signal, not a validated recommendation."

    return {
        **base,
        "status": status,
        "status_reason": reason,
        "best": showcase,
        "dry_run": not data_ok and showcase is not None,
        "candidates": [{k: c.get(k) for k in ("strategy", "label", "bias", "kind", "eligible", "exclusions", "risk_reward",
                                              "max_loss_per_lot", "max_profit_per_lot", "unlimited_loss", "breakevens", "legs")}
                       | {"grade": c.get("grade", {}).get("label"), "points": c.get("grade", {}).get("points"),
                          "net": c.get("entry", {}).get("value"), "kind": c.get("kind")} for c in candidates],
        "strikes": {"CE": ce_rank, "PE": pe_rank, "why_CE": why_selected(ce_rank), "why_PE": why_selected(pe_rank)},
    }
