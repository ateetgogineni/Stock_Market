"""Deterministic analysis core.

`compute_deterministic(snapshot)` is a pure function of the saved snapshot: no
network, no clock, no LLM. Replaying a run recomputes it and compares hashes.
"""

from __future__ import annotations

import hashlib
import math
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd

from ..analytics import ENGINE_VERSION, FORMULA_VERSIONS
from ..analytics import forecast as forecast_engine
from ..analytics import formatting as fmt
from ..analytics import fundamentals as fa
from ..analytics import indicators as ind
from ..analytics import risk_metrics as rm
from . import market_calendar as mc
from .evidence import EvidenceStore
from .quality import run_quality_gates, summarise_gates
from .recommendation import load_rules

STALE_CRITICAL_SESSIONS = 5
FULL_YEAR_SESSIONS = 252
RETURN_WINDOWS = {"1m": 21, "3m": 63, "6m": 126, "1y": 252}
LINE_LABELS = {
    "revenue": "Revenue", "gross_profit": "Gross profit", "operating_income": "Operating income",
    "ebit": "EBIT", "ebitda": "EBITDA", "interest_expense": "Interest expense", "net_income": "Net income",
    "diluted_eps": "Diluted EPS", "equity": "Shareholders' equity", "total_assets": "Total assets",
    "total_debt": "Total debt", "current_assets": "Current assets", "current_liabilities": "Current liabilities",
    "cash": "Cash and equivalents", "shares": "Shares outstanding", "operating_cash_flow": "Operating cash flow",
    "capex": "Capital expenditure", "free_cash_flow": "Free cash flow (provider-reported)",
}


def _f(x) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def _formula(fid: str, expression: str) -> dict:
    return {"id": fid, "version": FORMULA_VERSIONS.get(fid, FORMULA_VERSIONS.get("fundamentals")), "expression": expression}


def _bars(dataset: dict | None) -> pd.DataFrame | None:
    if not dataset or not dataset.get("data"):
        return None
    df = pd.DataFrame(dataset["data"]).set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df


# --------------------------------------------------------------------------- price


def _price_section(snapshot: dict, ev: EvidenceStore, requested_at: datetime, market: dict, notes: list) -> dict:
    ds = snapshot["datasets"]
    out: dict = {"data_status": "unavailable", "_bars": None}
    raw = _bars(ds.get("history"))
    if raw is None:
        out["reason"] = snapshot["errors"].get("history", {}).get("message", "no price history")
        return out

    total = len(raw)
    clean = raw.dropna(subset=["open", "high", "low", "close"])
    clean = clean[(clean[["open", "high", "low", "close"]] > 0).all(axis=1)]
    out["integrity"] = {
        "sessions_received": total,
        "sessions_dropped": total - len(clean),
        "high_below_low": int((clean["high"] < clean["low"]).sum()),
    }
    local_now = mc.to_ist(requested_at)
    if len(clean) and clean.index[-1] == local_now.date().isoformat() and local_now.time() < mc.EOD_READY:
        clean = clean.iloc[:-1]
        out["partial_session_excluded"] = True
        notes.append("Today's in-progress session bar was excluded; analytics use completed sessions only.")
    if clean.empty:
        out["reason"] = "no usable price bars"
        return out

    expected = mc.expected_last_session(requested_at)
    last_date = clean.index[-1]
    missing = mc.sessions_missing(date.fromisoformat(last_date), expected)
    quote = (ds.get("quote") or {}).get("data")
    quote_today = False
    if quote and quote.get("market_time"):
        quote_today = mc.to_ist(datetime.fromisoformat(quote["market_time"])).date() == local_now.date()

    if missing >= STALE_CRITICAL_SESSIONS:
        data_status = "stale"
    elif market["status"] == "open" and quote_today:
        data_status = "delayed"
    else:
        data_status = "end_of_day"

    close = clean["close"]
    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else None

    ev.add(
        "dataset.history", kind="dataset", label="Daily price history",
        display=f"{len(clean)} completed sessions from {clean.index[0]} to {last_date}",
        observed_at=last_date, source=ev.source("history", detail=snapshot["listing"]["provider_symbol"]),
        note="Open, high, low and close are split-adjusted by the provider; adj_close also adjusts for dividends. "
        "Indicators use split-adjusted prices; total return uses adj_close.",
    )
    ev.add("price.last_close", kind="source", label=f"Closing price on {last_date}", value=last_close,
           display=fmt.inr(last_close), unit="INR", currency="INR", observed_at=last_date,
           source=ev.source("history"))
    if prev_close:
        ev.add("price.prev_close", kind="source", label=f"Previous closing price ({close.index[-2]})",
               value=prev_close, display=fmt.inr(prev_close), unit="INR", currency="INR",
               observed_at=close.index[-2], source=ev.source("history"))
        chg = last_close / prev_close - 1
        ev.add("price.change_1d", kind="calculation", label=f"One-session change to {last_date}", value=chg,
               display=fmt.pct(chg), unit="ratio", observed_at=last_date,
               formula=_formula("risk.period_return", "close / previous close - 1"),
               inputs=["price.last_close", "price.prev_close"])

    header = {
        "price": last_close,
        "previous_close": prev_close,
        "change": (last_close - prev_close) if prev_close else None,
        "change_pct": (last_close / prev_close - 1) if prev_close else None,
        "as_of": f"{last_date}T15:30:00+05:30",
        "basis": "Last completed session close",
        "evidence_id": "price.last_close",
    }
    if data_status == "delayed" and quote and quote.get("price"):
        q_price, q_prev = float(quote["price"]), _f(quote.get("previous_close"))
        ev.add("quote.delayed_price", kind="source", label="Delayed intraday quote", value=q_price,
               display=fmt.inr(q_price), unit="INR", currency="INR", observed_at=quote["market_time"],
               source=ev.source("quote"), note=f"Delayed about {quote.get('delay_minutes') or '?'} minutes; not live.")
        header = {
            "price": q_price, "previous_close": q_prev,
            "change": (q_price - q_prev) if q_prev else None,
            "change_pct": (q_price / q_prev - 1) if q_prev else None,
            "as_of": quote["market_time"], "basis": f"Delayed quote (~{quote.get('delay_minutes') or '?'} min)",
            "evidence_id": "quote.delayed_price",
        }

    # How much trading history exists, and whether that is because the company listed recently
    # (expected) or because the provider's history is incomplete (a data gap).
    n_sessions = len(clean)
    listed = snapshot["instrument"].get("nse_listing_date") if snapshot["listing"]["exchange"] == "NSE" else None
    starts_at_listing = bool(listed) and date.fromisoformat(clean.index[0]) <= date.fromisoformat(listed) + timedelta(days=10)
    history = {
        "sessions": n_sessions,
        "first_session": clean.index[0],
        "listing_date": listed,
        "starts_at_listing": starts_at_listing,
        "recently_listed": starts_at_listing and n_sessions < FULL_YEAR_SESSIONS,
        "full_year_from": mc.add_sessions(date.fromisoformat(last_date), FULL_YEAR_SESSIONS - n_sessions).isoformat()
        if n_sessions < FULL_YEAR_SESSIONS else None,
    }

    actions = raw[(raw["dividend"] > 0) | (raw["split"] > 0)]
    out.update(
        {
            "data_status": data_status,
            "header": header,
            "history": history,
            "last_session": last_date,
            "expected_session": expected.isoformat(),
            "sessions_missing": missing,
            "quote": quote,
            "last_close": last_close,
            "corporate_actions": [
                {"date": d, "dividend": _f(r["dividend"]) or None, "split": _f(r["split"]) or None}
                for d, r in actions.iterrows()
            ][-20:],
            "_bars": clean,
        }
    )
    return out


