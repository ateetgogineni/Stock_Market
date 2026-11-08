"""Financial-statement arithmetic in Decimal (plan sections 4.4 and 7).

Statement values arrive as floats from the provider; they are converted to
Decimal once, at the boundary, and all ratio arithmetic happens in Decimal.
A metric that cannot be calculated is returned with status "unavailable" or
"not_meaningful" and value None. It is never silently set to zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext

FORMULA_VERSION = "1.0"

# Provider line items differ between companies; the first present name wins.
LINE_ALIASES: dict[str, list[str]] = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income"],
    "ebit": ["EBIT", "Operating Income"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "diluted_eps": ["Diluted EPS"],
    "equity": ["Stockholders Equity", "Common Stock Equity"],
    "total_assets": ["Total Assets"],
    "total_debt": ["Total Debt"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "shares": ["Ordinary Shares Number", "Share Issued"],
    "operating_cash_flow": ["Operating Cash Flow"],
    "capex": ["Capital Expenditure"],
    "free_cash_flow": ["Free Cash Flow"],
}

LINE_TABLE = {
    "revenue": "income", "gross_profit": "income", "operating_income": "income", "ebit": "income",
    "ebitda": "income", "interest_expense": "income", "net_income": "income", "diluted_eps": "income",
    "equity": "balance", "total_assets": "balance", "total_debt": "balance", "current_assets": "balance",
    "current_liabilities": "balance", "cash": "balance", "shares": "balance",
    "operating_cash_flow": "cashflow", "capex": "cashflow", "free_cash_flow": "cashflow",
}


def to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(repr(float(value)))


@dataclass(frozen=True)
class StatementValue:
    key: str
    line_item: str
    freq: str
    period: str
    value: Decimal


@dataclass
class MetricResult:
    metric: str
    value: Decimal | None
    status: str  # ok | unavailable | not_meaningful
    reason: str | None = None
    inputs: list[StatementValue] = field(default_factory=list)
    formula: str = ""
    version: str = FORMULA_VERSION

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class Statements:
    def __init__(self, raw: dict | None) -> None:
        self.raw = raw or {}

    def table(self, freq: str, key: str) -> dict:
        return self.raw.get(freq, {}).get(LINE_TABLE[key], {})

    def periods(self, freq: str, key: str = "revenue") -> list[str]:
        """Period-end dates (newest first) for which `key` has a value."""
        table = self.table(freq, key)
        for name in LINE_ALIASES[key]:
            if name in table:
                return sorted(table[name].keys(), reverse=True)
        return []

    def get(self, freq: str, key: str, period: str) -> StatementValue | None:
        table = self.table(freq, key)
        for name in LINE_ALIASES[key]:
            v = table.get(name, {}).get(period)
            if v is not None:
                return StatementValue(key, name, freq, period, to_decimal(v))
        return None


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"))


def ratio(metric: str, num: StatementValue | None, den: StatementValue | None, formula: str,
          *, den_positive: bool = True, num_abs: bool = False, den_abs: bool = False) -> MetricResult:
    inputs = [x for x in (num, den) if x is not None]
    if num is None or den is None:
        missing = "numerator" if num is None else "denominator"
        return MetricResult(metric, None, "unavailable", f"{missing} not reported", inputs, formula)
    n = abs(num.value) if num_abs else num.value
    d = abs(den.value) if den_abs else den.value
    if d == 0:
        return MetricResult(metric, None, "not_meaningful", "denominator is zero", inputs, formula)
    if den_positive and d < 0:
        return MetricResult(metric, None, "not_meaningful", "denominator is negative", inputs, formula)
    with localcontext() as ctx:
        ctx.prec = 28
        return MetricResult(metric, _q(n / d), "ok", None, inputs, formula)


def growth(metric: str, current: StatementValue | None, prior: StatementValue | None) -> MetricResult:
    formula = "current / prior - 1"
    inputs = [x for x in (current, prior) if x is not None]
    if current is None or prior is None:
        return MetricResult(metric, None, "unavailable", "comparison period not reported", inputs, formula)
    if prior.value <= 0:
        return MetricResult(metric, None, "not_meaningful", "prior-period value is zero or negative", inputs, formula)
    with localcontext() as ctx:
        ctx.prec = 28
        return MetricResult(metric, _q(current.value / prior.value - 1), "ok", None, inputs, formula)


def average_of(a: StatementValue | None, b: StatementValue | None) -> tuple[Decimal | None, list[StatementValue], str | None]:
    """Average of two balance-sheet values; falls back to the ending value with a note."""
    if a is None:
        return None, [], None
    if b is None:
        return a.value, [a], "prior-period balance unavailable; ending balance used instead of the average"
    return (a.value + b.value) / 2, [a, b], None


def ratio_on_average(metric: str, num: StatementValue | None, end: StatementValue | None,
                     start: StatementValue | None, formula: str) -> MetricResult:
    avg, bal_inputs, note = average_of(end, start)
    inputs = ([num] if num else []) + bal_inputs
    if num is None or avg is None:
        return MetricResult(metric, None, "unavailable", "inputs not reported", inputs, formula)
    if avg <= 0:
        return MetricResult(metric, None, "not_meaningful", "average balance is zero or negative", inputs, formula)
    with localcontext() as ctx:
        ctx.prec = 28
        return MetricResult(metric, _q(num.value / avg), "ok", note, inputs, formula)


def matching_prior_year(periods: list[str], period: str, tolerance_days: int = 20) -> str | None:
    """The period that ends roughly one year before `period` (for same-quarter comparisons)."""
    target = date.fromisoformat(period)
    for p in periods:
        delta = (target - date.fromisoformat(p)).days
        if abs(delta - 365) <= tolerance_days:
            return p
    return None


def consecutive_quarters(periods: list[str], count: int = 4) -> list[str] | None:
    """The newest `count` periods if they are consecutive quarters (each 80-100 days apart)."""
    if len(periods) < count:
        return None
    chosen = periods[:count]
    for newer, older in zip(chosen, chosen[1:]):
        gap = (date.fromisoformat(newer) - date.fromisoformat(older)).days
        if not 80 <= gap <= 100:
            return None
    return chosen
