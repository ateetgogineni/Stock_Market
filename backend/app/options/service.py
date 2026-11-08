"""Options service: builds reproducible chain snapshots and evaluates strategies.

A chain snapshot fixes everything an analysis depends on (contract specs, the
underlying close, assumptions and every quote) under a content-hash ID, like the
equity snapshots, so a strategy evaluation can be recomputed later.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd

from ..analytics import risk_metrics as rm
from ..services.market_calendar import IST, expected_last_session, sessions_missing
from ..services.snapshots import canonical_json, content_hash
from . import chain as chain_mod
from . import contracts, pricing, risk
from . import strategies as st
from .synthetic import SyntheticOptionsProvider

ENGINE_VERSION = "options-0.2.0"  # 0.1.1: payoff window sized by expected move; 0.2.0: binomial model check
RISK_FREE_RATE = 0.06  # assumption until a rate source is configured
INDEX_DIVIDEND_YIELD = 0.0  # assumption for indices
MAX_EXPIRIES = 6
MAX_DAYS = 100
STRIKE_BAND = 0.15  # chain shows strikes within +/-15% of the underlying


class OptionsDataError(ValueError):
    pass


def _session_close(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), time(15, 30), tzinfo=IST)


def build_snapshot(symbol: str, equity_provider, options_provider=None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    und = contracts.underlying_view(symbol)
    if und["price_symbol"] is None:
        raise OptionsDataError(f"INSUFFICIENT DATA: {und['price_note']}")
    options_provider = options_provider or SyntheticOptionsProvider()

    bars = equity_provider.history(und["price_symbol"], 2)
    bars = [b for b in bars if b.get("close")]
    if len(bars) < 30:
        raise OptionsDataError(f"INSUFFICIENT DATA: not enough price history for {und['price_symbol']}.")
    last = bars[-1]
    spot, spot_date = float(last["close"]), last["date"]
    realised = rm.annualised_volatility(pd.Series([b["close"] for b in bars]))
    year_ago = date.fromisoformat(spot_date) - timedelta(days=365)
    divs = sum(b.get("dividend") or 0 for b in bars if date.fromisoformat(b["date"]) > year_ago)
    q = INDEX_DIVIDEND_YIELD if und["type"] == "index" else min(divs / spot, 0.10)
    r = RISK_FREE_RATE
    base_vol = min(max((realised or 0.2) * 1.05, 0.10), 0.80)

    valuation = _session_close(spot_date)
    expiries = []
    for e in und["expiries"]:
        T = (_session_close(e["expiry"]) - valuation).total_seconds() / (365 * 86400)
        if T <= 0 or T * 365 > MAX_DAYS or len(expiries) >= MAX_EXPIRIES:
            continue
        spec = contracts.expiry_spec(symbol, e["expiry"])
        strikes = [k for k in spec["strikes"] if abs(k / spot - 1) <= STRIKE_BAND]
        if len(strikes) < 5:
            continue
        expiries.append({"expiry": e["expiry"], "T": T, "lot_size": spec["lot_size"], "strikes": strikes})
    if not expiries:
        raise OptionsDataError(f"INSUFFICIENT DATA: no {symbol} expiries within {MAX_DAYS} days with strikes near {spot:,.2f}.")

    chain = options_provider.chain(symbol, spot, spot_date, expiries, base_vol, r, q)
    body = {
        "schema_version": "1",
        "created_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "underlying": und,
        "spot": {"price": spot, "session": spot_date, "source": getattr(equity_provider, "name", "unknown"),
                 "price_symbol": und["price_symbol"], "sessions_missing": sessions_missing(date.fromisoformat(spot_date), expected_last_session(now))},
        "assumptions": {
            "risk_free_rate": r, "risk_free_rate_note": "Assumed 6.00%; no rate source is configured.",
            "dividend_yield": q, "dividend_yield_note": "Assumed 0% for indices." if und["type"] == "index"
            else "Trailing 12-month dividends / last close.",
            "realised_vol_1y": realised, "valuation_time": valuation.isoformat(), "day_count": "ACT/365",
        },
        "provider": {"name": options_provider.name, "version": options_provider.version, "entitlement": options_provider.entitlement},
        "pricing_model": pricing.MODEL,
        "engine_version": ENGINE_VERSION,
        "expiries": chain,
    }
    return {"chain_id": "opt_" + content_hash(body)[:24], **body}


def save(snapshot: dict, data_dir: Path) -> None:
    path = data_dir / "options" / f"{snapshot['chain_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(canonical_json(snapshot), encoding="utf-8")


def load(chain_id: str, data_dir: Path) -> dict:
    if not chain_id.startswith("opt_") or not chain_id[4:].isalnum():
        raise OptionsDataError("invalid chain id")
    snap = json.loads((data_dir / "options" / f"{chain_id}.json").read_text(encoding="utf-8"))
    body = {k: v for k, v in snap.items() if k != "chain_id"}
    if "opt_" + content_hash(body)[:24] != chain_id:
        raise OptionsDataError(f"Chain snapshot {chain_id} failed its integrity check.")
    return snap


def _expiry(snap: dict, expiry: str | None) -> dict:
    exps = snap["expiries"]
    if expiry is None:
        return exps[0]
    for e in exps:
        if e["expiry"] == expiry:
            return e
    raise OptionsDataError(f"Expiry {expiry} is not in this chain snapshot.")


def quality(snap: dict, summary: dict) -> list[dict]:
    gates = []
    ent = snap["provider"]["entitlement"]
    gates.append({"id": "data_source", "severity": "critical", "passed": ent["type"] != "synthetic",
                  "message": ent["notes"] if ent["type"] == "synthetic" else "Licensed option-chain feed."})
    missing = snap["spot"]["sessions_missing"]
    gates.append({"id": "underlying_freshness", "severity": "critical" if missing >= 5 else "warning", "passed": missing < 2,
                  "message": f"Underlying close from {snap['spot']['session']} ({missing} sessions behind the expected session)."})
    master_age = (date.fromisoformat(snap["created_at"][:10]) - date.fromisoformat(snap["underlying"]["contract_master_date"])).days
    gates.append({"id": "contract_master", "severity": "warning", "passed": master_age <= 7,
                  "message": f"NSE contract master dated {snap['underlying']['contract_master_date']} ({master_age} days old)."})
    liq = summary["liquidity"]
    gates.append({"id": "quote_integrity", "severity": "warning", "passed": liq["crossed_quotes"] == 0,
                  "message": f"{liq['crossed_quotes']} crossed quotes; {liq['no_bid']} of {liq['contracts']} contracts have no bid."})
    gates.append({"id": "implied_volatility", "severity": "warning", "passed": liq["no_iv"] < liq["contracts"] * 0.5,
                  "message": f"Implied volatility unavailable for {liq['no_iv']} of {liq['contracts']} contracts (mostly deep in- or out-of-the-money)."})
    return gates


def chain_view(snap: dict, expiry: str | None = None) -> dict:
    exp = _expiry(snap, expiry)
    spot, a = snap["spot"]["price"], snap["assumptions"]
    rows = chain_mod.enrich_rows(exp, spot, a["risk_free_rate"], a["dividend_yield"])
    summary = chain_mod.summarise(exp, rows, spot, a["risk_free_rate"], a["dividend_yield"], a["realised_vol_1y"])
    return {
        "chain_id": snap["chain_id"],
        "data_type": snap["provider"]["entitlement"]["type"],
        "underlying": snap["underlying"],
        "spot": snap["spot"],
        "assumptions": a,
        "provider": snap["provider"],
        "pricing_model": snap["pricing_model"],
        "engine_version": snap["engine_version"],
        "created_at": snap["created_at"],
        "expiries": [{"expiry": e["expiry"], "days": round(e["T"] * 365, 2), "lot_size": e["lot_size"]} for e in snap["expiries"]],
        "expiry": exp["expiry"],
        "summary": summary,
        "term_structure": _term_structure(snap),
        "model_check": model_check(exp, rows, summary, spot, a["risk_free_rate"], a["dividend_yield"]),
        "quality": quality(snap, summary),
        "rows": rows,
    }


MODEL_CHECK_TOLERANCE = 0.005  # 0.5% of the option price, or 0.05 points for cheap options


def model_check(exp: dict, rows: list[dict], summary: dict, spot: float, r: float, q: float) -> dict:
    """Reprice the ATM call and put with an independent binomial lattice and check put-call parity."""
    atm = next((x for x in rows if x["strike"] == summary["atm_strike"]), None)
    T = exp["T"]
    sigma = summary.get("atm_iv")
    if atm is None or not sigma or T <= 0:
        return {"status": "unavailable", "reason": "No ATM implied volatility to price with."}
    K = atm["strike"]
    checks = []
    bsm = {}
    for kind in ("CE", "PE"):
        b = pricing.price(kind, spot, K, T, r, sigma, q)
        lat = pricing.binomial_price(kind, spot, K, T, r, sigma, q, steps=pricing.BINOMIAL_MODEL["steps"])
        bsm[kind] = b
        diff = lat - b
        ok = abs(diff) <= max(MODEL_CHECK_TOLERANCE * b, 0.05)
        checks.append({"contract": f"{K:g} {kind}", "bsm": b, "binomial": lat, "difference": diff,
                       "difference_pct": diff / b if b else None, "passed": ok})
    gap = pricing.parity_gap(bsm["CE"], bsm["PE"], spot, K, T, r, q)
    return {"status": "ok", "strike": K, "iv": sigma, "days": round(T * 365, 2), "checks": checks,
            "parity_gap": gap, "parity_passed": abs(gap) < 0.01, "passed": all(c["passed"] for c in checks) and abs(gap) < 0.01,
            "models": {"primary": pricing.MODEL["id"], "check": pricing.BINOMIAL_MODEL},
            "note": "Two independently written models priced at the same ATM volatility. A gap above 0.5% means an input or code error."}


def _term_structure(snap: dict) -> list[dict]:
    spot, a = snap["spot"]["price"], snap["assumptions"]
    out = []
    for e in snap["expiries"]:
        rows = chain_mod.enrich_rows({**e, "rows": [min(e["rows"], key=lambda rw: abs(rw["strike"] - spot * math.exp((a["risk_free_rate"] - a["dividend_yield"]) * e["T"])))]},
                                     spot, a["risk_free_rate"], a["dividend_yield"])
        ivs = [rows[0][k]["iv"] for k in ("CE", "PE") if rows[0][k]["iv"]]
        out.append({"expiry": e["expiry"], "days": round(e["T"] * 365, 2), "atm_iv": sum(ivs) / len(ivs) if ivs else None})
    return out


def evaluate(snap: dict, template: str, expiry: str | None, width: int = 1, lots: int = 1,
             strikes: dict | None = None) -> dict:
    if lots < 1 or lots > 100:
        raise st.StrategyError("Lots must be between 1 and 100.")
    view = chain_view(snap, expiry)
    rows, summary = view["rows"], view["summary"]
    spot, a = snap["spot"]["price"], snap["assumptions"]
    exp = _expiry(snap, expiry)
    T, r, q = exp["T"], a["risk_free_rate"], a["dividend_yield"]
    lot = exp["lot_size"]
    if lot is None:
        raise OptionsDataError("INSUFFICIENT DATA: this expiry has more than one lot size in the contract master.")
    units = lot * lots
    legs = st.price_legs(st.build_legs(template, rows, summary["atm_strike"], width, snap["underlying"]["type"], strikes), rows, spot)
    spec = st.TEMPLATES[template]
    base = {
        "chain_id": snap["chain_id"], "template": template, "label": spec["label"], "outlook": spec["outlook"],
        "explanation": spec["explain"], "expiry": exp["expiry"], "days_to_expiry": round(T * 365, 2),
        "lot_size": lot, "lots": lots, "units": units, "data_type": view["data_type"],
        "legs": [{k: v for k, v in l.items() if k != "quote"} | {"quote": _leg_quote(l)} for l in legs],
        "pricing_model": snap["pricing_model"], "engine_version": ENGINE_VERSION,
    }
    unpriced = [l for l in legs if l["fill"] is None]
    if unpriced:
        names = ", ".join(f"{l['side']} {l['strike']:g} {l['type']}" for l in unpriced)
        ctx = _ctx(snap, view, T)
        verdict = {"verdict": "rejected", "rejections": [f"No tradable price for: {names}."], "flags": [],
                   "opportunity_status": "INSUFFICIENT_DATA", "opportunity_reason": "A leg has no price.",
                   "probability_estimates": "Not shown."}
        return {**base, "payoff": None, "risk": verdict, "context": ctx}

    exact = st.analyse_payoff(legs, units)
    verification = risk.verify_payoff(legs, units, exact)
    ctx = _ctx(snap, view, T)
    assessment = risk.assess(legs, exact, verification, ctx)
    net = units * sum((-1 if l["side"] == "buy" else 1) * l["fill"] for l in legs if l["type"] != "STOCK")
    finite = not exact["unlimited_profit"] and not exact["unlimited_loss"]
    rr = exact["max_profit"] / abs(exact["max_loss"]) if finite and exact["max_loss"] < 0 else None

    def money(x):
        return None if x in (math.inf, -math.inf) else round(x, 2)

    invalidation = []
    be = exact["breakevens"]
    if spec["outlook"] in ("bullish", "mildly bullish") and be:
        invalidation.append(f"The underlying stays below the break-even of {be[0]:,.2f} into expiry.")
    elif spec["outlook"] == "bearish" and be:
        invalidation.append(f"The underlying stays above the break-even of {be[-1]:,.2f} into expiry.")
    elif spec["outlook"] == "range-bound" and len(be) >= 2:
        invalidation.append(f"The underlying moves outside {be[0]:,.2f} to {be[-1]:,.2f} before expiry.")
    elif spec["outlook"] == "big move either way" and len(be) >= 2:
        invalidation.append(f"The underlying stays between {be[0]:,.2f} and {be[-1]:,.2f}, or implied volatility falls.")
    invalidation.append("Implied volatility changes sharply (see the scenario table).")
    invalidation.append("New information (results, events) gaps the price past the strikes.")

    return {
        **base,
        "payoff": {
            "net_premium": round(net, 2), "net_premium_kind": "credit" if net > 0 else "debit",
            "max_profit": money(exact["max_profit"]), "max_loss": money(exact["max_loss"]),
            "unlimited_profit": exact["unlimited_profit"], "unlimited_loss": exact["unlimited_loss"],
            "breakevens": be, "risk_reward": rr,
            "basis": "Expiry payoff using conservative fills (buy at ask, sell at bid), per position of "
                     f"{lots} lot(s) x {lot} units. Excludes brokerage, taxes and statutory charges.",
        },
        "verification": verification,
        "greeks": st.position_greeks(legs, spot, T, r, q, units),
        "curves": st.curves(legs, spot, T, r, q, units),
        "scenarios": st.scenarios(legs, spot, T, r, q, units),
        "invalidation": invalidation,
        "risk": assessment,
        "context": ctx,
    }


def _leg_quote(l: dict) -> dict | None:
    q = l.get("quote")
    if not q:
        return None
    return {k: q.get(k) for k in ("bid", "ask", "mid", "ltp", "spread_pct", "oi", "volume", "iv", "greeks")}


def _ctx(snap: dict, view: dict, T: float) -> dict:
    return {
        "data_type": view["data_type"],
        "data_fresh": snap["spot"]["sessions_missing"] < 2,
        "days_to_expiry": T * 365,
        "settlement": snap["underlying"]["settlement"],
        "underlying_type": snap["underlying"]["type"],
        "iv_to_realised": view["summary"]["iv_to_realised"],
        "spot": snap["spot"]["price"],
    }
