"""HTTP API for the research platform vertical slice."""

from __future__ import annotations

import concurrent.futures as cf
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import __version__
from .agents.llm import agent_runtime, make_llm
from .config import get_settings
from .db import AnalysisRun, Database, EvidenceRow
from .options.api import router as options_router
from .providers import get_provider
from .services import instruments as resolver
from .services.analysis import chart_series
from .services.orchestrator import Orchestrator
from .services.predictions import summarise
from .services.snapshots import load_snapshot


def build_orchestrator(settings) -> Orchestrator:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_url)
    db.create_all()
    return Orchestrator(
        db,
        settings,
        provider_factory=lambda: get_provider(settings.provider),
        llm_factory=lambda: make_llm(settings),
        alt_llm_factory=lambda: make_llm(settings, alternate=True),
        agent_label=lambda: (lambda rt: f"{rt['provider']}:{rt['model']}")(agent_runtime(settings)),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.orchestrator = getattr(app.state, "orchestrator", None) or build_orchestrator(settings)
    app.state.pool = cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis")
    yield
    app.state.pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Stock Research Platform API", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(options_router)


class RunRequest(BaseModel):
    instrument_id: str = Field(..., examples=["IN:INE002A01018"])
    exchange: str = Field("NSE", pattern="^(NSE|BSE)$")


def _orch() -> Orchestrator:
    return app.state.orchestrator


@app.get("/api/health")
def health():
    s = app.state.settings
    return {
        "status": "ok",
        "version": __version__,
        "provider": s.provider,
        "agents": {"enabled": s.agents_enabled, **agent_runtime(s)},
        "universe": resolver.load_universe()["counts"],
        "trading": "disabled",
    }


def _instrument_view(inst: dict, matched_on: str | None = None) -> dict:
    coverage = inst.get("coverage", "core")
    return {
        "instrument_id": inst["instrument_id"], "name": inst["name"], "isin": inst["isin"], "currency": inst["currency"],
        "security_type": inst["security_type"], "matched_on": matched_on, "coverage": coverage,
        "coverage_note": resolver.EXTENDED_NOTE if coverage == "extended" else None,
        "listings": [{k: l.get(k) for k in ("exchange", "symbol", "series", "is_primary", "identifier_verified", "verification_source")}
                     for l in inst["listings"]],
    }


@app.get("/api/system/sources")
def system_sources():
    from .services.sources import system_sources as build

    s = app.state.settings
    return build(s, get_provider(s.provider))


@app.get("/api/instruments/search")
def search(q: str = Query(..., min_length=1, max_length=60), limit: int = Query(10, ge=1, le=25)):
    u = resolver.load_universe()
    hits = resolver.search(q, limit)
    return {"query": q, "universe": u["universe_id"], "counts": u["counts"],
            "results": [_instrument_view(h.instrument, h.matched_on) for h in hits]}


@app.get("/api/instruments")
def list_instruments(tier: str = Query("core", pattern="^(core|extended|all)$")):
    u = resolver.load_universe()
    return {"universe": u["universe_id"], "source": u["source"], "source_file_date": u["source_file_date"],
            "counts": u["counts"], "instruments": [_instrument_view(i) for i in resolver.universe_instruments(tier)]}


@app.get("/api/instruments/{instrument_id}")
def get_instrument(instrument_id: str):
    try:
        return _instrument_view(resolver.get_instrument(instrument_id))
    except resolver.ResolutionError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/runs", status_code=202)
def create_run(body: RunRequest):
    try:
        run_id = _orch().create_run(body.instrument_id, body.exchange)
    except resolver.ResolutionError as exc:
        raise HTTPException(404, str(exc))
    app.state.pool.submit(_orch().execute, run_id)
    return {"analysis_run_id": run_id, "status": "queued"}


def _run_view(run: AnalysisRun, include_report: bool) -> dict:
    out = {
        "analysis_run_id": run.id, "instrument_id": run.instrument_id, "exchange": run.exchange, "symbol": run.symbol,
        "currency": run.currency, "status": run.status, "requested_at": run.requested_at, "completed_at": run.completed_at,
        "market_data_as_of": run.market_data_as_of, "data_status": run.data_status, "snapshot_id": run.snapshot_id,
        "deterministic_hash": run.deterministic_hash, "summary": run.summary, "error": run.error,
    }
    if include_report:
        out.update(activity=run.activity, versions=run.versions, warnings=run.warnings, report=run.report)
    return out


@app.get("/api/runs")
def list_runs(instrument_id: str | None = None, limit: int = Query(30, ge=1, le=200)):
    with _orch().db.Session() as s:
        q = select(AnalysisRun).order_by(AnalysisRun.requested_at.desc()).limit(limit)
        if instrument_id:
            q = q.where(AnalysisRun.instrument_id == instrument_id)
        return {"runs": [_run_view(r, False) for r in s.scalars(q).all()]}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    with _orch().db.Session() as s:
        run = s.get(AnalysisRun, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        return _run_view(run, True)


@app.get("/api/runs/{run_id}/evidence")
def get_evidence(run_id: str):
    with _orch().db.Session() as s:
        rows = s.scalars(select(EvidenceRow).where(EvidenceRow.run_id == run_id)).all()
        if not rows and s.get(AnalysisRun, run_id) is None:
            raise HTTPException(404, "run not found")
        return {"analysis_run_id": run_id, "evidence": [r.payload for r in rows]}


@app.get("/api/runs/{run_id}/chart")
def get_chart(run_id: str):
    with _orch().db.Session() as s:
        run = s.get(AnalysisRun, run_id)
        if run is None or not run.snapshot_id:
            raise HTTPException(404, "run or snapshot not found")
        snapshot_id = run.snapshot_id
    return chart_series(load_snapshot(snapshot_id, _orch().settings.data_dir))


@app.post("/api/runs/{run_id}/replay")
def replay(run_id: str):
    try:
        return _orch().replay(run_id)
    except KeyError:
        raise HTTPException(404, "run not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/predictions")
def predictions():
    preds = _orch().list_predictions()
    return {"summary": summarise(preds), "predictions": preds}


@app.post("/api/predictions/evaluate")
def evaluate_predictions():
    return _orch().evaluate_predictions(date.today().isoformat())
