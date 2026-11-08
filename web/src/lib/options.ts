// Client for the Options Trading Intelligence API.
import { API_BASE } from "./api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers: { "Content-Type": "application/json" }, cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export type Underlying = {
  symbol: string; name: string; type: "index" | "stock"; settlement: string; exercise: string;
  price_symbol: string | null; price_note: string | null; instrument_id: string | null;
  expiries: { expiry: string; lot_size: number | null; strikes: number }[]; contract_master_date: string;
};

export type Greeks = { delta: number; gamma: number; theta: number; vega: number; rho: number };

export type Quote = {
  bid: number; ask: number; ltp: number | null; prev_close: number; oi: number; oi_change: number; volume: number;
  mid: number | null; spread_pct: number | null; crossed: boolean; iv: number | null; iv_note: string | null;
  greeks: Greeks | null; theoretical: number | null;
};

export type ChainRow = { strike: number; CE: Quote; PE: Quote };

export type ChainSummary = {
  expiry: string; days_to_expiry: number; lot_size: number | null; forward: number; atm_strike: number;
  atm_iv: number | null; realised_vol_1y: number | null; iv_to_realised: number | null; pcr_oi: number | null; pcr_volume: number | null;
  total_oi: { CE: number; PE: number }; max_pain: number | null;
  oi_resistance: { strike: number; oi: number }[]; oi_support: { strike: number; oi: number }[];
  unusual_volume: { strike: number; type: "CE" | "PE"; volume: number; oi: number; volume_to_oi: number }[];
  skew_25d: number | null; expected_move: { straddle: number | null; pct: number | null; note: string };
  liquidity: Record<string, number>; positioning: { lean: string; evidence: string; caveat: string };
  signals: { signal: string; value: number; reading: string }[];
};

export type ChainView = {
  chain_id: string; data_type: string; underlying: Underlying;
  spot: { price: number; session: string; source: string; price_symbol: string; sessions_missing: number };
  assumptions: Record<string, number | string | null>;
  provider: { name: string; entitlement: { type: string; notes: string } };
  pricing_model: { id: string; version: string; assumptions: string };
  created_at: string; expiries: { expiry: string; days: number; lot_size: number | null }[]; expiry: string;
  summary: ChainSummary; term_structure: { expiry: string; days: number; atm_iv: number | null }[];
  quality: { id: string; severity: string; passed: boolean; message: string }[];
  model_check?: ModelCheck;
  rows: ChainRow[];
};

export type ModelCheck = {
  status: string; reason?: string; strike?: number; iv?: number; days?: number; passed?: boolean;
  parity_gap?: number; parity_passed?: boolean; note?: string;
  checks?: { contract: string; bsm: number; binomial: number; difference: number; difference_pct: number | null; passed: boolean }[];
  models?: { primary: string; check: { id: string; steps: number; use: string } };
};

export type Template = { id: string; label: string; outlook: string; explain: string; stock_only: boolean };

export type Evaluation = {
  template: string; label: string; outlook: string; explanation: string; expiry: string; days_to_expiry: number;
  lot_size: number; lots: number; units: number; data_type: string;
  legs: { leg: number; side: "buy" | "sell"; type: "CE" | "PE" | "STOCK"; strike: number | null; fill: number | null; fill_basis: string; quote: Partial<Quote> | null }[];
  payoff: {
    net_premium: number; net_premium_kind: "credit" | "debit"; max_profit: number | null; max_loss: number | null;
    unlimited_profit: boolean; unlimited_loss: boolean; breakevens: number[]; risk_reward: number | null; basis: string;
  } | null;
  verification?: { method: string; consistent: boolean; problems: string[] };
  greeks?: Partial<Greeks> & { note?: string };
  curves?: { prices: number[]; expiry: number[]; today: (number | null)[] };
  scenarios?: { when: string; vol_shift: number; pnl: Record<string, number | null> }[];
  invalidation?: string[];
  risk: {
    verdict: "passed" | "passed_with_warnings" | "rejected"; rejections: string[];
    flags: { id: string; severity: "critical" | "high" | "medium" | "low"; text: string }[];
    opportunity_status: string; opportunity_reason: string; probability_estimates: string;
  };
};

