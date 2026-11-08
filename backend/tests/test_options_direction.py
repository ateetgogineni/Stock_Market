"""Index direction engine: ADX, pivots and classification."""

import numpy as np
import pandas as pd
import pytest

from app.options import direction as d


def bars(closes, spread=0.004, volume=1000.0):
    dates = pd.bdate_range("2025-01-01", periods=len(closes)).date.astype(str)
    return [{"date": t, "open": c, "high": c * (1 + spread), "low": c * (1 - spread), "close": c, "volume": volume}
            for t, c in zip(dates, closes)]


def trend(n=260, start=100.0, step=0.004, noise=0.002, seed=1):
    rng = np.random.default_rng(seed)
    return list(start * np.cumprod(1 + step + rng.normal(0, noise, n)))


def test_adx_strong_uptrend_and_flat_market():
    up = pd.DataFrame(bars(trend()))
    a = d.adx(up["high"], up["low"], up["close"])
    assert a["adx"].iloc[-1] > 40 and a["plus_di"].iloc[-1] > a["minus_di"].iloc[-1]
    rng = np.random.default_rng(3)
    flat = pd.DataFrame(bars(list(100 + rng.normal(0, 0.3, 260))))
    assert d.adx(flat["high"], flat["low"], flat["close"])["adx"].iloc[-1] < 25


def test_pivots_hand_example():
    p = d.pivots(110, 90, 100)
    assert p["pivot"] == 100 and p["r1"] == 110 and p["s1"] == 90 and p["r2"] == 120 and p["s2"] == 80


def test_strong_uptrend_classified_bullish_with_evidence():
    out = d.analyse(bars(trend()), bars([14.0] * 30), {"S&P 500": bars(trend(30))}, {"pcr_oi": 1.4}, positioning_real=False)
    assert out["label"] == "Strong Bullish"
    keys = {c["key"]: c for c in out["components"]}
    assert keys["trend"]["score"] == 1.0
    assert keys["positioning"]["score"] is None and "synthetic" in keys["positioning"]["reading"]
    assert any("calendar" in m for m in out["missing"])


def test_downtrend_classified_bearish():
    out = d.analyse(bars(trend(step=-0.004)), bars([14.0] * 30), {}, None, positioning_real=False)
    assert out["label"] in ("Bearish", "Strong Bearish")
    assert out["composite"] < 0


def test_elevated_vix_with_weak_signal_is_uncertain():
    rng = np.random.default_rng(5)
    chop = list(100 + np.cumsum(rng.normal(0, 0.4, 260)))
    out = d.analyse(bars(chop), bars([24.0] * 30), {}, None, positioning_real=False)
    if abs(out["composite"]) < 0.5:
        assert out["label"] == "High Volatility / Uncertain"
    assert out["vix"]["regime"] == "elevated"


def test_short_history_is_insufficient():
    out = d.analyse(bars(trend(n=120)), None, {}, None, positioning_real=False)
    assert out["label"] == "INSUFFICIENT DATA"


def test_real_positioning_is_scored():
    out = d.analyse(bars(trend()), bars([14.0] * 30), {}, {"pcr_oi": 1.4}, positioning_real=True)
    pos = next(c for c in out["components"] if c["key"] == "positioning")
    assert pos["score"] == pytest.approx(1.0)
