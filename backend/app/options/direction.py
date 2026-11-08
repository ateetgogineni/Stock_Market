"""Index Market Direction engine (module 2, section 5; agent 21).

Deterministic: every component is a tested calculation with a score in [-1, 1],
a readable reading and its inputs. The classification thresholds are a draft,
unvalidated rule set. Option-chain positioning is used only when the chain is
real market data; a synthetic chain is listed as excluded, never scored.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..analytics import indicators as ind

VERSION = "direction-0.1.0-draft"
LABELS = ["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish", "High Volatility / Uncertain"]
WEIGHTS = {"trend": 0.30, "momentum": 0.20, "structure": 0.15, "directional_movement": 0.10, "vwap": 0.10,
           "global": 0.05, "positioning": 0.10}
THRESHOLDS = {"strong": 0.55, "normal": 0.20, "adx_trend": 25.0, "vix_elevated": 20.0, "vix_jump_5d": 0.15}


def _clip(x: float) -> float:
    return max(-1.0, min(1.0, x))


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.DataFrame:
    """Wilder's ADX with +DI and -DI."""
    h, l, c = high.to_numpy(float), low.to_numpy(float), close.to_numpy(float)
    size = len(c)
    plus_dm, minus_dm, tr = np.zeros(size), np.zeros(size), np.zeros(size)
    for i in range(1, size):
        up, down = h[i] - h[i - 1], l[i - 1] - l[i]
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = pd.DataFrame(index=close.index, columns=["adx", "plus_di", "minus_di"], dtype=float)
    if size <= 2 * n:
        return out
    s_tr, s_p, s_m = tr[1:n + 1].sum(), plus_dm[1:n + 1].sum(), minus_dm[1:n + 1].sum()
    dx = np.full(size, np.nan)
    pdi, mdi = np.full(size, np.nan), np.full(size, np.nan)
    for i in range(n, size):
        if i > n:
            s_tr = s_tr - s_tr / n + tr[i]
            s_p = s_p - s_p / n + plus_dm[i]
            s_m = s_m - s_m / n + minus_dm[i]
        pdi[i] = 100 * s_p / s_tr if s_tr else 0.0
        mdi[i] = 100 * s_m / s_tr if s_tr else 0.0
        denom = pdi[i] + mdi[i]
        dx[i] = 100 * abs(pdi[i] - mdi[i]) / denom if denom else 0.0
    adx_arr = np.full(size, np.nan)
    first = 2 * n - 1
    adx_arr[first] = np.nanmean(dx[n:first + 1])
    for i in range(first + 1, size):
        adx_arr[i] = (adx_arr[i - 1] * (n - 1) + dx[i]) / n
    out["adx"], out["plus_di"], out["minus_di"] = adx_arr, pdi, mdi
    return out


def pivots(high: float, low: float, close: float) -> dict:
    """Classic floor-trader pivots from the previous session."""
    p = (high + low + close) / 3
    return {"pivot": p, "r1": 2 * p - low, "s1": 2 * p - high, "r2": p + (high - low), "s2": p - (high - low)}


def _frame(bars: list[dict] | None) -> pd.DataFrame | None:
    if not bars:
        return None
    df = pd.DataFrame(bars).set_index("date").sort_index()
    df = df.dropna(subset=["close"])
    return df if len(df) else None


def _pct_change(df: pd.DataFrame | None, sessions: int) -> float | None:
    if df is None or len(df) <= sessions:
        return None
    return float(df["close"].iloc[-1] / df["close"].iloc[-1 - sessions] - 1)


