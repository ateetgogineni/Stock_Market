"""Final Verification gate for agent output (plan section 4.16).

Deterministic checks, independent of the narrative:
* every cited evidence ID must exist in the evidence the agent was given;
* facts and calculations must cite evidence;
* every number in a statement must appear in the evidence it cites
  (exactly, or as that value rounded to fewer decimals).
Anything that fails is removed from the report and listed with the reason.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

NUMBER = re.compile(r"\d+(?:,\d+)*(?:\.\d+)?")
SMALL_INT_LIMIT = Decimal(10)


def _places(token: str) -> int:
    return len(token.split(".", 1)[1]) if "." in token else 0


def numbers_in_statement(text: str) -> list[str]:
    """Numbers a claim makes. Digits glued to letters (FY2026, Q2, SMA200, ISINs) are labels, not claims."""
    out = []
    for m in NUMBER.finditer(text or ""):
        if m.start() > 0 and text[m.start() - 1].isalpha():
            continue
        out.append(m.group().replace(",", ""))
    return out


def numbers_in_evidence(items: list[dict]) -> list[str]:
    out = []
    for item in items:
        for field in ("display", "label", "period", "observed_at", "note"):
            val = item.get(field)
            if isinstance(val, str):
                out.extend(m.group().replace(",", "") for m in NUMBER.finditer(val))
    return out


def _supported(token: str, candidates: list[str]) -> bool:
    try:
        t = Decimal(token)
    except InvalidOperation:
        return False
    if _places(token) == 0 and t <= SMALL_INT_LIMIT:
        return True  # small counts ("3 quarters", "two of four")
    dp = _places(token)
    for c in candidates:
        try:
            cv = Decimal(c)
        except InvalidOperation:
            continue
        if cv == t:
            return True
        if dp < _places(c) and cv.quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP) == t:
            return True
    return False


def unsupported_numbers(text: str, cited: list[dict]) -> list[str]:
    candidates = numbers_in_evidence(cited)
    return [tok for tok in numbers_in_statement(text) if not _supported(tok, candidates)]


def _check_claim(text: str, ids: list[str], allowed: dict, require_citation: bool) -> str | None:
    unknown = [i for i in ids if i not in allowed]
    if unknown:
        return f"cites evidence that does not exist: {', '.join(unknown[:5])}"
    if require_citation and not ids:
        return "states a fact or calculation without citing evidence"
    bad = unsupported_numbers(text, [allowed[i] for i in ids])
    if bad:
        return f"contains numbers not found in the cited evidence: {', '.join(bad[:5])}"
    return None


def verify_agent_output(output: dict, allowed: dict, news_ids: set[str] | None = None) -> dict:
    """Return the verified output plus a list of removed items with reasons."""
    removed: list[dict] = []
    findings = []
    for f in output.get("findings", []):
        reason = _check_claim(f.get("statement", ""), f.get("evidence_ids", []), allowed,
                              require_citation=f.get("kind") in ("fact", "calculation"))
        if reason:
            removed.append({"type": "finding", "text": f.get("statement"), "reason": reason})
        else:
            findings.append(f)

    summary = output.get("summary", "")
    bad = unsupported_numbers(summary, list(allowed.values()))
    if bad:
        removed.append({"type": "summary", "text": summary, "reason": f"contains numbers not found in the evidence: {', '.join(bad[:5])}"})
        summary = None

    limitations = []
    for text in output.get("limitations", []):
        if unsupported_numbers(text, list(allowed.values())):
            removed.append({"type": "limitation", "text": text, "reason": "contains numbers not found in the evidence"})
        else:
            limitations.append(text)

    verified = {"summary": summary, "findings": findings, "limitations": limitations}

    if "swot" in output:
        swot = {}
        for key, points in (output.get("swot") or {}).items():
            kept = []
            for p in points:
                reason = _check_claim(p.get("point", ""), p.get("evidence_ids", []), allowed, require_citation=True)
                if reason:
                    removed.append({"type": f"swot.{key}", "text": p.get("point"), "reason": reason})
                else:
                    kept.append(p)
            swot[key] = kept
        verified["swot"] = swot

    if "items" in output:
        items, seen = [], set()
        for it in output.get("items", []):
            eid = it.get("evidence_id")
            if eid not in (news_ids or set()) or eid in seen:
                removed.append({"type": "news_label", "text": eid, "reason": "unknown or duplicate news evidence id"})
                continue
            seen.add(eid)
            items.append(it)
        verified["items"] = items

    return {"output": verified, "removed": removed}
