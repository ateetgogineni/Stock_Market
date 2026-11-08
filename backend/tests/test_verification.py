from app.services.verification import numbers_in_statement, unsupported_numbers, verify_agent_output

ALLOWED = {
    "calc.roe": {"id": "calc.roe", "label": "Return on equity (FY2026)", "display": "15.31%", "period": "FY2026"},
    "ind.sma200": {"id": "ind.sma200", "label": "Simple moving average (200 sessions)", "display": "₹1,302.45"},
    "calc.market_cap": {"id": "calc.market_cap", "label": "Market capitalisation", "display": "₹17,86,286.34 crore"},
    "news.abc": {"id": "news.abc", "label": "Some headline", "display": "Wire, published 2026-11-03T07:04:25Z"},
}


def test_number_extraction_skips_labels():
    assert numbers_in_statement("FY2026 ROE was 15.31% vs SMA200 at ₹1,302.45 in Q2") == ["15.31", "1302.45"]


def test_exact_and_rounded_numbers_are_supported():
    cited = [ALLOWED["calc.roe"]]
    assert unsupported_numbers("ROE of 15.31%", cited) == []
    assert unsupported_numbers("ROE of about 15.3%", cited) == []
    assert unsupported_numbers("ROE of 15%", cited) == []
    assert unsupported_numbers("ROE of 18.2%", cited) == ["18.2"]


def test_indian_grouped_amounts():
    assert unsupported_numbers("market cap ₹17,86,286.34 crore", [ALLOWED["calc.market_cap"]]) == []
    # Unit conversion invents a number that is not in the evidence.
    assert unsupported_numbers("market cap ₹17.86 lakh crore", [ALLOWED["calc.market_cap"]]) == ["17.86"]


def test_small_counts_are_allowed():
    assert unsupported_numbers("Revenue grew in 3 of the last 4 years", []) == []


def test_verifier_removes_bad_findings_and_keeps_good_ones():
    output = {
        "summary": "Profitability is solid with ROE of 15.31%.",
        "findings": [
            {"statement": "ROE was 15.31% in FY2026.", "kind": "calculation", "stance": "positive", "evidence_ids": ["calc.roe"]},
            {"statement": "ROE was 22% in FY2026.", "kind": "calculation", "stance": "positive", "evidence_ids": ["calc.roe"]},
            {"statement": "Margins expanded.", "kind": "fact", "stance": "positive", "evidence_ids": []},
            {"statement": "The stock trades above SMA200.", "kind": "fact", "stance": "positive", "evidence_ids": ["ind.sma999"]},
            {"statement": "Management appears focused on returns.", "kind": "interpretation", "stance": "neutral", "evidence_ids": []},
        ],
        "limitations": ["Segment data is not available."],
        "items": [
            {"evidence_id": "news.abc", "label": "positive"},
            {"evidence_id": "news.fake", "label": "negative"},
            {"evidence_id": "news.abc", "label": "negative"},
        ],
    }
    res = verify_agent_output(output, ALLOWED, news_ids={"news.abc"})
    kept = [f["statement"] for f in res["output"]["findings"]]
    assert kept == ["ROE was 15.31% in FY2026.", "Management appears focused on returns."]
    reasons = [r["reason"] for r in res["removed"]]
    assert any("numbers not found" in r for r in reasons)
    assert any("without citing evidence" in r for r in reasons)
    assert any("does not exist" in r for r in reasons)
    assert [i["evidence_id"] for i in res["output"]["items"]] == ["news.abc"]
    assert res["output"]["summary"] == "Profitability is solid with ROE of 15.31%."


def test_summary_with_invented_number_is_withheld():
    res = verify_agent_output({"summary": "Target price ₹2,000.", "findings": [], "limitations": []}, ALLOWED)
    assert res["output"]["summary"] is None
    assert res["removed"][0]["type"] == "summary"
