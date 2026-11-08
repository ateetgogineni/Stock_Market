"""HTTP endpoints for the Options Trading Intelligence module."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

import uuid

from ..db import OptionChain, OptionsSignal
from . import contracts, desk, service
from . import strategies as st

router = APIRouter(prefix="/api/options", tags=["options"])
FEATURED = ["NIFTY", "BANKNIFTY", "RELIANCE", "HDFCBANK", "INFY", "TCS", "SBIN", "ICICIBANK"]


class ChainRequest(BaseModel):
    symbol: str = Field(..., examples=["NIFTY"])


class StrategyRequest(BaseModel):
    template: str
    expiry: str | None = None
    width: int = Field(1, ge=1, le=20)
    lots: int = Field(1, ge=1, le=100)
    strikes: dict[str, float] | None = None


def _orch(request: Request):
    return request.app.state.orchestrator


@router.get("/underlyings")
def underlyings(q: str | None = Query(None, max_length=40)):
    master = contracts.load_master()
    found = contracts.search(q) if q else [contracts.underlying_view(s) for s in FEATURED if s in master["underlyings"]]
    return {"contract_master_date": master["file_date"], "count": len(master["underlyings"]), "results": found}


@router.get("/strategies")
def templates():
    return {"templates": [{"id": k, "label": v["label"], "outlook": v["outlook"], "explain": v["explain"],
                           "legs": [{"side": s, "type": t, "offset": o} for s, t, o in v["legs"]],
                           "stock_only": bool(v.get("stock_only"))} for k, v in st.TEMPLATES.items()]}


@router.post("/chains", status_code=201)
def create_chain(body: ChainRequest, request: Request):
    orch = _orch(request)
    symbol = body.symbol.strip().upper()
    try:
        snap = service.build_snapshot(symbol, orch.provider_factory())
    except contracts.ContractError as exc:
        raise HTTPException(404, str(exc))
    except service.OptionsDataError as exc:
        raise HTTPException(422, str(exc))
    service.save(snap, orch.settings.data_dir)
    with orch.db.Session.begin() as s:
        if s.get(OptionChain, snap["chain_id"]) is None:
            s.add(OptionChain(id=snap["chain_id"], symbol=symbol, created_at=snap["created_at"], spot=snap["spot"]["price"],
                              spot_session=snap["spot"]["session"], data_type=snap["provider"]["entitlement"]["type"],
                              expiries=len(snap["expiries"])))
    return {"chain_id": snap["chain_id"]}


def _load(request: Request, chain_id: str) -> dict:
    try:
        return service.load(chain_id, _orch(request).settings.data_dir)
    except FileNotFoundError:
        raise HTTPException(404, "chain snapshot not found")
    except service.OptionsDataError as exc:
        raise HTTPException(409, str(exc))


@router.get("/chains/{chain_id}")
def get_chain(chain_id: str, request: Request, expiry: str | None = None):
    snap = _load(request, chain_id)
    try:
        return service.chain_view(snap, expiry)
    except service.OptionsDataError as exc:
        raise HTTPException(404, str(exc))


@router.post("/chains/{chain_id}/strategies")
def evaluate(chain_id: str, body: StrategyRequest, request: Request):
    snap = _load(request, chain_id)
    try:
        return service.evaluate(snap, body.template, body.expiry, body.width, body.lots, body.strikes)
    except (st.StrategyError, service.OptionsDataError) as exc:
        raise HTTPException(422, str(exc))


class DeskRequest(BaseModel):
    symbol: str = Field("NIFTY")
    expiry: str | None = None
    budget: float = Field(25000, gt=0, le=1e8)


@router.get("/desk/indices")
def desk_indices():
    return {"indices": desk.indices()}


@router.post("/desk")
def run_desk(body: DeskRequest, request: Request):
    orch = _orch(request)
    try:
        out = desk.run(body.symbol.strip().upper(), body.expiry, body.budget, orch.provider_factory(), orch.settings.data_dir)
    except contracts.ContractError as exc:
        raise HTTPException(404, str(exc))
    except service.OptionsDataError as exc:
        raise HTTPException(422, str(exc))
    dec = out["decision"]
    signal_id = "sig_" + uuid.uuid4().hex[:16]
    best = dec.get("best") or {}
    with orch.db.Session.begin() as s:
        s.add(OptionsSignal(
            id=signal_id, created_at=out["generated_at"], symbol=out["header"]["symbol"], expiry=out["header"]["expiry"],
            status=dec["status"], strategy=best.get("strategy"), data_type=out["header"]["data_type"],
            mode="dry_run" if dec["dry_run"] else "paper", chain_id=dec["chain_id"],
            payload={"decision": {k: v for k, v in dec.items() if k != "strikes"},
                     "direction": {k: out["direction"].get(k) for k in ("label", "composite", "adx", "components", "vix", "atr", "last", "as_of")},
                     "header": out["header"], "budget": out["budget"]}))
    return {**out, "signal_id": signal_id}


@router.get("/signals")
def signals(request: Request, limit: int = Query(50, ge=1, le=500)):
    with _orch(request).db.Session() as s:
        rows = s.scalars(select(OptionsSignal).order_by(OptionsSignal.created_at.desc()).limit(limit)).all()
        items = [{"signal_id": r.id, "created_at": r.created_at, "symbol": r.symbol, "expiry": r.expiry, "status": r.status,
                  "strategy": r.strategy, "data_type": r.data_type, "mode": r.mode} for r in rows]
    counts: dict[str, int] = {}
    for i in items:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    return {"signals": items, "counts": counts,
            "performance": "Outcome tracking starts with live option prices; dry runs on synthetic data are not scored."}


@router.get("/chains")
def recent_chains(request: Request, limit: int = Query(20, ge=1, le=100)):
    with _orch(request).db.Session() as s:
        rows = s.scalars(select(OptionChain).order_by(OptionChain.created_at.desc()).limit(limit)).all()
        chains = [{"chain_id": r.id, "symbol": r.symbol, "created_at": r.created_at, "spot": r.spot,
                   "spot_session": r.spot_session, "data_type": r.data_type, "expiries": r.expiries} for r in rows]
    return {"chains": chains, "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds")}
