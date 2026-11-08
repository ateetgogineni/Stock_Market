"""Synthetic option-chain provider (development only).

No licensed NSE option-chain source is configured yet, so premiums, bid/ask,
open interest and volume are GENERATED here. Contract identifiers (expiries,
strikes, lot sizes) are real, taken from NSE's contract master, and the
underlying price is the provider's real end-of-day close. Everything this
module produces is labelled "synthetic", and the strategy engine refuses to
call any trade an opportunity on synthetic data.

The generator prices each contract with Black-Scholes-Merton on a volatility
smile around the underlying's realised volatility, adds small pricing noise,
and builds bid/ask spreads that widen away from the money. It also plants a
couple of volume spikes so the unusual-activity detector has something to find.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np

from . import pricing

TICK = 0.05


def _round_tick(x: float, mode: str = "nearest") -> float:
    n = x / TICK
    n = math.floor(n + 1e-9) if mode == "down" else math.ceil(n - 1e-9) if mode == "up" else round(n)
    return round(n * TICK, 2)


class SyntheticOptionsProvider:
    name = "synthetic_options"
    version = "0.1.0"
    entitlement = {
        "type": "synthetic",
        "licensed": False,
        "production_use": False,
        "realtime": False,
        "notes": "Option premiums, bid/ask, open interest and volume are generated for development. Contract specs "
                 "come from NSE's contract master and the underlying price is a real end-of-day close.",
    }

    def chain(self, symbol: str, spot: float, spot_date: str, expiries: list[dict], base_vol: float,
              r: float, q: float) -> list[dict]:
        """`expiries`: [{"expiry", "T", "lot_size", "strikes"}] -> per-expiry rows of CE/PE quotes."""
        seed = int(hashlib.sha256(f"{symbol}|{spot_date}".encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        out = []
        for e in expiries:
            T = e["T"]
            strikes = e["strikes"]
            step = min((b - a for a, b in zip(strikes, strikes[1:])), default=1) or 1
            fwd = spot * math.exp((r - q) * T)
            scale = 60_000 if len(strikes) > 150 else 6_000
            decay = math.exp(-T * 6)  # far expiries trade less
            rows = []
            for K in strikes:
                x = max(-4.0, min(4.0, math.log(K / fwd) / (base_vol * math.sqrt(T))))
                vol = max(0.5 * base_vol, base_vol * (1 + 0.035 * x * x - 0.05 * x))
                bump = 1.8 if K % (step * 10) == 0 else 1.2 if K % (step * 2) == 0 else 1.0
                row = {"strike": K}
                for kind in ("CE", "PE"):
                    theo = pricing.price(kind, spot, K, T, r, vol, q)
                    mid = max(theo * (1 + rng.normal(0, 0.004)), 0.0)
                    if mid < TICK:
                        bid, ask = 0.0, TICK
                    else:
                        half = max(TICK, mid * (0.004 + 0.012 * abs(x)))
                        bid, ask = max(_round_tick(mid - half, "down"), 0.0), _round_tick(mid + half, "up")
                    side_bias = 1.4 if (x > 0) == (kind == "CE") else 0.8
                    oi = int(scale * math.exp(-0.5 * (0.8 * x) ** 2) * side_bias * bump * rng.lognormal(0, 0.35))
                    volume = 0 if abs(x) > 3 and rng.random() < 0.6 else int(oi * decay * rng.lognormal(math.log(0.6), 0.5))
                    ltp = _round_tick(mid * (1 + rng.normal(0, 0.01))) if volume else None
                    row[kind] = {
                        "bid": bid, "ask": ask, "ltp": ltp,
                        "prev_close": _round_tick(max((ltp or mid) * (1 + rng.normal(0, 0.08)), 0.0)),
                        "oi": oi, "oi_change": int(oi * rng.normal(0.02, 0.12)), "volume": volume,
                    }
                rows.append(row)
            # Plant volume spikes near the money for the unusual-activity detector to find.
            near = [i for i, rw in enumerate(rows) if abs(math.log(rw["strike"] / fwd)) < 2 * base_vol * math.sqrt(T)]
            for i in rng.choice(near, size=min(2, len(near)), replace=False) if near else []:
                kind = "CE" if rng.random() < 0.5 else "PE"
                rows[int(i)][kind]["volume"] = int(max(rows[int(i)][kind]["volume"], 1) * 8)
            out.append({"expiry": e["expiry"], "T": T, "lot_size": e["lot_size"], "rows": rows})
        return out
