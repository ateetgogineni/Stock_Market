# AI-Powered Stock Market Research & Intelligence Platform

## Product Requirements, Multi-Agent Architecture & Development Roadmap — Version 2.0

**Document status:** Proposed master plan  
**Primary launch market:** India — NSE and BSE listed equities  
**Expansion markets:** United States, United Kingdom, Europe and Asia  
**Product category:** AI-powered investment research and decision-support platform  
**Core principle:** Evidence first, calculations by deterministic engines, AI for research and explanation, and no recommendation when evidence is insufficient.

---

# 1. Product Vision

Build a professional, AI-powered stock market research and intelligence platform. A user enters a company name, ticker symbol or exchange and receives a structured, source-backed analysis that combines market data, company fundamentals, technical indicators, news, market context, sentiment, risk and model-based forecasts.

The platform should help users understand:

- What is happening with a stock now?
- How financially healthy is the company?
- How has the company performed over time?
- What are the important technical levels and trends?
- What recent events could affect the company?
- What are the bullish, bearish and neutral scenarios?
- What risks could invalidate the analysis?
- How has the platform's forecasting system performed historically?
- What evidence supports the final research rating?

The product is a **research and decision-support system**, not a guaranteed prediction engine or an automated trading system.

## 1.1 Product Principles

1. **Evidence before opinion:** Every material claim should be linked to a source, calculation or model output.
2. **Time-aware data:** Every price, financial figure, news item and analysis must show its relevant date/time and freshness.
3. **No fabricated data:** Missing data stays missing. The platform must never invent values to complete a report.
4. **Deterministic finance:** Ratios, returns, indicators, valuation calculations and portfolio metrics must be calculated by tested code, not guessed by an LLM.
5. **Explainable conclusions:** Every rating must show supporting evidence, opposing evidence, assumptions and risks.
6. **Honest uncertainty:** Confidence must be measurable and calibrated. It must not be presented as a probability of profit unless that probability has been statistically validated.
7. **Modular architecture:** Agents and data providers can be replaced without rewriting the entire platform.
8. **Human control:** No trade execution, broker order placement or money movement in the initial product.
9. **Compliance by design:** The product must be reviewed for applicable securities regulations before public release or monetisation.
10. **Measure performance:** Forecasts and recommendations must be recorded and evaluated against what actually happened.

# 2. Product Scope

## 2.1 Initial MVP Scope

Launch with Indian listed cash-equity research for NSE and BSE. Start with a clearly defined supported-universe list rather than claiming complete coverage before data availability and licensing are confirmed.

The MVP must include:

- Company and ticker search with exchange selection.
- Canonical instrument identification and duplicate-listing handling.
- Latest available price, market status and data freshness label.
- Historical price charts and volume.
- Company profile and business overview.
- Quarterly and annual financial statements and key ratios.
- Technical indicators and deterministic signal calculations.
- Company news and official corporate announcements.
- Macro and sector context.
- Risk analysis.
- Explainable research rating: BUY / HOLD / SELL / INSUFFICIENT DATA.
- Source citations and a timestamped analysis report.
- Watchlist and saved analysis history.
- Basic stock comparison.
- Prediction log and initial offline backtesting framework.

## 2.2 Post-MVP Expansion

- User-maintained portfolio tracking.
- Portfolio exposure and concentration analytics.
- Price, event, news and indicator alerts.
- Advanced backtesting and strategy experiments.
- Prediction-performance dashboard.
- Expanded global equities coverage.
- More asset types, only after data and business rules are validated.
- Optional broker connectivity in a separate, approval-controlled future phase.

## 2.3 Explicitly Out of Scope for Initial Release

- Automatic trading or automatic order placement.
- Guaranteed-return claims.
- Unverified real-time prices presented as live.
- Personalised investment advice or recommended portfolio allocation without required regulatory review and permissions.
- Options strategies, derivatives execution, crypto or other asset classes until separately scoped and validated.
- A large collection of agents that all repeat the same research or calculations.

# 3. User Journey

1. User enters a company name, ticker or ISIN.
2. The Instrument Resolution service identifies the exact company, listing, exchange, currency and security type.
3. The user confirms the intended listing when multiple matches exist.
4. The platform creates an analysis run with a fixed data snapshot and an `as_of` timestamp.
5. Data services fetch prices, fundamentals, filings, corporate actions, news and market context.
6. Data-quality checks validate the inputs before analysis begins.
7. Specialist agents and deterministic analytics services work in parallel where appropriate.
8. The prediction service creates testable forecast scenarios, if its model is approved and sufficient data exists.
9. The Risk and Verification services challenge the analysis and identify missing or conflicting evidence.
10. The Recommendation Engine applies explicit rating rules and can return INSUFFICIENT DATA.
11. The dashboard displays the report, evidence, limitations, agent activity and source timestamps.
12. The prediction is stored so that its result can later be evaluated against actual market outcomes.

# 4. Multi-Agent System

## 4.1 Architecture Rule

Use one Master AI Orchestrator and a set of specialised capabilities. Do not force every capability to run for every request. The orchestrator chooses the relevant agents based on the security, requested analysis, available data and user-selected time horizon.

Agents should return structured outputs rather than long, unstructured essays. The dashboard and recommendation engine should consume validated structured data.

## 4.2 Agent 1 — Master AI Orchestrator

**Purpose:** Own the analysis workflow and produce the consolidated report.

Responsibilities:

