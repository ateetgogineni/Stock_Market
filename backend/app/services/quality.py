"""Data-quality gates (plan sections 3.6, 4.16 and 17.5).

These are deterministic rules, not LLM opinions. A failed critical gate blocks
the ratings it affects and forces INSUFFICIENT DATA; warnings are always shown.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from ..analytics import formatting as fmt
from .instruments import EXTENDED_NOTE
from .market_calendar import to_ist

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
STALE_CRITICAL = 5
STALE_WARNING = 2


def _gate(gid, title, severity, passed, message, affects=("all",), evidence_ids=()):
    return {
        "id": gid,
        "title": title,
        "severity": severity,  # critical | warning | info
        "passed": bool(passed),
        "status": "pass" if passed else {"critical": "fail", "warning": "warn", "info": "info"}[severity],
        "message": message,
        "affects": list(affects),
        "evidence_ids": list(evidence_ids),
    }


def run_quality_gates(snapshot, *, price, technical, fundamentals, news, returns, profile, bars) -> list[dict]:
    gates: list[dict] = []
    inst, listing = snapshot["instrument"], snapshot["listing"]
    ds, errors = snapshot["datasets"], snapshot["errors"]
    ent = snapshot["provider"]["entitlement"]

    ok_identity = bool(ISIN_RE.match(inst.get("isin", ""))) and listing.get("exchange") in ("NSE", "BSE") and inst.get("currency") == "INR"
    gates.append(_gate("instrument_identity", "Instrument identity", "critical", ok_identity,
                       f"{inst.get('name')} | ISIN {inst.get('isin')} | {listing.get('exchange')}:{listing.get('symbol')} | {inst.get('currency')}"
                       if ok_identity else "ISIN, exchange or currency could not be confirmed."))
    gates.append(_gate("listing_identifier", "Listing identifier verified", "warning", listing.get("identifier_verified", False),
                       "Listing confirmed against the NSE securities master." if listing.get("identifier_verified")
                       else listing.get("verification_source", "Listing identifier not verified."), affects=()))
    if inst.get("coverage") == "extended":
        gates.append(_gate("coverage_tier", "Coverage tier", "warning", False, EXTENDED_NOTE, affects=()))
    series = listing.get("series")
    if series and series != "EQ":
        gates.append(_gate("trading_series", "Trading series", "warning", False,
                           f"Listed in NSE series {series}, which settles trade-for-trade. Liquidity and settlement "
                           "differ from the regular EQ segment.", affects=()))
    dev = not ent.get("production_use", False)
    gates.append(_gate("provider_entitlement", "Data licence", "warning", not dev,
                       ent.get("notes", "") if dev else "Licensed feed.", affects=()))

    has_prices = price.get("data_status") != "unavailable"
    gates.append(_gate("price_history", "Price history available", "critical", has_prices,
                       f"{(bars is not None and len(bars)) or 0} completed sessions." if has_prices else f"No usable price history: {price.get('reason')}",
                       evidence_ids=["dataset.history"] if has_prices else []))
    if has_prices:
        n = len(bars)
        hist = price.get("history") or {}
        if n >= 252:
            depth_msg = f"{n} sessions available (SMA200, 1-year returns, volatility and beta need 252)."
        elif hist.get("recently_listed"):
            depth_msg = (f"Listed on NSE on {hist['listing_date']}, so there are only {n} trading sessions so far. "
                         "Medium- and long-term ratings need 252 sessions (about one year) to measure momentum, "
                         f"volatility, drawdown and beta. Enough history should exist from around {hist['full_year_from']} "
                         "(later if there are exchange holidays).")
        else:
            since = f", although the company has been listed on NSE since {hist['listing_date']}" if hist.get("listing_date") else ""
            depth_msg = (f"The provider returned only {n} sessions (from {hist.get('first_session')}){since}. The price "
                         "history is incomplete; medium- and long-term ratings need 252 sessions.")
        gates.append(_gate("price_history_depth", "At least one year of trading history", "critical", n >= 252,
                           depth_msg, affects=("medium", "long")))
        missing = price.get("sessions_missing", 0)
        if missing >= STALE_CRITICAL:
            gates.append(_gate("price_freshness", "Price freshness", "critical", False,
                               f"Last completed session is {price['last_session']}, {missing} sessions behind the expected {price['expected_session']}. Data is stale.",
                               evidence_ids=["price.last_close"]))
        elif missing >= STALE_WARNING:
            gates.append(_gate("price_freshness", "Price freshness", "warning", False,
                               f"Last completed session is {price['last_session']}, {missing} sessions behind the expected {price['expected_session']}. "
                               "This can be an exchange holiday (calendar not loaded) or provider lag.", affects=(),
                               evidence_ids=["price.last_close"]))
        else:
            gates.append(_gate("price_freshness", "Price freshness", "critical", True,
                               f"Last completed session {price['last_session']} (expected {price['expected_session']}).",
                               evidence_ids=["price.last_close"]))
        moves = bars["close"].astype(float).pct_change().abs()
        splits = set(bars.index[bars["split"].fillna(0) > 0])
        jumps = [d for d, m in moves.items() if m >= 0.40 and d not in splits]
        gates.append(_gate("corporate_action_adjustment", "Corporate-action adjustment", "warning", not jumps,
                           "No unexplained one-session moves of 40% or more." if not jumps else
                           f"One-session moves of 40%+ without a recorded split on {', '.join(jumps[:3])}. "
                           "This can be an unadjusted bonus, split or demerger; indicators around these dates may be wrong.",
                           affects=(), evidence_ids=["dataset.history"]))
        integ = price.get("integrity", {})
        bad = integ.get("sessions_dropped", 0) + integ.get("high_below_low", 0)
        gates.append(_gate("price_integrity", "Price series integrity", "warning", bad == 0,
                           "No missing or invalid bars." if bad == 0 else
                           f"{integ.get('sessions_dropped', 0)} bars dropped for missing/non-positive prices; {integ.get('high_below_low', 0)} bars with high below low.",
                           affects=()))

        quote = price.get("quote")
        if quote and quote.get("price") and quote.get("market_time"):
            qdate = to_ist(datetime.fromisoformat(quote["market_time"])).date().isoformat()
            if price["data_status"] == "end_of_day" and qdate == price["last_session"]:
                diff = abs(quote["price"] / price["last_close"] - 1)
                gates.append(_gate("quote_consistency", "Quote vs end-of-day close", "warning", diff <= 0.01,
                                   f"Provider quote {fmt.inr(quote['price'])} vs session close {fmt.inr(price['last_close'])} ({fmt.pct(diff)} apart). "
                                   "NSE's official close is a 30-minute weighted average, so small differences are expected.",
                                   affects=(), evidence_ids=["price.last_close"]))

        cross = ds.get("cross_listing")
        if cross and cross.get("data") and bars is not None:
            other = {r["date"]: r["close"] for r in cross["data"] if r.get("close")}
            common = [d for d in bars.index if d in other]
            if common:
                d = common[-1]
                diff = abs(other[d] / float(bars.loc[d, "close"]) - 1)
                gates.append(_gate("cross_listing_consistency", f"{listing['exchange']} vs {cross.get('exchange')} close", "warning", diff <= 0.015,
                                   f"On {d}: {listing['exchange']} {fmt.inr(float(bars.loc[d, 'close']))} vs {cross.get('exchange')} {fmt.inr(other[d])} ({fmt.pct(diff)} apart).",
                                   affects=()))
            else:
                gates.append(_gate("cross_listing_consistency", f"Cross-listing check ({cross.get('exchange')})", "info", False,
                                   "No common session with the other listing to compare.", affects=()))
        elif "cross_listing" in errors:
            gates.append(_gate("cross_listing_consistency", "Cross-listing check", "info", False,
                               f"Other listing could not be fetched: {errors['cross_listing']['message']}", affects=()))

    # Trading currency: prices must be in the listing's currency, or nothing price-based is valid.
    reported = {k: v for k, v in {
        "profile currency": profile.get("currency"),
        "quote currency": (price.get("quote") or {}).get("currency"),
    }.items() if v}
    mismatched = {k: v for k, v in reported.items() if v != inst.get("currency")}
    if mismatched:
        gates.append(_gate("currency_consistency", "Trading currency", "critical", False,
                           "Currency mismatch: " + ", ".join(f"{k} {v}" for k, v in mismatched.items()) + f" vs listing {inst.get('currency')}."))
    elif reported:
        gates.append(_gate("currency_consistency", "Trading currency", "critical", True,
                           f"Prices are in {inst.get('currency')}, matching the listing."))
    else:
        gates.append(_gate("currency_consistency", "Trading currency", "warning", False,
                           "Provider did not report a currency; INR assumed from the listing.", affects=()))
    # Reporting currency: statements in another currency keep currency-neutral ratios but lose price-based valuation.
    stmt_ccy = fundamentals.get("currency")
    if fundamentals.get("status") == "ok" and stmt_ccy:
        same = stmt_ccy == inst.get("currency")
        gates.append(_gate("reporting_currency", "Statement currency", "warning", same,
                           f"Statements are reported in {stmt_ccy}." if same else
                           f"Statements are reported in {stmt_ccy} while prices are in {inst.get('currency')}. Margins, returns and "
                           "leverage ratios are kept; P/E and P/B are withheld until an FX conversion source is configured.",
                           affects=()))

    ann = fundamentals.get("annual_periods") or []
    gates.append(_gate("annual_statements", "Two or more annual statements", "critical", len(ann) >= 2,
                       f"{len(ann)} annual period(s): {', '.join(fmt.fy_label(p) for p in ann[:5])}." if ann else
                       f"No annual statements: {errors.get('statements', {}).get('message', 'not reported')}",
                       affects=("long",)))
    if ann:
        as_of = datetime.fromisoformat(snapshot["requested_at"]).date()
        age = (as_of - date.fromisoformat(ann[0])).days
        if age > 640:
            gates.append(_gate("statement_recency", "Annual statements are recent", "critical", False,
                               f"Latest annual period {fmt.fy_label(ann[0])} is {age} days old.", affects=("long",)))
        else:
            gates.append(_gate("statement_recency", "Annual statements are recent", "warning", age <= 460,
                               f"Latest annual period {fmt.fy_label(ann[0])} ended {age} days before this run. Filing date not provided by the dev source.",
                               affects=()))
        gap = fundamentals.get("annual_gap_days")
        if gap is not None:
            gates.append(_gate("period_comparability", "Annual periods comparable", "warning", 350 <= gap <= 380,
                               f"Latest two annual periods are {gap} days apart.", affects=()))
    q = fundamentals.get("metrics", {}).get("q_revenue_yoy")
    if q is not None:
        gates.append(_gate("quarterly_yoy", "Same-quarter prior-year comparison", "warning", q["status"] == "ok",
                           f"Comparing {q['period']}." if q["status"] == "ok" else f"Unavailable: {q.get('reason')}.", affects=()))
    for note in fundamentals.get("notes", []):
        gates.append(_gate("fundamentals_note", "Fundamentals data note", "info", False, note, affects=()))

    rel = returns.get("relative", {}).get("3m")
    gates.append(_gate("benchmark", "NIFTY 50 benchmark data", "warning", rel is not None,
                       "Benchmark returns available." if rel is not None else
                       f"Benchmark unavailable: {errors.get('benchmark', {}).get('message', 'no overlapping data')}", affects=()))
    gates.append(_gate("news", "News items available", "warning", bool(news.get("items")),
                       f"{len(news.get('items', []))} unique headline(s) after removing {news.get('duplicates_removed', 0)} duplicate(s)."
                       if news.get("items") else f"No news: {errors.get('news', {}).get('message', 'none returned')}", affects=()))
    gates.append(_gate("official_filings", "Official exchange filings", "warning", "filings" in ds,
                       "Filings available." if "filings" in ds else errors.get("filings", {}).get("message", "Unavailable."), affects=()))

    reported_q = (price.get("quote") or {}).get("reported") or {}
    mcap = fundamentals.get("market_cap")
    if mcap and reported_q.get("market_cap"):
        diff = abs(mcap / reported_q["market_cap"] - 1)
        gates.append(_gate("market_cap_cross_check", "Market cap vs provider", "warning", diff <= 0.05,
                           f"Computed {fmt.inr(mcap)} vs provider {fmt.inr(reported_q['market_cap'])} ({fmt.pct(diff)} apart).",
                           affects=(), evidence_ids=["calc.market_cap"]))
    pe = fundamentals.get("metrics", {}).get("pe", {})
    if pe.get("value") and reported_q.get("trailing_pe"):
        diff = abs(pe["value"] / reported_q["trailing_pe"] - 1)
        gates.append(_gate("pe_cross_check", "P/E vs provider", "warning", diff <= 0.15,
                           f"Computed {fmt.times(pe['value'])} ({fundamentals.get('eps_basis')}) vs provider {fmt.times(reported_q['trailing_pe'])}. "
                           "Definitions can differ (consolidated vs standalone EPS, TTM window).", affects=(), evidence_ids=["calc.pe"]))
    if bars is not None and len(bars) >= 60:
        zero = int((bars["volume"].fillna(0).iloc[-60:] <= 0).sum())
        gates.append(_gate("liquidity_data", "Trading activity", "warning", zero <= 6,
                           f"{zero} of the last 60 sessions had zero reported volume.", affects=()))
    return gates


def summarise_gates(gates: list[dict]) -> dict:
    failed_all = [g for g in gates if g["severity"] == "critical" and not g["passed"] and "all" in g["affects"]]
    failed_partial = [g for g in gates if g["severity"] == "critical" and not g["passed"] and "all" not in g["affects"]]
    warnings = [g for g in gates if g["severity"] == "warning" and not g["passed"]]
    status = "insufficient" if failed_all else "partial" if failed_partial else "degraded" if warnings else "good"
    return {
        "status": status,
        "critical_failures": [g["id"] for g in failed_all + failed_partial],
        "warnings": [g["id"] for g in warnings],
        "passed": sum(1 for g in gates if g["passed"]),
        "total": len(gates),
    }


def blocked_horizon(gates: list[dict], horizon: str) -> list[dict]:
    return [g for g in gates if g["severity"] == "critical" and not g["passed"] and ("all" in g["affects"] or horizon in g["affects"])]