# ----------------------------------------------------------------------- technical


def _technical(bars: pd.DataFrame, ev: EvidenceStore) -> dict:
    close, high, low = bars["close"].astype(float), bars["high"].astype(float), bars["low"].astype(float)
    volume = bars["volume"].fillna(0).astype(float)
    last_date = bars.index[-1]
    last = float(close.iloc[-1])
    out: dict = {"status": "ok", "sessions": len(bars), "as_of": last_date}
    inputs = ["dataset.history"]

    def put(key, eid, label, value, display, fid, expr, unit, extra_inputs=None):
        v = _f(value)
        out[key] = v
        ev.add(eid, kind="calculation", label=label, value=v, display=display(v) if v is not None else "unavailable",
               unit=unit, observed_at=last_date, formula=_formula(fid, expr),
               inputs=inputs + (extra_inputs or []), status="ok" if v is not None else "unavailable",
               note=None if v is not None else "not enough sessions")

    for n in (20, 50, 200):
        put(f"sma{n}", f"ind.sma{n}", f"Simple moving average ({n} sessions)", ind.sma(close, n).iloc[-1],
            fmt.inr, "indicator.sma", f"mean of last {n} closes", "INR")
    put("ema20", "ind.ema20", "Exponential moving average (20 sessions)", ind.ema(close, 20).iloc[-1],
        fmt.inr, "indicator.ema_sma_seeded", "EMA, alpha = 2/21, SMA-seeded", "INR")
    put("rsi14", "ind.rsi14", "RSI (14 sessions, Wilder)", ind.rsi(close, 14).iloc[-1],
        lambda v: fmt.num(v, 1), "indicator.rsi_wilder", "100 - 100 / (1 + avg gain / avg loss)", "index")
    m = ind.macd(close)
    put("macd", "ind.macd", "MACD line (12, 26)", m["macd"].iloc[-1], fmt.num, "indicator.macd", "EMA12 - EMA26", "INR")
    put("macd_signal", "ind.macd_signal", "MACD signal (9)", m["signal"].iloc[-1], fmt.num, "indicator.macd", "EMA9 of MACD", "INR")
    put("macd_hist", "ind.macd_hist", "MACD histogram", m["hist"].iloc[-1], fmt.num, "indicator.macd", "MACD - signal", "INR")
    b = ind.bollinger(close)
    put("bb_upper", "ind.bb_upper", "Bollinger upper band (20, 2)", b["upper"].iloc[-1], fmt.inr,
        "indicator.bollinger_population_sd", "SMA20 + 2 sd", "INR")
    put("bb_lower", "ind.bb_lower", "Bollinger lower band (20, 2)", b["lower"].iloc[-1], fmt.inr,
        "indicator.bollinger_population_sd", "SMA20 - 2 sd", "INR")
    put("bb_percent_b", "ind.bb_percent_b", "Bollinger %B", b["percent_b"].iloc[-1], lambda v: fmt.num(v, 2),
        "indicator.bollinger_population_sd", "(close - lower) / (upper - lower)", "ratio")
    atr_series = ind.atr(high, low, close, 14)
    put("atr14", "ind.atr14", "Average true range (14 sessions, Wilder)", atr_series.iloc[-1], fmt.inr,
        "indicator.atr_wilder", "Wilder average of true range", "INR")
    atr_pct = atr_series / close
    put("atr_pct", "ind.atr_pct", "ATR as % of price", atr_pct.iloc[-1], fmt.pct, "indicator.atr_wilder",
        "ATR14 / close", "ratio", ["ind.atr14", "price.last_close"])
    put("vwap20", "ind.vwap20", "Rolling VWAP (20 sessions, daily bars)", ind.vwap_rolling(high, low, close, volume).iloc[-1],
        fmt.inr, "indicator.vwap_rolling_typical_price", "sum(typical price x volume) / sum(volume)", "INR")

    tail = bars.iloc[-250:]
    put("high_52w", "tech.high_52w", f"52-week high (last {len(tail)} sessions)", tail["high"].max(), fmt.inr,
        "indicator.support_resistance_rolling_extremes", "max(high)", "INR")
    put("low_52w", "tech.low_52w", f"52-week low (last {len(tail)} sessions)", tail["low"].min(), fmt.inr,
        "indicator.support_resistance_rolling_extremes", "min(low)", "INR")

    # Derived positioning used by the rating rules.
    def rel(key, eid, label, a, b_, extra):
        v = (a / b_ - 1) if a is not None and b_ else None
        put(key, eid, label, v, fmt.pct, "indicator.sma", "a / b - 1", "ratio", extra)

    rel("price_vs_sma200", "tech.price_vs_sma200", "Close vs SMA200", last, out["sma200"], ["price.last_close", "ind.sma200"])
    rel("price_vs_sma50", "tech.price_vs_sma50", "Close vs SMA50", last, out["sma50"], ["price.last_close", "ind.sma50"])
    rel("sma50_vs_sma200", "tech.sma50_vs_sma200", "SMA50 vs SMA200", out["sma50"], out["sma200"], ["ind.sma50", "ind.sma200"])
    hist_pct = out["macd_hist"] / last if out["macd_hist"] is not None else None
    put("macd_hist_pct", "tech.macd_hist_pct", "MACD histogram as % of price", hist_pct, fmt.pct, "indicator.macd",
        "MACD histogram / close", "ratio", ["ind.macd_hist", "price.last_close"])

    # Classifications (deterministic rules, shown with their inputs).
    if out["sma50"] is not None and out["sma200"] is not None:
        if last > out["sma200"] and out["sma50"] > out["sma200"]:
            trend, why = "uptrend", "close above SMA200 and SMA50 above SMA200"
        elif last < out["sma200"] and out["sma50"] < out["sma200"]:
            trend, why = "downtrend", "close below SMA200 and SMA50 below SMA200"
        else:
            trend, why = "mixed", "close and SMA50 disagree about SMA200"
    else:
        trend, why = "unavailable", "fewer than 200 sessions"
    out["trend"] = trend
    ev.add("tech.trend", kind="classification", label="Trend classification", value=trend,
           display=f"{trend} ({why})", observed_at=last_date,
           formula={"id": "rule.trend", "version": "1.0", "expression": "close vs SMA200 and SMA50 vs SMA200"},
           inputs=["price.last_close", "ind.sma50", "ind.sma200"])

    rsi_v = out["rsi14"]
    zone = None if rsi_v is None else "overbought zone (>70)" if rsi_v > 70 else "oversold zone (<30)" if rsi_v < 30 else "neutral zone (30-70)"
    out["rsi_zone"] = zone

    valid_atr = atr_pct.dropna().iloc[-250:]
    if len(valid_atr) >= 60 and out["atr_pct"] is not None:
        ratio = out["atr_pct"] / float(valid_atr.median())
        regime = "elevated" if ratio > 1.3 else "compressed" if ratio < 0.7 else "normal"
        out["volatility_regime"] = {"regime": regime, "atr_pct_vs_1y_median": ratio}
        ev.add("tech.volatility_regime", kind="classification", label="Volatility regime (ATR% vs 1-year median)",
               value=ratio, display=f"{regime} ({fmt.num(ratio)}x the 1-year median ATR%)", observed_at=last_date,
               formula={"id": "rule.volatility_regime", "version": "1.0", "expression": ">1.3x elevated, <0.7x compressed"},
               inputs=["ind.atr_pct"])

    levels = ind.support_resistance(bars)
    out["levels"] = levels
    for lv in levels:
        w = lv["window"]
        ev.add(f"tech.support_{w}", kind="calculation", label=f"Support: lowest low of last {w} sessions",
               value=lv["support"], display=fmt.inr(lv["support"]), unit="INR", observed_at=lv["support_date"],
               formula=_formula("indicator.support_resistance_rolling_extremes", f"min(low) over {w} sessions"), inputs=inputs)
        ev.add(f"tech.resistance_{w}", kind="calculation", label=f"Resistance: highest high of last {w} sessions",
               value=lv["resistance"], display=fmt.inr(lv["resistance"]), unit="INR", observed_at=lv["resistance_date"],
               formula=_formula("indicator.support_resistance_rolling_extremes", f"max(high) over {w} sessions"), inputs=inputs)

    if len(bars) > 61:
        prior_high = float(high.iloc[-61:-1].max())
        prior_low = float(low.iloc[-61:-1].min())
        cond = "breakout above prior 60-session high" if last > prior_high else \
            "breakdown below prior 60-session low" if last < prior_low else "inside prior 60-session range"
        out["range_condition"] = cond
        ev.add("tech.range_condition", kind="classification", label="Close vs prior 60-session range", value=cond,
               display=f"{cond} ({fmt.inr(prior_low)} to {fmt.inr(prior_high)})", observed_at=last_date,
               formula={"id": "rule.range_condition", "version": "1.0", "expression": "close vs max/min of previous 60 sessions"},
               inputs=inputs)

    vr = ind.volume_ratio(volume)
    put("volume_ratio", "tech.volume_ratio", "Latest volume vs 50-session median", vr, lambda v: fmt.times(v),
        "indicator.volume_ratio_median", "volume / median(previous 50 volumes)", "ratio")
    out["abnormal_volume"] = vr is not None and vr >= 2.0
    out["gaps"] = ind.price_gaps(bars)
    return out


