# AI Stock Research Platform: vertical slice

This is the first end-to-end flow from section 19 of [the plan](ai_stock_research_platform_plan_v2.md). It covers 24 core NSE companies checked end to end, plus every other NSE main-board equity as extended coverage. A user searches for a company, picks the exact listing, and gets a timestamped, source-backed report. Every figure in the report links to its source or calculation, and the report can be replayed from its saved snapshot.

It is a research and decision-support tool. It places no orders and has no broker integration.

## Run it

Requirements: Python 3.12+ and Node 20+.

```bash
cd backend
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r pyproject.toml --extra dev
.venv/bin/uvicorn app.main:app --port 8000
```

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000. The Next.js dev server proxies `/api/*` to the backend on 127.0.0.1:8000.

To turn on the research agents, copy `.env.example` to `.env` in the project root and set one key. Without a key, the four agents show as "skipped" and the report is built from the deterministic engines alone.

- **Gemini (free tier):** set `GEMINI_API_KEY`, created at https://aistudio.google.com/apikey. The default model is `gemini-3.6-flash`. If a model is overloaded, the agents fall back to the next one in `SRP_GEMINI_FALLBACK_MODELS`. Free-tier requests may be used by Google to improve its products; only public market data is sent.
- **Claude (paid API):** set `ANTHROPIC_API_KEY`. With `SRP_AGENT_PROVIDER=auto`, Claude is used whenever its key is present.

Tests:

```bash
cd backend && .venv/bin/python -m pytest -q
```

## What happens in one analysis run

| Step (plan §3) | Where |
|---|---|
| Resolve company, ISIN, listing, exchange, currency. One company listed on NSE and BSE is one instrument with two listings, and the user picks one. | `backend/app/services/instruments.py`, `app/universe/` |
| Fetch prices, quote, statements, profile, news, results calendar, NIFTY 50 and the other listing into one snapshot. The snapshot ID is a content hash. | `app/providers/`, `app/services/snapshots.py` |
| Calculate ratios in Decimal and indicators with tested, versioned formulas. | `app/analytics/` |
| Run 20+ deterministic data-quality checks: freshness, history depth, currency, cross-listing and quote conflicts, statement recency, corporate-action jumps and more. | `app/services/quality.py` |
| Compute risk metrics and flags. | `app/services/analysis.py` |
| Run Company, Financial, Technical and News agents (Claude) in parallel on curated evidence. They have no tools and return structured output. | `app/agents/` |
| Verify agent output: unknown citations, uncited facts and numbers not found in the cited evidence are removed. | `app/services/verification.py` |
| Rate each horizon BUY / HOLD / SELL / INSUFFICIENT DATA using versioned rules. | `app/services/recommendation.py`, `app/rules/rules_v0_1.json` |
| Store the report, evidence and prediction log. Replay recomputes everything from the snapshot and compares hashes. | `app/services/orchestrator.py`, `app/db.py` |

## Deliberate limits in this slice

