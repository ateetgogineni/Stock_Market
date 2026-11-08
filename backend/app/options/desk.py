"""Options Trading Desk (module 2): one fresh run per request.

Index selection -> fresh chain snapshot -> direction (agent 21) -> chain
intelligence (agent 22) -> strike selection, trade decision, entry/exit,
sizing and final verification (agents 23-27). Every run is stored as a signal
so outcomes can be measured later; a stored run is never re-shown as fresh.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from ..services import market_calendar as mc
from . import contracts, decision, direction, service

GLOBAL_SYMBOLS = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC"}
VIX_SYMBOL = "^INDIAVIX"


def indices() -> list[dict]:
    out = []
    for sym, u in contracts.load_master()["underlyings"].items():
        if u["type"] != "index":
            continue
        v = contracts.underlying_view(sym)
        out.append({"symbol": sym, "name": v["name"], "supported": v["price_symbol"] is not None, "note": v["price_note"],
                    "expiries": [e for e in v["expiries"]][:8]})
    out.sort(key=lambda x: (not x["supported"], x["symbol"] != "NIFTY", x["symbol"]))
    return out


def _safe_history(provider, symbol: str, years: int):
    try:
        return provider.history(symbol, years)
    except Exception:
        return None


def run(symbol: str, expiry: str | None, budget: float, provider, data_dir, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    und = contracts.underlying_view(symbol)
    if und["type"] != "index":
        raise contracts.ContractError(f"{symbol} is not an index. The trading desk covers index options.")
    snap = service.build_snapshot(symbol, provider, now=now)
    service.save(snap, data_dir)
    chain = service.chain_view(snap, expiry)

    index_bars = _safe_history(provider, und["price_symbol"], 2) or []
    vix = _safe_history(provider, VIX_SYMBOL, 1)
    global_bars = {name: bars for name, s in GLOBAL_SYMBOLS.items() if (bars := _safe_history(provider, s, 1))}
    real_chain = chain["data_type"] != "synthetic"
    dirn = direction.analyse(index_bars, vix, global_bars, chain["summary"], positioning_real=real_chain)

    spec = contracts.expiry_spec(symbol, chain["expiry"])
    market = mc.market_status(now)
    dec = decision.decide(chain, dirn, budget, set(spec["strikes"]), spec["lot_size"], market, now)

    expiry_close = datetime.combine(date.fromisoformat(chain["expiry"]), time(15, 30), tzinfo=mc.IST)
    remaining = (expiry_close - now).total_seconds()
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "fresh_until": None,  # a stored run is historical; the UI re-runs instead of reusing it
        "header": {
            "symbol": symbol, "name": und["name"], "price": dirn.get("last", chain["spot"]["price"]),
            "change_1d": dirn.get("change_1d"), "as_of": dirn.get("as_of", chain["spot"]["session"]),
            "trend": dirn["label"], "market": market, "expiry": chain["expiry"],
            "time_to_expiry_hours": max(remaining / 3600, 0.0), "lot_size": chain["summary"]["lot_size"],
            "data_type": chain["data_type"],
        },
        "direction": dirn,
        "chain": {k: chain[k] for k in ("chain_id", "data_type", "expiry", "expiries", "summary", "term_structure", "quality", "rows", "provider", "assumptions", "spot", "created_at")},
        "decision": dec,
        "budget": budget,
    }