# ------------------------------------------------------------------------- returns


def _returns(bars: pd.DataFrame, bench: pd.DataFrame | None, ev: EvidenceStore) -> dict:
    close = bars["close"].astype(float)
    last_date = bars.index[-1]
    out: dict = {"stock": {}, "benchmark": {}, "relative": {}}
    b_close = None
    if bench is not None:
        b_close = bench["close"].dropna().astype(float)
        b_close = b_close[b_close.index <= last_date]
        if b_close.empty:
            b_close = None
    for key, n in RETURN_WINDOWS.items():
        r = rm.period_return(close, n)
        start = close.index[-1 - n] if len(close) > n else None
        period = f"{start} to {last_date}" if start else None
        out["stock"][key] = r
        ev.add(f"ret.{key}", kind="calculation", label=f"Price return, {key} ({n} sessions)", value=r,
               display=fmt.pct(r), unit="ratio", period=period, observed_at=last_date,
               formula=_formula("risk.period_return", f"close / close {n} sessions earlier - 1"),
               inputs=["dataset.history"], status="ok" if r is not None else "unavailable")
        br = rm.period_return(b_close, n) if b_close is not None else None
        out["benchmark"][key] = br
        ev.add(f"bench.ret.{key}", kind="calculation", label=f"NIFTY 50 return, {key} ({n} sessions)", value=br,
               display=fmt.pct(br), unit="ratio", period=period, observed_at=last_date,
               formula=_formula("risk.period_return", f"index close / close {n} sessions earlier - 1"),
               source=ev.source("benchmark", detail="^NSEI"), status="ok" if br is not None else "unavailable")
        rel = (r - br) if r is not None and br is not None else None
        out["relative"][key] = rel
        ev.add(f"rel.ret.{key}", kind="calculation", label=f"Return vs NIFTY 50, {key}", value=rel,
               display=fmt.pct(rel), unit="ratio", period=period, observed_at=last_date,
               formula=_formula("risk.period_return", "stock return - NIFTY 50 return"),
               inputs=[f"ret.{key}", f"bench.ret.{key}"], status="ok" if rel is not None else "unavailable")
    adj = bars["adj_close"].dropna().astype(float) if "adj_close" in bars else None
    tr = rm.period_return(adj, 252) if adj is not None and len(adj) > 252 else None
    out["stock"]["total_1y"] = tr
    ev.add("ret.total_1y", kind="calculation", label="Total return incl. dividends, 1 year", value=tr,
           display=fmt.pct(tr), unit="ratio", observed_at=last_date,
           formula=_formula("risk.period_return", "adj_close / adj_close 252 sessions earlier - 1"),
           inputs=["dataset.history"], status="ok" if tr is not None else "unavailable")
    mom = rm.momentum_12_1(close)
    out["momentum_12_1"] = mom
    ev.add("ret.momentum_12_1", kind="calculation", label="12-1 month momentum (skips latest month)", value=mom,
           display=fmt.pct(mom), unit="ratio", observed_at=last_date,
           formula=_formula("risk.momentum_12_1", "close 21 sessions ago / close 252 sessions ago - 1"),
           inputs=["dataset.history"], status="ok" if mom is not None else "unavailable")
    return out