- Receive the user's company, ticker, exchange and analysis request.
- Call the Instrument Resolution service.
- Build an analysis plan based on requested scope and available data.
- Dispatch independent research tasks in parallel where safe.
- Enforce timeouts, retry policies and API budgets.
- Collect structured agent results.
- Detect missing, stale, conflicting or unsupported results.
- Ask the relevant agent or data service to re-check important discrepancies.
- Pass outputs to Risk, Verification and Recommendation services.
- Produce the final user-facing report with supporting evidence.
- Return INSUFFICIENT DATA when hard quality gates fail.

The orchestrator must not invent financial figures, calculate ratios from prose or override a failed data-quality gate merely to produce a complete-looking report.

## 4.3 Agent 2 — Company Research Agent

Responsibilities:

- Company background, business model and operating segments.
- Products, services, geography and customer concentration where disclosed.
- Industry classification and competitive environment.
- Competitors and market position, where supported by sources.
- Management and governance developments.
- Material strategic announcements, acquisitions, expansions and contracts.
- SWOT-style summary grounded in evidence.

Output must distinguish company-reported facts, third-party estimates and AI interpretation.

## 4.4 Agent 3 — Financial Analysis Agent

Responsibilities:

- Analyse income statement, balance sheet and cash-flow statement.
- Track revenue, gross profit, operating profit, EBITDA, net profit and margins.
- Track EPS, diluted EPS where available, and share-count changes.
- Analyse assets, liabilities, cash, debt and debt maturity where available.
- Calculate operating cash flow, free cash flow and cash conversion.
- Calculate ROE, ROCE, ROA, debt/equity, interest coverage, P/E and P/B where meaningful.
- Analyse dividend history, payout and yield.
- Compare quarterly, annual and trailing-twelve-month performance.
- Highlight one-off items, exceptional items, restatements and accounting-quality concerns.
- Compare relevant metrics with peers using consistent periods and definitions.

All numeric calculations must use the Financial Calculation Engine. The agent explains the results; it does not independently invent or recalculate source figures in natural language.

## 4.5 Agent 4 — Market Data Agent

Responsibilities:

- Fetch current, delayed or end-of-day prices, depending on licensed entitlement.
- Fetch OHLCV, bid/ask or market depth only when entitlement supports it.
- Track opening price, previous close, high, low, volume and turnover.
- Track market capitalisation and shares outstanding with their source dates.
- Retrieve historical bars and corporate-action-adjusted series.
- Handle exchange trading sessions, holidays, circuit limits and suspensions where data is available.
- Distinguish pre-market, regular session and post-market data where supported.
- Display exchange, currency, source, timestamp, delay status and last successful refresh.

This agent uses provider adapters and must never label delayed or end-of-day data as real-time.

## 4.6 Agent 5 — Technical Analysis Agent

Responsibilities:

- Analyse price and volume trends across supported timeframes.
- Calculate SMA, EMA, RSI, MACD, Bollinger Bands, VWAP and ATR.
- Identify trend direction, momentum and volatility regimes.
- Calculate support and resistance zones using disclosed methods.
- Identify potential breakout or breakdown conditions.
- Detect abnormal volume and price gaps.
- Provide scenario-based technical levels and invalidation points.

Indicator calculations must come from a tested technical-analysis service. The agent explains signal meaning and limitations. A technical indicator is not, by itself, a recommendation.

## 4.7 Agent 6 — Market, Sector and Macro Research Agent

Responsibilities:

- Monitor relevant domestic and global indices.
- Analyse sector performance and peer-group trends.
- Track interest rates, inflation, currency movements and important economic releases.
- Track commodities such as oil, gold or other inputs when relevant to the company.
- Explain plausible transmission paths from macro events to the company.
- Separate broad market correlation from demonstrated company-specific impact.

Only include indicators relevant to the selected company and market.

## 4.8 Agent 7 — News and Corporate Events Agent

Responsibilities:

- Retrieve company announcements, exchange filings and credible financial news.
- Monitor results, management changes, acquisitions, litigation, regulatory events, contracts and product launches.
- Detect duplicate or syndicated articles.
- Classify items as positive, negative, neutral or uncertain.
- Explain the likely relevance and possible time horizon of the event.
- Show original source, publication time, event date and link.
- Give official filings and company disclosures priority over commentary.

The agent must not treat a news headline as verified fact without checking the article or primary source. Rumours must be labelled as unverified.

## 4.9 Agent 8 — Sentiment and Ownership Flows Agent

Responsibilities:

- Analyse analyst ratings and target prices where licensed and available.
- Track institutional, mutual-fund, foreign-investor and promoter activity where reliable public data exists.
- Track insider transactions where officially disclosed.
- Analyse public financial-media and social discussions only when permitted by the source's terms.
- Identify sentiment direction, disagreement and unusual changes.
- Separate verified ownership disclosures from commentary and online speculation.

Sentiment is contextual evidence, not a substitute for company fundamentals or price data.

## 4.10 Agent 9 — Quantitative Forecasting Agent

Responsibilities:

- Generate short-, medium- and long-horizon scenarios only for horizons the model has been trained and evaluated to support.
- Use historical prices, volatility, fundamentals, technical features, news features and market-regime variables when validated.
- Produce forecast distributions or ranges rather than one unsupported exact target.
- Generate bullish, base and bearish scenarios.
- Provide assumptions, important catalysts and invalidation conditions.
- Report model version, training window, evaluation window and forecast timestamp.
- Abstain when inputs are incomplete, the security is illiquid or the current market regime is outside the validated range.

Do not use an LLM alone to guess future prices. LLM output can explain model results but must not replace a tested forecasting model.

## 4.11 Agent 10 — Risk Management Agent

Responsibilities:

