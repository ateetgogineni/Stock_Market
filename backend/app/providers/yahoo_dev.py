"""Development-only adapter backed by the unofficial yfinance library.

This is NOT a licensed NSE/BSE feed (plan section 6.2). Prices are delayed or
end-of-day, coverage and accuracy are not guaranteed, and the data must not be
redistributed or used in production. The entitlement block below travels with
every snapshot so the UI can say so.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from .base import DatasetUnavailable

STATEMENT_ATTRS = {
    "annual": {"income": "income_stmt", "balance": "balance_sheet", "cashflow": "cashflow"},
    "quarterly": {
        "income": "quarterly_income_stmt",
        "balance": "quarterly_balance_sheet",
        "cashflow": "quarterly_cashflow",
    },
}

PROFILE_FIELDS = [
    "longName", "shortName", "sector", "industry", "longBusinessSummary", "website",
    "fullTimeEmployees", "country", "city", "currency", "financialCurrency", "exchange",
    "fullExchangeName", "quoteType",
]


def _clean(value):
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 6)


def _frame_to_lines(df: pd.DataFrame) -> dict:
    out: dict[str, dict[str, float]] = {}
    if df is None or df.empty:
        return out
    for line, row in df.iterrows():
        values = {}
        for col, val in row.items():
            v = _clean(val)
            if v is not None:
                values[pd.Timestamp(col).date().isoformat()] = v
        if values:
            out[str(line)] = values
    return out


class YahooDevProvider:
    name = "yahoo_dev"
    version = "0.1.0"
    entitlement = {
        "type": "delayed_or_end_of_day",
        "licensed": False,
        "production_use": False,
        "realtime": False,
        "notes": "Unofficial Yahoo Finance data via yfinance, for development only. Not an NSE/BSE "
        "authorised feed. Intraday quotes are delayed (typically 15 minutes); daily bars are end-of-day.",
    }

    def __init__(self) -> None:
        self._tickers: dict[str, yf.Ticker] = {}
        self._info: dict[str, dict] = {}

    def _ticker(self, symbol: str) -> yf.Ticker:
        if symbol not in self._tickers:
            self._tickers[symbol] = yf.Ticker(symbol)
        return self._tickers[symbol]

    def _get_info(self, symbol: str) -> dict:
        if symbol not in self._info:
            self._info[symbol] = self._ticker(symbol).info or {}
        return self._info[symbol]

    def history(self, provider_symbol: str, years: int = 5) -> list[dict]:
        df = self._ticker(provider_symbol).history(
            period=f"{years}y", interval="1d", auto_adjust=False, actions=True
        )
        if df is None or df.empty:
            raise DatasetUnavailable(f"No price history returned for {provider_symbol}.")
        records = []
        for ts, row in df.iterrows():
            records.append(
                {
                    "date": pd.Timestamp(ts).date().isoformat(),
                    "open": _clean(row.get("Open")),
                    "high": _clean(row.get("High")),
                    "low": _clean(row.get("Low")),
                    "close": _clean(row.get("Close")),
                    "adj_close": _clean(row.get("Adj Close")),
                    "volume": _clean(row.get("Volume")),
                    "dividend": _clean(row.get("Dividends")) or 0.0,
                    "split": _clean(row.get("Stock Splits")) or 0.0,
                }
            )
        return records

    def quote(self, provider_symbol: str) -> dict:
        info = self._get_info(provider_symbol)
        price = _clean(info.get("regularMarketPrice") or info.get("currentPrice"))
        if price is None:
            raise DatasetUnavailable(f"No quote returned for {provider_symbol}.")
        market_time = info.get("regularMarketTime")
        return {
            "price": price,
            "previous_close": _clean(info.get("regularMarketPreviousClose") or info.get("previousClose")),
            "market_time": datetime.fromtimestamp(int(market_time), tz=timezone.utc).isoformat()
            if market_time
            else None,
            "delay_minutes": info.get("exchangeDataDelayedBy"),
            "market_state": info.get("marketState"),
            "currency": info.get("currency"),
            # Provider-reported reference values. Used only to cross-check our own calculations.
            "reported": {
                "fifty_two_week_high": _clean(info.get("fiftyTwoWeekHigh")),
                "fifty_two_week_low": _clean(info.get("fiftyTwoWeekLow")),
                "market_cap": _clean(info.get("marketCap")),
                "shares_outstanding": _clean(info.get("sharesOutstanding")),
                "trailing_pe": _clean(info.get("trailingPE")),
                "price_to_book": _clean(info.get("priceToBook")),
            },
        }

    def profile(self, provider_symbol: str) -> dict:
        info = self._get_info(provider_symbol)
        if not info.get("longName") and not info.get("shortName"):
            raise DatasetUnavailable(f"No profile returned for {provider_symbol}.")
        return {k: info.get(k) for k in PROFILE_FIELDS}

    def statements(self, provider_symbol: str) -> dict:
        t = self._ticker(provider_symbol)
        out: dict[str, dict] = {}
        for freq, attrs in STATEMENT_ATTRS.items():
            out[freq] = {kind: _frame_to_lines(getattr(t, attr)) for kind, attr in attrs.items()}
        if not any(out[f][k] for f in out for k in out[f]):
            raise DatasetUnavailable(f"No financial statements returned for {provider_symbol}.")
        return out

    def news(self, provider_symbol: str) -> list[dict]:
        items = []
        for raw in self._ticker(provider_symbol).news or []:
            c = raw.get("content") if isinstance(raw.get("content"), dict) else None
            if c:  # yfinance >= 0.2.50 shape
                url = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url")
                items.append(
                    {
                        "id": str(raw.get("id") or c.get("id")),
                        "title": c.get("title"),
                        "publisher": (c.get("provider") or {}).get("displayName"),
                        "published_at": c.get("pubDate"),
                        "url": url,
                        "summary": c.get("summary") or c.get("description"),
                        "content_type": c.get("contentType"),
                    }
                )
            else:  # legacy shape
                ts = raw.get("providerPublishTime")
                items.append(
                    {
                        "id": str(raw.get("uuid")),
                        "title": raw.get("title"),
                        "publisher": raw.get("publisher"),
                        "published_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
                        "url": raw.get("link"),
                        "summary": None,
                        "content_type": raw.get("type"),
                    }
                )
        return [i for i in items if i.get("title")]

    def calendar(self, provider_symbol: str) -> dict:
        cal = self._ticker(provider_symbol).calendar or {}
        earnings = cal.get("Earnings Date") or []
        ex_div = cal.get("Ex-Dividend Date")
        return {
            "earnings_dates": [d.isoformat() for d in earnings if hasattr(d, "isoformat")],
            "ex_dividend_date": ex_div.isoformat() if hasattr(ex_div, "isoformat") else None,
        }

    def filings(self, provider_symbol: str) -> list[dict]:
        raise DatasetUnavailable(
            "Official NSE/BSE corporate filings need a licensed source. The dev adapter does not "
            "scrape exchange websites (plan section 6.2)."
        )