# -------------------------------------------------------------------- fundamentals


class _Fundamentals:
    def __init__(self, raw: dict | None, ev: EvidenceStore, ccy: str):
        self.st = fa.Statements(raw)
        self.ev = ev
        self.ccy = ccy  # currency the statements are reported in
        self.ids: dict[tuple, str] = {}

    def sv_id(self, v: fa.StatementValue) -> str:
        k = (v.freq, v.key, v.period)
        if k in self.ids:
            return self.ids[k]
        if v.freq == "derived":
            raise KeyError(k)
        eid = f"stmt.{v.freq[0]}.{v.key}.{v.period}"
        label_period = fmt.fy_label(v.period) if v.freq == "annual" else fmt.quarter_label(v.period)
        is_eps = v.key == "diluted_eps"
        is_shares = v.key == "shares"
        display = fmt.indian_number(v.value, 0) if is_shares else fmt.money(v.value, self.ccy)
        self.ev.add(eid, kind="source", label=f"{LINE_LABELS[v.key]} ({label_period})", value=float(v.value),
                    display=display, unit="shares" if is_shares else f"{self.ccy}/share" if is_eps else self.ccy,
                    currency=None if is_shares else self.ccy, period=label_period,
                    source=self.ev.source("statements", detail=f"{v.freq} {fa.LINE_TABLE[v.key]}: {v.line_item}"))
        self.ids[k] = eid
        return eid

    def get(self, key, period, freq="annual"):
        return self.st.get(freq, key, period) if period else None

    def metric(self, eid: str, label: str, res: fa.MetricResult, kind: str, period_label: str) -> dict:
        disp = {"pct": fmt.pct, "times": fmt.times, "money": lambda x: fmt.money(x, self.ccy)}[kind]
        v = _f(res.value)
        input_ids = [self.sv_id(i) for i in res.inputs]
        display = disp(v) if v is not None else f"unavailable ({res.reason})"
        self.ev.add(eid, kind="calculation", label=f"{label} ({period_label})", value=v, display=display,
                    unit="ratio" if kind == "pct" else "x" if kind == "times" else self.ccy, period=period_label,
                    formula={"id": f"fundamentals.{res.metric}", "version": res.version, "expression": res.formula},
                    inputs=input_ids, status=res.status, note=res.reason)
        return {"value": v, "status": res.status, "reason": res.reason, "evidence_id": eid, "display": display,
                "label": label, "period": period_label}

    def derived(self, key: str, label: str, value: Decimal, period: str, eid: str, expr: str, inputs: list,
                ccy: str | None = None) -> fa.StatementValue:
        ccy = ccy or self.ccy
        self.ev.add(eid, kind="calculation", label=label, value=float(value), display=fmt.money(value, ccy), unit=ccy,
                    currency=ccy, period=period, formula={"id": f"fundamentals.{key}", "version": fa.FORMULA_VERSION,
                                                            "expression": expr},
                    inputs=[self.sv_id(i) for i in inputs])
        sv = fa.StatementValue(key, label, "derived", period, value)
        self.ids[("derived", key, period)] = eid
        return sv


