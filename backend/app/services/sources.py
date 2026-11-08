"""What data the platform runs on, how far each source can be trusted, and what could replace it."""

from __future__ import annotations

import json
from pathlib import Path

from .. import __version__
from ..agents.llm import agent_runtime
from ..analytics import ENGINE_VERSION, forecast
from ..options import contracts, decision, pricing
from ..options.desk import GLOBAL_SYMBOLS, VIX_SYMBOL
from ..options.service import ENGINE_VERSION as OPTIONS_ENGINE_VERSION
from ..options.synthetic import SyntheticOptionsProvider
from ..providers import BENCHMARK
from . import instruments as resolver
from .recommendation import load_rules

UNIVERSE_DIR = Path(__file__).resolve().parent.parent / "universe"

# Candidates only. None is connected, and licence terms, prices and redistribution rights must be
# checked with each vendor before use.
CANDIDATES = [
    {"name": "TrueData", "kind": "NSE authorised data vendor", "covers": ["equities", "F&O chain", "indices", "tick and minute bars"],
     "replaces": ["equity prices", "option chain"], "url": "https://www.truedata.in"},
    {"name": "Global Datafeeds", "kind": "NSE authorised data vendor", "covers": ["equities", "F&O chain", "indices", "historical data"],
     "replaces": ["equity prices", "option chain"], "url": "https://globaldatafeeds.in"},
    {"name": "NSE Data & Analytics", "kind": "Exchange data products", "covers": ["end-of-day and real-time licences", "corporate data"],
     "replaces": ["equity prices", "option chain", "filings"], "url": "https://www.nseindia.com"},
    {"name": "Broker market-data APIs (Kite Connect, Upstox, SmartAPI, Dhan)", "kind": "Broker API, account holders only",
     "covers": ["quotes", "option chain", "historical bars"], "replaces": ["option chain"],
     "caveat": "Usually for the account holder's personal use; redistribution is restricted."},
    {"name": "NSE SPAN and exposure margin files", "kind": "Exchange daily files", "covers": ["F&O margin parameters"],
     "replaces": ["margin model"], "url": "https://www.nseindia.com"},
    {"name": "NSE / BSE corporate announcements", "kind": "Exchange filings", "covers": ["results", "board meetings", "disclosures"],
     "replaces": ["news and filings"]},
]


def _universe_meta() -> dict:
    m = json.loads((UNIVERSE_DIR / "nse_master.json").read_text(encoding="utf-8"))
    return {"source": m.get("source"), "file_date": m.get("source_file_date")}


def _alternate(rt: dict, fallbacks: list[str]) -> str:
    others = [m for m in fallbacks if m != rt["model"]] if rt["provider"] == "gemini" else []
    return others[0] if others else rt["model"]


def system_sources(settings, equity_provider) -> dict:
    ent = equity_provider.entitlement
    synth = SyntheticOptionsProvider.entitlement
    fo = contracts.load_master()
    uni = resolver.load_universe()["counts"]
    rt = agent_runtime(settings)
    fallbacks = [m.strip() for m in (getattr(settings, "gemini_fallback_models", "") or "").split(",") if m.strip()]
    rules = load_rules()

    def src(id, name, used_for, status, provider, notes, licensed=False, as_of=None, link=None):
        return {"id": id, "name": name, "used_for": used_for, "status": status, "provider": provider,
                "licensed": licensed, "as_of": as_of, "notes": notes, "link": link}

    sources = [
        src("equity_prices", "Equity prices, statements, profile, news", ["Stock reports", "Forecasts", "Index spot for options"],
            "dev_only" if not ent.get("licensed") else "licensed", equity_provider.name, ent["notes"], ent.get("licensed", False)),
        src("benchmark", f"{BENCHMARK['name']} benchmark", ["Relative strength", "Beta"], "dev_only", equity_provider.name,
            f"{BENCHMARK['symbol']} from the same development provider."),
        src("option_chain", "Option premiums, bid/ask, OI, volume", ["Options lab", "Trade desk"], "synthetic",
            SyntheticOptionsProvider.name, synth["notes"]),
        src("fo_master", "NSE F&O contract master", ["Expiries", "Strikes", "Lot sizes"], "official", "NSE archives",
            f"{len(fo['underlyings'])} underlyings. Refresh with scripts/build_fo_master.py.", True, fo["file_date"], fo["source"]),
        src("equity_master", "NSE securities master (EQUITY_L)", ["Search", "ISINs", "Coverage tiers"], "official", "NSE archives",
            f"{uni.get('core', 0)} core and {uni.get('extended', 0)} extended companies. Refresh with scripts/build_universe.py.",
            True, _universe_meta()["file_date"], _universe_meta()["source"]),
        src("india_vix", "India VIX", ["Trade desk volatility gate"], "dev_only", equity_provider.name, f"{VIX_SYMBOL} end-of-day."),
        src("global_cues", "US market cues", ["Trade desk direction"], "dev_only", equity_provider.name,
            ", ".join(f"{k} ({v})" for k, v in GLOBAL_SYMBOLS.items()) + " previous close."),
        src("filings", "Exchange announcements and filings", ["News agent", "Event risk"], "missing", None,
            "Not connected. Reports say filings are unavailable."),
        src("margin", "SPAN and exposure margin", ["Short option legs"], "missing", None,
            "Not connected. The trade desk blocks any short leg until margin data exists."),
        src("fx", "FX rates", ["Statements in other currencies"], "missing", None,
            "Not connected. P/E and P/B are withheld when statements are not in INR."),
    ]
    return {
        "app_version": __version__,
        "trading": "disabled",
        "sources": sources,
        "agents": {"enabled": settings.agents_enabled, **rt, "fallbacks": fallbacks if rt["provider"] == "gemini" else [],
                   "debate": {"bull": rt["model"], "bear": _alternate(rt, fallbacks)}},
        "engines": {
            "analytics": ENGINE_VERSION, "forecast": forecast.VERSION, "options": OPTIONS_ENGINE_VERSION,
            "pricing": [pricing.MODEL["id"], pricing.BINOMIAL_MODEL["id"]],
            "rating_rules": rules["version"], "trade_rules": decision.RULES["version"],
        },
        "candidates": [{**c, "status": "to evaluate; not connected"} for c in CANDIDATES],
    }