def analyse(index_bars: list[dict], vix_bars: list[dict] | None, global_bars: dict[str, list[dict]],
            positioning: dict | None, positioning_real: bool) -> dict:
    df = _frame(index_bars)
    if df is None or len(df) < 200:
        return {"label": "INSUFFICIENT DATA", "version": VERSION, "composite": None, "components": [],
                "reason": f"Need 200 sessions of index history; have {0 if df is None else len(df)}.", "levels": {}, "missing": []}
    close, high, low = df["close"].astype(float), df["high"].astype(float), df["low"].astype(float)
    volume = df["volume"].fillna(0).astype(float) if "volume" in df else pd.Series(0.0, index=df.index)
    last = float(close.iloc[-1])
    comps: list[dict] = []

    def add(key, label, score, value, reading):
        comps.append({"key": key, "label": label, "score": None if score is None else round(_clip(score), 4),
                      "weight": WEIGHTS.get(key, 0.0), "value": value, "reading": reading})

    sma20, sma50, sma200 = (float(ind.sma(close, n).iloc[-1]) for n in (20, 50, 200))
    trend_votes = [np.sign(last - sma20), np.sign(last - sma50), np.sign(last - sma200), np.sign(sma20 - sma50), np.sign(sma50 - sma200)]
    add("trend", "Trend (moving averages)", float(np.mean(trend_votes)),
        f"close {last:,.2f} · SMA20 {sma20:,.2f} · SMA50 {sma50:,.2f} · SMA200 {sma200:,.2f}",
        f"{sum(v > 0 for v in trend_votes)} of 5 moving-average checks are bullish")

    rsi = float(ind.rsi(close).iloc[-1])
    m = ind.macd(close)
    hist, hist_prev = float(m["hist"].iloc[-1]), float(m["hist"].iloc[-2])
    mom = 0.6 * _clip((rsi - 50) / 20) + 0.4 * _clip(hist / last / 0.002)
    add("momentum", "Momentum (RSI, MACD)", mom, f"RSI {rsi:.1f} · MACD hist {hist:+.2f} ({'rising' if hist > hist_prev else 'falling'})",
        "RSI above 50 and positive MACD favour buyers" if mom > 0.1 else "RSI below 50 and negative MACD favour sellers" if mom < -0.1 else "momentum is flat")

    recent, prior = df.iloc[-10:], df.iloc[-20:-10]
    hh, hl = recent["high"].max() > prior["high"].max(), recent["low"].min() > prior["low"].min()
    structure = 1.0 if hh and hl else -1.0 if (not hh and not hl) else 0.0
    add("structure", "Market structure (10-session swings)", structure,
        f"recent high {recent['high'].max():,.2f} vs {prior['high'].max():,.2f} · recent low {recent['low'].min():,.2f} vs {prior['low'].min():,.2f}",
        "higher highs and higher lows" if structure > 0 else "lower highs and lower lows" if structure < 0 else "mixed swings (range)")

    a = adx(high, low, close)
    adx_v, pdi, mdi = (float(a[c].iloc[-1]) for c in ("adx", "plus_di", "minus_di"))
    add("directional_movement", "Trend strength (ADX, +DI/-DI)", (pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0,
        f"ADX {adx_v:.1f} · +DI {pdi:.1f} · -DI {mdi:.1f}",
        f"{'strong' if adx_v >= THRESHOLDS['adx_trend'] else 'weak'} trend; {'+DI' if pdi > mdi else '-DI'} leads")

    if volume.iloc[-20:].sum() > 0:
        vwap = float(ind.vwap_rolling(high, low, close, volume).iloc[-1])
        add("vwap", "Price vs 20-session VWAP", (last / vwap - 1) / 0.02, f"VWAP20 {vwap:,.2f} ({(last / vwap - 1):+.2%})",
            "above VWAP" if last > vwap else "below VWAP")
    else:
        vwap = None
        add("vwap", "Price vs VWAP", None, "unavailable", "no index volume from the provider")

    g_scores, g_parts = [], []
    for name, bars in global_bars.items():
        gdf = _frame(bars)
        d1, d5 = _pct_change(gdf, 1), _pct_change(gdf, 5)
        if d1 is not None:
            g_scores.append(0.6 * _clip(d1 / 0.01) + 0.4 * _clip((d5 or 0) / 0.03))
            g_parts.append(f"{name} {d1:+.2%} (5d {d5:+.2%}) to {gdf.index[-1]}" if d5 is not None else f"{name} {d1:+.2%}")
    add("global", "Global cues", float(np.mean(g_scores)) if g_scores else None, "; ".join(g_parts) or "unavailable",
        "overseas markets supportive" if g_scores and np.mean(g_scores) > 0.1 else "overseas markets weak" if g_scores and np.mean(g_scores) < -0.1 else "overseas markets mixed or unavailable")

    if positioning and positioning_real:
        pcr = positioning.get("pcr_oi")
        pos_score = _clip((pcr - 1.0) / 0.4) if pcr else None
        add("positioning", "Option-chain positioning", pos_score, f"PCR (OI) {pcr:.2f}" if pcr else "unavailable",
            "OI positioning is weak evidence; every contract has a buyer and a seller")
    else:
        add("positioning", "Option-chain positioning", None, "excluded",
            "the option chain is synthetic, so positioning is not used for direction" if positioning else "no option chain")

    vdf = _frame(vix_bars)
    vix_level = float(vdf["close"].iloc[-1]) if vdf is not None else None
    vix_5d = _pct_change(vdf, 5)
    vix_regime = "unavailable" if vix_level is None else (
        "elevated" if vix_level >= THRESHOLDS["vix_elevated"] or (vix_5d or 0) >= THRESHOLDS["vix_jump_5d"] else
        "calm" if vix_level < 13 else "normal")

    usable = [c for c in comps if c["score"] is not None and c["weight"] > 0]
    wsum = sum(c["weight"] for c in usable)
    composite = sum(c["weight"] * c["score"] for c in usable) / wsum if wsum else 0.0
    t = THRESHOLDS
    if vix_regime == "elevated" and abs(composite) < 0.5:
        label = "High Volatility / Uncertain"
    elif composite >= t["strong"] and adx_v >= t["adx_trend"]:
        label = "Strong Bullish"
    elif composite >= t["normal"]:
        label = "Bullish"
    elif composite <= -t["strong"] and adx_v >= t["adx_trend"]:
        label = "Strong Bearish"
    elif composite <= -t["normal"]:
        label = "Bearish"
    else:
        label = "Neutral"

    atr_v = float(ind.atr(high, low, close).iloc[-1])
    prev = df.iloc[-1]
    piv = pivots(float(prev["high"]), float(prev["low"]), float(prev["close"]))
    levels = {
        "support_20": float(low.iloc[-20:].min()), "resistance_20": float(high.iloc[-20:].max()),
        "support_60": float(low.iloc[-60:].min()), "resistance_60": float(high.iloc[-60:].max()),
        **piv, "sma20": sma20, "sma50": sma50, "sma200": sma200, "vwap20": vwap,
        "prev_high": float(prev["high"]), "prev_low": float(prev["low"]),
    }
    return {
        "label": label,
        "version": VERSION,
        "validation_status": "draft_unvalidated",
        "composite": round(composite, 4),
        "coverage": round(wsum / sum(WEIGHTS.values()), 4),
        "adx": adx_v,
        "components": comps,
        "vix": {"level": vix_level, "change_5d": vix_5d, "regime": vix_regime, "as_of": vdf.index[-1] if vdf is not None else None},
        "atr": atr_v,
        "atr_pct": atr_v / last,
        "last": last,
        "change_1d": _pct_change(df, 1),
        "as_of": df.index[-1],
        "levels": levels,
        "missing": [m for m in (
            "Economic-event calendar (no source configured)",
            "Intraday session VWAP (index has no traded volume; needs a futures feed)",
            None if positioning_real else "Real option-chain positioning (chain is synthetic)",
        ) if m],
        "thresholds": THRESHOLDS,
    }
