"""Recommendation Engine (plan section 5).

Explicit, versioned rules turn evidence into one of BUY / HOLD / SELL /
INSUFFICIENT DATA per horizon. HOLD is never used as a fallback for missing
data: missing required inputs, low coverage or a failed critical gate always
give INSUFFICIENT DATA. No probability-of-profit or "AI confidence" number is
produced; coverage and signal agreement are reported separately (section 5.4).
"""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

from ..analytics import formatting as fmt
from .quality import blocked_horizon

RULES_FILE = Path(__file__).resolve().parent.parent / "rules" / "rules_v0_1.json"
INSUFFICIENT = "INSUFFICIENT_DATA"
COMPONENT_LABELS = {
    "roe": "ROE", "net_margin": "net margin", "revenue_growth": "revenue growth", "debt_to_equity": "debt/equity",
    "interest_coverage": "interest coverage", "fcf_margin": "FCF margin", "cash_conversion": "cash conversion",
    "pe": "P/E", "pb": "P/B", "price_vs_sma200": "close vs SMA200", "sma50_vs_sma200": "SMA50 vs SMA200",
    "price_vs_sma50": "close vs SMA50", "macd_hist_pct": "MACD histogram", "rel_return_3m": "3M return vs NIFTY 50",
    "rel_return_6m": "6M return vs NIFTY 50", "momentum_12_1": "12-1 month momentum",
    "q_revenue_yoy": "quarterly revenue YoY", "q_net_income_yoy": "quarterly net income YoY",
    "volatility_1y": "1Y volatility", "max_drawdown_1y": "1Y max drawdown", "beta_1y": "beta",
    "median_traded_value_cr": "median traded value", "news_tone": "headline tone",
}


@lru_cache
def load_rules() -> dict:
    text = RULES_FILE.read_text(encoding="utf-8")
    rules = json.loads(text)
    rules["sha256"] = hashlib.sha256(text.encode()).hexdigest()
    return rules


