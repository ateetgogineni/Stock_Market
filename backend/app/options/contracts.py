"""Options contract identification (options spec phase 7).

Contract specifications come from NSE's daily F&O contract master
(`scripts/build_fo_master.py`): underlyings, expiries (already shifted for
exchange holidays), strikes, lot sizes, settlement method and exercise style.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ..services import instruments as equity_resolver

FO_FILE = Path(__file__).resolve().parent.parent / "universe" / "nse_fo_contracts.json"

# Underlying price sources. Index symbols are listed only where the provider symbol
# was checked against the index level; others are reported as unsupported, not guessed.
INDEX_PRICE_SYMBOLS = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK"}
INDEX_NAMES = {
    "NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY Bank", "FINNIFTY": "NIFTY Financial Services",
    "MIDCPNIFTY": "NIFTY Midcap Select", "NIFTYNXT50": "NIFTY Next 50",
}


class ContractError(ValueError):
    pass


@lru_cache
def load_master() -> dict:
    return json.loads(FO_FILE.read_text(encoding="utf-8"))


@lru_cache
def _equity_by_symbol() -> dict:
    out = {}
    for inst in equity_resolver.universe_instruments():
        for l in inst["listings"]:
            if l["exchange"] == "NSE":
                out[l["symbol"]] = inst
    return out


def underlying_view(symbol: str) -> dict:
    master = load_master()
    u = master["underlyings"].get(symbol)
    if u is None:
        raise ContractError(f"{symbol!r} has no options listed in NSE's F&O contract master ({master['file_date']}).")
    equity = _equity_by_symbol().get(symbol) if u["type"] == "stock" else None
    if u["type"] == "index":
        price_symbol = INDEX_PRICE_SYMBOLS.get(symbol)
        price_note = None if price_symbol else "No verified price source is configured for this index yet."
        name = INDEX_NAMES.get(symbol, symbol)
    else:
        price_symbol = f"{symbol}.NS"
        price_note = None
        name = equity["name"] if equity else symbol
    return {
        "symbol": symbol,
        "name": name,
        "type": u["type"],
        "settlement": u["settlement"],
        "exercise": u["exercise"],
        "price_symbol": price_symbol,
        "price_note": price_note,
        "instrument_id": equity["instrument_id"] if equity else None,
        "isin": equity["isin"] if equity else None,
        "expiries": [{"expiry": e, "lot_size": v["lot_size"], "strikes": len(v["strikes"])} for e, v in u["expiries"].items()],
        "contract_master_date": master["file_date"],
    }


def expiry_spec(symbol: str, expiry: str) -> dict:
    u = load_master()["underlyings"].get(symbol)
    if u is None or expiry not in u["expiries"]:
        raise ContractError(f"No {symbol} options expire on {expiry}.")
    return u["expiries"][expiry]


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def search(query: str, limit: int = 12) -> list[dict]:
    q = query.strip()
    if not q:
        return []
    q_up, q_norm = q.upper(), _norm(q)
    hits = []
    for sym, u in load_master()["underlyings"].items():
        name = INDEX_NAMES.get(sym) if u["type"] == "index" else (_equity_by_symbol().get(sym) or {}).get("name", "")
        name_norm = _norm(name or "")
        if sym == q_up:
            score = 100
        elif sym.startswith(q_up):
            score = 80
        elif q_norm and name_norm.startswith(q_norm):
            score = 70
        elif q_norm and (" " + q_norm) in (" " + name_norm):
            score = 50
        else:
            continue
        hits.append((score, u["type"] != "index", sym))
    hits.sort(key=lambda h: (-h[0], h[1], h[2]))
    return [underlying_view(sym) for _, _, sym in hits[:limit]]
