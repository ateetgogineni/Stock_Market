"""Provider Adapter Registry."""

from __future__ import annotations

from .base import DatasetUnavailable, MarketDataProvider

BENCHMARK = {"symbol": "^NSEI", "name": "NIFTY 50"}


def get_provider(name: str) -> MarketDataProvider:
    if name == "yahoo_dev":
        from .yahoo_dev import YahooDevProvider

        return YahooDevProvider()
    if name == "fixture":
        from ..services.market_calendar import expected_last_session, now_ist
        from .fixture import FixtureProvider

        return FixtureProvider(end_date=expected_last_session(now_ist()))
    raise ValueError(f"Unknown provider {name!r}")


__all__ = ["BENCHMARK", "DatasetUnavailable", "MarketDataProvider", "get_provider"]