- Identify market, company, valuation, liquidity, leverage, governance, regulatory and geopolitical risks.
- Calculate volatility, drawdown, beta and downside scenarios where data supports them.
- Identify concentration and correlation risks for portfolio analytics.
- Review downside assumptions and risk/reward calculations.
- Flag low liquidity, extreme volatility, data gaps and event risk.
- Provide risk warnings and possible invalidation levels where statistically and technically supported.

Stop-loss and position-sizing figures must be labelled as analytical examples, not personalised instructions, unless the product has been appropriately authorised to provide such advice.

## 4.12 Agent 11 — Portfolio Analytics Agent

**Initial release:** watchlist and user-entered holdings analytics only.

Responsibilities:

- Allow users to enter holdings, quantity, average cost and transaction dates.
- Calculate cost basis, current value, realised and unrealised P/L.
- Account for splits, bonuses, dividends and other corporate actions when supported.
- Display allocation by stock, sector, market and currency.
- Highlight concentration, correlation and volatility exposure.
- Compare portfolio performance with a user-selected benchmark.
- Show data gaps and stale holding prices.

Do not generate personalised allocation or buy/sell instructions from a user's personal circumstances in the MVP. Any move into personalised advisory services requires a separate compliance assessment.

## 4.13 Agent 12 — Stock Comparison Capability

This capability may be implemented as a deterministic comparison service with AI explanation rather than a separately running agent.

Responsibilities:

- Compare selected companies over matching financial periods.
- Normalise currencies, units and accounting definitions where possible.
- Compare growth, profitability, leverage, cash flow, valuation, dividends and price performance.
- Use sector-appropriate metrics; do not compare unlike business models with one universal score.
- Identify where data is missing or not comparable.
- Produce a side-by-side table and evidence-backed explanation.

## 4.14 Agent 13 — Backtesting and Model Evaluation Agent

Responsibilities:

- Run historical simulations using point-in-time data.
- Prevent look-ahead bias and survivorship bias.
- Include transaction costs, taxes where relevant, slippage and realistic execution assumptions.
- Account for corporate actions, delisted securities and trading halts where possible.
- Use walk-forward validation and a final untouched holdout period.
- Compare strategies with appropriate benchmarks.
- Calculate CAGR, volatility, maximum drawdown, Sharpe ratio, Sortino ratio, turnover, win rate, average win/loss and benchmark-relative returns.
- Report sample size and statistical limitations.
- Store backtest configuration, dataset version, code version and model version for reproducibility.

Backtest results must never be presented as a guarantee of future performance.

## 4.15 Agent 14 — Monitoring, Alerts and Prediction Tracking

Responsibilities:

- Monitor watchlist and portfolio securities at configured intervals allowed by provider entitlements.
- Trigger price, percentage-move, volume, news, filing and indicator alerts.
- Detect when a previous forecast reaches its horizon or invalidation condition.
- Compare forecast with realised outcome.
- Track directional accuracy, range coverage and calibration over time.
- Notify users about material changes without generating unnecessary duplicate alerts.
- Maintain a complete history of sent alerts and prediction outcomes.

## 4.16 Agent 15 — Final Verification and Quality Gate

Responsibilities:

- Verify company, ticker, exchange, ISIN and currency.
- Check data timestamps and freshness thresholds.
- Confirm that cited sources support the statements made.
- Check calculation outputs against source data and calculation version.
- Detect conflicting values from providers.
- Check that financial periods and currencies are comparable.
- Identify stale, missing, adjusted or restated data.
- Check that forecast model is approved for the instrument and horizon.
- Ensure uncertainty and contradictory evidence are displayed.
- Block unsupported recommendations.

This service must operate independently of the narrative generated by the Master Agent. Critical checks should be deterministic rules, not only another LLM opinion.

# 5. Recommendation Framework

## 5.1 Rating Options

The system must return exactly one primary status:

- **BUY:** Evidence meets the approved positive-signal rules for the selected horizon.
- **HOLD:** Evidence is mixed, neutral or does not meet BUY/SELL thresholds.
- **SELL:** Evidence meets the approved negative-signal rules for the selected horizon.
- **INSUFFICIENT DATA:** Required data, source quality or model validation is inadequate.

A HOLD rating must not be used as a fallback when critical data is missing. In that situation, use INSUFFICIENT DATA.

## 5.2 Horizon-Specific Ratings

Do not combine all investment horizons into one vague rating. Display separate ratings when supported:

- Short term: define the exact model horizon, for example 1–20 trading sessions.
- Medium term: define the exact model horizon, for example 1–6 months.
- Long term: define the exact model horizon, for example 6–24 months.

These are proposed product defaults. Final horizons must match the data frequency and model validation results.

## 5.3 Evidence-Based Scoring

Create transparent sub-scores, for example:

- Fundamental quality.
- Valuation.
- Technical condition.
- Earnings and business momentum.
- News and event risk.
- Market and sector conditions.
- Forecast model output.
- Financial and market risk.
- Data quality.

Weights must be configurable by sector and investment horizon, tested historically and documented. Avoid a single universal formula for banks, insurers, manufacturers, software companies and other very different business models.

The platform must show the factors that contributed to the result and explain which signals disagreed.

## 5.4 Confidence and Uncertainty

Do not display an arbitrary 90% AI confidence score. Separate:

- **Data quality:** completeness, freshness and source reliability.
- **Model calibration:** how frequently historical forecast intervals contained actual outcomes.
- **Signal agreement:** how strongly independent evidence sources align.
- **Forecast uncertainty:** width of the projected distribution or range.

A confidence label can be shown only when its definition is documented and empirically validated. Never describe it as a probability of profit unless that is exactly what the evaluated model estimates.

## 5.5 Recommendation Output Contract

Every recommendation must contain:

