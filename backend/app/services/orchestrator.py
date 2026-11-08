"""Master Orchestrator (plan sections 3, 4.2 and 19).

The orchestrator is code, not an LLM. It fixes the input snapshot, runs the
deterministic engines and quality gates, dispatches the research agents in
parallel with timeouts, verifies their output, applies the rating rules and
stores a reproducible report. It never overrides a failed gate to produce a
complete-looking report.
"""

from __future__ import annotations

import concurrent.futures as cf
import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select

from .. import __version__
from ..agents.llm import LLMError, LLMUnavailable, StructuredLLM
from ..agents.research import AGENTS, build_user_message
from ..analytics import ENGINE_VERSION, FORMULA_VERSIONS
from ..db import AnalysisRun, Database, EvidenceRow, Prediction
from ..providers import MarketDataProvider
from . import instruments as resolver
from .analysis import compute_deterministic
from .market_calendar import add_sessions
from .recommendation import INSUFFICIENT, load_rules, rate
from .snapshots import SNAPSHOT_SCHEMA_VERSION, build_snapshot, canonical_json, content_hash, load_snapshot, save_snapshot
from .verification import verify_agent_output

DATASET_GROUP = {
    "history": "ingest.market_data", "quote": "ingest.market_data", "benchmark": "ingest.market_data",
    "cross_listing": "ingest.market_data", "statements": "ingest.fundamentals", "profile": "ingest.fundamentals",
    "news": "ingest.news", "calendar": "ingest.news", "filings": "ingest.news",
}

STEPS = [
    ("resolve", "Instrument Resolver", "service", "Identify company, ISIN, listing, exchange and currency"),
    ("ingest.market_data", "Market Data adapter", "service", "Daily bars, delayed quote, NIFTY 50 and the other listing"),
    ("ingest.fundamentals", "Financial Statements ingestion", "service", "Annual and quarterly statements, company profile"),
    ("ingest.news", "News and Filings ingestion", "service", "Headlines, results calendar, official filings"),
    ("snapshot", "Snapshot store", "service", "Freeze every input under a content-hash ID"),
    ("analytics", "Calculation and Technical engines", "service", "Ratios, indicators, returns and risk metrics"),
    ("quality", "Data-quality gates", "service", "Deterministic freshness, completeness and consistency checks"),
    *[(f"agent.{a.name}", a.title.replace("the ", "").strip(), "agent", a.description) for a in AGENTS],
    ("verification", "Final Verification", "service", "Check agent citations and numbers against the evidence store"),
    ("recommendation", "Recommendation Engine", "service", "Apply versioned rating rules per horizon"),
    ("report", "Report and prediction log", "service", "Store the report and log ratings for later evaluation"),
]

