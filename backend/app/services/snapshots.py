"""Fixed input snapshots (plan sections 3.4, 13 and 19.9).

Every analysis run reads exclusively from one snapshot. The snapshot ID is a
content hash, so a saved run can be replayed later and we can prove the inputs
did not change.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..providers import BENCHMARK, DatasetUnavailable, MarketDataProvider

SNAPSHOT_SCHEMA_VERSION = "1"
HISTORY_YEARS = 5


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def content_hash(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_snapshot(
    provider: MarketDataProvider,
    instrument: dict,
    listing: dict,
    requested_at: datetime,
    progress=None,
) -> dict:
    """Fetch every dataset once. Failures are recorded per dataset, never filled in."""
    datasets: dict[str, dict] = {}
    errors: dict[str, dict] = {}
    sym = listing["provider_symbol"]

    def fetch(key: str, fn, *args) -> None:
        if progress:
            progress(key, "running")
        try:
            datasets[key] = {"retrieved_at": _utcnow(), "data": fn(*args)}
            if progress:
                progress(key, "completed")
        except DatasetUnavailable as exc:
            errors[key] = {"kind": "unavailable", "message": str(exc)}
            if progress:
                progress(key, "unavailable", str(exc))
        except Exception as exc:  # provider outage, parsing failure, network error
            errors[key] = {"kind": "error", "message": f"{type(exc).__name__}: {exc}"}
            if progress:
                progress(key, "failed", str(exc))

    fetch("history", provider.history, sym, HISTORY_YEARS)
    fetch("quote", provider.quote, sym)
    fetch("profile", provider.profile, sym)
    fetch("statements", provider.statements, sym)
    fetch("news", provider.news, sym)
    fetch("calendar", provider.calendar, sym)
    fetch("filings", provider.filings, sym)
    fetch("benchmark", provider.history, BENCHMARK["symbol"], HISTORY_YEARS)

    other = [l for l in instrument["listings"] if l["exchange"] != listing["exchange"]]
    if other:
        fetch("cross_listing", provider.history, other[0]["provider_symbol"], 1)
        if "cross_listing" in datasets:
            datasets["cross_listing"]["exchange"] = other[0]["exchange"]
            datasets["cross_listing"]["provider_symbol"] = other[0]["provider_symbol"]

    body = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "requested_at": requested_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "provider": {"name": provider.name, "version": provider.version, "entitlement": provider.entitlement},
        "instrument": instrument,
        "listing": listing,
        "benchmark": BENCHMARK,
        "datasets": datasets,
        "errors": errors,
    }
    return {"snapshot_id": "snap_" + content_hash(body)[:24], **body}


def _path(data_dir: Path, snapshot_id: str) -> Path:
    if not snapshot_id.startswith("snap_") or not snapshot_id[5:].isalnum():
        raise ValueError("invalid snapshot id")
    return data_dir / "snapshots" / f"{snapshot_id}.json"


def save_snapshot(snapshot: dict, data_dir: Path) -> Path:
    path = _path(data_dir, snapshot["snapshot_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(canonical_json(snapshot), encoding="utf-8")
    return path


def load_snapshot(snapshot_id: str, data_dir: Path) -> dict:
    snapshot = json.loads(_path(data_dir, snapshot_id).read_text(encoding="utf-8"))
    body = {k: v for k, v in snapshot.items() if k != "snapshot_id"}
    if "snap_" + content_hash(body)[:24] != snapshot_id:
        raise ValueError(f"Snapshot {snapshot_id} failed its integrity check.")
    return snapshot