1. Rating and horizon.
2. Generated timestamp and market-data `as_of` timestamp.
3. Instrument, exchange and currency.
4. Data-quality status.
5. Summary of supporting evidence.
6. Summary of contradictory evidence.
7. Fundamental assessment.
8. Technical assessment.
9. News and market context.
10. Forecast scenario ranges, if model-approved.
11. Key risks and invalidation conditions.
12. Source citations and calculation/model versions.
13. Reasons for abstention, where applicable.

# 6. Data Sources and Data Engineering

## 6.1 Provider Strategy

Build provider adapters so that market-data, financial-data, news and macro providers can be changed without changing the agent logic.

Potential source categories:

- Official exchange market-data feeds and authorised vendors.
- Company filings and official corporate announcements.
- Regulatory filings and company investor-relations material.
- Licensed financial-statement and market-data APIs.
- Reputable, licensed financial-news sources.
- Official central-bank and government macroeconomic datasets.
- Licensed analyst-consensus and ownership datasets, if required.

Provider selection must be based on exchange coverage, latency, historical depth, reliability, redistribution rights, commercial-use terms, API limits and total cost. Do not assume a provider covers every Indian or international exchange just because it offers a stock API.

## 6.2 Indian Market Data Requirements

- Confirm NSE/BSE data access and permitted display/redistribution rights with the exchange or authorised vendors.
- Confirm whether each feed is real-time, delayed, snapshot or end-of-day.
- Store the source, exchange, timestamp and entitlement type with each quote.
- Keep exchange data licences and user display permissions documented.
- Do not scrape exchange pages or unofficial websites as a production substitute for a licensed feed.

## 6.3 Global Market Data Requirements

For each country, define:

- Supported exchanges and instrument universe.
- Trading hours, timezone and holidays.
- Currency and FX conversion source.
- Price-adjustment and corporate-action methodology.
- Market-data delay and redistribution terms.
- Financial reporting periods and accounting standards.
- Regulatory filing sources.

## 6.4 Data Freshness Policy

Define configurable freshness rules by data type. Example policy to be finalised with provider contracts:

| Data type | Required metadata | UI behaviour when stale |
|---|---|---|
| Intraday quote | Exchange timestamp, received timestamp, delay flag | Show stale/delayed badge; suppress live label |
| End-of-day price | Trading date, close timestamp | Show last completed session |
| Financial statement | Fiscal period, filing date, source | Show period and filing date |
| News | Published time, event time, source | Show both times where different |
| Macro data | Observation period, release date, source | Do not imply current-day measurement |
| Forecast | Model version, generated time, input snapshot | Expire or mark overdue after horizon |

## 6.5 Data Normalisation

Create a canonical data model for:

- Company.
- Instrument/security.
- Exchange listing.
- ISIN or equivalent stable identifier.
- Currency.
- Price bar and quote.
- Corporate action.
- Financial statement and financial metric.
- News article and corporate filing.
- Economic indicator.
- Analyst estimate.
- Forecast and recommendation.
- User watchlist and holding.

Never identify a security from ticker text alone. Tickers can be reused or differ between exchanges. Resolve the company and listing using stable identifiers and explicit exchange context.

## 6.6 Source Provenance

Every displayed material figure should store:

- Provider/source name.
- Original source URL or source identifier.
- Retrieved timestamp.
- Source observation timestamp or reporting period.
- Currency and unit.
- Transformation or calculation applied.
- Data version/snapshot ID.

# 7. Financial Calculation and Analytics Engine

Build a deterministic analytics service, primarily in Python, with unit tests and documented formulas.

It should calculate:

- Percentage returns and total returns where dividends are included.
- Moving averages, RSI, MACD, Bollinger Bands, VWAP and ATR.
- Volatility, beta and drawdown.
- Financial ratios and growth rates.
- Valuation metrics and peer comparisons.
- Portfolio valuation and performance.
- Forecast errors and backtest statistics.

Requirements:

- Use decimal-safe handling for money and explicit precision rules.
- Preserve currency, unit and period metadata.
- Adjust price series consistently for splits and other corporate actions.
- Test calculations against known examples and independent reference calculations.
- Version formulas so old reports remain reproducible.
- Return `null` or an explicit unavailable state when a metric cannot be calculated; do not silently substitute zero.
- Make financial-sector and other sector-specific metrics configurable.

# 8. Forecasting and Model Governance

## 8.1 Model Approach

Use a model registry and a controlled evaluation process. Begin with simple baselines before adopting complex machine-learning models.

Possible model families to evaluate:

- Naive and historical-return baselines.
- Moving-average and momentum baselines.
- Regression and tree-based models.
- Volatility and time-series models.
- Probabilistic or quantile forecasting.
- NLP-derived event features, only after source and leakage controls.

Do not assume that a complex model is better. Promote a model only when it improves out-of-sample performance after costs and remains stable across relevant regimes.

## 8.2 Validation Rules

- Use time-based train/validation/test splits.
- Use walk-forward evaluation.
- Prevent look-ahead and survivorship bias.
- Prevent data leakage from future filings, revised data or news timestamps.
- Include transaction costs, slippage and applicable taxes in strategy simulations.
- Evaluate by stock, sector, market regime and time horizon.
- Keep a final holdout dataset untouched during model development.
- Compare with simple baselines and relevant market benchmarks.
- Monitor drift and retrain only through a documented approval process.

## 8.3 Forecast Metrics

Track metrics appropriate to the forecast type:

- Directional accuracy.
- Mean absolute error and root mean square error where suitable.
- Forecast interval coverage and width.
- Calibration error for probabilistic outputs.
- Benchmark-relative return for simulated strategies.
- Maximum drawdown and tail-loss measures.
- Sample size and confidence intervals for performance statistics.

