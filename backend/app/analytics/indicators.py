"""Technical indicators (plan sections 4.6 and 7).

Conventions are fixed and documented so results are reproducible and can be
compared with reference implementations:

* EMA: alpha = 2 / (n + 1), seeded with the simple average of the first n values
  (the TA-Lib convention). Values before the seed are NaN.
* RSI and ATR: Wilder smoothing, seeded with the simple average of the first n
  changes / true ranges. A window with no gains and no losses has RSI 50.
* Bollinger Bands use the population standard deviation (ddof = 0).
* VWAP: daily bars only carry one price per session, so we compute a rolling
  20-session VWAP from the typical price (high + low + close) / 3. A true
  intraday session VWAP needs intraday data.

Inputs are float64 pandas Series indexed by session date with no gaps; the
caller drops sessions with missing prices first.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FORMULAS = {
    "sma": "1.0",
    "ema_sma_seeded": "1.0",
    "rsi_wilder": "1.0",
    "macd": "1.0",
    "bollinger_population_sd": "1.0",
    "atr_wilder": "1.0",
    "vwap_rolling_typical_price": "1.0",
    "support_resistance_rolling_extremes": "1.0",
    "volume_ratio_median": "1.0",
    "price_gaps": "1.0",
}


def _series(arr: np.ndarray, like: pd.Series) -> pd.Series:
    return pd.Series(arr, index=like.index, dtype=float)


def sma(values: pd.Series, n: int) -> pd.Series:
    return values.astype(float).rolling(n, min_periods=n).mean()


def ema(values: pd.Series, n: int) -> pd.Series:
    arr = values.to_numpy(dtype=float)
    out = np.full(arr.shape, np.nan)
    valid = np.flatnonzero(~np.isnan(arr))
    if len(valid) < n:
        return _series(out, values)
    start = int(valid[0])
    seed_end = start + n - 1
    if seed_end >= len(arr) or np.isnan(arr[start : seed_end + 1]).any():
        raise ValueError("EMA input has gaps inside the seed window")
    alpha = 2.0 / (n + 1)
    out[seed_end] = arr[start : seed_end + 1].mean()
    for i in range(seed_end + 1, len(arr)):
        if np.isnan(arr[i]):
            raise ValueError("EMA input has gaps after the seed window")
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return _series(out, values)


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    arr = close.to_numpy(dtype=float)
    out = np.full(arr.shape, np.nan)
    if len(arr) <= n:
        return _series(out, close)
    delta = np.diff(arr)
    gains = np.clip(delta, 0, None)
    losses = np.clip(-delta, 0, None)
    avg_gain = gains[:n].mean()
    avg_loss = losses[:n].mean()
    out[n] = _rsi_value(avg_gain, avg_loss)
    for i in range(n, len(delta)):
        avg_gain = (avg_gain * (n - 1) + gains[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i]) / n
        out[i + 1] = _rsi_value(avg_gain, avg_loss)
    return _series(out, close)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    sd = close.astype(float).rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    width = upper - lower
    percent_b = (close - lower) / width.where(width != 0)
    return pd.DataFrame(
        {"middle": mid, "upper": upper, "lower": lower, "percent_b": percent_b, "bandwidth": width / mid}
    )


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1, skipna=False)
    tr.iloc[0] = np.nan  # no previous close for the first bar
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = true_range(high, low, close).to_numpy(dtype=float)
    out = np.full(tr.shape, np.nan)
    if len(tr) <= n:
        return _series(out, close)
    out[n] = tr[1 : n + 1].mean()
    for i in range(n + 1, len(tr)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return _series(out, close)


def vwap_rolling(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, n: int = 20) -> pd.Series:
    tp = (high + low + close) / 3.0
    pv = (tp * volume).rolling(n, min_periods=n).sum()
    v = volume.rolling(n, min_periods=n).sum()
    return pv / v.where(v != 0)


def support_resistance(bars: pd.DataFrame, windows: tuple[int, ...] = (20, 60, 250)) -> list[dict]:
    """Rolling-extreme levels: lowest low and highest high over each trailing window."""
    levels = []
    for w in windows:
        if len(bars) < w:
            continue
        tail = bars.iloc[-w:]
        lo_idx, hi_idx = tail["low"].idxmin(), tail["high"].idxmax()
        levels.append(
            {
                "window": w,
                "support": float(tail["low"].min()),
                "support_date": str(lo_idx),
                "resistance": float(tail["high"].max()),
                "resistance_date": str(hi_idx),
            }
        )
    return levels


def volume_ratio(volume: pd.Series, lookback: int = 50) -> float | None:
    """Latest session volume divided by the median of the previous `lookback` sessions."""
    if len(volume) < lookback + 1:
        return None
    base = float(volume.iloc[-lookback - 1 : -1].median())
    if base <= 0:
        return None
    return float(volume.iloc[-1]) / base


def price_gaps(bars: pd.DataFrame, lookback: int = 20, threshold: float = 0.03) -> list[dict]:
    """Sessions in the last `lookback` whose open moved at least `threshold` from the prior close."""
    out = []
    opens, closes = bars["open"], bars["close"]
    start = max(1, len(bars) - lookback)
    for i in range(start, len(bars)):
        prev = float(closes.iloc[i - 1])
        if prev <= 0:
            continue
        gap = float(opens.iloc[i]) / prev - 1
        if abs(gap) >= threshold:
            out.append({"date": str(bars.index[i]), "gap": gap, "prev_close": prev, "open": float(opens.iloc[i])})
    return out
