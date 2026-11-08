// Typed client for the FastAPI backend. Calls go to /api on this origin (proxied by next.config.ts);
// no keys live in the browser.

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export type Listing = {
  exchange: "NSE" | "BSE";
  symbol: string;
  series: string | null;
  is_primary: boolean;
  identifier_verified: boolean;
  verification_source: string;
};

export type Instrument = {
  instrument_id: string;
  name: string;
  isin: string;
  currency: string;
  security_type: string;
  matched_on: string | null;
  coverage: "core" | "extended";
  coverage_note: string | null;
  listings: Listing[];
};

export type UniverseCounts = { core: number; extended: number };

export type Health = {
  status: string;
  version: string;
  provider: string;
  agents: { enabled: boolean; credentials: boolean; model: string; provider?: "anthropic" | "gemini" };
  universe: UniverseCounts;
  trading: string;
};

export type Evidence = {
  id: string;
  kind: string;
  label: string;
  value: unknown;
  display: string;
  unit: string | null;
  period: string | null;
  observed_at: string | null;
  status: string;
  note: string | null;
  source: { provider: string; dataset: string; retrieved_at: string | null; detail?: string; url?: string } | null;
  formula: { id: string; version: string; expression: string } | null;
  inputs: string[];
};

export type Step = {
  id: string;
  name: string;
  kind: "service" | "agent";
  description: string;
  status: "queued" | "running" | "completed" | "partial" | "failed" | "skipped" | "unavailable";
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
};

export type Gate = {
  id: string;
  title: string;
  severity: "critical" | "warning" | "info";
  passed: boolean;
  status: "pass" | "fail" | "warn" | "info";
  message: string;
  affects: string[];
  evidence_ids: string[];
};

export type Reason = { sub_score: string; score: number; weight: number; text: string; evidence_ids: string[] };

export type Horizon = {
  horizon: "short" | "medium" | "long";
  label: string;
  window: string;
  sessions: number;
  rating: "BUY" | "HOLD" | "SELL" | "INSUFFICIENT_DATA";
  // "horizon_disabled": not offered for any stock yet; "data": this stock's evidence is insufficient.
  abstention_kind?: "horizon_disabled" | "data" | null;
  composite: number | null;
  coverage: number | null;
  agreement: number | null;
  contributions: { sub_score: string; label: string; weight: number; score: number; contribution: number }[];
  key_reasons: Reason[];
  positive_signals: Reason[];
  negative_signals: Reason[];
  strongest_opposing: Reason | null;
  hold_reason?: string | null;
  abstention_reasons: string[];
  invalidation: { condition: string; evidence_ids: string[] }[];
};

export type SubScore = {
  name: string;
  label: string;
  score: number | null;
  reason: string | null;
  note: string | null;
  sector_note: string | null;
  components: { name: string; label: string; status: string; score: number | null; display: string; evidence_ids: string[] }[];
};

export type Finding = { statement: string; kind: "fact" | "calculation" | "interpretation"; stance: string; evidence_ids: string[] };

export type AgentResult = {
  agent: string;
  title: string;
  version: string;
  description: string;
  status: "completed" | "failed" | "skipped";
  reason?: string;
  summary?: string | null;
  findings: Finding[];
  limitations?: string[];
  swot?: Record<string, { point: string; evidence_ids: string[] }[]>;
  items?: { evidence_id: string; label: string; event_type: string; relevance: string; time_horizon: string; unverified_rumour: boolean }[];
  removed: { type: string; text: string; reason: string }[];
  model?: string;
  usage?: { input_tokens: number; output_tokens: number };
};

export type Metric = {
  value: number | null;
  status: string;
  reason?: string | null;
  evidence_id: string;
  display: string;
  label: string;
  period: string;
  sector_note?: string;
};

type TableCell = { value: number | null; display: string; line_item: string } | null;