Do not show a single model-accuracy percentage without explaining the metric, period, instrument universe and sample size.

## 8.4 Model Registry

For every production model, store:

- Model ID and version.
- Model family and feature set.
- Training and validation windows.
- Supported securities and horizons.
- Performance metrics.
- Known limitations.
- Approval date and owner.
- Deployment and rollback history.

# 9. Backtesting Framework

The backtesting system must support:

- Historical entry and exit rules.
- Long-only strategy testing initially.
- Rebalancing frequency and position limits.
- Benchmark comparison.
- Brokerage, taxes, exchange fees and slippage assumptions where applicable.
- Corporate actions and dividends.
- Liquidity and execution constraints.
- Delisted securities and survivorship-bias controls where data is available.
- Walk-forward testing and out-of-sample reports.

Required report metrics:

- Starting and ending capital.
- CAGR and cumulative return.
- Annualised volatility.
- Maximum drawdown and recovery time.
- Sharpe and Sortino ratios, with assumptions shown.
- Win rate and average win/loss.
- Turnover and estimated trading costs.
- Benchmark-relative performance.
- Number of trades and sample period.

A strategy must not be promoted to production based only on an attractive backtest. Require out-of-sample evidence, risk review and ongoing paper monitoring.

# 10. Portfolio, Watchlist and Alerts

## 10.1 Watchlists

- Create multiple named watchlists.
- Add/remove securities.
- Display latest available price and daily move.
- Display rating changes and key events.
- Store watchlist history and alert preferences.

## 10.2 Portfolio Tracking

- Let users enter holdings manually in the MVP or import a supported statement format in a later phase.
- Store quantity, average cost, transaction dates and transaction costs where supplied.
- Calculate holdings value and unrealised/realised P&L.
- Reflect supported corporate actions and dividends.
- Show asset, sector, currency and single-stock concentration.
- Show historical portfolio performance only where complete data exists.
- Clearly label user-entered versus imported data.

Portfolio analytics should be informational in the initial release, not a personalised advisory engine.

## 10.3 Alerts

Support configurable alerts for:

- Price reaching a level.
- Percentage move over a defined period.
- Unusual volume.
- Important company news or official filings.
- Rating change.
- Technical condition change.
- Forecast horizon completion or invalidation.

Support in-app alerts first. Add email, push or messaging channels only after consent, delivery controls and privacy requirements are implemented. Include alert deduplication and quiet hours.

# 11. Dashboard and UX Requirements

## 11.1 Main Navigation

- Overview.
- Stocks / Search.
- Watchlists.
- Portfolio.
- Compare.
- Market Overview.
- Alerts.
- Prediction Performance.
- Saved Reports.
- Settings and Data Sources.

Hide unfinished modules until they are ready for use.

## 11.2 Stock Analysis Page

### A. Instrument Header

- Company name and logo where licensed.
- Symbol, exchange, ISIN and currency.
- Latest available price and absolute/percentage change.
- Market status.
- Price data status: live, delayed, snapshot or end-of-day.
- Source and last-updated timestamp.
- 52-week high/low and market capitalisation, with relevant dates.

### B. Analysis Summary

- Primary rating and horizon.
- Data-quality status.
- Key reasons for the rating.
- Strongest opposing signal.
- Key risks.
- Forecast range/scenarios only when validated.

### C. Price and Technical Chart

- Candlestick and line chart.
- Period filters: 1D, 1W, 1M, 3M, 6M, 1Y, 5Y and MAX where data exists.
- Volume.
- Optional SMA, EMA, RSI, MACD, Bollinger Bands, VWAP and ATR overlays/panels.
- Support/resistance zones and explanation of method.
- Corporate-action-adjustment information.

### D. Fundamentals

- Revenue, profit and margin trends.
- Cash flow and balance-sheet summary.
- Debt and liquidity.
- Financial ratios.
- Quarterly and annual comparisons.
- Peer comparison with period and source context.

### E. Company and Sector Research

- Business overview.
- Segment and geography breakdown where disclosed.
- Industry trends.
- Competitors.
- Relevant macro factors.

### F. News and Events

- Official announcements first.
- Recent news with date, source and link.
- Positive/negative/neutral/uncertain labels.
- AI summary clearly marked as generated.
- Event impact explanation and confidence limitations.

### G. Forecast and Scenarios

- Short-, medium- and long-horizon sections only where approved.
- Bull/base/bear scenarios.
- Expected range, not false precision.
- Model name/version and as-of timestamp.
- Assumptions, catalysts and invalidation conditions.
- Historical performance of the model for the relevant horizon.

### H. Risk Analysis

- Volatility and drawdown.
- Liquidity risk.
- Balance-sheet and earnings risks.
- Valuation risks.
- Governance and event risks.
- Data/model limitations.

### I. Agent and Data Activity

- Agent/service name.
- Queued, running, completed, failed or skipped status.
- Short task description.
- Data source and timestamp.
- Warning or missing-data reason.

## 11.3 Comparison Page

Allow users to compare 2–5 securities, with:

- Comparable period and currency.
- Revenue/profit growth.
- Profitability and returns.
- Debt and cash flow.
- Valuation.
- Price performance.
- Risk and liquidity.
- Data coverage and non-comparable metrics highlighted.

## 11.4 Prediction Performance Page

Display actual historical prediction outcomes, not promotional claims:

- Number of forecasts issued.
- Forecasts by horizon and rating.
- Directional accuracy.
- Forecast range coverage.
- Calibration and error metrics.
- Performance by sector and market regime.
- Model version and evaluation period.
- Failed or withdrawn forecasts and their reasons.

# 12. Technical Architecture

