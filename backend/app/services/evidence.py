"""Evidence and Citation Store (plan sections 6.6 and 12.3).

Every material figure in a report is an evidence item: a source value from the
snapshot, or a calculation that names its formula, version and inputs. Agents
may only cite IDs from this store, and the verifier checks their numbers
against the `display` strings recorded here.
"""

from __future__ import annotations

import re

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class EvidenceStore:
    def __init__(self, snapshot: dict) -> None:
        self.snapshot_id = snapshot["snapshot_id"]
        self.provider = snapshot["provider"]["name"]
        self.datasets = snapshot["datasets"]
        self.items: dict[str, dict] = {}

    def source(self, dataset: str, detail: str | None = None, url: str | None = None) -> dict:
        ds = self.datasets.get(dataset, {})
        out = {"provider": self.provider, "dataset": dataset, "retrieved_at": ds.get("retrieved_at")}
        if detail:
            out["detail"] = detail
        if url:
            out["url"] = url
        return out

    def add(
        self,
        evidence_id: str,
        *,
        kind: str,
        label: str,
        display: str,
        value=None,
        unit: str | None = None,
        period: str | None = None,
        observed_at: str | None = None,
        source: dict | None = None,
        formula: dict | None = None,
        inputs: list[str] | None = None,
        status: str = "ok",
        note: str | None = None,
        currency: str | None = None,
    ) -> str:
        if not ID_RE.match(evidence_id):
            raise ValueError(f"bad evidence id {evidence_id!r}")
        if evidence_id in self.items:
            raise ValueError(f"duplicate evidence id {evidence_id!r}")
        self.items[evidence_id] = {
            "id": evidence_id,
            "kind": kind,  # source | calculation | classification | profile | news | dataset
            "label": label,
            "value": value,
            "display": display,
            "unit": unit,
            "currency": currency,
            "period": period,
            "observed_at": observed_at,
            "status": status,
            "note": note,
            "source": source,
            "formula": formula,
            "inputs": inputs or [],
            "snapshot_id": self.snapshot_id,
        }
        return evidence_id

    def get(self, evidence_id: str) -> dict | None:
        return self.items.get(evidence_id)

    def as_list(self) -> list[dict]:
        return list(self.items.values())
