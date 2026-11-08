"""Display formatting. Agents must quote these strings verbatim, which lets the
verifier check every number in their prose against the calculation engine."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

CRORE = Decimal(10_000_000)


def _indian_group(int_part: str) -> str:
    if len(int_part) <= 3:
        return int_part
    head, tail = int_part[:-3], int_part[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def indian_number(value, dp: int = 2) -> str:
    d = Decimal(str(value)).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_EVEN)
    sign = "-" if d < 0 else ""
    text = f"{abs(d):.{dp}f}"
    int_part, _, frac = text.partition(".")
    return sign + _indian_group(int_part) + (f".{frac}" if dp > 0 else "")


def inr(value, dp: int = 2) -> str:
    """Rupee amount; amounts of one crore or more are shown in crore."""
    if value is None:
        return "unavailable"
    d = Decimal(str(value))
    sign = "-" if d < 0 else ""
    if abs(d) >= CRORE:
        return f"{sign}₹{indian_number(abs(d) / CRORE, dp)} crore"
    return f"{sign}₹{indian_number(abs(d), dp)}"


def money(value, currency: str, dp: int = 2) -> str:
    """Amount in its own currency. INR uses crore; other currencies use million/billion."""
    if currency == "INR":
        return inr(value, dp)
    if value is None:
        return "unavailable"
    d = Decimal(str(value))
    for scale, word in ((Decimal(10) ** 9, "billion"), (Decimal(10) ** 6, "million")):
        if abs(d) >= scale:
            return f"{currency} {d / scale:,.{dp}f} {word}"
    return f"{currency} {d:,.{dp}f}"


def pct(ratio, dp: int = 2) -> str:
    if ratio is None:
        return "unavailable"
    return f"{Decimal(str(ratio)) * 100:.{dp}f}%"


def times(value, dp: int = 2) -> str:
    if value is None:
        return "unavailable"
    return f"{Decimal(str(value)):.{dp}f}x"


def num(value, dp: int = 2) -> str:
    if value is None:
        return "unavailable"
    return f"{Decimal(str(value)):.{dp}f}"


def fy_label(period_end: str) -> str:
    """Indian fiscal years end on 31 March: 2026-03-31 is FY2026."""
    d = date.fromisoformat(period_end)
    return f"FY{d.year}" if d.month == 3 else f"FY ending {period_end}"


def quarter_label(period_end: str) -> str:
    d = date.fromisoformat(period_end)
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
    if q is None:
        return f"quarter ending {period_end}"
    fy = d.year + 1 if d.month in (6, 9, 12) else d.year
    return f"Q{q} FY{fy}"