export type Report = {
  analysis_run_id: string;
  generated_at: string;
  requested_at: string;
  market_data_as_of: string | null;
  instrument: {
    instrument_id: string; name: string; isin: string; exchange: string; symbol: string; currency: string;
    identifier_verified: boolean; sector: string | null; industry: string | null; other_listings: string[];
    series?: string | null; coverage?: "core" | "extended"; coverage_note?: string | null;
  };
  market: { status: string; exchange_time: string; session: string; note: string };
  price: {
    price: number; previous_close: number | null; change: number | null; change_pct: number | null; as_of: string; basis: string;
    data_status: "live" | "delayed" | "end_of_day" | "stale" | "unavailable"; last_session: string; expected_session: string;
    history?: {
      sessions: number; first_session: string; listing_date: string | null; starts_at_listing: boolean;
      recently_listed: boolean; full_year_from: string | null;
    } | null;
    high_52w: number | null; low_52w: number | null; market_cap: number | null;
    source: { provider: string; retrieved_at: string | null; entitlement: { type: string; licensed: boolean; production_use: boolean; notes: string } };
    corporate_actions: { date: string; dividend: number | null; split: number | null }[];
    adjustment_note: string;
  };
  data_quality: { status: string; critical_failures: string[]; warnings: Gate[]; passed: number; total: number; gates: Gate[] };
  ratings: { rules_version: string; validation_status: string; validation_note: string; scoring_method: string; thresholds: Record<string, number> };
  horizons: Record<"short" | "medium" | "long", Horizon>;
  sub_scores: Record<string, SubScore>;
  summary: { key_risks: RiskFlag[]; abstentions: Record<string, string[]> };
  fundamentals: {
    status: string; currency: string; metrics: Record<string, Metric>; eps_basis?: string; notes: string[]; sector_note?: string;
    annual_table: ({ period: string; label: string } & Record<string, TableCell | string>)[];
    quarterly_table: ({ period: string; label: string } & Record<string, TableCell | string>)[];
  };
  technical: Record<string, unknown> & { status: string; trend?: string; rsi_zone?: string; range_condition?: string; levels?: Level[] };
  returns: { stock: Record<string, number | null>; benchmark: Record<string, number | null>; relative: Record<string, number | null> };
  risk: { flags: RiskFlag[]; downside_examples?: { var95_rupees: number; two_atr_rupees: number; note: string } } & Record<string, unknown>;
  news: {
    items: { evidence_id: string; title: string; summary: string | null; publisher: string | null; published_at: string | null; url: string | null;
      duplicates: { publisher: string | null; url: string | null }[]; classification: NonNullable<AgentResult["items"]>[number] | null }[];
    received: number; duplicates_removed: number;
  };
  company: { status: string; name?: string; sector?: string; industry?: string; summary?: string; website?: string; employees?: number; city?: string };
  agents: Record<string, AgentResult>;
  forecast: Forecast;
  notes: string[];
  versions: Record<string, unknown> & { engine: string; rules: string; snapshot_id: string; agent_model: string };
  disclaimer: string;
};

export type ForecastModelName = "random_walk" | "drift" | "momentum_ridge";
export type ForecastMetrics = { n: number; mae: number | null; direction: number | null; coverage: number | null; width: number | null };
export type ForecastModel = {
  dev: ForecastMetrics; holdout: ForecastMetrics;
  forecast: { median_return: number; q10: number; q90: number; median_price: number; low_price: number; high_price: number } | null;
};
export type ForecastHorizon = {
  sessions: number; label: string; origins: number; first_origin: string | null; holdout_from: string | null;
  models: Record<ForecastModelName, ForecastModel>; selected: ForecastModelName | null; approved: boolean; reason: string;
  shown_model: ForecastModelName; scenarios: { bear: number; base: number; bull: number } | null; scenario_note: string;
};
export type Forecast = {
  status: "ok" | "unavailable" | string; version?: string; reason?: string; mode?: "paper"; as_of?: string; spot?: number;
  horizons?: ForecastHorizon[];
  method?: { evaluation: string; approval: Record<string, unknown>; returns: string; caveat: string };
};

