"""Return and risk statistics (plan sections 4.11 and 7).

* Volatility: sample standard deviation (ddof = 1) of daily log returns, times sqrt(252).
* Beta: covariance / variance of daily simple returns over dates both series traded.
* Historical VaR: the loss at the 5th percentile of daily simple returns (numpy linear quantile),
  reported as a positive fraction.
* Max drawdown: the worst peak-to-trough fall of the close series.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

FORMULAS = {
    "period_return": "1.0",
    "volatility_log_annualised": "1.0",
    "max_drawdown": "1.0",
    "beta_simple_returns": "1.0",
    "historical_var": "1.0",
    "momentum_12_1": "1.0",
}

TRADING_DAYS = 252


def period_return(close: pd.Series, sessions: int) -> float | None:
    if len(close) <= sessions:
        return None
    start = float(close.iloc[-1 - sessions])
    if start <= 0:
        return None
    return float(close.iloc[-1]) / start - 1


def momentum_12_1(close: pd.Series) -> float | None:
    """Return from 12 months ago to 1 month ago (skips the most recent month)."""
    if len(close) <= 252:
        return None
    start, end = float(close.iloc[-253]), float(close.iloc[-22])
    return end / start - 1 if start > 0 else None


def annualised_volatility(close: pd.Series, window: int = TRADING_DAYS) -> float | None:
    if len(close) < window + 1:
        return None
    log_ret = np.log(close.iloc[-window - 1 :].astype(float)).diff().dropna()
    return float(log_ret.std(ddof=1) * math.sqrt(TRADING_DAYS))


def max_drawdown(close: pd.Series) -> dict | None:
    if len(close) < 2:
        return None
    running_peak = close.cummax()
    dd = close / running_peak - 1
    trough = dd.idxmin()
    peak = close.loc[:trough].idxmax()
    return {"value": float(dd.min()), "peak_date": str(peak), "trough_date": str(trough)}


def beta(stock_close: pd.Series, bench_close: pd.Series, window: int = TRADING_DAYS, min_obs: int = 120) -> dict | None:
    joined = pd.concat([stock_close.rename("s"), bench_close.rename("b")], axis=1, join="inner").dropna()
    rets = joined.pct_change().dropna().iloc[-window:]
    if len(rets) < min_obs:
        return None
    var_b = float(rets["b"].var(ddof=1))
    if var_b == 0:
        return None
    cov = float(rets["s"].cov(rets["b"], ddof=1))
    corr = float(rets["s"].corr(rets["b"]))
    return {"value": cov / var_b, "correlation": corr, "observations": int(len(rets))}


def historical_var(close: pd.Series, window: int = TRADING_DAYS, level: float = 0.95) -> float | None:
    rets = close.astype(float).pct_change().dropna().iloc[-window:]
    if len(rets) < 100:
        return None
    return float(-np.quantile(rets.to_numpy(), 1 - level))