def _fundamentals(ds: dict, ev: EvidenceStore, bars: pd.DataFrame | None, last_close: float | None, sector: str | None,
                  stmt_ccy: str, price_ccy: str) -> dict:
    raw = (ds.get("statements") or {}).get("data")
    F = _Fundamentals(raw, ev, stmt_ccy)
    out: dict = {"status": "unavailable", "metrics": {}, "annual_table": [], "quarterly_table": [], "notes": [],
                 "currency": stmt_ccy}
    cross_ccy = stmt_ccy != price_ccy
    fx_reason = f"statements are in {stmt_ccy} and the price is in {price_ccy}; no FX conversion source is configured"
    if not raw:
        return out
    ann = F.st.periods("annual", "revenue") or F.st.periods("annual", "net_income")
    out["annual_periods"] = ann
    if not ann:
        out["notes"].append("No annual statements with revenue or net income.")
        return out
    out["status"] = "ok"
    p0 = ann[0]
    p1 = ann[1] if len(ann) > 1 else None
    L0 = fmt.fy_label(p0)
    Lg = f"{L0} vs {fmt.fy_label(p1)}" if p1 else L0
    M = out["metrics"]
    g = F.get

    M["revenue_growth"] = F.metric("calc.revenue_growth", "Revenue growth", fa.growth("revenue_growth", g("revenue", p0), g("revenue", p1)), "pct", Lg)
    M["net_income_growth"] = F.metric("calc.net_income_growth", "Net income growth", fa.growth("net_income_growth", g("net_income", p0), g("net_income", p1)), "pct", Lg)
    for key, line, label in [("gross_margin", "gross_profit", "Gross margin"), ("operating_margin", "operating_income", "Operating margin"),
                             ("ebitda_margin", "ebitda", "EBITDA margin"), ("net_margin", "net_income", "Net margin")]:
        M[key] = F.metric(f"calc.{key}", label, fa.ratio(key, g(line, p0), g("revenue", p0), f"{line} / revenue"), "pct", L0)
    M["roe"] = F.metric("calc.roe", "Return on equity", fa.ratio_on_average("roe", g("net_income", p0), g("equity", p0), g("equity", p1), "net income / average equity"), "pct", L0)
    M["roa"] = F.metric("calc.roa", "Return on assets", fa.ratio_on_average("roa", g("net_income", p0), g("total_assets", p0), g("total_assets", p1), "net income / average total assets"), "pct", L0)

    ta, cl = g("total_assets", p0), g("current_liabilities", p0)
    if ta and cl:
        ce = F.derived("capital_employed", f"Capital employed ({L0})", ta.value - cl.value, L0, "calc.capital_employed",
                       "total assets - current liabilities", [ta, cl])
        M["roce"] = F.metric("calc.roce", "Return on capital employed", fa.ratio("roce", g("ebit", p0), ce, "EBIT / capital employed"), "pct", L0)
    else:
        M["roce"] = F.metric("calc.roce", "Return on capital employed", fa.MetricResult("roce", None, "unavailable", "total assets or current liabilities not reported", [x for x in (ta, cl) if x], "EBIT / capital employed"), "pct", L0)
    M["debt_to_equity"] = F.metric("calc.debt_to_equity", "Debt to equity", fa.ratio("debt_to_equity", g("total_debt", p0), g("equity", p0), "total debt / equity"), "times", L0)
    M["interest_coverage"] = F.metric("calc.interest_coverage", "Interest coverage", fa.ratio("interest_coverage", g("ebit", p0), g("interest_expense", p0), "EBIT / |interest expense|", den_abs=True), "times", L0)
    M["current_ratio"] = F.metric("calc.current_ratio", "Current ratio", fa.ratio("current_ratio", g("current_assets", p0), cl, "current assets / current liabilities"), "times", L0)

    ocf, capex = g("operating_cash_flow", p0), g("capex", p0)
    if ocf and capex:
        fcf = F.derived("fcf", f"Free cash flow ({L0})", ocf.value - abs(capex.value), L0, "calc.fcf",
                        "operating cash flow - |capital expenditure|", [ocf, capex])
        M["fcf_margin"] = F.metric("calc.fcf_margin", "Free cash flow margin", fa.ratio("fcf_margin", fcf, g("revenue", p0), "free cash flow / revenue"), "pct", L0)
        reported = g("free_cash_flow", p0)
        if reported and reported.value != 0 and abs(fcf.value / reported.value - 1) > Decimal("0.02"):
            out["notes"].append(f"Computed free cash flow differs from the provider's reported figure by more than 2% ({L0}).")
    else:
        M["fcf_margin"] = F.metric("calc.fcf_margin", "Free cash flow margin", fa.MetricResult("fcf_margin", None, "unavailable", "operating cash flow or capex not reported", [x for x in (ocf, capex) if x], "free cash flow / revenue"), "pct", L0)
    M["cash_conversion"] = F.metric("calc.cash_conversion", "Cash conversion", fa.ratio("cash_conversion", ocf, g("net_income", p0), "operating cash flow / net income"), "times", L0)

    # ---- valuation
    if cross_ccy:
        out["notes"].append(f"Financial statements are reported in {stmt_ccy}, while the share price is in {price_ccy}. "
                            "Price-based valuation (P/E, P/B) is withheld until an FX conversion source is configured.")
    price = fa.to_decimal(last_close) if last_close else None
    price_sv = fa.StatementValue("price", "Last close", "derived", "latest", price) if price else None
    if price_sv:
        F.ids[("derived", "price", "latest")] = "price.last_close"
    q_eps_periods = F.st.periods("quarterly", "diluted_eps")
    quarters = fa.consecutive_quarters(q_eps_periods, 4)
    eps_sv = None
    if quarters:
        q_vals = [g("diluted_eps", p, "quarterly") for p in quarters]
        total = sum((q.value for q in q_vals), Decimal(0))
        basis = f"TTM: {fmt.quarter_label(quarters[-1])} to {fmt.quarter_label(quarters[0])}"
        eps_sv = F.derived("eps_ttm", f"Diluted EPS ({basis})", total, basis, "calc.eps_ttm", "sum of last 4 quarterly diluted EPS", q_vals)
    elif g("diluted_eps", p0):
        eps_sv = g("diluted_eps", p0)
        basis = f"annual {L0}"
    else:
        basis = "unavailable"
    out["eps_basis"] = basis
    if cross_ccy:
        pe_res = fa.MetricResult("pe", None, "not_meaningful", fx_reason, [x for x in (price_sv, eps_sv) if x], "price / diluted EPS")
    elif eps_sv is not None and eps_sv.value <= 0:
        pe_res = fa.MetricResult("pe", None, "not_meaningful", "EPS is zero or negative", [x for x in (price_sv, eps_sv) if x], "price / EPS")
    else:
        pe_res = fa.ratio("pe", price_sv, eps_sv, "price / diluted EPS")
    M["pe"] = F.metric("calc.pe", "Price to earnings", pe_res, "times", basis)

    shares_periods = F.st.periods("quarterly", "shares") + F.st.periods("annual", "shares")
    shares_sv = None
    if shares_periods:
        newest = max(shares_periods)
        shares_sv = g("shares", newest, "quarterly") or g("shares", newest, "annual")
    eq0 = g("equity", p0)
    if eq0 and shares_sv and shares_sv.value > 0:
        bvps = F.derived("book_value_per_share", f"Book value per share ({L0})", (eq0.value / shares_sv.value).quantize(Decimal("0.0001")),
                         L0, "calc.bvps", "equity / shares outstanding", [eq0, shares_sv])
        pb_res = (fa.MetricResult("pb", None, "not_meaningful", fx_reason, [x for x in (price_sv, bvps) if x], "price / book value per share")
                  if cross_ccy else fa.ratio("pb", price_sv, bvps, "price / book value per share"))
        M["pb"] = F.metric("calc.pb", "Price to book", pb_res, "times", L0)
    else:
        M["pb"] = F.metric("calc.pb", "Price to book", fa.MetricResult("pb", None, "unavailable", "equity or share count not reported", [], "price / book value per share"), "times", L0)
    if price_sv and shares_sv:
        mcap = price_sv.value * shares_sv.value
        F.derived("market_cap", "Market capitalisation (last close x shares)", mcap, "latest", "calc.market_cap",
                  "last close x shares outstanding", [price_sv, shares_sv], ccy=price_ccy)
        out["market_cap"] = float(mcap)

    if bars is not None and price:
        last_date = date.fromisoformat(bars.index[-1])
        window = [d for d in bars.index if date.fromisoformat(d) > last_date - timedelta(days=365)]
        divs = bars.loc[window, "dividend"].fillna(0)
        dps = Decimal(repr(float(divs.sum())))
        y = (dps / price).quantize(Decimal("0.000001"))
        ev.add("calc.dividend_yield", kind="calculation", label="Dividend yield, trailing 12 months", value=float(y),
               display=fmt.pct(y), unit="ratio", period="trailing 365 days",
               formula={"id": "fundamentals.dividend_yield", "version": fa.FORMULA_VERSION, "expression": "dividends per share (365 days) / last close"},
               inputs=["dataset.history", "price.last_close"],
               note=f"{int((divs > 0).sum())} dividend payment(s) of total {fmt.inr(dps)} per share")
        M["dividend_yield"] = {"value": float(y), "status": "ok", "evidence_id": "calc.dividend_yield",
                               "display": fmt.pct(y), "label": "Dividend yield (TTM)", "period": "trailing 365 days"}

    # ---- quarterly momentum
    qrev = F.st.periods("quarterly", "revenue")
    pair = next(((p, fa.matching_prior_year(qrev, p)) for p in qrev if fa.matching_prior_year(qrev, p)), None)
    if pair:
        qa, qb = pair
        Lq = f"{fmt.quarter_label(qa)} vs {fmt.quarter_label(qb)}"
        if qrev and qa != qrev[0]:
            out["notes"].append(f"Latest quarter {fmt.quarter_label(qrev[0])} has no same-quarter prior-year figures; YoY comparison uses {fmt.quarter_label(qa)}.")
        M["q_revenue_yoy"] = F.metric("calc.q_revenue_yoy", "Quarterly revenue YoY", fa.growth("q_revenue_yoy", g("revenue", qa, "quarterly"), g("revenue", qb, "quarterly")), "pct", Lq)
        M["q_net_income_yoy"] = F.metric("calc.q_net_income_yoy", "Quarterly net income YoY", fa.growth("q_net_income_yoy", g("net_income", qa, "quarterly"), g("net_income", qb, "quarterly")), "pct", Lq)
    else:
        for key, label in [("q_revenue_yoy", "Quarterly revenue YoY"), ("q_net_income_yoy", "Quarterly net income YoY")]:
            M[key] = F.metric(f"calc.{key}", label, fa.MetricResult(key, None, "unavailable", "no quarter with same-quarter prior-year figures", [], "current / prior - 1"), "pct", "latest quarter")

    # ---- display tables (source values with provenance)
    for p in ann[:4]:
        row = {"period": p, "label": fmt.fy_label(p)}
        for key in ("revenue", "operating_income", "net_income", "diluted_eps", "operating_cash_flow", "capex", "total_debt", "equity", "cash"):
            v = g(key, p)
            row[key] = {"value": _f(v.value), "display": fmt.money(v.value, stmt_ccy), "line_item": v.line_item} if v else None
        out["annual_table"].append(row)
    for p in qrev[:6]:
        row = {"period": p, "label": fmt.quarter_label(p)}
        for key in ("revenue", "net_income", "diluted_eps"):
            v = g(key, p, "quarterly")
            row[key] = {"value": _f(v.value), "display": fmt.money(v.value, stmt_ccy), "line_item": v.line_item} if v else None
        out["quarterly_table"].append(row)

    override = load_rules().get("sector_overrides", {}).get(sector or "")
    if override:
        for key in override["exclude_components"]:
            if key in M:
                M[key]["sector_note"] = "Not meaningful for this sector; excluded from scoring."
        out["sector_note"] = override["note"]

    if p1:
        gap = (date.fromisoformat(p0) - date.fromisoformat(p1)).days
        out["annual_gap_days"] = gap
    out["latest_annual"] = p0
    out["latest_quarter"] = qrev[0] if qrev else None
    out["sector"] = sector
    return out


