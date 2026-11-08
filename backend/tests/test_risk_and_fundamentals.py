import math
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.analytics import formatting as fmt
from app.analytics import fundamentals as fa
from app.analytics import risk_metrics as rm


def s(values, start="2025-01-01"):
    return pd.Series([float(v) for v in values], index=pd.bdate_range(start, periods=len(values)).date.astype(str))


# ---------- risk metrics ----------

def test_period_return():
    assert rm.period_return(s([100, 110, 121]), 2) == pytest.approx(0.21)
    assert rm.period_return(s([100, 110]), 5) is None


def test_volatility_alternating_log_returns():
    r = 0.01
    logp = np.cumsum([0] + [r if i % 2 == 0 else -r for i in range(252)])
    vol = rm.annualised_volatility(s(np.exp(logp) * 100))
    rets = np.array([r if i % 2 == 0 else -r for i in range(252)])
    assert vol == pytest.approx(rets.std(ddof=1) * math.sqrt(252))


def test_volatility_needs_full_window():
    assert rm.annualised_volatility(s([1, 2, 3])) is None


def test_max_drawdown_dates():
    dd = rm.max_drawdown(s([100, 120, 90, 130, 117]))
    assert dd["value"] == pytest.approx(-0.25)
    idx = s([0] * 5).index
    assert dd["peak_date"] == idx[1] and dd["trough_date"] == idx[2]


def test_beta_of_levered_series_is_two():
    rng = np.random.default_rng(11)
    b_ret = rng.normal(0.0004, 0.01, 300)
    bench = 100 * np.cumprod(1 + np.concatenate([[0], b_ret]))
    stock = 100 * np.cumprod(1 + np.concatenate([[0], 2 * b_ret]))
    out = rm.beta(s(stock), s(bench))
    assert out["value"] == pytest.approx(2.0)
    assert out["correlation"] == pytest.approx(1.0)
    assert out["observations"] == 252


def test_beta_aligns_on_common_dates_only():
    bench = s(100 + np.arange(300))
    stock = bench.iloc[::2]  # half the dates missing
    out = rm.beta(stock, bench, min_obs=100)
    assert out["observations"] <= 150


def test_historical_var():
    rets = np.linspace(-0.05, 0.05, 201)
    close = s(100 * np.cumprod(1 + np.concatenate([[0], rets])))
    var = rm.historical_var(close, window=201)
    assert var == pytest.approx(-np.quantile(rets, 0.05))


# ---------- fundamentals (Decimal) ----------

def sv(value, key="x", period="2026-03-31"):
    return fa.StatementValue(key, key, "annual", period, fa.to_decimal(value))


def test_ratio_is_decimal_and_exact():
    r = fa.ratio("m", sv(0.3), sv(0.1), "a / b")
    assert r.ok and r.value == Decimal("3.000000")
    assert fa.ratio("m", sv(1), sv(3), "a / b").value == Decimal("0.333333")


def test_ratio_never_substitutes_zero():
    missing = fa.ratio("m", sv(10), None, "a / b")
    assert missing.status == "unavailable" and missing.value is None
    zero = fa.ratio("m", sv(10), sv(0), "a / b")
    assert zero.status == "not_meaningful" and zero.value is None
    negative_equity = fa.ratio("de", sv(10), sv(-5), "debt / equity")
    assert negative_equity.status == "not_meaningful"


def test_growth_rules():
    assert fa.growth("g", sv(110), sv(100)).value == Decimal("0.100000")
    assert fa.growth("g", sv(110), sv(-100)).status == "not_meaningful"
    assert fa.growth("g", sv(110), None).status == "unavailable"


def test_average_balance_falls_back_with_note():
    r = fa.ratio_on_average("roe", sv(20), sv(100), None, "ni / avg equity")
    assert r.value == Decimal("0.200000")
    assert "ending balance" in r.reason
    r2 = fa.ratio_on_average("roe", sv(20), sv(120), sv(80), "ni / avg equity")
    assert r2.value == Decimal("0.200000") and r2.reason is None


def test_statement_aliases_and_periods():
    st = fa.Statements(
        {"annual": {"income": {"Operating Revenue": {"2026-03-31": 5.0, "2025-03-31": 4.0}}, "balance": {}, "cashflow": {}}}
    )
    assert st.periods("annual", "revenue") == ["2026-03-31", "2025-03-31"]
    v = st.get("annual", "revenue", "2026-03-31")
    assert v.line_item == "Operating Revenue" and v.value == Decimal("5.0")
    assert st.get("annual", "net_income", "2026-03-31") is None


def test_quarter_matching():
    periods = ["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30"]
    assert fa.matching_prior_year(periods, "2026-09-30") is None  # 2025-09-30 missing
    assert fa.matching_prior_year(periods, "2026-06-30") == "2025-06-30"
    assert fa.consecutive_quarters(periods, 4) == periods[:4]
    assert fa.consecutive_quarters(["2026-09-30", "2026-06-30", "2025-12-31", "2025-09-30"], 4) is None


# ---------- formatting ----------

def test_indian_number_grouping():
    assert fmt.indian_number(123456789.5) == "12,34,56,789.50"
    assert fmt.indian_number(999) == "999.00"
    assert fmt.indian_number(-1234567, 0) == "-12,34,567"


def test_inr_crore():
    assert fmt.inr(3.30601e12) == "₹3,30,601.00 crore"
    assert fmt.inr(1320.5) == "₹1,320.50"
    assert fmt.inr(None) == "unavailable"
    assert fmt.inr(-1.114e8) == "-₹11.14 crore"
    assert fmt.inr(-5.5) == "-₹5.50"


def test_pct_and_labels():
    assert fmt.pct(0.123456) == "12.35%"
    assert fmt.pct(0.12345) == "12.34%"  # half-even rounding
    assert fmt.pct(-0.05) == "-5.00%"
    assert fmt.fy_label("2026-03-31") == "FY2026"
    assert fmt.quarter_label("2026-09-30") == "Q2 FY2027"
    assert fmt.quarter_label("2026-03-31") == "Q4 FY2026"
