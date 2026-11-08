"""Instrument Resolution service (plan sections 3 and 6.5).

A security is never identified from ticker text alone. Every result is keyed
by ISIN and carries its explicit exchange listings, so a company listed on both
NSE and BSE resolves to ONE instrument with two listings and the caller must
pick the listing.

Two coverage tiers:
* core: the curated universe, checked end to end against the dev provider;
* extended: every other NSE main-board equity from NSE's official securities
  master. Identifiers are verified, data availability is not pre-validated, and
  the data-quality gates decide what each report may conclude. Only the NSE
  listing is known for these; BSE listings are not inferred.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

UNIVERSE_DIR = Path(__file__).resolve().parent.parent / "universe"
CORE_FILE = UNIVERSE_DIR / "nse_universe.json"
MASTER_FILE = UNIVERSE_DIR / "nse_master.json"
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
EXTENDED_NOTE = ("Extended coverage: identifier verified against NSE's securities master; provider data for this "
                 "company has not been pre-validated, so the data-quality checks decide what the report can conclude.")


class ResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class SearchHit:
    instrument: dict
    score: int
    matched_on: str


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def _extended_instrument(row: list) -> dict:
    symbol, name, series, isin, listed, face_value = row
    return {
        "instrument_id": f"IN:{isin}",
        "isin": isin,
        "name": name,
        "security_type": "equity",
        "country": "IN",
        "currency": "INR",
        "nse_listing_date": listed,
        "face_value": face_value,
        "coverage": "extended",
        "listings": [
            {
                "exchange": "NSE",
                "symbol": symbol,
                "series": series,
                "provider_symbol": f"{symbol}.NS",
                "is_primary": True,
                "identifier_verified": True,
                "verification_source": "NSE EQUITY_L.csv",
            }
        ],
    }


@lru_cache
def load_universe() -> dict:
    core = json.loads(CORE_FILE.read_text(encoding="utf-8"))
    master = json.loads(MASTER_FILE.read_text(encoding="utf-8")) if MASTER_FILE.exists() else {"rows": []}
    instruments = [{**inst, "coverage": "core"} for inst in core["instruments"]]
    known = {inst["isin"] for inst in instruments}
    instruments += [_extended_instrument(r) for r in master["rows"] if r[3] not in known]
    index = {inst["instrument_id"]: inst for inst in instruments}
    keys = [
        (inst, {l["symbol"].upper() for l in inst["listings"]}, _norm(inst["name"]))
        for inst in instruments
    ]
    return {
        "universe_id": "nse-dev-v2",
        "source": core["source"],
        "source_file_date": core.get("source_file_date"),
        "counts": {"core": len(core["instruments"]), "extended": len(instruments) - len(core["instruments"])},
        "instruments": instruments,
        "_index": index,
        "_keys": keys,
    }


def universe_instruments(tier: str | None = None) -> list[dict]:
    instruments = load_universe()["instruments"]
    return [i for i in instruments if tier in (None, "all") or i["coverage"] == tier]


def get_instrument(instrument_id: str) -> dict:
    inst = load_universe()["_index"].get(instrument_id)
    if inst is None:
        raise ResolutionError(f"Instrument {instrument_id!r} is not in the NSE securities master.")
    return inst


def get_listing(instrument: dict, exchange: str) -> dict:
    for listing in instrument["listings"]:
        if listing["exchange"] == exchange.upper():
            return listing
    raise ResolutionError(f"{instrument['name']} has no {exchange.upper()} listing loaded.")


def search(query: str, limit: int = 10) -> list[SearchHit]:
    """Search by ISIN, exchange symbol or company name.

    Ranking: exact ISIN > exact symbol > name starts with the query > symbol prefix >
    a name word starts with the query > name substring. Ties go to the core tier, then by name.
    """
    q = query.strip()
    if not q:
        return []
    q_upper = q.upper()
    q_norm = _norm(q)
    is_isin = bool(ISIN_RE.match(q_upper))
    hits: list[SearchHit] = []
    for inst, symbols, name_norm in load_universe()["_keys"]:
        if is_isin:
            if inst["isin"] == q_upper:
                hits.append(SearchHit(inst, 100, "isin"))
        elif q_upper in symbols:
            hits.append(SearchHit(inst, 90, "symbol"))
        elif q_norm and name_norm.startswith(q_norm):
            hits.append(SearchHit(inst, 75, "name"))
        elif any(s.startswith(q_upper) for s in symbols):
            hits.append(SearchHit(inst, 70, "symbol_prefix"))
        elif q_norm and (" " + q_norm) in (" " + name_norm):
            hits.append(SearchHit(inst, 55, "name"))
        elif q_norm and q_norm in name_norm:
            hits.append(SearchHit(inst, 40, "name_substring"))
    hits.sort(key=lambda h: (-h.score, h.instrument["coverage"] != "core", h.instrument["name"]))
    return hits[:limit]
