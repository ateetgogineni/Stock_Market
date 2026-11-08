"""Option-chain analysis (options spec sections 2.1-2.3).

Deterministic: implied volatility and Greeks are solved from each quote's
mid price with the pricing engine, then the chain is summarised. Open interest
is reported as positioning evidence only. Every contract has a buyer and a
seller, so OI alone never proves a bullish or bearish view.
"""

from __future__ import annotations

import math
import statistics

from . import pricing

OI_CAVEAT = ("Open interest alone is not proof of bullish or bearish activity: every open contract has both a buyer "
             "and a seller, and positions are often hedges.")
WIDE_SPREAD = 0.10  # bid-ask spread above 10% of mid
MIN_TIME_VALUE = 0.10  # rupees; below this IV is not meaningful


def _mid(q: dict) -> float | None:
    if q["bid"] > 0 and q["ask"] > 0:
        return (q["bid"] + q["ask"]) / 2
    return q.get("ltp")


def enrich_rows(exp: dict, spot: float, r: float, q: float) -> list[dict]:
    """Add mid, spread %, implied volatility and Greeks to every CE/PE quote."""
    T = exp["T"]
    rows = []
    for row in exp["rows"]:
        K = row["strike"]
        out = {"strike": K}
        for kind in ("CE", "PE"):
            quote = dict(row[kind])
            mid = _mid(quote)
            quote["mid"] = mid
            quote["spread_pct"] = (quote["ask"] - quote["bid"]) / mid if mid and quote["bid"] > 0 else None
            quote["crossed"] = quote["bid"] > quote["ask"] > 0
            iv, reason = (None, "no usable price")
            if mid:
                lower, _ = pricing.no_arbitrage_bounds(kind, spot, K, T, r, q)
                if mid - lower < MIN_TIME_VALUE:
                    reason = "too little time value for a meaningful implied volatility"
                else:
                    iv, reason = pricing.implied_vol(kind, mid, spot, K, T, r, q)
            quote["iv"] = iv
            quote["iv_note"] = reason
            g = pricing.greeks(kind, spot, K, T, r, iv, q) if iv else None
            quote["greeks"] = {k: v for k, v in g.as_dict().items() if k != "price"} if g else None
            quote["theoretical"] = g.price if g else None
            out[kind] = quote
        rows.append(out)
    return rows


def max_pain(rows: list[dict]) -> float | None:
    """Strike at which option holders' total intrinsic value at expiry is smallest."""
    if not rows:
        return None
    strikes = [r["strike"] for r in rows]
    best, best_val = None, None
    for s in strikes:
        payout = sum(r["CE"]["oi"] * max(s - r["strike"], 0) + r["PE"]["oi"] * max(r["strike"] - s, 0) for r in rows)
        if best_val is None or payout < best_val:
            best, best_val = s, payout
    return best


def _closest(rows: list[dict], kind: str, target_delta: float) -> dict | None:
    cands = [r for r in rows if r[kind]["greeks"] and r[kind]["iv"]]
    if not cands:
        return None
    return min(cands, key=lambda r: abs(r[kind]["greeks"]["delta"] - target_delta))