DISCLAIMER = (
    "Research and decision-support output, not investment advice. Ratings come from a draft, unvalidated rule set "
    "applied to unlicensed development data. Past prices and indicators do not predict future returns. "
    "No orders are placed by this platform."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Orchestrator:
    def __init__(self, db: Database, settings, provider_factory: Callable[[], MarketDataProvider],
                 llm_factory: Callable[[], StructuredLLM], clock: Callable[[], datetime] | None = None,
                 agent_label: Callable[[], str] | None = None,
                 alt_llm_factory: Callable[[], StructuredLLM] | None = None) -> None:
        self.db = db
        self.settings = settings
        self.provider_factory = provider_factory
        self.llm_factory = llm_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.agent_label = agent_label or (lambda: getattr(settings, "agent_model", "unknown"))
        # Opposing debate roles run on a different model when one is configured.
        self.alt_llm_factory = alt_llm_factory
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ run state

    def create_run(self, instrument_id: str, exchange: str) -> str:
        inst = resolver.get_instrument(instrument_id)
        listing = resolver.get_listing(inst, exchange)
        run_id = "run_" + uuid.uuid4().hex[:16]
        activity = [{"id": sid, "name": name, "kind": kind, "description": desc, "status": "queued",
                     "started_at": None, "finished_at": None, "message": None} for sid, name, kind, desc in STEPS]
        activity[0].update(status="completed", started_at=_now(), finished_at=_now(),
                           message=f"{inst['name']} | {inst['isin']} | {listing['exchange']}:{listing['symbol']} | {inst['currency']}")
        with self.db.Session.begin() as s:
            s.add(AnalysisRun(id=run_id, instrument_id=instrument_id, exchange=listing["exchange"], symbol=listing["symbol"],
                              currency=inst["currency"], status="queued",
                              requested_at=self.clock().astimezone(timezone.utc).isoformat(timespec="seconds"), activity=activity,
                              versions={}, warnings=[]))
        return run_id

    def _update(self, run_id: str, **fields) -> None:
        with self._lock, self.db.Session.begin() as s:
            run = s.get(AnalysisRun, run_id)
            for k, v in fields.items():
                setattr(run, k, v)

    def _step(self, run_id: str, step_id: str, status: str, message: str | None = None) -> None:
        with self._lock, self.db.Session.begin() as s:
            run = s.get(AnalysisRun, run_id)
            activity = [dict(a) for a in run.activity]
            for a in activity:
                if a["id"] == step_id:
                    if status == "running" and not a["started_at"]:
                        a["started_at"] = _now()
                    if status not in ("running", "queued"):
                        a["started_at"] = a["started_at"] or _now()
                        a["finished_at"] = _now()
                    a["status"] = status
                    if message is not None:
                        a["message"] = message
            run.activity = activity

    # ------------------------------------------------------------------- workflow

    def execute(self, run_id: str) -> None:
        try:
            self._execute(run_id)
        except Exception as exc:  # never leave a run stuck in "running"
            self._update(run_id, status="failed", completed_at=_now(), error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}")

    def _execute(self, run_id: str) -> None:
        with self.db.Session() as s:
            run = s.get(AnalysisRun, run_id)
            instrument_id, exchange, requested_at = run.instrument_id, run.exchange, run.requested_at
        inst = resolver.get_instrument(instrument_id)
        listing = resolver.get_listing(inst, exchange)
        self._update(run_id, status="running")

        # 1. Fixed input snapshot.
        provider = self.provider_factory()
        started: set[str] = set()

        def progress(key, status, msg=None):
            group = DATASET_GROUP.get(key)
            if group and status == "running" and group not in started:
                started.add(group)
                self._step(run_id, group, "running")

        snapshot = build_snapshot(provider, inst, listing, datetime.fromisoformat(requested_at), progress)
        for group in ("ingest.market_data", "ingest.fundamentals", "ingest.news"):
            keys = [k for k, g in DATASET_GROUP.items() if g == group]
            errs = {k: snapshot["errors"][k] for k in keys if k in snapshot["errors"]}
            got = [k for k in keys if k in snapshot["datasets"]]
            if not got:
                self._step(run_id, group, "failed", "; ".join(f"{k}: {v['message']}" for k, v in errs.items()))
            elif errs:
                self._step(run_id, group, "partial", f"Fetched {', '.join(got)}. Missing: " + "; ".join(f"{k} ({v['message']})" for k, v in errs.items()))
            else:
                self._step(run_id, group, "completed", f"Fetched {', '.join(got)} from {provider.name}.")
        save_snapshot(snapshot, self.settings.data_dir)
        self._step(run_id, "snapshot", "completed", snapshot["snapshot_id"])

        # 2. Deterministic engines and quality gates.
        self._step(run_id, "analytics", "running")
        det = compute_deterministic(snapshot)
        self._step(run_id, "analytics", "completed", f"{len(det['evidence'])} evidence items, engine {ENGINE_VERSION}.")
        dq = det["data_quality"]
        self._step(run_id, "quality", "completed" if dq["status"] in ("good", "degraded") else "partial",
                   f"Status {dq['status']}: {dq['passed']}/{dq['total']} checks passed"
                   + (f"; critical failures: {', '.join(dq['critical_failures'])}" if dq["critical_failures"] else ""))
        self._update(run_id, snapshot_id=snapshot["snapshot_id"], data_status=det["price"]["data_status"],
                     market_data_as_of=(det["price"].get("header") or {}).get("as_of"))

        # 3. Research agents in parallel; 4. verification.
        agents = self._run_agents(run_id, det, inst, listing)
        self._step(run_id, "verification", "running")
        removed = sum(len(a.get("removed", [])) for a in agents.values())
        verified = sum(1 for a in agents.values() if a["status"] == "completed")
        if not verified:
            msg = "No agent output to verify; the report uses deterministic engines only."
        elif removed:
            msg = f"{removed} agent statement(s) removed for unsupported citations or numbers."
        else:
            msg = f"All statements from {verified} agent(s) are traceable to evidence."
        self._step(run_id, "verification", "completed", msg)

        # 5. Rating rules.
        news_labels = [{"evidence_id": i["evidence_id"], "label": i["label"]} for i in agents.get("news_events", {}).get("items", [])]
        rating = rate(det, news_labels)
        rated = {h: v["rating"] for h, v in rating["horizons"].items()}
        self._step(run_id, "recommendation", "completed", ", ".join(f"{h}: {r}" for h, r in rated.items()))

        # 6. Report, evidence, prediction log.
        det_hash = deterministic_hash(det, rating)
        report = self._report(run_id, requested_at, snapshot, det, rating, agents, inst, listing)
        status = "completed"
        if any(a["status"] in ("failed",) for a in agents.values()) or dq["status"] in ("partial", "insufficient"):
            status = "partial"
        summary = {
            "name": inst["name"], "ratings": rated, "data_quality": dq["status"], "data_status": det["price"]["data_status"],
            "price": (det["price"].get("header") or {}).get("price"), "provider": snapshot["provider"]["name"],
        }
        with self._lock, self.db.Session.begin() as s:
            for item in det["evidence"].values():
                s.add(EvidenceRow(run_id=run_id, evidence_id=item["id"], kind=item["kind"], payload=item))
            for h, v in rating["horizons"].items():
                if v["rating"] == INSUFFICIENT or not det["price"].get("last_session"):
                    continue
                bench_close = _bench_close(snapshot, det["price"]["last_session"])
                s.add(Prediction(
                    id=f"{run_id}:{h}", run_id=run_id, instrument_id=inst["instrument_id"], exchange=listing["exchange"],
                    provider_symbol=listing["provider_symbol"], horizon=h, rating=v["rating"], issued_at=report["generated_at"],
                    start_date=det["price"]["last_session"], start_close=det["price"]["last_close"],
                    benchmark_start_close=bench_close, horizon_sessions=v["sessions"],
                    horizon_end_date=add_sessions(datetime.fromisoformat(det["price"]["last_session"]).date(), v["sessions"]).isoformat(),
                    rules_version=rating["rules_version"], status="open", outcome=None))
        self._step(run_id, "report", "completed", "Report stored; ratings logged for outcome tracking.")
        self._update(run_id, status=status, completed_at=_now(), deterministic_hash=det_hash, report=report,
                     summary=summary, versions=report["versions"], warnings=report["data_quality"]["warnings"])

    def _run_agents(self, run_id: str, det: dict, inst: dict, listing: dict) -> dict:
        results: dict[str, dict] = {}
        llm, unavailable = None, None
        if not self.settings.agents_enabled:
            unavailable = "Research agents are disabled by configuration (SRP_AGENTS_ENABLED=false)."
        else:
            try:
                llm = self.llm_factory()
            except LLMUnavailable as exc:
                unavailable = str(exc)
        alt_llm = llm
        if llm is not None and self.alt_llm_factory is not None:
            try:
                alt_llm = self.alt_llm_factory()
            except LLMUnavailable:
                alt_llm = llm

        runnable = []
        for spec in AGENTS:
            base = {"agent": spec.name, "title": spec.title.replace("the ", ""), "version": spec.version,
                    "description": spec.description}
            skip = unavailable or spec.requirement(det)
            if skip:
                results[spec.name] = {**base, "status": "skipped", "reason": skip, "findings": [], "removed": []}
                self._step(run_id, f"agent.{spec.name}", "skipped", skip)
            else:
                runnable.append((spec, base))

        def call(spec, base):
            self._step(run_id, f"agent.{spec.name}", "running")
            user, ids = build_user_message(spec, det, inst, listing)
            started = _now()
            runtime = alt_llm if spec.role == "alternate" else llm
            out = runtime.generate(system=spec.system_prompt(), user=user, schema=spec.schema,
                               max_tokens=self.settings.agent_max_tokens)
            allowed = {i: det["evidence"][i] for i in ids}
            news_ids = {i for i in ids if i.startswith("news.")}
            verified = verify_agent_output(out["output"], allowed, news_ids)
            return {**base, "status": "completed", **verified["output"], "removed": verified["removed"],
                    "model": out.get("model"), "usage": out.get("usage"), "request_id": out.get("request_id"),
                    "evidence_given": len(ids), "started_at": started, "finished_at": _now()}

        if runnable:
            pool = cf.ThreadPoolExecutor(max_workers=len(runnable))
            futures = {pool.submit(call, spec, base): (spec, base) for spec, base in runnable}
            try:
                for fut in cf.as_completed(futures, timeout=self.settings.agent_timeout_seconds):
                    spec, base = futures[fut]
                    try:
                        res = fut.result()
                        results[spec.name] = res
                        n_removed = len(res["removed"])
                        self._step(run_id, f"agent.{spec.name}", "completed",
                                   f"{len(res['findings'])} verified finding(s)" + (f", {n_removed} removed by verification" if n_removed else ""))
                    except LLMUnavailable as exc:
                        results[spec.name] = {**base, "status": "skipped", "reason": str(exc), "findings": [], "removed": []}
                        self._step(run_id, f"agent.{spec.name}", "skipped", str(exc))
                    except (LLMError, Exception) as exc:
                        results[spec.name] = {**base, "status": "failed", "reason": f"{type(exc).__name__}: {exc}", "findings": [], "removed": []}
                        self._step(run_id, f"agent.{spec.name}", "failed", str(exc))
            except cf.TimeoutError:
                for fut, (spec, base) in futures.items():
                    if spec.name not in results:
                        fut.cancel()
                        msg = f"Timed out after {self.settings.agent_timeout_seconds:.0f}s."
                        results[spec.name] = {**base, "status": "failed", "reason": msg, "findings": [], "removed": []}
                        self._step(run_id, f"agent.{spec.name}", "failed", msg)
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
        return results

    # --------------------------------------------------------------------- report

    def _report(self, run_id, requested_at, snapshot, det, rating, agents, inst, listing) -> dict:
        price = det["price"]
        tech = det["technical"]
        labels = {i["evidence_id"]: i for i in agents.get("news_events", {}).get("items", [])}
        news_items = [{**n, "classification": labels.get(n["evidence_id"])} for n in det["news"]["items"]]
        risks = sorted(det["risk"].get("flags", []), key=lambda f: {"high": 0, "medium": 1, "low": 2}[f["severity"]])
        horizons = rating["horizons"]
        return {
            "analysis_run_id": run_id,
            "generated_at": _now(),
            "requested_at": requested_at,
            "market_data_as_of": (price.get("header") or {}).get("as_of"),
            "instrument": {
                "instrument_id": inst["instrument_id"], "name": inst["name"], "isin": inst["isin"],
                "exchange": listing["exchange"], "symbol": listing["symbol"], "currency": inst["currency"],
                "identifier_verified": listing.get("identifier_verified"), "series": listing.get("series"),
                "coverage": inst.get("coverage", "core"),
                "coverage_note": resolver.EXTENDED_NOTE if inst.get("coverage") == "extended" else None,
                "sector": det["profile"].get("sector"),
                "industry": det["profile"].get("industry"), "other_listings": [l["exchange"] for l in inst["listings"] if l["exchange"] != listing["exchange"]],
            },
            "market": det["market"],
            "price": {
                **(price.get("header") or {}),
                "data_status": price["data_status"],
                "last_session": price.get("last_session"),
                "expected_session": price.get("expected_session"),
                "history": price.get("history"),
                "high_52w": tech.get("high_52w"), "low_52w": tech.get("low_52w"),
                "market_cap": det["fundamentals"].get("market_cap"),
                "source": {"provider": snapshot["provider"]["name"], "entitlement": snapshot["provider"]["entitlement"],
                           "retrieved_at": (snapshot["datasets"].get("history") or {}).get("retrieved_at")},
                "corporate_actions": price.get("corporate_actions", []),
                "adjustment_note": "Prices are split-adjusted by the provider; total return uses dividend-adjusted closes.",
            },
            "data_quality": {**det["data_quality"], "gates": det["gates"], "warnings": [g for g in det["gates"] if not g["passed"] and g["severity"] != "info"]},
            "ratings": {k: rating[k] for k in ("rules_version", "rules_sha256", "validation_status", "validation_note", "scoring_method", "thresholds")},
            "horizons": horizons,
            "sub_scores": rating["sub_scores"],
            "summary": {
                "key_risks": risks[:3],
                "abstentions": {h: v["abstention_reasons"] for h, v in horizons.items() if v["rating"] == INSUFFICIENT},
            },
            "fundamentals": det["fundamentals"],
            "technical": tech,
            "returns": det["returns"],
            "risk": det["risk"],
            "news": {**det["news"], "items": news_items},
            "company": det["profile"],
            "agents": agents,
            "forecast": det.get("forecast") or {"status": "unavailable", "reason": "not computed"},
            "notes": det["notes"],
            "versions": {
                "app": __version__, "engine": ENGINE_VERSION, "formulas": FORMULA_VERSIONS,
                "rules": rating["rules_version"], "rules_sha256": rating["rules_sha256"],
                "provider": {"name": snapshot["provider"]["name"], "version": snapshot["provider"]["version"]},
                "agents": {a.name: a.version for a in AGENTS}, "agent_model": self.agent_label(),
                "snapshot_schema": SNAPSHOT_SCHEMA_VERSION, "snapshot_id": snapshot["snapshot_id"],
            },
            "disclaimer": DISCLAIMER,
        }

    # --------------------------------------------------------------------- replay

    def replay(self, run_id: str) -> dict:
        with self.db.Session() as s:
            run = s.get(AnalysisRun, run_id)
            if run is None:
                raise KeyError(run_id)
            if not run.snapshot_id or not run.report:
                raise ValueError("Run has no completed snapshot to replay.")
            snapshot_id, stored_hash, report = run.snapshot_id, run.deterministic_hash, run.report
            stored_versions = dict(run.versions or {})
        snapshot = load_snapshot(snapshot_id, self.settings.data_dir)  # verifies the content hash
        det = compute_deterministic(snapshot)
        stored_labels = [{"evidence_id": i["evidence_id"], "label": i["label"]}
                         for i in report["agents"].get("news_events", {}).get("items", [])]
        rating = rate(det, stored_labels)
        new_hash = deterministic_hash(det, rating)
        stored_ratings = {h: v["rating"] for h, v in report["horizons"].items()}
        replay_ratings = {h: v["rating"] for h, v in rating["horizons"].items()}
        versions = {
            "engine": {"stored": stored_versions.get("engine"), "current": ENGINE_VERSION},
            "rules": {"stored": stored_versions.get("rules_sha256"), "current": rating["rules_sha256"]},
        }
        versions_changed = any(v["stored"] != v["current"] for v in versions.values())
        reproducible = new_hash == stored_hash
        if reproducible:
            explanation = "Recomputed output matches the stored hash exactly."
        elif versions_changed:
            explanation = ("The engine or rule set has changed since this run, so a different hash is expected. "
                           "The input snapshot itself passed its integrity check.")
        else:
            explanation = "Same engine and rules but a different result: investigate before trusting this report."
        return {
            "analysis_run_id": run_id,
            "snapshot_id": snapshot_id,
            "snapshot_integrity": "verified",
            "stored_hash": stored_hash,
            "replay_hash": new_hash,
            "reproducible": reproducible,
            "versions": versions,
            "versions_changed": versions_changed,
            "explanation": explanation,
            "stored_ratings": stored_ratings,
            "replay_ratings": replay_ratings,
            "note": "Calculations, gates and ratings are recomputed from the saved snapshot. Agent narratives are not "
                    "regenerated; their stored news labels are reused as rating inputs.",
            "replayed_at": _now(),
        }

    def list_predictions(self) -> list[dict]:
        with self.db.Session() as s:
            rows = s.scalars(select(Prediction).order_by(Prediction.issued_at.desc())).all()
            return [{c.name: getattr(r, c.name) for c in Prediction.__table__.columns} for r in rows]

    def evaluate_predictions(self, today: str) -> dict:
        from .predictions import evaluate

        hold_band = load_rules()["prediction_evaluation"]["hold_band"]
        with self.db.Session() as s:
            due = s.scalars(select(Prediction).where(Prediction.status == "open", Prediction.horizon_end_date <= today)).all()
            due = [{c.name: getattr(r, c.name) for c in Prediction.__table__.columns} for r in due]
        if not due:
            return {"evaluated": 0, "still_open": 0}
        provider = self.provider_factory()
        bench = provider.history("^NSEI", 5)
        evaluated = still_open = 0
        cache: dict[str, list] = {}
        for p in due:
            bars = cache.setdefault(p["provider_symbol"], provider.history(p["provider_symbol"], 5))
            outcome = evaluate(p, bars, bench, hold_band)
            if outcome is None:
                still_open += 1
                continue
            with self._lock, self.db.Session.begin() as s:
                row = s.get(Prediction, p["id"])
                row.status, row.outcome = "evaluated", outcome
            evaluated += 1
        return {"evaluated": evaluated, "still_open": still_open}


def _bench_close(snapshot: dict, session: str) -> float | None:
    for b in reversed((snapshot["datasets"].get("benchmark") or {}).get("data") or []):
        if b["date"] <= session and b.get("close"):
            return b["close"]
    return None


def deterministic_hash(det: dict, rating: dict) -> str:
    return content_hash({"det": det, "rating": rating})


__all__ = ["Orchestrator", "deterministic_hash", "canonical_json"]