def component_score(value: float | None, band: dict) -> float | None:
    """Linear map: 'bad' -> -1, 'good' -> +1, clipped. Works when lower is better (bad > good)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    bad, good = float(band["bad"]), float(band["good"])
    t = (float(value) - bad) / (good - bad)
    return max(-1.0, min(1.0, 2.0 * t - 1.0))


def news_tone(news_labels: list[dict], min_items: int) -> tuple[float | None, list[str], str]:
    weights = {"positive": 1.0, "negative": -1.0, "neutral": 0.0, "uncertain": 0.0}
    usable = [n for n in news_labels if n.get("label") in weights]
    if len(usable) < min_items:
        return None, [n["evidence_id"] for n in usable], f"{len(usable)} classified headline(s); {min_items} needed"
    tone = sum(weights[n["label"]] for n in usable) / len(usable)
    counts = {k: sum(1 for n in usable if n["label"] == k) for k in weights}
    disp = f"{fmt.num(tone)} ({counts['positive']} positive, {counts['negative']} negative, {counts['neutral']} neutral, {counts['uncertain']} uncertain)"
    return tone, [n["evidence_id"] for n in usable], disp


def score_sub_scores(det: dict, news_labels: list[dict], rules: dict) -> dict:
    metrics, evidence = det["metrics"], det["evidence"]
    sector = det["profile"].get("sector")
    override = rules.get("sector_overrides", {}).get(sector or "", {})
    excluded = set(override.get("exclude_components", []))
    out = {}
    for name, spec in rules["sub_scores"].items():
        comps = []
        for cname, band in spec["components"].items():
            if cname in excluded:
                comps.append({"name": cname, "label": COMPONENT_LABELS.get(cname, cname), "status": "excluded_for_sector", "score": None, "value": None,
                              "display": "excluded for sector", "evidence_ids": [], "band": band})
                continue
            if cname == "news_tone":
                value, eids, display = news_tone(news_labels, rules["thresholds"]["news_min_items"])
            else:
                m = metrics.get(cname) or {}
                value, eids = m.get("value"), [m["evidence_id"]] if m.get("evidence_id") else []
                item = evidence.get(eids[0]) if eids else None
                display = item["display"] if item else "unavailable"
            s = component_score(value, band)
            comps.append({"name": cname, "label": COMPONENT_LABELS.get(cname, cname), "status": "ok" if s is not None else "unavailable",
                          "score": s, "value": value, "display": display, "evidence_ids": eids, "band": band})
        eligible = [c for c in comps if c["status"] != "excluded_for_sector"]
        avail = [c for c in eligible if c["score"] is not None]
        needed = math.ceil(len(eligible) / 2) if eligible else 1
        if eligible and len(avail) >= needed:
            score, reason = sum(c["score"] for c in avail) / len(avail), None
        else:
            score, reason = None, f"{len(avail)} of {len(eligible)} components available; {needed} needed"
        out[name] = {"name": name, "label": spec["label"], "score": score, "reason": reason, "components": comps,
                     "note": spec.get("note"), "sector_note": override.get("note") if excluded & set(spec["components"]) else None}
    return out


def _sign(x: float, band: float) -> int:
    return 0 if abs(x) < band else (1 if x > 0 else -1)


def _invalidation(horizon: str, rating: str, det: dict) -> list[dict]:
    ev = det["evidence"]

    def d(eid):
        item = ev.get(eid)
        return item["display"] if item and item["status"] == "ok" else None

    sma200, sup, res = d("ind.sma200"), d("tech.support_60"), d("tech.resistance_60")
    out = []
    if horizon == "medium":
        if rating == "BUY" and sma200:
            out.append({"condition": f"A daily close below SMA200 ({sma200})" + (f" or below 60-session support ({sup})" if sup else ""),
                        "evidence_ids": [e for e in ("ind.sma200", "tech.support_60") if d(e)]})
        elif rating == "SELL" and sma200:
            out.append({"condition": f"A daily close above SMA200 ({sma200})" + (f" or above 60-session resistance ({res})" if res else ""),
                        "evidence_ids": [e for e in ("ind.sma200", "tech.resistance_60") if d(e)]})
        elif rating == "HOLD" and sup and res:
            out.append({"condition": f"A close above 60-session resistance ({res}) or below 60-session support ({sup}) triggers re-evaluation",
                        "evidence_ids": ["tech.resistance_60", "tech.support_60"]})
    if horizon == "long":
        if rating == "BUY":
            out.append({"condition": "Next annual results show falling revenue, or ROE below 8%", "evidence_ids": ["calc.revenue_growth", "calc.roe"]})
        elif rating == "SELL":
            out.append({"condition": "Next annual results show revenue growth above 15% with ROE above 20%", "evidence_ids": ["calc.revenue_growth", "calc.roe"]})
        elif rating == "HOLD":
            out.append({"condition": "A material change in annual revenue growth, ROE or valuation re-rates this", "evidence_ids": ["calc.revenue_growth", "calc.roe", "calc.pe"]})
    if out:
        out.append({"condition": "Any critical data-quality gate failing on refresh", "evidence_ids": []})
    return out


def rate(det: dict, news_labels: list[dict], rules: dict | None = None) -> dict:
    rules = rules or load_rules()
    th = rules["thresholds"]
    subs = score_sub_scores(det, news_labels, rules)
    horizons = {}
    for h, spec in rules["horizons"].items():
        base = {"horizon": h, "label": spec["label"], "window": spec["window"], "sessions": spec["sessions"]}
        if not spec.get("enabled"):
            horizons[h] = {**base, "rating": INSUFFICIENT, "abstention_kind": "horizon_disabled",
                           "abstention_reasons": [spec["abstain_reason"]],
                           "composite": None, "coverage": None, "agreement": None, "contributions": [],
                           "positive_signals": [], "negative_signals": [], "strongest_opposing": None,
                           "key_reasons": [], "invalidation": []}
            continue
        weights = spec["weights"]
        total_w = sum(weights.values())
        avail = {k: w for k, w in weights.items() if subs[k]["score"] is not None}
        avail_w = sum(avail.values())
        coverage = avail_w / total_w if total_w else 0.0
        composite = sum(w * subs[k]["score"] for k, w in avail.items()) / avail_w if avail_w else None
        contributions = sorted(
            [{"sub_score": k, "label": subs[k]["label"], "weight": w, "score": subs[k]["score"],
              "contribution": w * subs[k]["score"] / avail_w} for k, w in avail.items()],
            key=lambda c: -abs(c["contribution"]),
        )
        abstain = []
        for g in blocked_horizon(det["gates"], h):
            abstain.append(f"{g['title']}: {g['message']}")
        for k in spec["required"]:
            if subs[k]["score"] is None:
                abstain.append(f"Required sub-score '{subs[k]['label']}' unavailable ({subs[k]['reason']}).")
        if coverage < th["min_coverage"]:
            missing = [subs[k]["label"] for k in weights if k not in avail]
            abstain.append(f"Evidence coverage {fmt.pct(coverage, 0)} is below the {fmt.pct(th['min_coverage'], 0)} minimum (missing: {', '.join(missing)}).")

        direction = _sign(composite, th["neutral_band"]) if composite is not None else 0
        agreement = None
        if direction:
            agree = sum(w for k, w in avail.items() if _sign(subs[k]["score"], th["neutral_band"]) == direction)
            oppose = sum(w for k, w in avail.items() if _sign(subs[k]["score"], th["neutral_band"]) == -direction)
            agreement = agree / (agree + oppose) if agree + oppose else 1.0

        hold_reason = None
        if abstain:
            rating = INSUFFICIENT
        elif composite >= th["buy"] and agreement is not None and agreement >= th["min_agreement"]:
            rating = "BUY"
        elif composite <= th["sell"] and agreement is not None and agreement >= th["min_agreement"]:
            rating = "SELL"
        else:
            rating = "HOLD"
            if composite >= th["buy"] or composite <= th["sell"]:
                hold_reason = (f"Composite {composite:+.2f} meets the {'BUY' if composite > 0 else 'SELL'} threshold, but only "
                               f"{fmt.pct(agreement, 0)} of directional evidence weight agrees (minimum {fmt.pct(th['min_agreement'], 0)}).")
            else:
                hold_reason = f"Composite {composite:+.2f} is between the SELL ({th['sell']:+.2f}) and BUY ({th['buy']:+.2f}) thresholds."

        positive = [c for c in contributions if c["score"] >= th["neutral_band"]]
        negative = [c for c in contributions if c["score"] <= -th["neutral_band"]]
        if rating == "BUY":
            opposing = negative[0] if negative else None
        elif rating == "SELL":
            opposing = positive[0] if positive else None
        elif rating == "HOLD":
            opposing = contributions[0] if contributions and abs(contributions[0]["score"]) >= th["neutral_band"] else None
        else:
            opposing = None

        def reason_text(c):
            # Show the components that pushed this sub-score in its own direction.
            comps = [x for x in subs[c["sub_score"]]["components"] if x["status"] == "ok"]
            sign = 1 if c["score"] >= 0 else -1
            comps.sort(key=lambda x: -sign * x["score"])
            detail = "; ".join(f"{COMPONENT_LABELS.get(x['name'], x['name'])} {x['display']}" for x in comps[:2])
            return {"sub_score": c["sub_score"], "score": c["score"], "weight": c["weight"],
                    "text": f"{c['label']} {c['score']:+.2f} (weight {fmt.pct(c['weight'], 0)}): {detail}",
                    "evidence_ids": [e for x in comps[:2] for e in x["evidence_ids"]]}

        if rating in ("BUY", "SELL"):
            sign = 1 if rating == "BUY" else -1
            key = [reason_text(c) for c in contributions if _sign(c["score"], th["neutral_band"]) == sign][:3]
        elif rating == "HOLD":
            key = [reason_text(c) for c in contributions[:3]]
        else:
            key = []

        horizons[h] = {
            **base,
            "rating": rating,
            "abstention_kind": "data" if rating == INSUFFICIENT else None,
            "composite": composite,
            "coverage": coverage,
            "agreement": agreement,
            "contributions": contributions,
            "positive_signals": [reason_text(c) for c in positive],
            "negative_signals": [reason_text(c) for c in negative],
            "strongest_opposing": reason_text(opposing) if opposing else None,
            "key_reasons": key,
            "hold_reason": hold_reason,
            "abstention_reasons": abstain,
            "invalidation": _invalidation(h, rating, det) if rating != INSUFFICIENT else [],
        }
    return {
        "rules_version": rules["version"],
        "rules_sha256": rules["sha256"],
        "validation_status": rules["validation_status"],
        "validation_note": rules["validation_note"],
        "scoring_method": rules["scoring_method"],
        "thresholds": th,
        "sub_scores": subs,
        "horizons": horizons,
    }
