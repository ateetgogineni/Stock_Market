"""End-to-end vertical slice on synthetic data: run, verify, rate, store, replay (plan section 19)."""

import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agents.llm import LLMUnavailable
from app.db import Database
from app.providers.fixture import FixtureProvider
from app.services.orchestrator import Orchestrator
from app.services.predictions import evaluate
from tests.conftest import AS_OF, END, EXTENDED_ID, INSTRUMENT_ID


class FakeLLM:
    """Deterministic stand-in for Claude. Cites real evidence, plus one invented number to be caught."""

    model = "fake-llm"

    def __init__(self):
        self.calls = []

    def generate(self, *, system, user, schema, max_tokens):
        self.calls.append({"system": system, "user": user})
        payload = json.loads(user.split("<evidence_json>\n", 1)[1].split("\n</evidence_json>", 1)[0])
        ev = [e for e in payload["evidence"] if e["status"] == "ok"]
        first = ev[0]
        out = {
            "summary": "The evidence is summarised here.",
            "findings": [
                {"statement": f"{first['label']} is {first['display']}.", "kind": "fact", "stance": "neutral", "evidence_ids": [first["id"]]},
                {"statement": "The figure is 987.65, which is invented.", "kind": "calculation", "stance": "positive", "evidence_ids": [first["id"]]},
            ],
            "limitations": ["Segment data is not available."],
        }
        props = schema["properties"]
        if "swot" in props:
            out["swot"] = {"strengths": [{"point": "Large scale.", "evidence_ids": [first["id"]]}], "weaknesses": [], "opportunities": [], "threats": []}
        if "items" in props:
            out["items"] = [
                {"evidence_id": e["id"], "label": "uncertain" if "ignore all previous" in e["label"].lower() else "positive",
                 "event_type": "other", "relevance": "test", "time_horizon": "weeks", "unverified_rumour": False}
                for e in payload["evidence"] if e["id"].startswith("news.")
            ]
        return {"output": out, "model": self.model, "usage": {"input_tokens": 1, "output_tokens": 1}, "request_id": None}


def make_orchestrator(tmp_path, llm_factory, alt_llm_factory=None):
    settings = SimpleNamespace(data_dir=tmp_path, agents_enabled=True, agent_timeout_seconds=30, agent_max_tokens=1000,
                               agent_model="fake-llm")
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_all()
    return Orchestrator(db, settings, provider_factory=lambda: FixtureProvider(end_date=END), llm_factory=llm_factory,
                        clock=lambda: AS_OF, alt_llm_factory=alt_llm_factory)


def run_once(orch):
    run_id = orch.create_run(INSTRUMENT_ID, "NSE")
    orch.execute(run_id)
    from app.db import AnalysisRun
    with orch.db.Session() as s:
        return s.get(AnalysisRun, run_id)


def test_full_run_with_agents(tmp_path):
    llm = FakeLLM()
    orch = make_orchestrator(tmp_path, lambda: llm)
    run = run_once(orch)
    assert run.status == "completed", run.error
    report = run.report

    # Section 5.5 output contract.
    for key in ("generated_at", "market_data_as_of", "instrument", "data_quality", "horizons", "fundamentals",
                "technical", "news", "risk", "forecast", "versions", "agents"):
        assert key in report
    assert report["price"]["data_status"] == "end_of_day"
    fc = report["forecast"]
    assert fc["status"] == "ok" and fc["mode"] == "paper" and len(fc["horizons"]) == 2
    assert set(report["horizons"]) == {"short", "medium", "long"}

    # Agents ran, and the verifier removed the invented number from every agent.
    assert len(llm.calls) == 6
    for name in ("company_research", "financial_analysis", "technical_analysis", "news_events", "bull_case", "bear_case"):
        a = report["agents"][name]
        assert a["status"] == "completed"
        assert all("987.65" not in f["statement"] for f in a["findings"])
        assert any("987.65" in r["text"] for r in a["removed"])

    # The prompt-injection headline was passed as data and is labelled uncertain, not obeyed.
    injected = [n for n in report["news"]["items"] if "ignore all previous" in n["title"].lower()]
    assert injected and injected[0]["classification"]["label"] == "uncertain"
    assert "untrusted" in llm.calls[0]["system"]

    # Every step reports a terminal status.
    assert all(a["status"] in ("completed", "partial", "skipped") for a in run.activity)

    # Ratings are logged for later evaluation; INSUFFICIENT DATA is not.
    preds = orch.list_predictions()
    assert {p["horizon"] for p in preds} == {"medium", "long"}
    assert all(p["start_date"] == "2026-11-06" for p in preds)


def test_replay_is_reproducible_and_detects_tampering(tmp_path):
    orch = make_orchestrator(tmp_path, FakeLLM)
    run = run_once(orch)
    result = orch.replay(run.id)
    assert result["reproducible"] is True
    assert result["versions_changed"] is False
    assert result["stored_ratings"] == result["replay_ratings"]

    # A run stored by an older engine explains its mismatch instead of looking like tampering.
    from app.db import AnalysisRun
    with orch.db.Session.begin() as s:
        row = s.get(AnalysisRun, run.id)
        row.versions = {**row.versions, "engine": "analytics-0.0.1"}
        row.deterministic_hash = "0" * 64
    old = orch.replay(run.id)
    assert old["reproducible"] is False and old["versions_changed"] is True
    assert "expected" in old["explanation"]

    path = tmp_path / "snapshots" / f"{run.snapshot_id}.json"
    data = json.loads(path.read_text())
    data["datasets"]["history"]["data"][-1]["close"] *= 1.10
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="integrity"):
        orch.replay(run.id)


