"use client";

import { useEffect, useState } from "react";
import { formatDate, formatPct } from "@/lib/format";
import { optionsApi, type ChainRow, type ChainView as Chain, type ModelCheck } from "@/lib/options";
import { DotStrip, KpiTile, Pill, Tip, type Tone } from "../viz";
import StrategyLab from "./StrategyLab";

const num = (v: number | null | undefined, dp = 2) => (v == null ? "—" : v.toLocaleString("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: dp }));
const compact = (v: number) => (v >= 1e5 ? `${(v / 1e5).toFixed(1)}L` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : `${v}`);

export default function ChainView({ chainId }: { chainId: string }) {
  const [view, setView] = useState<Chain | null>(null);
  const [expiry, setExpiry] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    optionsApi.chain(chainId, expiry).then(setView).catch((e) => setError(e.message));
  }, [chainId, expiry]);

  if (error) return <div className="rounded-xl border border-neg/40 bg-neg-bg px-4 py-3 text-sm text-neg">{error}</div>;
  if (!view) return <p className="text-sm text-muted">Loading option chain…</p>;

  const s = view.summary;
  const u = view.underlying;
  const leanTone: Tone = s.positioning.lean.startsWith("bullish") ? "pos" : s.positioning.lean.startsWith("bearish") ? "neg" : "cyan";

  return (
    <div className="space-y-5">
      <section className="panel rounded-2xl p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone="purple">{u.symbol}</Pill>
          <Pill tone={u.type === "index" ? "purple" : "cyan"}>{u.type}</Pill>
          <Pill tone={u.settlement === "physical" ? "warn" : "neutral"} title={u.settlement === "physical" ? "In-the-money stock options settle by delivery of shares" : "Cash-settled"}>{u.settlement}-settled</Pill>
          {view.data_type === "synthetic" && <Pill tone="warn" title={view.provider.entitlement.notes}>Synthetic prices</Pill>}
          <span className="ml-auto flex items-center gap-2 text-[11px] text-faint">
            Checks
            <DotStrip items={view.quality.map((g) => ({ id: g.id, status: g.passed ? "pass" : g.severity === "critical" ? "fail" : "warn", title: g.message }))} />
          </span>
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-6">
          <div>
            <h1 className="text-3xl font-black tracking-tight">{u.name}</h1>
            <div className="text-xs text-faint">Underlying close {formatDate(view.spot.session)} · {view.spot.price_symbol} · contracts from NSE master {u.contract_master_date}</div>
          </div>
          <div className="text-5xl font-black tabular text-ink text-glow-cyan">{num(view.spot.price)}</div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {view.expiries.map((e) => (
            <button key={e.expiry} onClick={() => setExpiry(e.expiry)}
              className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${e.expiry === view.expiry ? "border-cyan bg-cyan-bg text-cyan glow-cyan" : "border-line text-muted hover:border-purple hover:text-purple"}`}>
              {formatDate(e.expiry)} <span className="text-faint">· {Math.round(e.days)}d</span>
            </button>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
        <KpiTile label="ATM IV" value={formatPct(s.atm_iv, 1)} tone="purple" sub={`strike ${num(s.atm_strike, 0)}`} />
        <KpiTile label="PCR (OI)" value={num(s.pcr_oi)} tone={leanTone} sub={s.positioning.lean} title={s.positioning.caveat} />
        <KpiTile label="Max pain" value={num(s.max_pain, 0)} tone="cyan" sub="not a forecast" />
        <KpiTile label="Expected move" value={s.expected_move.pct != null ? `±${formatPct(s.expected_move.pct, 1)}` : "—"} tone="warn" sub={`±${num(s.expected_move.straddle)} by expiry`} title={s.expected_move.note} />
        <KpiTile label="Support (PE OI)" value={num(s.oi_support[0]?.strike ?? null, 0)} tone="pos" sub="largest put OI" />
        <KpiTile label="Resistance (CE OI)" value={num(s.oi_resistance[0]?.strike ?? null, 0)} tone="neg" sub="largest call OI" />
        <KpiTile label="25Δ skew" value={s.skew_25d != null ? `${(s.skew_25d * 100).toFixed(1)} pts` : "—"} tone={s.skew_25d != null && s.skew_25d > 0 ? "neg" : "pos"} sub={s.skew_25d != null && s.skew_25d > 0 ? "puts richer" : "calls richer"} />
        <KpiTile label="IV / realised" value={s.iv_to_realised != null ? `${s.iv_to_realised.toFixed(2)}x` : "—"} tone={s.iv_to_realised != null && s.iv_to_realised > 1.5 ? "neg" : "neutral"} sub="1Y realised vol" />
      </section>

      {view.model_check && <ModelCheckStrip mc={view.model_check} />}

      <div className="grid gap-5 xl:grid-cols-[1fr_1.15fr]">
        <OiProfile rows={view.rows} spot={view.spot.price} atm={s.atm_strike} unusual={s.unusual_volume} caveat={s.positioning.caveat} />
        <StrategyLab chainId={view.chain_id} expiry={view.expiry} underlyingType={u.type} spot={view.spot.price} />
      </div>

      <ChainTable rows={view.rows} atm={s.atm_strike} spot={view.spot.price} unusual={s.unusual_volume} />

      <p className="text-center text-[11px] text-faint">
        {view.pricing_model.id} v{view.pricing_model.version} · r = {formatPct(view.assumptions.risk_free_rate as number)} (assumed) · q = {formatPct(view.assumptions.dividend_yield as number)} ·
        IV and Greeks solved from each quote&apos;s mid price. Greeks are model estimates, not guarantees.
      </p>
    </div>
  );
}

function ModelCheckStrip({ mc }: { mc: ModelCheck }) {
  if (mc.status !== "ok" || !mc.checks) {
    return <div className="panel rounded-xl px-4 py-2 text-[11px] text-muted">Model check unavailable: {mc.reason}</div>;
  }
  const tone: Tone = mc.passed ? "pos" : "neg";
  return (
    <section className="panel flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl px-4 py-2.5 text-[11px]">
      <span className="flex items-center gap-2">
        <Pill tone={tone}>{mc.passed ? "✓ Models agree" : "✕ Models disagree"}</Pill>
        <Tip text={`${mc.note} Primary: ${mc.models?.primary}. Check: ${mc.models?.check.id} lattice, ${mc.models?.check.steps} steps, at ATM IV ${formatPct(mc.iv, 1)}. ${mc.models?.check.use}`} />
      </span>
      {mc.checks.map((c) => (
        <span key={c.contract} className="tabular">
          <span className="font-semibold">{c.contract}</span>
          <span className="text-faint"> BSM </span>{num(c.bsm)}
          <span className="text-faint"> · lattice </span>{num(c.binomial)}
          <span className={c.passed ? "text-pos" : "text-neg"}> ({c.difference_pct != null ? formatPct(c.difference_pct, 2) : "—"})</span>
        </span>
      ))}
      <span className="tabular">
        <span className="text-faint">Put-call parity gap </span>
        <span className={mc.parity_passed ? "text-pos" : "text-neg"}>{num(mc.parity_gap ?? null)}</span>
      </span>
    </section>
  );
}

function OiProfile({ rows, spot, atm, unusual, caveat }: { rows: ChainRow[]; spot: number; atm: number; unusual: Chain["summary"]["unusual_volume"]; caveat: string }) {
  const i = rows.findIndex((r) => r.strike === atm);
  const near = rows.slice(Math.max(0, i - 12), i + 13);
  const max = Math.max(1, ...near.flatMap((r) => [r.CE.oi, r.PE.oi]));
  const hot = new Set(unusual.map((x) => `${x.strike}${x.type}`));
  return (
    <section className="panel rounded-2xl p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="h-4 w-1 rounded-full bg-purple" style={{ boxShadow: "0 0 3px var(--neon-purple)" }} />
        <h2 className="text-sm font-bold uppercase tracking-wider">Open interest</h2>
        <Tip text={caveat} />
        <span className="ml-auto flex gap-3 text-[10px] font-semibold uppercase tracking-wider">
          <span className="text-pos">■ Put OI</span><span className="text-neg">■ Call OI</span><span className="text-warn">⚡ unusual volume</span>
        </span>
      </div>
      <div className="space-y-[3px]">
        {near.map((r) => {
          const isAtm = r.strike === atm;
          return (
            <div key={r.strike} className="grid grid-cols-[1fr_4.5rem_1fr] items-center gap-2 text-[11px]"
              title={`${r.strike}: put OI ${r.PE.oi.toLocaleString("en-IN")} (Δ ${r.PE.oi_change.toLocaleString("en-IN")}), call OI ${r.CE.oi.toLocaleString("en-IN")} (Δ ${r.CE.oi_change.toLocaleString("en-IN")})`}>
              <div className="flex items-center justify-end gap-1">
                {hot.has(`${r.strike}PE`) && <span className="text-warn">⚡</span>}
                <div className="h-3 rounded-l-full" style={{ width: `${(r.PE.oi / max) * 100}%`, background: "var(--neon-green)", opacity: 0.8, boxShadow: "0 0 3px rgba(95,211,154,0.5)" }} />
              </div>
              <div className={`text-center font-bold tabular ${isAtm ? "rounded-full bg-cyan-bg text-cyan" : r.strike < spot ? "text-muted" : "text-faint"}`}>{r.strike.toLocaleString("en-IN")}</div>
              <div className="flex items-center gap-1">
                <div className="h-3 rounded-r-full" style={{ width: `${(r.CE.oi / max) * 100}%`, background: "var(--neon-red)", opacity: 0.8, boxShadow: "0 0 3px rgba(232,102,127,0.5)" }} />
                {hot.has(`${r.strike}CE`) && <span className="text-warn">⚡</span>}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ChainTable({ rows, atm, spot, unusual }: { rows: ChainRow[]; atm: number; spot: number; unusual: Chain["summary"]["unusual_volume"] }) {
  const [all, setAll] = useState(false);
  const i = rows.findIndex((r) => r.strike === atm);
  const shown = all ? rows : rows.slice(Math.max(0, i - 10), i + 11);
  const hot = new Set(unusual.map((x) => `${x.strike}${x.type}`));
  const cell = "px-2 py-1 text-right tabular";
  return (
    <section className="panel rounded-2xl p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="h-4 w-1 rounded-full bg-cyan" style={{ boxShadow: "0 0 3px var(--neon-cyan)" }} />
        <h2 className="text-sm font-bold uppercase tracking-wider">Option chain</h2>
        <button onClick={() => setAll((a) => !a)} className="ml-auto rounded-full border border-line px-3 py-1 text-xs font-semibold text-muted hover:border-cyan hover:text-cyan">
          {all ? "Near the money" : `All ${rows.length} strikes`}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[920px] text-xs">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider">
              <th colSpan={7} className="pb-1 text-center text-neg">Calls (CE)</th>
              <th />
              <th colSpan={7} className="pb-1 text-center text-pos">Puts (PE)</th>
            </tr>
            <tr className="text-[10px] uppercase tracking-wider text-faint">
              {["OI", "ΔOI", "Vol", "IV", "Δ", "Bid", "Ask"].map((h) => <th key={`c${h}`} className="px-2 py-1 text-right">{h}</th>)}
              <th className="px-2 py-1 text-center text-ink">Strike</th>
              {["Bid", "Ask", "Δ", "IV", "Vol", "ΔOI", "OI"].map((h) => <th key={`p${h}`} className="px-2 py-1 text-right">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => {
              const isAtm = r.strike === atm;
              const ceItm = r.strike < spot, peItm = r.strike > spot;
              const chg = (v: number) => <span className={v >= 0 ? "text-pos" : "text-neg"}>{v >= 0 ? "+" : "-"}{compact(Math.abs(v))}</span>;
              return (
                <tr key={r.strike} className={`border-t border-line/50 ${isAtm ? "bg-cyan-bg" : ""}`}>
                  <td className={`${cell} ${ceItm ? "bg-neg-bg/40" : ""}`}>{compact(r.CE.oi)}</td>
                  <td className={`${cell} ${ceItm ? "bg-neg-bg/40" : ""}`}>{chg(r.CE.oi_change)}</td>
                  <td className={`${cell} ${ceItm ? "bg-neg-bg/40" : ""} ${hot.has(`${r.strike}CE`) ? "font-bold text-warn" : ""}`}>{hot.has(`${r.strike}CE`) && "⚡"}{compact(r.CE.volume)}</td>
                  <td className={`${cell} ${ceItm ? "bg-neg-bg/40" : ""} text-purple`} title={r.CE.iv_note ?? undefined}>{r.CE.iv != null ? (r.CE.iv * 100).toFixed(1) : "—"}</td>
                  <td className={`${cell} ${ceItm ? "bg-neg-bg/40" : ""}`}>{r.CE.greeks ? r.CE.greeks.delta.toFixed(2) : "—"}</td>
                  <td className={`${cell} ${ceItm ? "bg-neg-bg/40" : ""}`}>{r.CE.bid > 0 ? r.CE.bid.toFixed(2) : "—"}</td>
                  <td className={`${cell} ${ceItm ? "bg-neg-bg/40" : ""}`}>{r.CE.ask.toFixed(2)}</td>
                  <td className={`px-2 py-1 text-center font-black tabular ${isAtm ? "text-cyan text-glow-cyan" : ""}`}>{r.strike.toLocaleString("en-IN")}</td>
                  <td className={`${cell} ${peItm ? "bg-pos-bg/40" : ""}`}>{r.PE.bid > 0 ? r.PE.bid.toFixed(2) : "—"}</td>
                  <td className={`${cell} ${peItm ? "bg-pos-bg/40" : ""}`}>{r.PE.ask.toFixed(2)}</td>
                  <td className={`${cell} ${peItm ? "bg-pos-bg/40" : ""}`}>{r.PE.greeks ? r.PE.greeks.delta.toFixed(2) : "—"}</td>
                  <td className={`${cell} ${peItm ? "bg-pos-bg/40" : ""} text-purple`} title={r.PE.iv_note ?? undefined}>{r.PE.iv != null ? (r.PE.iv * 100).toFixed(1) : "—"}</td>
                  <td className={`${cell} ${peItm ? "bg-pos-bg/40" : ""} ${hot.has(`${r.strike}PE`) ? "font-bold text-warn" : ""}`}>{hot.has(`${r.strike}PE`) && "⚡"}{compact(r.PE.volume)}</td>
                  <td className={`${cell} ${peItm ? "bg-pos-bg/40" : ""}`}>{chg(r.PE.oi_change)}</td>
                  <td className={`${cell} ${peItm ? "bg-pos-bg/40" : ""}`}>{compact(r.PE.oi)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] text-faint">Shaded cells are in the money. OI in contracts. IV in %. Hover IV dashes for the reason.</p>
    </section>
  );
}