export const optionsApi = {
  underlyings: (q?: string) =>
    req<{ results: Underlying[]; count: number; contract_master_date: string }>(`/api/options/underlyings${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  createChain: (symbol: string) => req<{ chain_id: string }>("/api/options/chains", { method: "POST", body: JSON.stringify({ symbol }) }),
  chains: () => req<{ chains: { chain_id: string; symbol: string; created_at: string; spot: number; data_type: string; expiries: number }[] }>("/api/options/chains"),
  chain: (id: string, expiry?: string) => req<ChainView>(`/api/options/chains/${id}${expiry ? `?expiry=${expiry}` : ""}`),
  templates: () => req<{ templates: Template[] }>("/api/options/strategies"),
  evaluate: (id: string, body: { template: string; expiry: string; width: number; lots: number }) =>
    req<Evaluation>(`/api/options/chains/${id}/strategies`, { method: "POST", body: JSON.stringify(body) }),
};

// ---------------------------------------------------------------- trading desk (module 2)

export type DeskIndex = { symbol: string; name: string; supported: boolean; note: string | null; expiries: { expiry: string; lot_size: number | null; strikes: number }[] };

export type DeskLeg = {
  side: "buy" | "sell"; type: "CE" | "PE"; strike: number; fill: number | null; fill_basis: string;
  bid: number; ask: number; mid: number | null; iv: number | null; delta: number | null; spread_pct: number | null; oi: number; volume: number;
};

export type DeskCandidate = {
  strategy: string; label: string; bias: "bullish" | "bearish" | "neutral"; kind: "debit" | "credit";
  legs: DeskLeg[];
  entry: { value: number; kind: string; zone: [number, number]; per_lot: number; basis: string };
  stop: { index_level: number | number[]; pnl_per_lot: number | null; value?: number | null; rule: string };
  targets: { index_level: number | null; pnl_per_lot: number | null; value?: number | null; rule: string }[];
  breakevens: number[]; max_loss_per_lot: number | null; max_profit_per_lot: number | null;
  unlimited_loss: boolean; unlimited_profit: boolean; risk_reward: number | null;
  liquidity: { leg: string; spread_pct: number | null; oi: number; volume: number }[];
  sizing: { budget: number; lots: number; lot_size: number; units: number; max_loss_total: number | null; stop_loss_total: number | null;
    target1_total: number | null; capital: number | null; margin: string; rule: string };
  grade: { label: string; points: number; breakdown: { factor: string; points: number; met: boolean }[]; note: string };
  supporting: string[]; against: string[]; entry_confirmation: string[]; confirmed: boolean; invalidation: string[]; exit_signals: string[];
  verification: { consistent: boolean; method: string; problems: string[] };
  risk: Evaluation["risk"]; eligible: boolean; exclusions: string[];
  curves?: { prices: number[]; expiry: number[]; today: (number | null)[] };
};

export type DeskCandidateSummary = {
  strategy: string; label: string; bias: string; kind: string; eligible: boolean; exclusions: string[]; risk_reward: number | null;
  max_loss_per_lot: number | null; max_profit_per_lot: number | null; unlimited_loss: boolean; breakevens: number[];
  legs: DeskLeg[]; grade: string | null; points: number | null; net: number | null;
};

export type StrikeRank = {
  strike: number; type: "CE" | "PE"; delta: number; gamma: number; theta: number; vega: number; iv: number | null;
  bid: number; ask: number; mid: number; spread_pct: number; oi: number; volume: number;
  one_atr_gain_pct: number; decay_pct_per_day: number; iv_vs_atm: number; score: number;
};

export type DirectionComponent = { key: string; label: string; score: number | null; weight: number; value: string; reading: string };

export type Desk = {
  signal_id: string; generated_at: string; budget: number;
  header: {
    symbol: string; name: string; price: number; change_1d: number | null; as_of: string; trend: string;
    market: { status: string; note: string }; expiry: string; time_to_expiry_hours: number; lot_size: number; data_type: string;
  };
  direction: {
    label: string; version: string; composite: number | null; coverage?: number; adx: number; components: DirectionComponent[];
    vix: { level: number | null; change_5d: number | null; regime: string; as_of: string | null };
    atr: number; atr_pct: number; last: number; change_1d: number | null; as_of: string;
    levels: Record<string, number | null>; missing: string[]; reason?: string;
  };
  chain: Pick<ChainView, "chain_id" | "data_type" | "expiry" | "expiries" | "summary" | "term_structure" | "quality" | "rows" | "provider" | "assumptions" | "spot" | "created_at">;
  decision: {
    status: string; status_reason: string; dry_run: boolean; generated_at: string; expiry: string;
    rules: { version: string; validation_status: string; paper_mode: boolean };
    data_gates: { check: string; passed: boolean; detail: string }[];
    best: DeskCandidate | null; candidates: DeskCandidateSummary[];
    strikes: { CE?: StrikeRank[]; PE?: StrikeRank[]; why_CE?: string | null; why_PE?: string | null };
  };
};

export const deskApi = {
  indices: () => req<{ indices: DeskIndex[] }>("/api/options/desk/indices"),
  run: (body: { symbol: string; expiry?: string; budget: number }) => req<Desk>("/api/options/desk", { method: "POST", body: JSON.stringify(body) }),
  signals: () => req<{ signals: { signal_id: string; created_at: string; symbol: string; expiry: string; status: string; strategy: string | null; data_type: string; mode: string }[]; counts: Record<string, number>; performance: string }>("/api/options/signals?limit=20"),
};