## 12.1 Recommended Starting Architecture

Start with a modular monolith plus background workers and a separate analytics service. Do not begin with many microservices. Extract services only when scale, deployment independence or reliability requires it.

### Frontend

- React / Next.js with TypeScript.
- Responsive desktop, tablet and mobile layouts.
- Interactive charts with a licensed or appropriately permitted charting library.
- Accessible components and clear data-status indicators.

### Backend API

- Python FastAPI for core APIs and analytics integration, or a TypeScript backend if the development team has stronger expertise there.
- REST endpoints for normal requests.
- WebSocket or server-sent events for analysis progress and permitted streaming updates.
- Strong request validation and typed response schemas.

### AI Orchestration

- OpenAI Agents SDK or a comparable framework when code-first orchestration, tool permissions, guardrails and tracing are required.
- Keep the agent runtime behind an internal service interface so the provider can be changed.
- Use bounded tools and structured output schemas.
- Keep API keys and data-provider credentials on the server only.

### Analytics

- Python service for financial calculations, technical indicators, forecasting and backtesting.
- Versioned formula library and tests.
- Separate production inference from model training jobs.

### Storage

- PostgreSQL for users, instruments, financial data, analysis runs and recommendations.
- TimescaleDB or partitioned PostgreSQL tables for time-series data, subject to workload testing.
- Redis for caching, job coordination and rate-limit counters.
- Object storage for report snapshots, raw vendor files and model artifacts where permitted.

### Background Jobs

- Task queue for data ingestion, research runs, alerts, backtests and evaluation.
- Idempotent jobs and retry policies.
- Dead-letter handling for repeated failures.
- Scheduled refreshes aligned with provider entitlements and market sessions.

### Observability

- Centralised logs, metrics and traces.
- Agent run IDs and correlation IDs.
- Provider latency, error and quota monitoring.
- Cost and token usage tracking.
- Alerts for data outages and abnormal agent behaviour.

## 12.2 High-Level System Flow

```text
Web / Mobile Dashboard
          |
          v
     API Gateway
          |
          v
Instrument Resolver ---- User / Watchlist / Portfolio Services
          |
          v
   Master Orchestrator
          |
   +------+------+----------------+----------------+
   |             |                |                |
   v             v                v                v
Market Data   Fundamentals     News & Events   Macro / Sentiment
Adapters      + Calculations   Research        Research
   |             |                |                |
   +-------------+----------------+----------------+
                         |
                         v
              Technical Analytics Engine
                         |
                         v
                Forecasting Service
                         |
                         v
             Risk & Verification Gates
                         |
                         v
               Recommendation Engine
                         |
                         v
              Report / Dashboard API
                         |
                         v
          Prediction Log & Outcome Tracker
```

## 12.3 Core Internal Services

- Instrument Resolver.
- Provider Adapter Registry.
- Market Data Ingestion.
- Financial Statements Ingestion.
- News and Filings Ingestion.
- Corporate Actions Service.
- Financial Calculation Engine.
- Technical Analytics Engine.
- Forecasting and Model Registry.
- Backtesting Engine.
- Portfolio Analytics.
- Alert Scheduler and Dispatcher.
- Recommendation Engine.
- Evidence and Citation Store.
- Audit and Observability Service.

# 13. API and Data Contract Requirements

Every analysis run should have a stable run ID and a fixed input snapshot.

Minimum `AnalysisRun` fields:

```json
{
  "analysis_run_id": "unique-id",
  "instrument_id": "canonical-instrument-id",
  "exchange": "NSE",
  "currency": "INR",
  "requested_at": "ISO-8601 timestamp",
  "market_data_as_of": "ISO-8601 timestamp",
  "data_status": "live|delayed|end_of_day|stale|unavailable",
  "status": "queued|running|completed|partial|failed",
  "model_versions": {},
  "provider_snapshot_ids": [],
  "recommendation": {},
  "warnings": []
}
```

Minimum specialist result fields:

- Agent/service name and version.
- Status: completed, partial, failed or skipped.
- Structured findings.
- Numeric values with units and periods.
- Evidence/source references.
- Data timestamps.
- Assumptions and limitations.
- Warnings and missing fields.

Do not pass large raw datasets between LLM agents when a storage reference or compact structured result is sufficient.

# 14. Security, Privacy and Reliability

- Store secrets in a managed secret store; never expose API keys in frontend code.
- Encrypt data in transit and at rest.
- Use role-based access control and least-privilege service accounts.
- Separate user data by tenant/account.
- Protect APIs from abuse with authentication, rate limits and request validation.
- Keep audit logs for analysis generation, data changes and administrative actions.
- Define data retention and deletion rules.
- Minimise collection of personal information.
- Validate file uploads and imported portfolio statements.
- Protect against prompt injection in news articles, filings and external web content; treat retrieved content as untrusted data, never as instructions.
- Use strict tool allowlists for agents.
- Prevent agents from placing trades or accessing broker execution tools.
- Add provider circuit breakers, retries, caching and graceful degradation.
- Clearly show when a module is unavailable rather than displaying stale content as current.
- Maintain backups and test restoration.

# 15. Compliance and Product Governance

This section is a development requirement, not legal advice.

Before public release, subscription, paid reports or personalised features, obtain advice from qualified Indian securities-regulatory counsel on whether the product's activities fall within Research Analyst, Investment Adviser or other applicable regulatory requirements. The answer can depend on what the platform actually publishes, whether it charges users, whether recommendations are personalised and how services are delivered.

Build the following controls from the beginning:

- Disclosures for data sources, methodology, model limitations and conflicts of interest.
- Clear separation between general research and personalised advice.
- Versioned and timestamped recommendation records.
- Retention of research rationale and source evidence.
- User-facing risk warnings and complaint/support process where required.
- Review of advertising and performance claims.
- No guaranteed-return language.
- No undisclosed sponsored rankings or paid promotion of securities.
- No trading or market-manipulation functionality.
- Regional legal review before launching in each non-Indian market.

Maintain a compliance checklist that is reviewed against the latest SEBI regulations, master circulars and applicable exchange/data-vendor contracts at release time.

# 16. Development Roadmap

Build in controlled phases. Each phase must pass its exit criteria before the next phase is treated as production-ready.

## Phase 0 — Product and Data Feasibility

Deliverables:

- Confirm target users and MVP use cases.
- Confirm initial supported NSE/BSE universe.
- Compare data vendors and licensing costs.
- Confirm live/delayed/end-of-day entitlements.
- Confirm news and financial-data rights.
- Obtain initial regulatory assessment.
- Define core data schemas and data-quality rules.
- Create clickable dashboard prototype.

Exit criteria:

- One chosen initial provider for each critical data category.
- Written coverage, pricing and permitted-use assumptions.
- Approved MVP scope and architecture.

## Phase 1 — Reliable Stock Data Foundation

Deliverables:

- Instrument search and resolution.
- Market quote and historical price ingestion.
- Company master and exchange mapping.
- Financial statement ingestion.
- Corporate actions handling.
- Provider adapters and freshness indicators.
- Initial overview, chart and fundamentals screens.

Exit criteria:

- Supported securities resolve to the correct exchange and currency.
- Price/financial values have traceable sources and timestamps.
- Stale and missing data is visibly handled.
- Calculation tests pass.

## Phase 2 — Research and Analysis

Deliverables:

- Company Research Agent.
- Financial Analysis Agent.
- Technical Analysis Agent.
- Market/Sector/Macro Agent.
- News and Events Agent.
- Evidence and citation storage.
- First consolidated research report.

Exit criteria:

- All material report claims are source-backed or explicitly marked as model interpretation.
- Numeric data matches the underlying calculation engine.
- Conflicting and missing data appears as warnings.

## Phase 3 — Orchestration, Risk and Recommendations

Deliverables:

- Master Orchestrator.
- Sentiment/Ownership capability where reliable data exists.
- Risk Management Agent.
- Final Verification service.
- Recommendation Engine with BUY/HOLD/SELL/INSUFFICIENT DATA.
- Analysis history and agent activity view.

Exit criteria:

- The system abstains when critical inputs are missing.
- Each rating has a defined horizon and evidence.
- The verification gate blocks unsupported output.
- Failures and partial runs are handled transparently.

## Phase 4 — Forecasting and Backtesting

Deliverables:

- Baseline forecasting models.
- Forecast scenarios and uncertainty ranges.
- Model registry and versioning.
- Historical backtesting.
- Walk-forward and holdout evaluation.
- Prediction log and outcome tracking.

Exit criteria:

- Model beats or provides a justified benefit over baseline under out-of-sample testing.
- No known look-ahead or survivorship bias in the supported test universe.
- Costs and realistic execution assumptions are included.
- Model report displays limitations and sample size.
- Forecasts are initially paper-tracked before being used as a prominent recommendation input.

## Phase 5 — Watchlist, Comparison, Portfolio and Alerts

Deliverables:

- Multiple watchlists.
- 2–5 stock comparison.
- Manual portfolio tracking.
- Portfolio performance and exposure charts.
- Price, news and rating alerts.
- Prediction performance dashboard.

Exit criteria:

- Portfolio calculations reconcile to test cases.
- Alerts are deduplicated and timestamped.
- User data is isolated and secured.
- Personalised advisory functions remain disabled unless separately cleared.

## Phase 6 — Global Market Expansion and Scale

Deliverables:

- Additional licensed market-data adapters.
- Global exchange calendars, currency and timezone handling.
- Country-specific financial and filing sources.
- Localised instrument resolution.
- Infrastructure scaling and performance improvements.

Exit criteria:

- Each newly supported market has tested data coverage, licences, exchange rules, currency conversion and quality checks.
- No global coverage claim is made until it is verified.

# 17. Testing and Acceptance Criteria

## 17.1 Data Tests

- Correct ticker and company mapping.
- Correct exchange and currency.
- Quote timestamps and delay labels.
- Trading holiday and market-close handling.
- Corporate actions and adjusted price series.
- Financial period and unit consistency.
- Provider outage and stale-data scenarios.

## 17.2 Calculation Tests

- Ratio calculations against independently verified examples.
- Technical indicator calculations against known datasets.
- Portfolio cost-basis and P/L calculations.
- Currency conversion and rounding.
- Corporate-action adjustments.
- Missing-value and divide-by-zero behaviour.

## 17.3 AI and Agent Tests

- Prompt-injection attempts in source documents.
- Unsupported claim detection.
- Duplicate news detection.
- Conflicting provider values.
- Stale data handling.
- Structured output validation.
- Correct use of abstention.
- Agent timeout and retry behaviour.
- Reproducibility of saved analysis runs.

## 17.4 Forecast and Backtest Tests

- Time-split integrity.
- Look-ahead bias checks.
- Survivorship bias checks.
- Transaction-cost sensitivity.
- Benchmark comparison.
- Calibration and forecast interval coverage.
- Performance across market regimes.

## 17.5 Suggested Launch Gates

Do not set arbitrary accuracy goals before collecting a valid baseline. Set measurable launch gates after the initial dataset is assembled. At minimum:

- 100% of displayed market prices show source and timestamp.
- 100% of recommendations show horizon and data-quality status.
- 100% of material numeric claims trace to source data or a versioned calculation.
- 100% of critical data-quality failures trigger abstention or a clear warning.
- No unresolved critical security or compliance issues at public launch.
- Forecasting feature remains in paper mode until independent evaluation approves it.

# 18. Cost and Operational Controls

- Estimate provider costs by symbols covered, data frequency, history depth and user count.
- Track AI cost per analysis run and per active user.
- Cache stable company profile and financial statement data.
- Reuse retrieved evidence across agents within its valid freshness window.
- Do not call every agent for every stock query.
- Use smaller/cheaper models for classification and extraction when quality tests allow.
- Reserve more capable models for synthesis and complex reasoning.
- Put API quotas, timeout budgets and cost ceilings on each workflow.
- Log provider failures and switch providers only where licensing and data consistency allow.

# 19. MVP Build Order — The Best First End-to-End Flow

Build one reliable vertical slice before adding every dashboard feature:

1. Search and resolve one NSE-listed company correctly.
2. Fetch its latest permitted quote and historical prices.
3. Fetch its latest available financial statements and official filings.
4. Calculate a small set of tested financial ratios and technical indicators.
5. Retrieve a few relevant, dated news items.
6. Run the Company, Financial, Technical and News research capabilities.
7. Run deterministic risk and data-quality checks.
8. Generate an evidence-backed report with BUY/HOLD/SELL/INSUFFICIENT DATA only when the rating rules permit it.
9. Save the data snapshot, report, model version and sources.
10. Re-run the same workflow and confirm that results are traceable and reproducible.

Once this flow works reliably for a small supported universe, expand coverage and capabilities.

# 20. Definition of Done

The platform is ready for its first public MVP when:

- A user can search and select a supported NSE/BSE company.
- The correct instrument, exchange and currency are identified.
- Price, financial, news and filing data display source and timestamps.
- Technical and financial metrics are calculated by tested code.
- The research report separates facts, calculations, opinions and model output.
- The recommendation includes a time horizon, evidence, opposing signals and risks.
- The system can return INSUFFICIENT DATA and does not force a rating.
- Analysis runs are reproducible from saved data and model snapshots.
- Users can save stocks to a watchlist and compare supported securities.
- Security, data licensing and regulatory review gates are complete for the intended launch model.
- There is no automatic trade execution.

# 21. Final Product Outcome

The expected result is a scalable AI-powered stock research and intelligence platform where a user can enter a stock name or ticker and receive a comprehensive, traceable and time-aware analysis.

The platform combines:

- Reliable market and company data.
- Specialist research agents.
- Deterministic financial and technical calculations.
- Quantitative forecasting with model governance.
- Risk analysis and independent verification.
- Backtesting and prediction-performance tracking.
- Watchlists, comparison, portfolio tracking and alerts.
- Explainable recommendations with an abstention option.

The product's competitive advantage should not be the number of AI agents. It should be the quality, freshness, traceability and historical evaluation of the information and conclusions it provides.

---

# Appendix A — Suggested Initial Technology Stack

This is a starting recommendation, not a mandatory vendor selection.

| Layer | Suggested option | Reason |
|---|---|---|
| Web frontend | Next.js + React + TypeScript | Responsive dashboard and maintainable UI |
| API backend | Python FastAPI | Strong fit with data and analytics ecosystem |
| AI orchestration | OpenAI Agents SDK behind an adapter | Code-first agent orchestration, tools and handoffs |
| Financial analytics | Python, pandas/NumPy and tested domain modules | Deterministic calculations and model workflow |
| Database | PostgreSQL | Transactional and relational data |
| Time-series storage | TimescaleDB or PostgreSQL partitioning | Evaluate against actual quote/history volume |
| Cache/queue support | Redis | Caching, rate limits and job coordination |
| Background workers | Celery, RQ or another managed queue | Ingestion, alerts, backtests and scheduled jobs |
| Object storage | S3-compatible storage | Raw files, report snapshots and model artifacts |
| Charts | A charting library with appropriate commercial/data-display rights | Candlesticks, volume and indicators |
| Monitoring | OpenTelemetry-compatible logs, metrics and traces | Operational visibility and debugging |

Keep data-provider and AI-vendor integrations replaceable. Select the final stack based on developer experience, operating cost, deployment environment and security requirements.

# Appendix B — Research and Compliance References

The following official references should be checked again during implementation and before launch because regulations, data entitlements and provider contracts can change:

- SEBI Research Analysts Regulations, last amended November 25, 2025: https://www.sebi.gov.in/legal/regulations/nov-2025/securities-and-exchange-board-of-india-research-analysts-regulations-2014-last-amended-on-november-25-2025-_98248.html
- SEBI Master Circular for Research Analysts, February 6, 2026: https://www.sebi.gov.in/legal/master-circulars/feb-2026/master-circular-for-research-analysts_99571.html
- SEBI Investment Advisers Regulations, last amended November 25, 2025: https://www.sebi.gov.in/legal/regulations/nov-2025/securities-and-exchange-board-of-india-investment-advisers-regulations-2013-and-securities-last-amended-on-november-25-2025-_98246.html
- NSE paid real-time market data and authorised-vendor information: https://www.nseindia.com/static/market-data/real-time-data-subscription
- BSE market data services: https://marketdata.bseindia.com/
- OpenAI Agents SDK documentation: https://developers.openai.com/api/docs/guides/agents/sdk
- OpenAI agent orchestration and handoffs: https://developers.openai.com/api/docs/guides/agents/orchestration

**Important:** This document is a product and technical plan, not legal, investment or financial advice. Confirm regulatory applicability, market-data licensing, redistribution rights and all provider terms with qualified professionals before launch.