- **Data is unlicensed.** The `yahoo_dev` adapter uses the unofficial yfinance library. Its data is delayed or end-of-day and must not be used in production (plan §6.2). The UI never labels it "live". Replace it with a licensed NSE/BSE vendor adapter behind the same interface (`app/providers/base.py`).
- **No official filings.** Exchange announcements need a licensed source, so the gate reports them as unavailable.
- **Draft rating rules.** `rules-v0.1-draft` has not been backtested. Every rating carries that label. The short-term horizon always abstains until a forecasting model passes Phase 4 evaluation.
- **No FX source yet.** When statements are in another currency (Yahoo reports Infosys's in USD), P/E and P/B are withheld. Margins, returns and leverage ratios are kept.
- **No exchange holiday calendar.** Freshness uses weekdays only. A lag of 2–4 sessions is a warning; 5 or more is critical.
- **Two coverage tiers.** All ISINs come from NSE's official securities master (`EQUITY_L.csv`).
  - *Core:* 24 large caps checked end to end. Each has an NSE listing and a BSE listing flagged as unverified, because BSE's scrip master isn't loaded.
  - *Extended:* every other NSE main-board equity (about 2,600, series EQ, BE and BZ), NSE listing only. Their reports say the provider data was not pre-validated, and the data-quality checks decide what each report can conclude.
  - *Not covered yet:* BSE-only and NSE SME-platform companies.
  - To refresh both tiers, run `python scripts/build_universe.py` (downloads the latest master) or pass a local copy of the CSV.
- **Engine versioning.** When calculation or check logic changes, `ENGINE_VERSION` in `app/analytics/__init__.py` is bumped. Replaying an older report then explains its hash mismatch instead of flagging it as tampering.
- **Storage is SQLite** under `backend/data/`. The models are plain SQLAlchemy, so `SRP_DATABASE_URL` can point at PostgreSQL.
- **Not built yet:** watchlists, comparison, portfolio, alerts, backtesting, forecasting and the prediction-performance page (plan phases 4–5). The prediction log already records every rating for later scoring (`POST /api/predictions/evaluate`).

## Options module (spec phases 7–8)

The **Options** page builds an option chain for any of the 224 NSE F&O underlyings and runs a strategy lab on it. The code lives in `backend/app/options/` and the screens are under `/options`.

- **Contracts are real.** Expiries (already shifted for exchange holidays), strikes, lot sizes, settlement method and exercise style come from NSE's daily F&O contract master. Refresh it with `python scripts/build_fo_master.py`, which downloads the latest `NSE_FO_contract_<date>.csv.gz`.
- **Prices are synthetic.** No licensed NSE options feed is configured, so premiums, bid/ask, OI and volume are generated around the real end-of-day underlying close. Every screen and API response labels this, and the strategy engine always returns `INSUFFICIENT_DATA` as the opportunity status on synthetic data.
- **Engines are deterministic and tested.**
  - Black-Scholes-Merton prices and all five Greeks, checked against Hull's worked examples and finite differences.
  - An implied-volatility solver.
  - Chain analytics: PCR, max pain, OI support and resistance, unusual volume, skew and expected move.
  - Exact payoffs for 13 strategies, each re-checked by an independent brute-force verifier.
  - Risk rules that reject illiquid, wide-spread or unpriced legs. They always disclose unlimited loss and the physical delivery that applies to stock options.
- **Index price sources.** Only NIFTY and BANKNIFTY are configured; the other index underlyings return INSUFFICIENT DATA until a verified source is added.
- **Assumptions.** The risk-free rate is fixed at 6% and margin isn't calculated. Backtesting and the AI strategy agents (phases 9–10) aren't built yet.

## Index trade desk (module 2)

`/options/desk` answers "what index options trade should I consider now?" for NIFTY and BANKNIFTY. It never forces a trade. The code is in `backend/app/options/direction.py`, `decision.py` and `desk.py`.

- **Direction.** One of six labels, scored from moving averages, RSI/MACD, 10-session structure, ADX/DI, a 20-session VWAP and US market cues, each shown with its reading. India VIX can override the label to High Volatility / Uncertain. Option-chain positioning is excluded while the chain is synthetic. There's no economic calendar or intraday VWAP yet.
- **Decision.** A playbook per direction (BUY CE/PE, vertical spreads, SELL CE/PE, iron condor) and strike comparison by delta, decay, spread, OI and gain per ATR. Each candidate gets an entry zone, a model-priced stop and two targets (±1 and 2 ATR on the index), break-even, max loss and profit, and R:R. Sizing uses the worst-case loss, so it never exceeds the risk budget. Each candidate also gets a draft grade and lists the evidence for and against.
- **Gates.** These hard rules return NO TRADE or WAIT FOR CONFIRMATION:
  - option prices must be live, not synthetic;
  - the market must be open;
  - quotes must be at most 5 minutes old;
  - the expiry must be valid and the contract must be in NSE's master;
  - margin data must be available for any short leg;
  - the trade must pass the risk and liquidity rules and the independent payoff check.
- **What it says today.** With synthetic prices the desk always returns NO TRADE and shows its best candidate as a labelled dry run.
- **Signal log.** Every run, including NO TRADE, is stored in `options_signals` (API `/api/options/signals`). Outcome scoring starts once live prices exist.
- **Not built yet.** Live monitoring and alerts, backtesting, the trade journal, a SPAN margin model, and FINNIFTY/MIDCPNIFTY price sources.

## Interface

The interface uses a dark, soft-neon theme. Muted neon tones and light glows mark accents and status, always with a text label. Chart lines use a separate palette checked for colour-blind separation on the dark chart surface (`--series-1` to `--series-5` in `web/src/app/globals.css`). Reports lead with visuals: rating lights, score gauges, coverage and agreement rings, colour-coded tiles and signal bars. Detailed text sits behind tabs.

## Regulatory note

Before any public release or paid use, get advice from Indian securities counsel on SEBI Research Analyst and Investment Adviser requirements (plan §15). Also review the market-data licence terms.