# ---------------------------------------------------------------------------- risk


def _risk(bars: pd.DataFrame, bench: pd.DataFrame | None, fundamentals: dict, ds: dict, ev: EvidenceStore,
          requested_at: datetime, technical: dict) -> dict:
    close = bars["close"].astype(float)
    volume = bars["volume"].fillna(0).astype(float)
    last_date = bars.index[-1]
    out: dict = {"flags": []}
    inputs = ["dataset.history"]

    vol = rm.annualised_volatility(close)
    out["volatility_1y"] = vol
    ev.add("risk.volatility_1y", kind="calculation", label="Annualised volatility, 1 year", value=vol,
           display=fmt.pct(vol) if vol is not None else f"unavailable (only {len(close)} sessions since {close.index[0]})",
           unit="ratio", observed_at=last_date, formula=_formula("risk.volatility_log_annualised", "stdev(daily log returns) x sqrt(252)"),
           inputs=inputs, status="ok" if vol is not None else "unavailable")
    short_history = f"only {len(close)} sessions since {close.index[0]}"
    # A "1 year" figure needs a full year of closes; a shorter window is never relabelled as one year.
    dd1 = rm.max_drawdown(close.iloc[-(FULL_YEAR_SESSIONS + 1):]) if len(close) > FULL_YEAR_SESSIONS else None
    out["max_drawdown_1y"] = dd1
    ev.add("risk.max_drawdown_1y", kind="calculation", label="Maximum drawdown, 1 year", value=dd1["value"] if dd1 else None,
           display=f"{fmt.pct(dd1['value'])} ({dd1['peak_date']} to {dd1['trough_date']})" if dd1 else f"unavailable ({short_history})",
           unit="ratio", observed_at=last_date, formula=_formula("risk.max_drawdown", "min(close / running peak - 1)"), inputs=inputs,
           status="ok" if dd1 else "unavailable")
    ddf = rm.max_drawdown(close)
    out["max_drawdown_full"] = ddf
    ev.add("risk.max_drawdown_full", kind="calculation", label=f"Maximum drawdown since {close.index[0]}",
           value=ddf["value"] if ddf else None,
           display=f"{fmt.pct(ddf['value'])} ({ddf['peak_date']} to {ddf['trough_date']})" if ddf else "unavailable",
           unit="ratio", observed_at=last_date, formula=_formula("risk.max_drawdown", "min(close / running peak - 1)"), inputs=inputs)
    b = rm.beta(close, bench["close"].astype(float)) if bench is not None else None
    out["beta_1y"] = b
    beta_window = "1 year" if b and b["observations"] >= FULL_YEAR_SESSIONS - 2 else f"{b['observations']} sessions" if b else "1 year"
    ev.add("risk.beta_1y", kind="calculation", label=f"Beta vs NIFTY 50, {beta_window}", value=b["value"] if b else None,
           display=f"{fmt.num(b['value'])} (correlation {fmt.num(b['correlation'])}, {b['observations']} sessions)" if b
           else f"unavailable (needs 120 sessions; {short_history})",
           unit="x", observed_at=last_date, formula=_formula("risk.beta_simple_returns", "cov(stock, index) / var(index), daily simple returns"),
           inputs=inputs, source=ev.source("benchmark", detail="^NSEI"), status="ok" if b else "unavailable")
    var95 = rm.historical_var(close)
    out["var95_1d"] = var95
    var_returns = min(len(close) - 1, FULL_YEAR_SESSIONS)
    var_window = "1 year" if var_returns >= FULL_YEAR_SESSIONS else f"{var_returns} sessions"
    ev.add("risk.var95_1d", kind="calculation", label=f"1-day historical VaR (95%), {var_window}", value=var95,
           display=fmt.pct(var95) if var95 is not None else f"unavailable (needs 100 sessions; {short_history})",
           unit="ratio", observed_at=last_date, formula=_formula("risk.historical_var", "-5th percentile of daily returns"),
           inputs=inputs, status="ok" if var95 is not None else "unavailable",
           note="Analytical example only; not a personalised loss limit.")
    traded = (close * volume).iloc[-20:]
    mtv = float(traded.median()) if len(traded) else None
    out["median_traded_value"] = mtv
    out["median_traded_value_cr"] = mtv / 1e7 if mtv is not None else None
    ev.add("risk.median_traded_value_20d", kind="calculation", label="Median daily traded value, 20 sessions", value=mtv,
           display=fmt.inr(mtv), unit="INR", currency="INR", observed_at=last_date,
           formula={"id": "risk.liquidity", "version": "1.0", "expression": "median(close x volume) over 20 sessions"}, inputs=inputs)
    zero_days = int((volume.iloc[-60:] <= 0).sum())
    out["zero_volume_days_60"] = zero_days

    cal = (ds.get("calendar") or {}).get("data") or {}
    as_of_day = mc.to_ist(requested_at).date()
    upcoming = sorted(d for d in cal.get("earnings_dates", []) if date.fromisoformat(d) >= as_of_day)
    out["next_earnings"] = upcoming[0] if upcoming else None
    if upcoming:
        ev.add("event.next_earnings", kind="source", label="Next scheduled results date (provider calendar)", value=upcoming[0],
               display=upcoming[0], observed_at=upcoming[0], source=ev.source("calendar"),
               note="Provider estimate; confirm against the official exchange announcement.")

    def flag(fid, severity, title, detail, ids):
        out["flags"].append({"id": fid, "severity": severity, "title": title, "detail": detail, "evidence_ids": ids})

    if vol is not None and vol > 0.40:
        flag("high_volatility", "high", "High volatility", f"Annualised volatility is {fmt.pct(vol)}.", ["risk.volatility_1y"])
    if dd1 and dd1["value"] < -0.30:
        flag("deep_drawdown", "high", "Deep drawdown in the last year", f"Maximum 1-year drawdown is {fmt.pct(dd1['value'])}.", ["risk.max_drawdown_1y"])
    if b and b["value"] > 1.3:
        flag("high_beta", "medium", "High market sensitivity", f"Beta vs NIFTY 50 is {fmt.num(b['value'])}.", ["risk.beta_1y"])
    if mtv is not None and mtv < 1e8:
        flag("low_liquidity", "high", "Low liquidity", f"Median daily traded value is {fmt.inr(mtv)}.", ["risk.median_traded_value_20d"])
    if zero_days > 6:
        flag("no_trade_days", "high", "Sessions without trades", f"{zero_days} of the last 60 sessions had zero volume.", ["dataset.history"])
    fin = fundamentals.get("metrics", {})
    is_financial = (fundamentals.get("sector") or "") == "Financial Services"
    de = fin.get("debt_to_equity", {})
    if not is_financial and de.get("value") is not None and de["value"] > 1.5:
        flag("high_leverage", "medium", "High leverage", f"Debt to equity is {de['display']}.", [de["evidence_id"]])
    ic = fin.get("interest_coverage", {})
    if not is_financial and ic.get("value") is not None and ic["value"] < 2.0:
        flag("weak_coverage", "high", "Weak interest coverage", f"Interest coverage is {ic['display']}.", [ic["evidence_id"]])
    ni = fin.get("net_income_growth", {})
    if ni.get("value") is not None and ni["value"] < -0.20:
        flag("earnings_decline", "medium", "Falling annual earnings", f"Net income growth is {ni['display']}.", [ni["evidence_id"]])
    if upcoming and (date.fromisoformat(upcoming[0]) - as_of_day).days <= 14:
        flag("results_soon", "medium", "Results due soon", f"Scheduled results date {upcoming[0]} may move the price sharply.", ["event.next_earnings"])
    if technical.get("abnormal_volume"):
        flag("abnormal_volume", "low", "Abnormal volume", "Latest session volume is at least twice the 50-session median.", ["tech.volume_ratio"])
    if technical.get("gaps"):
        flag("price_gaps", "low", "Recent price gaps", f"{len(technical['gaps'])} opening gap(s) of 3% or more in the last 20 sessions.", ["dataset.history"])

    atr_v = technical.get("atr14")
    if var95 is not None and atr_v is not None:
        last = float(close.iloc[-1])
        out["downside_examples"] = {
            "var95_rupees": var95 * last,
            "two_atr_rupees": 2 * atr_v,
            "note": "Analytical examples of typical adverse moves, not stop-loss or position-sizing instructions.",
        }
    return out