def summarise(exp: dict, rows: list[dict], spot: float, r: float, q: float, realised_vol: float | None) -> dict:
    T = exp["T"]
    fwd = spot * math.exp((r - q) * T)
    atm = min(rows, key=lambda x: abs(x["strike"] - fwd))
    atm_ivs = [atm[k]["iv"] for k in ("CE", "PE") if atm[k]["iv"]]
    atm_iv = sum(atm_ivs) / len(atm_ivs) if atm_ivs else None
    ce_oi, pe_oi = sum(x["CE"]["oi"] for x in rows), sum(x["PE"]["oi"] for x in rows)
    ce_vol, pe_vol = sum(x["CE"]["volume"] for x in rows), sum(x["PE"]["volume"] for x in rows)
    pcr_oi = pe_oi / ce_oi if ce_oi else None
    pcr_vol = pe_vol / ce_vol if ce_vol else None
    mp = max_pain(rows)

    above = [x for x in rows if x["strike"] >= spot]
    below = [x for x in rows if x["strike"] <= spot]
    resistance = sorted(above, key=lambda x: -x["CE"]["oi"])[:3]
    support = sorted(below, key=lambda x: -x["PE"]["oi"])[:3]

    def oi_moves(kind):
        ranked = sorted(rows, key=lambda x: x[kind]["oi_change"])
        return {"largest_additions": [{"strike": x["strike"], "oi_change": x[kind]["oi_change"], "oi": x[kind]["oi"]} for x in ranked[::-1][:3]],
                "largest_reductions": [{"strike": x["strike"], "oi_change": x[kind]["oi_change"], "oi": x[kind]["oi"]} for x in ranked[:3] if x[kind]["oi_change"] < 0]}

    ratios = [x[k]["volume"] / x[k]["oi"] for x in rows for k in ("CE", "PE") if x[k]["oi"] > 0 and x[k]["volume"] > 0]
    med_ratio = statistics.median(ratios) if ratios else None
    med_volume = statistics.median([x[k]["volume"] for x in rows for k in ("CE", "PE")]) if rows else 0
    unusual = []
    if med_ratio:
        for x in rows:
            for k in ("CE", "PE"):
                qd = x[k]
                if qd["oi"] > 0 and qd["volume"] > max(med_volume, 1) and qd["volume"] / qd["oi"] > 3 * med_ratio:
                    unusual.append({"strike": x["strike"], "type": k, "volume": qd["volume"], "oi": qd["oi"],
                                    "volume_to_oi": qd["volume"] / qd["oi"], "median_volume_to_oi": med_ratio})
    unusual.sort(key=lambda u: -u["volume_to_oi"])

    put25, call25 = _closest(rows, "PE", -0.25), _closest(rows, "CE", 0.25)
    skew = (put25["PE"]["iv"] - call25["CE"]["iv"]) if put25 and call25 else None
    straddle = (atm["CE"]["mid"] or 0) + (atm["PE"]["mid"] or 0) if atm["CE"]["mid"] and atm["PE"]["mid"] else None

    near = [x for x in rows if abs(x["strike"] / spot - 1) <= 0.05]
    wide = [x["strike"] for x in near for k in ("CE", "PE") if x[k]["spread_pct"] is not None and x[k]["spread_pct"] > WIDE_SPREAD]
    no_bid = sum(1 for x in rows for k in ("CE", "PE") if x[k]["bid"] <= 0)
    zero_vol = sum(1 for x in rows for k in ("CE", "PE") if x[k]["volume"] == 0)
    crossed = sum(1 for x in rows for k in ("CE", "PE") if x[k]["crossed"])
    no_iv = sum(1 for x in rows for k in ("CE", "PE") if x[k]["iv"] is None)

    if pcr_oi is None:
        lean = "unavailable"
    elif pcr_oi > 1.3:
        lean = "bullish-leaning"
    elif pcr_oi < 0.7:
        lean = "bearish-leaning"
    else:
        lean = "neutral"

    signals = []
    if pcr_oi is not None:
        signals.append({
            "signal": "Put-call ratio (open interest)", "value": round(pcr_oi, 2),
            "reading": "More puts than calls are open. Conventionally read as put writers expecting support (mildly bullish), "
                       "but heavy put buying for hedges looks the same." if pcr_oi > 1 else
                       "More calls than puts are open. Conventionally read as call writers expecting a cap (mildly bearish), "
                       "but covered-call writing looks the same.",
        })
    if resistance:
        signals.append({"signal": "Largest call open interest above spot", "value": resistance[0]["strike"],
                        "reading": "Often treated as a resistance zone where call writers are concentrated."})
    if support:
        signals.append({"signal": "Largest put open interest below spot", "value": support[0]["strike"],
                        "reading": "Often treated as a support zone where put writers are concentrated."})
    if mp is not None:
        signals.append({"signal": "Max pain", "value": mp,
                        "reading": "Strike where option holders would lose the most at expiry. It is not a price forecast."})
    if skew is not None:
        signals.append({"signal": "25-delta skew (put IV minus call IV)", "value": round(skew, 4),
                        "reading": "Puts priced richer than calls, i.e. more demand for downside protection." if skew > 0
                        else "Calls priced richer than puts, i.e. more demand for upside exposure."})

    return {
        "expiry": exp["expiry"],
        "days_to_expiry": round(T * 365, 2),
        "lot_size": exp["lot_size"],
        "forward": fwd,
        "atm_strike": atm["strike"],
        "atm_iv": atm_iv,
        "realised_vol_1y": realised_vol,
        "iv_to_realised": atm_iv / realised_vol if atm_iv and realised_vol else None,
        "pcr_oi": pcr_oi,
        "pcr_volume": pcr_vol,
        "total_oi": {"CE": ce_oi, "PE": pe_oi},
        "total_volume": {"CE": ce_vol, "PE": pe_vol},
        "max_pain": mp,
        "oi_resistance": [{"strike": x["strike"], "oi": x["CE"]["oi"]} for x in resistance],
        "oi_support": [{"strike": x["strike"], "oi": x["PE"]["oi"]} for x in support],
        "oi_changes": {"CE": oi_moves("CE"), "PE": oi_moves("PE")},
        "unusual_volume": unusual[:5],
        "skew_25d": skew,
        "expected_move": {
            "straddle": straddle,
            "pct": straddle / spot if straddle else None,
            "note": "ATM straddle mid: the market's rough expected move to expiry, not a forecast.",
        },
        "liquidity": {"wide_spread_near_money": len(wide), "no_bid": no_bid, "zero_volume": zero_vol,
                      "crossed_quotes": crossed, "no_iv": no_iv, "contracts": 2 * len(rows)},
        "positioning": {"lean": lean, "evidence": "weak", "caveat": OI_CAVEAT},
        "signals": signals,
    }
