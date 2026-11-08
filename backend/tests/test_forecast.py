"""Forecast engine: no look-ahead, calibrated baseline bands, honest approval."""

import numpy as np
import pandas as pd
import pytest

from app.analytics import forecast as fc


def gbm(n=1260, mu=0.10, sigma=0.25, seed=7):
    rng = np.random.default_rng(seed)
    r = rng.normal((mu - 0.5 * sigma**2) / 252, sigma / np.sqrt(252), n)
    return pd.Series(1000 * np.exp(np.cumsum(r)), index=pd.bdate_range("2021-11-01", periods=n).date.astype(str))


def test_short_history_is_unavailable():
    out = fc.run(gbm(n=400))
    assert out["status"] == "unavailable" and "600" in out["reason"]


def test_no_look_ahead_changing_the_future_does_not_change_past_forecasts():
    a = gbm()
    b = a.copy()
    b.iloc[-120:] = b.iloc[-120:] * 1.5  # rewrite the last 120 sessions
    ra, rb = fc.run(a), fc.run(b)
    # Holdout origins that end before the rewritten window must see identical forecasts.
    for ha, hb in zip(ra["horizons"], rb["horizons"]):
        h = ha["sessions"]
        cut = a.index[-120 - h]
        assert ha["first_origin"] == hb["first_origin"]
        # Recompute raw walk-forward rows to compare per origin.
        X = fc.features(a)[fc.FEATURES].to_numpy(float)
        Xb = fc.features(b)[fc.FEATURES].to_numpy(float)
        ya, yb = fc.forward_return(a, h).to_numpy(float), fc.forward_return(b, h).to_numpy(float)
        da = np.concatenate([[np.nan], np.diff(np.log(a.to_numpy()))])
        db = np.concatenate([[np.nan], np.diff(np.log(b.to_numpy()))])
        ok = ~np.isnan(X).any(axis=1)
        for i in range(400, len(a) - 120 - h, 63):
            train_a = ok & ~np.isnan(ya) & (np.arange(len(a)) <= i - h)
            train_b = (~np.isnan(Xb).any(axis=1)) & ~np.isnan(yb) & (np.arange(len(b)) <= i - h)
            pa, pb = fc._predict_all(da, X, ya, train_a, i, h), fc._predict_all(db, Xb, yb, train_b, i, h)
            assert a.index[i] < cut
            for k in pa:
                assert pa[k] == pytest.approx(pb[k])


def test_random_walk_band_is_roughly_calibrated_on_a_random_walk():
    out = fc.run(gbm(n=2500, seed=3))
    one_month = out["horizons"][0]
    cov = one_month["models"]["random_walk"]["dev"]["coverage"]
    assert 0.65 <= cov <= 0.95


def test_no_signal_series_does_not_get_an_approved_model():
    out = fc.run(gbm(n=1500, mu=0.0, seed=11))
    for h in out["horizons"]:
        assert h["shown_model"] in ("random_walk", "momentum_ridge", "drift")
        if not h["approved"]:
            assert "Statistical range only" in h["scenario_note"]
    assert out["mode"] == "paper"


def test_scenarios_are_ordered_around_spot():
    out = fc.run(gbm())
    for h in out["horizons"]:
        s = h["scenarios"]
        assert s["bear"] < s["base"] < s["bull"]
        assert s["bear"] < out["spot"] < s["bull"]


def test_approval_rules():
    base = {"n": 40, "mae": 0.05, "direction": None, "coverage": 0.8, "width": 0.1}
    good = {"n": 40, "mae": 0.045, "direction": 0.6, "coverage": 0.8, "width": 0.1}
    bad = {"n": 40, "mae": 0.06, "direction": 0.4, "coverage": 0.5, "width": 0.1}
    assert fc.approve({"random_walk": base, "momentum_ridge": good, "drift": bad})[0] == "momentum_ridge"
    name, why = fc.approve({"random_walk": base, "momentum_ridge": bad, "drift": bad})
    assert name is None and "random-walk baseline" in why
    assert fc.approve({"random_walk": {**base, "n": 5}})[0] is None
