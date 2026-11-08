"""Prediction log and outcome tracking (plan sections 4.15, 8.3 and 11.4).

Every non-abstaining rating is logged with its starting price. When its horizon
has passed, it is scored against NIFTY 50 using completed sessions only.
"""

from __future__ import annotations

from datetime import date


def evaluate(pred: dict, stock_bars: list[dict], bench_bars: list[dict] | None, hold_band: float) -> dict | None:
    """Score one prediction. Returns None while the horizon has not completed."""
    end = pred["horizon_end_date"]
    after = [b for b in stock_bars if b["date"] >= end and b.get("close")]
    if not after:
        return None
    exit_bar = after[0]
    stock_ret = exit_bar["close"] / pred["start_close"] - 1
    bench_ret = None
    if bench_bars and pred.get("benchmark_start_close"):
        b_after = [b for b in bench_bars if b["date"] >= end and b.get("close")]
        if b_after:
            bench_ret = b_after[0]["close"] / pred["benchmark_start_close"] - 1
    excess = stock_ret - bench_ret if bench_ret is not None else None
    hit = None
    if excess is not None:
        hit = {"BUY": excess > 0, "SELL": excess < 0, "HOLD": abs(excess) <= hold_band}.get(pred["rating"])
    return {
        "evaluated_on": exit_bar["date"],
        "exit_close": exit_bar["close"],
        "stock_return": stock_ret,
        "benchmark_return": bench_ret,
        "excess_return": excess,
        "hit": hit,
        "rule": "BUY hit if excess > 0; SELL hit if excess < 0; HOLD hit if |excess| <= hold band",
        "hold_band": hold_band,
        "note": "Close-to-close on completed sessions; no costs, taxes or slippage.",
    }


def summarise(preds: list[dict]) -> dict:
    by = {}
    for p in preds:
        key = (p["horizon"], p["rating"])
        row = by.setdefault(key, {"horizon": p["horizon"], "rating": p["rating"], "issued": 0, "evaluated": 0, "hits": 0})
        row["issued"] += 1
        if p["status"] == "evaluated" and p["outcome"] and p["outcome"].get("hit") is not None:
            row["evaluated"] += 1
            row["hits"] += int(bool(p["outcome"]["hit"]))
    rows = sorted(by.values(), key=lambda r: (r["horizon"], r["rating"]))
    for r in rows:
        r["hit_rate"] = r["hits"] / r["evaluated"] if r["evaluated"] else None
    return {
        "issued": len(preds),
        "open": sum(1 for p in preds if p["status"] == "open"),
        "evaluated": sum(1 for p in preds if p["status"] == "evaluated"),
        "by_horizon_and_rating": rows,
        "note": "Hit rates need a meaningful sample before they say anything; see sample sizes.",
        "today": date.today().isoformat(),
    }
