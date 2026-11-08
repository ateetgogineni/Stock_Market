"""Instrument resolution across the core and extended (full NSE master) tiers."""

import pytest

from app.services import instruments as r
from app.services.analysis import compute_deterministic
from tests.conftest import EXTENDED_ID, INSTRUMENT_ID, make_snapshot


def symbols(hits):
    return [h.instrument["listings"][0]["symbol"] for h in hits]


def test_universe_has_both_tiers():
    counts = r.load_universe()["counts"]
    assert counts["core"] == 24
    assert counts["extended"] > 2000
    isins = [i["isin"] for i in r.universe_instruments()]
    assert len(isins) == len(set(isins)), "one instrument per ISIN"


@pytest.mark.parametrize("query", ["cupid", "CUPID", "Cupid Limited", "INE509F01029"])
def test_cupid_resolves_from_the_nse_master(query):
    hits = r.search(query)
    assert hits and hits[0].instrument["instrument_id"] == EXTENDED_ID
    inst = hits[0].instrument
    assert inst["coverage"] == "extended"
    assert [l["exchange"] for l in inst["listings"]] == ["NSE"]  # no BSE listing is invented
    assert inst["listings"][0]["identifier_verified"] is True
    assert inst["listings"][0]["provider_symbol"] == "CUPID.NS"


def test_isin_match_wins_and_exact_symbol_beats_prefix():
    assert r.search("INE002A01018")[0].matched_on == "isin"
    hits = r.search("M&M")
    assert symbols(hits)[0] == "M&M" and hits[0].matched_on == "symbol"


def test_core_ranks_first_on_ties():
    hits = r.search("hdfc")
    assert symbols(hits)[0] == "HDFCBANK"
    assert hits[0].instrument["coverage"] == "core"


def test_unknown_queries_and_listings():
    assert r.search("zzzz-not-a-company") == []
    with pytest.raises(r.ResolutionError):
        r.get_instrument("IN:XX0000000000")
    with pytest.raises(r.ResolutionError, match="no BSE listing"):
        r.get_listing(r.get_instrument(EXTENDED_ID), "BSE")
    assert r.get_listing(r.get_instrument(INSTRUMENT_ID), "BSE")["identifier_verified"] is False


def test_extended_instrument_report_is_flagged_and_skips_cross_listing():
    det = compute_deterministic(make_snapshot(instrument_id=EXTENDED_ID))
    ids = {g["id"]: g for g in det["gates"]}
    assert ids["coverage_tier"]["status"] == "warn"
    assert "not been pre-validated" in ids["coverage_tier"]["message"]
    assert "cross_listing_consistency" not in ids  # only the NSE listing is known
    assert det["data_quality"]["critical_failures"] == []


def test_trade_for_trade_series_is_flagged():
    be = next(i for i in r.universe_instruments("extended") if i["listings"][0]["series"] == "BE")
    det = compute_deterministic(make_snapshot(instrument_id=be["instrument_id"]))
    gate = next(g for g in det["gates"] if g["id"] == "trading_series")
    assert gate["status"] == "warn" and "trade-for-trade" in gate["message"]
