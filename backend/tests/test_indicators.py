"""Indicator tests: hand-worked examples plus independent reference implementations."""

import math

import numpy as np
import pandas as pd
import pytest

from app.analytics import indicators as ind


def s(values):
    return pd.Series([float(v) for v in values], index=[f"d{i}" for i in range(len(values))])


def test_sma_hand_example():
    out = ind.sma(s([1, 2, 3, 4, 5]), 3)
    assert out.isna().tolist() == [True, True, False, False, False]
    assert out.iloc[2:].tolist() == [2.0, 3.0, 4.0]


def test_ema_hand_example_sma_seeded():
    # n=3 -> alpha 0.5, seed = mean(1,2,3) = 2
    out = ind.ema(s([1, 2, 3, 4, 5, 6]), 3)
    assert math.isnan(out.iloc[1])
    assert out.iloc[2:].tolist() == [2.0, 3.0, 4.0, 5.0]


def test_ema_matches_pandas_ewm_after_seed():
    rng = np.random.default_rng(1)
    values = s(100 + np.cumsum(rng.normal(0, 1, 300)))
    n = 20
    ours = ind.ema(values, n)
    seeded = values.iloc[n - 1 :].copy()
    seeded.iloc[0] = values.iloc[:n].mean()
    reference = seeded.ewm(span=n, adjust=False).mean()
    np.testing.assert_allclose(ours.iloc[n - 1 :].to_numpy(), reference.to_numpy(), rtol=1e-12)


def test_ema_skips_leading_nans():
    values = s([np.nan, np.nan, 1, 2, 3, 4])
    out = ind.ema(values, 3)
    assert out.iloc[4] == 2.0 and out.iloc[5] == 3.0


def test_rsi_hand_example_wilder():
    out = ind.rsi(s([10, 11, 10.5, 11.5, 11, 12]), 3)
    assert out.iloc[3] == pytest.approx(80.0)
    assert out.iloc[4] == pytest.approx(100 - 100 / 2.6)
    assert out.iloc[5] == pytest.approx(100 - 100 / 4.4)


def test_rsi_extremes():
    assert ind.rsi(s(range(1, 40)), 14).iloc[-1] == 100.0
    assert ind.rsi(s(range(40, 1, -1)), 14).iloc[-1] == 0.0
    assert ind.rsi(s([5.0] * 30), 14).iloc[-1] == 50.0


def _reference_rsi(closes, n):
    """Independent, deliberately naive implementation."""
    out = [None] * len(closes)
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out[n] = 100 - 100 / (1 + ag / al)
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
        out[i + 1] = 100 - 100 / (1 + ag / al)
    return out


def test_rsi_matches_reference_implementation():
    rng = np.random.default_rng(7)
    closes = list(100 + np.cumsum(rng.normal(0, 1.5, 400)))
    ours = ind.rsi(s(closes), 14).tolist()
    ref = _reference_rsi(closes, 14)
    for a, b in zip(ours[14:], ref[14:]):
        assert a == pytest.approx(b, rel=1e-12)


def test_macd_structure():
    rng = np.random.default_rng(3)
    close = s(500 + np.cumsum(rng.normal(0, 3, 200)))
    m = ind.macd(close)
    assert m["macd"].first_valid_index() == "d25"
    assert m["signal"].first_valid_index() == "d33"
    expected_line = ind.ema(close, 12) - ind.ema(close, 26)
    np.testing.assert_allclose(m["macd"].dropna(), expected_line.dropna())
    np.testing.assert_allclose((m["macd"] - m["signal"]).dropna(), m["hist"].dropna())


def test_bollinger_population_sd():
    b = ind.bollinger(s([1, 2, 3, 4, 5]), n=5, k=2)
    assert b["middle"].iloc[-1] == 3.0
    assert b["upper"].iloc[-1] == pytest.approx(3 + 2 * math.sqrt(2))
    assert b["lower"].iloc[-1] == pytest.approx(3 - 2 * math.sqrt(2))
    assert b["percent_b"].iloc[-1] == pytest.approx((5 - (3 - 2 * math.sqrt(2))) / (4 * math.sqrt(2)))


def test_bollinger_flat_series_has_no_percent_b():
    b = ind.bollinger(s([10] * 25), n=20)
    assert b["upper"].iloc[-1] == b["lower"].iloc[-1] == 10.0
    assert math.isnan(b["percent_b"].iloc[-1])


def test_atr_constant_range():
    n = 30
    out = ind.atr(s([11] * n), s([9] * n), s([10] * n), 14)
    assert math.isnan(out.iloc[13])
    assert out.iloc[14:].tolist() == [2.0] * (n - 14)


def test_true_range_uses_previous_close_on_gaps():
    tr = ind.true_range(s([10, 15]), s([9, 14]), s([9.5, 14.5]))
    assert math.isnan(tr.iloc[0])
    assert tr.iloc[1] == pytest.approx(15 - 9.5)


def test_vwap_rolling_constant_volume_equals_mean_typical_price():
    h, l, c = s(range(10, 40)), s(range(8, 38)), s(range(9, 39))
    v = s([1000] * 30)
    out = ind.vwap_rolling(h, l, c, v, n=20)
    tp = (h + l + c) / 3
    assert out.iloc[-1] == pytest.approx(tp.iloc[-20:].mean())


def test_vwap_zero_volume_is_unavailable_not_zero():
    out = ind.vwap_rolling(s([2] * 20), s([1] * 20), s([1.5] * 20), s([0] * 20), n=20)
    assert math.isnan(out.iloc[-1])


def test_support_resistance_and_gaps():
    idx = [f"2026-01-{i:02d}" for i in range(1, 26)]
    bars = pd.DataFrame(
        {
            "open": [100.0] * 24 + [110.0],
            "high": [101.0] * 10 + [130.0] + [101.0] * 14,
            "low": [99.0] * 5 + [80.0] + [99.0] * 19,
            "close": [100.0] * 25,
        },
        index=idx,
    )
    levels = ind.support_resistance(bars, windows=(20, 60))
    assert len(levels) == 1  # 60-session window skipped: not enough data
    assert levels[0]["support"] == 80.0 and levels[0]["support_date"] == "2026-01-06"
    assert levels[0]["resistance"] == 130.0
    gaps = ind.price_gaps(bars, lookback=5, threshold=0.03)
    assert [g["date"] for g in gaps] == ["2026-01-25"]
    assert gaps[0]["gap"] == pytest.approx(0.10)


def test_volume_ratio():
    vol = s([100] * 50 + [300])
    assert ind.volume_ratio(vol, 50) == 3.0
    assert ind.volume_ratio(s([100] * 10), 50) is None