def test_run_without_llm_credentials_skips_agents(tmp_path):
    def no_llm():
        raise LLMUnavailable("No Anthropic credentials configured.")

    orch = make_orchestrator(tmp_path, no_llm)
    run = run_once(orch)
    assert run.status == "completed"
    agents = run.report["agents"]
    assert {a["status"] for a in agents.values()} == {"skipped"}
    # Without news labels the medium horizon still gets 70% coverage from fundamentals here.
    assert run.report["horizons"]["short"]["rating"] == "INSUFFICIENT_DATA"


def test_agent_failure_marks_run_partial(tmp_path):
    class Broken(FakeLLM):
        def generate(self, **kw):
            if "Technical Analysis" in kw["system"]:
                raise RuntimeError("boom")
            return super().generate(**kw)

    orch = make_orchestrator(tmp_path, Broken)
    run = run_once(orch)
    assert run.status == "partial"
    assert run.report["agents"]["technical_analysis"]["status"] == "failed"
    assert run.report["agents"]["financial_analysis"]["status"] == "completed"


def test_prediction_evaluation_rules():
    pred = {"horizon_end_date": "2026-12-01", "start_close": 100.0, "benchmark_start_close": 1000.0, "rating": "BUY"}
    bars = [{"date": "2026-11-30", "close": 104.0}, {"date": "2026-12-01", "close": 110.0}]
    bench = [{"date": "2026-12-01", "close": 1050.0}]
    out = evaluate(pred, bars, bench, 0.05)
    assert out["stock_return"] == pytest.approx(0.10)
    assert out["excess_return"] == pytest.approx(0.05)
    assert out["hit"] is True
    assert evaluate({**pred, "rating": "SELL"}, bars, bench, 0.05)["hit"] is False
    assert evaluate(pred, bars[:1], bench, 0.05) is None  # horizon not reached


def test_http_api_flow(tmp_path):
    from app import main

    main.app.state.orchestrator = make_orchestrator(tmp_path, FakeLLM)
    with TestClient(main.app) as client:
        assert client.get("/api/health").json()["trading"] == "disabled"
        src = client.get("/api/system/sources").json()
        by_id = {x["id"]: x for x in src["sources"]}
        assert by_id["option_chain"]["status"] == "synthetic" and by_id["fo_master"]["licensed"] is True
        assert src["candidates"] and all(c["status"] == "to evaluate; not connected" for c in src["candidates"])
        assert src["engines"]["analytics"].startswith("analytics-") and src["trading"] == "disabled"
        res = client.get("/api/instruments/search", params={"q": "reliance"}).json()["results"]
        assert res[0]["instrument_id"] == INSTRUMENT_ID
        assert [l["exchange"] for l in res[0]["listings"]] == ["NSE", "BSE"]  # one company, two listings
        isin = client.get("/api/instruments/search", params={"q": "INE002A01018"}).json()["results"]
        assert isin[0]["matched_on"] == "isin"

        run_id = client.post("/api/runs", json={"instrument_id": INSTRUMENT_ID, "exchange": "NSE"}).json()["analysis_run_id"]
        for _ in range(100):
            run = client.get(f"/api/runs/{run_id}").json()
            if run["status"] not in ("queued", "running"):
                break
            time.sleep(0.1)
        assert run["status"] == "completed", run["error"]
        chart = client.get(f"/api/runs/{run_id}/chart").json()
        assert len(chart["bars"]) > 1000 and chart["sma200"]
        evidence = client.get(f"/api/runs/{run_id}/evidence").json()["evidence"]
        assert any(e["id"] == "calc.roe" for e in evidence)
        assert client.post(f"/api/runs/{run_id}/replay").json()["reproducible"] is True
        assert client.get("/api/runs").json()["runs"][0]["analysis_run_id"] == run_id
        assert client.post("/api/runs", json={"instrument_id": "IN:XX0000000000", "exchange": "NSE"}).status_code == 404

        # Extended coverage: any NSE main-board equity can be searched and analysed.
        found = client.get("/api/instruments/search", params={"q": "cupid"}).json()
        assert found["results"][0]["instrument_id"] == EXTENDED_ID
        assert found["results"][0]["coverage"] == "extended" and found["results"][0]["coverage_note"]
        assert client.post("/api/runs", json={"instrument_id": EXTENDED_ID, "exchange": "BSE"}).status_code == 404
        ext_id = client.post("/api/runs", json={"instrument_id": EXTENDED_ID, "exchange": "NSE"}).json()["analysis_run_id"]
        for _ in range(100):
            ext = client.get(f"/api/runs/{ext_id}").json()
            if ext["status"] not in ("queued", "running"):
                break
            time.sleep(0.1)
        assert ext["status"] == "completed", ext["error"]
        assert ext["report"]["instrument"]["coverage"] == "extended"
        listing = client.get("/api/instruments").json()
        assert len(listing["instruments"]) == 24 and listing["counts"]["extended"] > 2000
    del main.app.state.orchestrator


def test_bear_case_runs_on_the_alternate_model(tmp_path):
    primary, alternate = FakeLLM(), FakeLLM()
    orch = make_orchestrator(tmp_path, lambda: primary, lambda: alternate)
    run = run_once(orch)
    assert run.status == "completed", run.error
    assert len(alternate.calls) == 1 and "Bear Researcher" in alternate.calls[0]["system"]
    assert len(primary.calls) == 5 and all("Bear Researcher" not in c["system"] for c in primary.calls)
    debate = run.report["agents"]
    assert debate["bull_case"]["status"] == debate["bear_case"]["status"] == "completed"