# ---------------------------------------------------------------------------- news


_TITLE_NORM = re.compile(r"[^a-z0-9 ]+")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _clean_text(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    return _CTRL.sub(" ", str(text)).strip()[:limit]


def _news(ds: dict, ev: EvidenceStore) -> dict:
    items = (ds.get("news") or {}).get("data") or []
    groups: dict[str, list[dict]] = {}
    for it in items:
        key = " ".join(_TITLE_NORM.sub(" ", (it.get("title") or "").lower()).split())
        if key:
            groups.setdefault(key, []).append(it)
    out_items = []
    for group in groups.values():
        group.sort(key=lambda x: x.get("published_at") or "")
        first = group[0]
        nid = "news." + hashlib.sha1(str(first.get("id")).encode()).hexdigest()[:10]
        title = _clean_text(first.get("title"), 300)
        summary = _clean_text(first.get("summary"), 600)
        ev.add(nid, kind="news", label=title, value=None,
               display=f"{first.get('publisher') or 'unknown publisher'}, published {first.get('published_at') or 'unknown time'}",
               observed_at=first.get("published_at"), source=ev.source("news", detail=first.get("publisher"), url=first.get("url")),
               note="Headline only; article text not retrieved or verified.")
        out_items.append({
            "evidence_id": nid, "title": title, "summary": summary, "publisher": first.get("publisher"),
            "published_at": first.get("published_at"), "url": first.get("url"),
            "duplicates": [{"publisher": d.get("publisher"), "url": d.get("url")} for d in group[1:]],
        })
    out_items.sort(key=lambda x: x["published_at"] or "", reverse=True)
    return {
        "items": out_items[:15],
        "received": len(items),
        "duplicates_removed": len(items) - len(out_items),
        "filings_status": "unavailable",
    }


def _profile(ds: dict, ev: EvidenceStore) -> dict:
    p = (ds.get("profile") or {}).get("data")
    if not p:
        return {"status": "unavailable"}
    src = ev.source("profile")
    fields = {
        "profile.name": ("Company name", p.get("longName") or p.get("shortName")),
        "profile.sector": ("Sector (provider classification)", p.get("sector")),
        "profile.industry": ("Industry (provider classification)", p.get("industry")),
        "profile.business_summary": ("Business summary (provider text)", _clean_text(p.get("longBusinessSummary"), 2000)),
        "profile.employees": ("Full-time employees", p.get("fullTimeEmployees")),
        "profile.website": ("Website", p.get("website")),
    }
    for eid, (label, value) in fields.items():
        if value is None:
            continue
        display = fmt.indian_number(value, 0) if eid == "profile.employees" else str(value)
        ev.add(eid, kind="profile", label=label, value=value if not isinstance(value, str) else None,
               display=display, source=src)
    return {
        "status": "ok", "name": p.get("longName") or p.get("shortName"), "sector": p.get("sector"),
        "industry": p.get("industry"), "summary": _clean_text(p.get("longBusinessSummary"), 2000),
        "website": p.get("website"), "employees": p.get("fullTimeEmployees"), "city": p.get("city"),
        "currency": p.get("currency"), "financial_currency": p.get("financialCurrency"),
    }


# ------------------------------------------------------------------------- entry


def _metric_index(technical: dict, returns: dict, fundamentals: dict, risk: dict) -> dict:
    """Flat name -> {value, evidence_id} map consumed by the rating rules."""
    fm = fundamentals.get("metrics", {})

    def m(value, eid):
        return {"value": value, "evidence_id": eid}

    idx = {k: m(fm[k]["value"], fm[k]["evidence_id"]) for k in fm}
    for k in ("price_vs_sma200", "sma50_vs_sma200", "price_vs_sma50", "macd_hist_pct"):
        idx[k] = m(technical.get(k), f"tech.{k}")
    idx["rel_return_3m"] = m(returns.get("relative", {}).get("3m"), "rel.ret.3m")
    idx["rel_return_6m"] = m(returns.get("relative", {}).get("6m"), "rel.ret.6m")
    idx["momentum_12_1"] = m(returns.get("momentum_12_1"), "ret.momentum_12_1")
    idx["volatility_1y"] = m(risk.get("volatility_1y"), "risk.volatility_1y")
    idx["max_drawdown_1y"] = m((risk.get("max_drawdown_1y") or {}).get("value"), "risk.max_drawdown_1y")
    idx["beta_1y"] = m((risk.get("beta_1y") or {}).get("value"), "risk.beta_1y")
    idx["median_traded_value_cr"] = m(risk.get("median_traded_value_cr"), "risk.median_traded_value_20d")
    return idx


def compute_deterministic(snapshot: dict) -> dict:
    ev = EvidenceStore(snapshot)
    ds = snapshot["datasets"]
    requested_at = datetime.fromisoformat(snapshot["requested_at"])
    notes: list[str] = []
    market = mc.market_status(requested_at)

    profile = _profile(ds, ev)
    price = _price_section(snapshot, ev, requested_at, market, notes)
    bars = price.pop("_bars")
    bench = _bars(ds.get("benchmark"))
    if bars is not None and len(bars) >= 30:
        technical = _technical(bars, ev)
        returns = _returns(bars, bench, ev)
    else:
        technical = {"status": "unavailable", "reason": "fewer than 30 usable sessions"}
        returns = {"stock": {}, "benchmark": {}, "relative": {}}
    inst_ccy = snapshot["instrument"]["currency"]
    fundamentals = _fundamentals(ds, ev, bars, price.get("last_close"), profile.get("sector"),
                                 profile.get("financial_currency") or inst_ccy, inst_ccy)
    risk = _risk(bars, bench, fundamentals, ds, ev, requested_at, technical) if bars is not None and len(bars) >= 30 else {"flags": [], "status": "unavailable"}
    news = _news(ds, ev)
    forecast = forecast_engine.run(bars["close"]) if bars is not None and "close" in bars else {
        "status": "unavailable", "version": forecast_engine.VERSION, "reason": "no price history"}
    gates = run_quality_gates(snapshot, price=price, technical=technical, fundamentals=fundamentals, news=news,
                              returns=returns, profile=profile, bars=bars)
    return {
        "engine_version": ENGINE_VERSION,
        "formula_versions": FORMULA_VERSIONS,
        "market": market,
        "price": price,
        "profile": profile,
        "technical": technical,
        "returns": returns,
        "fundamentals": fundamentals,
        "risk": risk,
        "news": news,
        "forecast": forecast,
        "metrics": _metric_index(technical, returns, fundamentals, risk),
        "gates": gates,
        "data_quality": summarise_gates(gates),
        "evidence": ev.items,
        "notes": notes,
    }


def chart_series(snapshot: dict) -> dict:
    """Price and indicator series for the chart, recomputed from the snapshot."""
    requested_at = datetime.fromisoformat(snapshot["requested_at"])
    price = _price_section(snapshot, EvidenceStore(snapshot), requested_at, mc.market_status(requested_at), [])
    bars = price.get("_bars")
    if bars is None:
        return {"bars": []}
    close, high, low = bars["close"], bars["high"], bars["low"]
    volume = bars["volume"].fillna(0)
    m = ind.macd(close)
    bb = ind.bollinger(close)

    def series(s):
        return [{"time": t, "value": round(float(v), 4)} for t, v in s.items() if not math.isnan(v)]

    return {
        "bars": [
            {"time": t, "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"], "volume": _f(r["volume"]) or 0}
            for t, r in bars.iterrows()
        ],
        "sma50": series(ind.sma(close, 50)),
        "sma200": series(ind.sma(close, 200)),
        "ema20": series(ind.ema(close, 20)),
        "bb_upper": series(bb["upper"]),
        "bb_lower": series(bb["lower"]),
        "vwap20": series(ind.vwap_rolling(high, low, close, volume)),
        "rsi14": series(ind.rsi(close, 14)),
        "macd": series(m["macd"]),
        "macd_signal": series(m["signal"]),
        "macd_hist": series(m["hist"]),
        "levels": ind.support_resistance(bars),
        "adjustment": "Prices are split-adjusted by the provider. Dividends are not deducted from the price series.",
    }
