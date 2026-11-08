"""Provider adapter interface (plan section 6.1).

Agents and analytics never talk to a vendor directly. They consume a snapshot
built through this interface, so a licensed NSE/BSE vendor can replace the dev
adapter without touching analysis code.
"""

from __future__ import annotations

from typing import Protocol


class DatasetUnavailable(Exception):
    """Raised when a provider does not offer a dataset (as opposed to a transient failure)."""


class MarketDataProvider(Protocol):
    name: str
    version: str
    # Describes what the data is allowed to be called. Shown in the UI and stored
    # with every snapshot. A dev adapter must never claim to be real-time.
    entitlement: dict

    def history(self, provider_symbol: str, years: int) -> list[dict]:
        """Daily bars, oldest first: date, open, high, low, close, adj_close, volume, dividend, split."""

    def quote(self, provider_symbol: str) -> dict:
        """Latest quote fields plus provider-reported reference values used for cross-checks."""

    def profile(self, provider_symbol: str) -> dict:
        """Company profile: name, sector, industry, business summary, website, employees."""

    def statements(self, provider_symbol: str) -> dict:
        """{"annual"|"quarterly": {"income"|"balance"|"cashflow": {line_item: {period_end: value}}}}"""

    def news(self, provider_symbol: str) -> list[dict]:
        """News items: id, title, publisher, published_at, url, summary, content_type."""

    def calendar(self, provider_symbol: str) -> dict:
        """Upcoming corporate events: earnings_dates, ex_dividend_date."""

    def filings(self, provider_symbol: str) -> list[dict]:
        """Official exchange filings. Raise DatasetUnavailable when the adapter has no licensed source."""
