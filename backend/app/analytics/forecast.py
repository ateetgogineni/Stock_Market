"""Forecast engine with walk-forward evaluation (plan sections 4.10 and 8; Qlib-style discipline).

Three models forecast the h-session forward log return:
* random_walk: zero median, band from trailing 1-year volatility (the baseline);
* drift: trailing 1-year mean return, same band;
* momentum_ridge: ridge regression on momentum and trend features, band from training residuals.

Evaluation is walk-forward with no look-ahead: at each origin a model is trained only on
rows whose forward outcome was already known at that origin. The most recent 25% of
origins is a holdout. A model is approved only if, on the holdout, it beats the random
walk on error, gets direction right more often than not and keeps its 10-90% band
honest. Forecasts are paper-only either way; they never feed the rating engine.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import indicators as ind

VERSION = "forecast-0.1.0"
HORIZONS = {21: "1 month (21 sessions)", 63: "3 months (63 sessions)"}
Z90 = 1.2815515655446004  # 10th / 90th percentile of a standard normal
STEP = 5
MIN_TRAIN = 250
MIN_SESSIONS = 600
HOLDOUT_SHARE = 0.25
APPROVAL = {"min_holdout": 30, "min_independent": 6, "mae_vs_baseline": 0.98, "min_direction": 0.52, "coverage": (0.65, 0.95)}
FEATURES = ["r21", "r63", "r126", "r252", "d50", "d200", "rsi", "vol63"]


def features(close: pd.Series) -> pd.DataFrame:
    logc = np.log(close.astype(float))
    f = pd.DataFrame(index=close.index)
    for n in (21, 63, 126, 252):
        f[f"r{n}"] = logc - logc.shift(n)
    f["d50"] = close / close.rolling(50).mean() - 1
    f["d200"] = close / close.rolling(200).mean() - 1
    f["rsi"] = ind.rsi(close) / 100 - 0.5
    f["vol63"] = logc.diff().rolling(63).std() * math.sqrt(252)
    return f


def forward_return(close: pd.Series, h: int) -> pd.Series:
    logc = np.log(close.astype(float))
    return logc.shift(-h) - logc


def _ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float = 1.0):
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    y_mean = y.mean()
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - y_mean))
    resid = y - (Z @ beta + y_mean)
    return {"mu": mu, "sd": sd, "beta": beta, "y_mean": y_mean, "q10": float(np.quantile(resid, 0.10)), "q90": float(np.quantile(resid, 0.90))}


def _ridge_predict(model, x: np.ndarray) -> float:
    return float(((x - model["mu"]) / model["sd"]) @ model["beta"] + model["y_mean"])


def _predict_all(daily: np.ndarray, X: np.ndarray, y: np.ndarray, train_mask: np.ndarray, i: int, h: int) -> dict:
    """Forecasts made at position i, using only rows in train_mask (all labels known by i)."""
    hist = daily[max(1, i - 251): i + 1]
    hist = hist[~np.isnan(hist)]
    sigma = float(np.std(hist, ddof=1)) if len(hist) > 20 else float("nan")
    band = Z90 * sigma * math.sqrt(h)
    out = {"random_walk": (0.0, -band, band), "drift": None, "momentum_ridge": None}
    mean = float(np.mean(hist)) * h if len(hist) > 20 else float("nan")
    out["drift"] = (mean, mean - band, mean + band)
    Xt, yt = X[train_mask], y[train_mask]
    if len(yt) >= MIN_TRAIN and not np.isnan(X[i]).any():
        m = _ridge_fit(Xt, yt)
        p = _ridge_predict(m, X[i])
        out["momentum_ridge"] = (p, p + m["q10"], p + m["q90"])
    return out


def _metrics(rows: list[dict], name: str) -> dict:
    pts = [r for r in rows if r["pred"].get(name) is not None]
    if not pts:
        return {"n": 0, "mae": None, "direction": None, "coverage": None, "width": None}
    err = [abs(r["pred"][name][0] - r["actual"]) for r in pts]
    covered = [r["pred"][name][1] <= r["actual"] <= r["pred"][name][2] for r in pts]
    width = [r["pred"][name][2] - r["pred"][name][1] for r in pts]
    directional = [r for r in pts if r["pred"][name][0] != 0]
    hits = [math.copysign(1, r["pred"][name][0]) == math.copysign(1, r["actual"]) for r in directional]
    return {"n": len(pts), "mae": float(np.mean(err)), "direction": float(np.mean(hits)) if hits else None,
            "coverage": float(np.mean(covered)), "width": float(np.mean(width))}


def approve(holdout: dict[str, dict], horizon: int = STEP) -> tuple[str | None, str]:
    """Pick the best non-baseline model that clears every rule on the holdout, or explain why none did."""
    base = holdout.get("random_walk", {})
    if not base.get("n") or base["n"] < APPROVAL["min_holdout"]:
        return None, f"Holdout has {base.get('n', 0)} forecasts; {APPROVAL['min_holdout']} are needed."
    independent = base["n"] * STEP // horizon  # non-overlapping windows in the holdout
    if independent < APPROVAL["min_independent"]:
        return None, (f"Holdout covers only {independent} non-overlapping {horizon}-session windows; "
                      f"{APPROVAL['min_independent']} are needed before any model can be approved.")
    passed, why = [], []
    for name in ("momentum_ridge", "drift"):
        m = holdout.get(name, {})
        if not m.get("n"):
            why.append(f"{name}: no holdout forecasts")
            continue
        lo, hi = APPROVAL["coverage"]
        checks = [
            (m["mae"] < base["mae"] * APPROVAL["mae_vs_baseline"], f"error {m['mae']:.4f} vs random walk {base['mae']:.4f}"),
            ((m["direction"] or 0) >= APPROVAL["min_direction"], f"direction right {0 if m['direction'] is None else m['direction']:.0%} of the time"),
            (lo <= m["coverage"] <= hi, f"10-90% band held the outcome {m['coverage']:.0%} of the time"),
        ]
        failed = [t for ok, t in checks if not ok]
        (passed.append((m["mae"], name)) if not failed else why.append(f"{name}: " + "; ".join(failed)))
    if passed:
        return min(passed)[1], "Beats the random-walk baseline on the untouched holdout."
    return None, "No model beats the random-walk baseline on the holdout (" + " | ".join(why) + ")."


def run(close: pd.Series) -> dict:
    close = close.astype(float).dropna()
    if len(close) < MIN_SESSIONS:
        return {"status": "unavailable", "version": VERSION,
                "reason": f"Walk-forward evaluation needs about {MIN_SESSIONS} sessions of history; {len(close)} available."}
    feats = features(close)
    X = feats[FEATURES].to_numpy(float)
    daily = np.log(close.to_numpy()).copy()
    daily = np.concatenate([[np.nan], np.diff(daily)])
    spot = float(close.iloc[-1])
    n = len(close)
    out = {"status": "ok", "version": VERSION, "mode": "paper", "as_of": str(close.index[-1]), "spot": spot,
           "horizons": [], "method": {
               "evaluation": f"Walk-forward every {STEP} sessions; training uses only outcomes known at each origin; "
                             f"last {int(HOLDOUT_SHARE * 100)}% of origins held out.",
               "approval": APPROVAL, "returns": "close-to-close log returns, no costs",
               "caveat": "Forecast windows overlap (a new origin every 5 sessions), so neighbouring forecasts are correlated and the effective sample is smaller than the count."}}
    feature_ok = ~np.isnan(X).any(axis=1)
    for h, label in HORIZONS.items():
        y = forward_return(close, h).to_numpy(float)
        labelled = feature_ok & ~np.isnan(y)
        rows = []
        for i in range(0, n - h, STEP):
            train = labelled & (np.arange(n) <= i - h)
            if train.sum() < MIN_TRAIN or not feature_ok[i]:
                continue
            rows.append({"origin": str(close.index[i]), "actual": float(y[i]), "pred": _predict_all(daily, X, y, train, i, h)})
        split = int(len(rows) * (1 - HOLDOUT_SHARE))
        dev, hold = rows[:split], rows[split:]
        names = ("random_walk", "drift", "momentum_ridge")
        metrics = {k: {"dev": _metrics(dev, k), "holdout": _metrics(hold, k)} for k in names}
        selected, reason = approve({k: v["holdout"] for k, v in metrics.items()}, h)
        final_train = labelled & (np.arange(n) <= n - 1 - h)
        now = _predict_all(daily, X, y, final_train, n - 1, h)
        models = {}
        for k in names:
            p = now.get(k)
            models[k] = {**metrics[k], "forecast": None if p is None else {
                "median_return": p[0], "q10": p[1], "q90": p[2],
                "median_price": spot * math.exp(p[0]), "low_price": spot * math.exp(p[1]), "high_price": spot * math.exp(p[2])}}
        shown = selected or "random_walk"
        f = models[shown]["forecast"]
        out["horizons"].append({
            "sessions": h, "label": label, "origins": len(rows), "holdout_from": hold[0]["origin"] if hold else None,
            "first_origin": rows[0]["origin"] if rows else None, "models": models,
            "selected": selected, "approved": selected is not None, "reason": reason, "shown_model": shown,
            "scenarios": None if f is None else {"bear": f["low_price"], "base": f["median_price"], "bull": f["high_price"]},
            "scenario_note": "Model forecast range (10th, 50th and 90th percentiles)." if selected else
                             "Statistical range only: no model beat the random walk, so this is the 10-90% band of a no-edge random walk.",
        })
    return out