export type DataSource = {
  id: string; name: string; used_for: string[]; status: "official" | "licensed" | "dev_only" | "synthetic" | "missing";
  provider: string | null; licensed: boolean; as_of: string | null; notes: string; link: string | null;
};
export type SystemSources = {
  app_version: string; trading: string; sources: DataSource[];
  agents: { enabled: boolean; provider: string; model: string; credentials: boolean; fallbacks: string[]; debate: { bull: string; bear: string } };
  engines: { analytics: string; forecast: string; options: string; pricing: string[]; rating_rules: string; trade_rules: string };
  candidates: { name: string; kind: string; covers: string[]; replaces: string[]; url?: string; caveat?: string; status: string }[];
};

export type RiskFlag = { id: string; severity: "high" | "medium" | "low"; title: string; detail: string; evidence_ids: string[] };
export type Level = { window: number; support: number; support_date: string; resistance: number; resistance_date: string };

export type Run = {
  analysis_run_id: string;
  instrument_id: string;
  exchange: string;
  symbol: string;
  currency: string;
  status: "queued" | "running" | "completed" | "partial" | "failed";
  requested_at: string;
  completed_at: string | null;
  market_data_as_of: string | null;
  data_status: string | null;
  snapshot_id: string | null;
  deterministic_hash: string | null;
  summary: { name: string; ratings: Record<string, string>; data_quality: string; data_status: string; price: number | null; provider: string } | null;
  error: string | null;
  activity?: Step[];
  report?: Report | null;
};

export type ChartData = {
  bars: { time: string; open: number; high: number; low: number; close: number; volume: number }[];
  sma50: { time: string; value: number }[];
  sma200: { time: string; value: number }[];
  ema20: { time: string; value: number }[];
  bb_upper: { time: string; value: number }[];
  bb_lower: { time: string; value: number }[];
  vwap20: { time: string; value: number }[];
  rsi14: { time: string; value: number }[];
  macd: { time: string; value: number }[];
  macd_signal: { time: string; value: number }[];
  macd_hist: { time: string; value: number }[];
  levels: Level[];
  adjustment: string;
};

export type Replay = {
  reproducible: boolean;
  snapshot_integrity: string;
  stored_hash: string;
  replay_hash: string;
  versions: Record<string, { stored: string | null; current: string }>;
  versions_changed: boolean;
  explanation: string;
  stored_ratings: Record<string, string>;
  replay_ratings: Record<string, string>;
  note: string;
  replayed_at: string;
};

export const api = {
  health: () => request<Health>("/api/health"),
  sources: () => request<SystemSources>("/api/system/sources"),
  search: (q: string) =>
    request<{ results: Instrument[]; counts: UniverseCounts }>(`/api/instruments/search?q=${encodeURIComponent(q)}`),
  // Core tier only; the extended tier (full NSE master) is reached through search.
  instruments: () => request<{ instruments: Instrument[]; source: string; counts: UniverseCounts }>("/api/instruments"),
  createRun: (instrument_id: string, exchange: string) =>
    request<{ analysis_run_id: string }>("/api/runs", { method: "POST", body: JSON.stringify({ instrument_id, exchange }) }),
  run: (id: string) => request<Run>(`/api/runs/${encodeURIComponent(id)}`),
  runs: (limit = 30) => request<{ runs: Run[] }>(`/api/runs?limit=${limit}`),
  evidence: (id: string) => request<{ evidence: Evidence[] }>(`/api/runs/${encodeURIComponent(id)}/evidence`),
  chart: (id: string) => request<ChartData>(`/api/runs/${encodeURIComponent(id)}/chart`),
  replay: (id: string) => request<Replay>(`/api/runs/${encodeURIComponent(id)}/replay`, { method: "POST" }),
};
