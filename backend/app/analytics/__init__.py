"""Deterministic Financial Calculation and Technical Analytics Engine."""

from . import forecast, fundamentals, indicators, risk_metrics

# Covers the calculation engine, data-quality gates and report-shaping logic. Bump it whenever
# their output can change, so replays of older runs can explain a hash mismatch.
# 0.2.0: statement-currency handling, corporate-action and coverage-tier checks.
# 0.3.0: "1 year" risk metrics need a full year; history-depth check explains recent listings; abstention kinds.
# 0.3.1: negative rupee amounts display as -₹x instead of ₹-x.
# 0.4.0: walk-forward forecast engine (paper mode) added to the deterministic output.
ENGINE_VERSION = "analytics-0.4.0"

FORMULA_VERSIONS = {
    **{f"indicator.{k}": v for k, v in indicators.FORMULAS.items()},
    **{f"risk.{k}": v for k, v in risk_metrics.FORMULAS.items()},
    "fundamentals": fundamentals.FORMULA_VERSION,
    "forecast": forecast.VERSION,
}
