"use client";

import { useCallback, useEffect, useState } from "react";
import { formatDate, formatDateTime, formatPct } from "@/lib/format";
import { deskApi, type Desk, type DeskCandidate, type DeskIndex, type StrikeRank } from "@/lib/options";
import { Gauge, KpiTile, Pill, SignalBar, Tip, type Tone } from "../viz";
import { PayoffChart } from "./StrategyLab";

const STATUS_TONE: Record<string, Tone> = {
  "HIGH-QUALITY SETUP": "pos", "MODERATE SETUP": "cyan", "LOW-QUALITY SETUP": "purple",
  "WAIT FOR CONFIRMATION": "warn", "NO TRADE": "neg",
};
const TONE_COLOR: Record<Tone, string> = {
  pos: "var(--neon-green)", neg: "var(--neon-red)", warn: "var(--neon-yellow)", cyan: "var(--neon-cyan)", purple: "var(--neon-purple)", neutral: "var(--muted)",
};

function directionTone(label: string): Tone {
  if (label.includes("Bullish")) return "pos";
  if (label.includes("Bearish")) return "neg";
  if (label === "Neutral") return "cyan";
  if (label.includes("Uncertain")) return "warn";
  return "neutral";
}

const rupees = (v: number | null | undefined, signed = false) =>
  v == null ? "—" : `${signed ? (v >= 0 ? "+" : "-") : v < 0 ? "-" : ""}₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const num = (v: number | null | undefined, dp = 2) => (v == null ? "—" : v.toLocaleString("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: dp }));
const level = (v: number | number[] | null | undefined) =>
  v == null ? "—" : Array.isArray(v) ? v.map((x) => x.toLocaleString("en-IN", { maximumFractionDigits: 0 })).join(" / ") : v.toLocaleString("en-IN", { maximumFractionDigits: 0 });

function timeLeft(hours: number) {
  const d = Math.floor(hours / 24), h = Math.floor(hours % 24);
  return d > 0 ? `${d}d ${h}h` : `${h}h ${Math.round((hours % 1) * 60)}m`;
}

function Bar({ tone }: { tone: Tone }) {
  return <span className="h-4 w-1 rounded-full" style={{ background: TONE_COLOR[tone], boxShadow: `0 0 3px ${TONE_COLOR[tone]}` }} />;
}

function Heading({ children, tone = "cyan", right }: { children: React.ReactNode; tone?: Tone; right?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <Bar tone={tone} />
      <h2 className="text-sm font-bold uppercase tracking-wider">{children}</h2>
      {right && <div className="ml-auto">{right}</div>}
    </div>
  );
}

export default function TradingDesk() {
  const [indices, setIndices] = useState<DeskIndex[]>([]);
  // Each selection is a numbered request; the effect runs it and only sets state when it settles.
  const [req, setReq] = useState<{ symbol: string; expiry?: string; budget: number; n: number }>({ symbol: "NIFTY", budget: 25000, n: 0 });
  const [settled, setSettled] = useState(-1);
  const [budgetDraft, setBudgetDraft] = useState("25000");
  const [desk, setDesk] = useState<Desk | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0); // set from data arrival and a timer, never during prerender
  const busy = settled !== req.n;
  const { symbol } = req;

  useEffect(() => {
    deskApi.indices().then((r) => setIndices(r.indices)).catch((e) => setError(e.message));
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let live = true;
    deskApi.run({ symbol: req.symbol, expiry: req.expiry, budget: req.budget })
      .then((d) => { if (live) { setDesk(d); setError(null); setNow(Date.now()); } })
      .catch((e) => { if (live) setError(e.message); })
      .finally(() => { if (live) setSettled(req.n); });
    return () => { live = false; };
  }, [req]);

  const request = useCallback((patch: Partial<{ symbol: string; expiry?: string; budget: number }>) => {
    setReq((r) => ({ ...r, ...patch, n: r.n + 1 }));
  }, []);

  const ageMin = desk && now ? Math.max(0, (now - new Date(desk.generated_at).getTime()) / 60000) : 0;
  const expiries = desk?.chain.expiries ?? [];

  return (
    <div className="space-y-5">
      <section className="panel rounded-2xl p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-faint">Index</span>
          {indices.map((i) => (
            <button key={i.symbol} disabled={!i.supported || busy} title={i.note ?? i.name}
              onClick={() => request({ symbol: i.symbol, expiry: undefined })}
              className={`rounded-full border px-3 py-1 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-35 ${i.symbol === symbol ? "border-cyan bg-cyan-bg text-cyan glow-cyan" : "border-line text-muted hover:border-purple hover:text-purple"}`}>
              {i.symbol}
            </button>
          ))}
          <span className="ml-auto flex items-center gap-2 text-xs">
            <span className="text-faint">Risk budget ₹</span>
            <input value={budgetDraft} onChange={(e) => setBudgetDraft(e.target.value.replace(/[^0-9]/g, ""))}
              className="w-24 rounded-lg border border-line bg-bg px-2 py-1 text-right font-bold tabular outline-none focus:border-cyan" />
            <button onClick={() => request({ budget: Number(budgetDraft) || 25000 })} disabled={busy}
              className="rounded-full border border-cyan/60 bg-cyan-bg px-3 py-1 font-bold text-cyan disabled:opacity-50">
              {busy ? "Analysing…" : "Re-run"}
            </button>
          </span>
        </div>
        {expiries.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-faint">Expiry</span>
            {expiries.map((e) => (
              <button key={e.expiry} disabled={busy} onClick={() => request({ expiry: e.expiry })}
                className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${e.expiry === desk?.header.expiry ? "border-purple bg-purple-bg text-purple glow-purple" : "border-line text-muted hover:border-cyan hover:text-cyan"}`}>
                {formatDate(e.expiry)} <span className="text-faint">· {Math.round(e.days)}d</span>
              </button>
            ))}
          </div>
        )}
      </section>

      {error && <div className="rounded-xl border border-neg/40 bg-neg-bg px-4 py-3 text-sm text-neg">{error}</div>}
      {!desk && !error && <div className="panel h-64 animate-pulse rounded-2xl" />}

      {desk && (
        <div className={`space-y-5 transition ${busy ? "opacity-60" : ""}`}>
          <HeaderStrip desk={desk} ageMin={ageMin} />
          <DecisionHero desk={desk} ageMin={ageMin} />
          {desk.decision.best && <TradeCard c={desk.decision.best} desk={desk} />}
          <div className="grid gap-5 xl:grid-cols-[1fr_1.1fr]">
            <DirectionPanel desk={desk} />
            <ChainPanel desk={desk} />
          </div>
          <div className="grid gap-5 xl:grid-cols-2">
            <StrategyTable desk={desk} />
            <StrikeTable desk={desk} />
          </div>
          <SignalsPanel signalId={desk.signal_id} />
          <p className="text-center text-[11px] text-faint">
            {desk.decision.rules.version} · {desk.direction.version} · draft rules in paper mode. Decision support only; you place any trade yourself. No orders are sent.
          </p>
        </div>
      )}
    </div>
  );
}

function HeaderStrip({ desk, ageMin }: { desk: Desk; ageMin: number }) {
  const h = desk.header;
  const up = (h.change_1d ?? 0) >= 0;
  return (
    <section className="panel rounded-2xl p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="purple">{h.symbol}</Pill>
        <Pill tone={directionTone(h.trend)}>{h.trend}</Pill>
        <Pill tone={h.market.status === "open" ? "pos" : "neutral"} title={h.market.note}>Market {h.market.status.replace("_", " ")}</Pill>
        {h.data_type === "synthetic" && <Pill tone="warn" title={desk.chain.provider.entitlement.notes}>Synthetic option prices</Pill>}
        <span className={`ml-auto text-[11px] ${ageMin > 5 ? "text-warn" : "text-faint"}`}>
          {ageMin > 5 ? `Analysis is ${Math.round(ageMin)} min old: re-run before acting` : `Analysed ${formatDateTime(desk.generated_at)}`}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-x-10 gap-y-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight">{h.name}</h1>
          <div className="mt-1 flex items-end gap-3">
            <span className="text-5xl font-black tabular text-ink text-glow-cyan">{num(h.price)}</span>
            {h.change_1d != null && <Pill tone={up ? "pos" : "neg"} className="mb-2 text-sm">{up ? "▲" : "▼"} {formatPct(h.change_1d)}</Pill>}
          </div>
          <div className="text-[11px] text-faint">Close {formatDate(h.as_of)}</div>
        </div>
        <div className="grid grid-cols-3 gap-6 text-xs">
          <div><div className="text-[10px] uppercase tracking-wider text-faint">Expiry</div><div className="text-lg font-bold">{formatDate(h.expiry)}</div></div>
          <div><div className="text-[10px] uppercase tracking-wider text-faint">Time left</div><div className={`text-lg font-bold ${h.time_to_expiry_hours < 48 ? "text-warn" : ""}`}>{timeLeft(h.time_to_expiry_hours)}</div></div>
          <div><div className="text-[10px] uppercase tracking-wider text-faint">Lot size</div><div className="text-lg font-bold">{h.lot_size}</div></div>
        </div>
      </div>
    </section>
  );
}

function DecisionHero({ desk, ageMin }: { desk: Desk; ageMin: number }) {
  const d = desk.decision;
  const tone = STATUS_TONE[d.status] ?? "neutral";
  const color = TONE_COLOR[tone];
  return (
    <section className="panel rounded-2xl p-5" style={{ borderColor: color }}>
      <div className="grid gap-5 lg:grid-cols-[auto_1fr_auto] lg:items-center">
        <div className="flex flex-col items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-faint">Decision</span>
          <span className="rounded-2xl border-2 px-6 py-3 text-center text-2xl font-black tracking-wider"
            style={{ borderColor: color, color, background: "rgba(255,255,255,0.03)", boxShadow: `0 0 10px ${color}33` }}>
            {d.status}
          </span>
          {d.rules.paper_mode && d.status !== "NO TRADE" && <Pill tone="warn">Paper signal</Pill>}
        </div>
        <div>
          <p className="text-sm text-muted">{d.status_reason}</p>
          {d.dry_run && d.best && (
            <p className="mt-2 text-sm">
              <span className="font-bold text-warn">Dry run:</span> the engine&apos;s best candidate is shown below for inspection only. Its prices are generated, so it is not a trade signal.
            </p>
          )}
          {ageMin > 5 && <p className="mt-2 text-sm font-semibold text-warn">This analysis is no longer fresh. Re-run it before relying on any level.</p>}
        </div>
        <ul className="grid grid-cols-1 gap-1 text-xs sm:grid-cols-2 lg:grid-cols-1">
          {d.data_gates.map((g) => (
            <li key={g.check} className="flex items-center gap-2" title={g.detail}>
              <span className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-black ${g.passed ? "bg-pos-bg text-pos" : "bg-neg-bg text-neg"}`}>{g.passed ? "✓" : "✕"}</span>
              <span className={g.passed ? "text-muted" : "text-ink"}>{g.check}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function TradeCard({ c, desk }: { c: DeskCandidate; desk: Desk }) {
  const dry = desk.decision.dry_run;
  const bias: Tone = c.bias === "bullish" ? "pos" : c.bias === "bearish" ? "neg" : "purple";
  const hatch = dry ? { backgroundImage: "repeating-linear-gradient(135deg, rgba(227,194,90,0.045) 0 12px, transparent 12px 24px)" } : undefined;
  const single = c.legs.length === 1;
  const premium = (v: number | null | undefined) => (v == null ? "—" : `₹${num(Math.abs(v))}`);
  return (
    <section className="panel rounded-2xl p-5" style={hatch}>
      <Heading tone={bias} right={dry ? <Pill tone="warn">Dry run · synthetic prices</Pill> : <Pill tone={STATUS_TONE[c.grade.label] ?? "neutral"}>{c.grade.label}</Pill>}>
        {single ? "Trade candidate" : "Strategy candidate"}
      </Heading>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-3xl font-black" style={{ color: TONE_COLOR[bias] }}>{c.label}</span>
        <span className="text-lg font-bold">{c.legs.map((l) => `${l.side === "buy" ? "" : "−"}${l.strike.toLocaleString("en-IN")} ${l.type}`).join("  ")}</span>
        <Pill tone="neutral">{formatDate(desk.header.expiry)}</Pill>
        <Pill tone={c.kind === "debit" ? "purple" : "cyan"}>{c.kind}</Pill>
        {!c.eligible && <Pill tone="neg" title={c.exclusions.join(" ")}>Excluded</Pill>}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        <KpiTile label={single ? "Entry premium" : `Net ${c.kind}`} tone="cyan" value={premium(c.entry.value)} sub={`zone ${num(c.entry.zone[0])}–${num(c.entry.zone[1])}`} title={c.entry.basis} />
        <KpiTile label="Stop-loss" tone="neg" value={c.stop.value != null ? premium(c.stop.value) : rupees(c.stop.pnl_per_lot, true)} sub={`index ${level(c.stop.index_level)}`} title={c.stop.rule} />
        <KpiTile label="Target 1" tone="pos" value={c.targets[0]?.value != null ? premium(c.targets[0].value) : rupees(c.targets[0]?.pnl_per_lot, true)} sub={c.targets[0]?.index_level != null ? `index ${level(c.targets[0].index_level)}` : c.targets[0]?.rule} title={c.targets[0]?.rule} />
        <KpiTile label="Target 2" tone="pos" value={c.targets[1]?.value != null ? premium(c.targets[1].value) : rupees(c.targets[1]?.pnl_per_lot, true)} sub={c.targets[1]?.index_level != null ? `index ${level(c.targets[1].index_level)}` : c.targets[1]?.rule} title={c.targets[1]?.rule} />
        <KpiTile label="Break-even" tone="warn" value={c.breakevens.map((b) => b.toLocaleString("en-IN", { maximumFractionDigits: 0 })).join(" / ") || "—"} sub="at expiry" />
        <KpiTile label="Max loss / lot" tone="neg" value={c.unlimited_loss ? "UNLIMITED" : rupees(c.max_loss_per_lot)} sub={c.unlimited_loss ? "no cap" : "worst case"} />
        <KpiTile label="Max profit / lot" tone="pos" value={c.unlimited_profit ? "∞" : rupees(c.max_profit_per_lot)} sub="at expiry" />
        <KpiTile label="Reward / risk" tone="cyan" value={c.risk_reward != null ? `${c.risk_reward.toFixed(2)}x` : "—"} sub="T1 vs stop" />
      </div>

      <div className="mt-4 grid gap-5 lg:grid-cols-[1.25fr_1fr]">
        <div>
          {c.curves && <PayoffChart curves={c.curves} breakevens={c.breakevens} spot={desk.header.price} />}
          <p className="mt-1 text-[11px] text-faint">P&amp;L per lot ({desk.header.lot_size} units). Stop and targets are model prices if the index reaches those levels within about a day.</p>
        </div>
        <div className="space-y-4">
          <Sizing c={c} />
          <div>
            <div className="mb-1.5 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-faint">
              Setup grade <Tip text={c.grade.note} /> <span className="ml-auto text-ink">{c.grade.points} pts</span>
            </div>
            <ul className="space-y-1 text-xs">
              {c.grade.breakdown.map((g) => (
                <li key={g.factor} className="flex items-center gap-2">
                  <span className={g.met ? "text-pos" : "text-neg"}>{g.met ? "✓" : "✕"}</span>
                  <span className={g.met ? "" : "text-muted"}>{g.factor}</span>
                  <span className="ml-auto font-bold tabular text-faint">{g.points > 0 ? `+${g.points}` : g.points}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Bullets title="For" tone="pos" items={c.supporting} />
        <Bullets title="Against" tone="neg" items={c.against} />
        <Bullets title="Enter only if" tone="cyan" items={c.entry_confirmation} badge={c.confirmed ? "met" : "not met"} />
        <Bullets title="Invalidated if" tone="warn" items={[...c.invalidation, ...c.exit_signals.map((e) => `Exit: ${e}`)]} />
      </div>
      {c.exclusions.length > 0 && (
        <div className="mt-4 rounded-xl border border-neg/40 bg-neg-bg px-3 py-2 text-xs text-neg">
          <span className="font-bold">Why it is excluded:</span> {c.exclusions.join(" ")}
        </div>
      )}
    </section>
  );
}

function Sizing({ c }: { c: DeskCandidate }) {
  const s = c.sizing;
  return (
    <div className="rounded-xl bg-panel-2/70 p-3">
      <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-faint">Position size <Tip text={s.rule} /></div>
      <div className="flex items-end gap-4">
        <div><div className={`text-4xl font-black tabular ${s.lots > 0 ? "text-cyan" : "text-neg"}`}>{s.lots}</div><div className="text-[10px] uppercase text-faint">lots</div></div>
        <div className="grid flex-1 grid-cols-2 gap-x-4 gap-y-1 text-xs tabular">
          <span className="text-faint">Budget</span><span className="text-right">{rupees(s.budget)}</span>
          <span className="text-faint">Max loss</span><span className="text-right text-neg">{rupees(s.max_loss_total)}</span>
          <span className="text-faint">At stop</span><span className="text-right text-neg">{rupees(s.stop_loss_total)}</span>
          <span className="text-faint">At target 1</span><span className="text-right text-pos">{rupees(s.target1_total)}</span>
          <span className="text-faint">Capital</span><span className="text-right">{rupees(s.capital)}</span>
          <span className="text-faint">Margin</span><span className={`text-right ${s.margin === "unavailable" ? "text-warn" : ""}`}>{s.margin === "unavailable" ? "unavailable" : "none"}</span>
        </div>
      </div>
    </div>
  );
}

function Bullets({ title, tone, items, badge }: { title: string; tone: Tone; items: string[]; badge?: string }) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider" style={{ color: TONE_COLOR[tone] }}>
        {title}{badge && <span className="rounded-full border border-line px-1.5 text-faint">{badge}</span>}
      </div>
      {items.length === 0 ? <p className="text-xs text-faint">None</p> : (
        <ul className="space-y-1 text-xs text-muted">{items.slice(0, 6).map((t, i) => <li key={i} className="flex gap-1.5"><span style={{ color: TONE_COLOR[tone] }}>•</span><span>{t}</span></li>)}</ul>
      )}
    </div>
  );
}

const SHORT: Record<string, string> = {
  trend: "Trend", momentum: "Momentum", structure: "Structure", directional_movement: "ADX / DI", vwap: "VWAP", global: "Global", positioning: "OI positioning",
};

function DirectionPanel({ desk }: { desk: Desk }) {
  const d = desk.direction;
  const tone = directionTone(d.label);
  const lv = d.levels ?? {};
  return (
    <section className="panel rounded-2xl p-4">
      <Heading tone={tone} right={<Pill tone={tone}>{d.label}</Pill>}>Market direction</Heading>
      {d.reason && <p className="text-sm text-warn">{d.reason}</p>}
      <div className="grid gap-4 sm:grid-cols-[auto_1fr] sm:items-center">
        <div className="flex justify-center"><Gauge value={d.composite} buy={0.2} sell={-0.2} label="Direction score" /></div>
        <div className="space-y-2">
          {d.components.map((c) => (
            <div key={c.key} className="grid grid-cols-[6.5rem_1fr_2.8rem] items-center gap-2" title={`${c.value} · ${c.reading}`}>
              <span className="truncate text-xs font-semibold">{SHORT[c.key] ?? c.label}</span>
              <SignalBar value={c.score} />
              <span className={`text-right text-[11px] font-bold tabular ${c.score == null ? "text-faint" : c.score >= 0.1 ? "text-pos" : c.score <= -0.1 ? "text-neg" : "text-muted"}`}>
                {c.score == null ? "n/a" : `${c.score >= 0 ? "+" : ""}${c.score.toFixed(2)}`}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2">
        <KpiTile label="India VIX" value={num(d.vix.level)} tone={d.vix.regime === "elevated" ? "neg" : d.vix.regime === "calm" ? "pos" : "cyan"} sub={`${d.vix.regime} · 5d ${formatPct(d.vix.change_5d, 1)}`} />
        <KpiTile label="ADX" value={num(d.adx, 1)} tone={d.adx >= 25 ? "purple" : "neutral"} sub={d.adx >= 25 ? "trending" : "weak trend"} />
        <KpiTile label="ATR (day)" value={num(d.atr, 0)} tone="warn" sub={formatPct(d.atr_pct, 2)} />
      </div>
      <div className="mt-4">
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint">Key levels</div>
        <div className="flex flex-wrap gap-1.5 text-[11px]">
          {[["S2", lv.s2], ["S1", lv.s1], ["Pivot", lv.pivot], ["R1", lv.r1], ["R2", lv.r2], ["20d low", lv.support_20], ["20d high", lv.resistance_20], ["SMA200", lv.sma200]].map(([k, v]) => (
            <span key={k as string} className={`rounded-full border px-2 py-0.5 tabular ${String(k).startsWith("S") && k !== "SMA200" ? "border-pos/40 text-pos" : String(k).startsWith("R") ? "border-neg/40 text-neg" : "border-line text-muted"}`}>
              {k} {level(v as number | null)}
            </span>
          ))}
        </div>
      </div>
      {d.missing.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {d.missing.map((m) => <Pill key={m} tone="neutral" title={m}>Missing: {m.split(" (")[0]}</Pill>)}
        </div>
      )}
    </section>
  );
}

type Metric = "oi" | "oi_change" | "volume";

function ChainPanel({ desk }: { desk: Desk }) {
  const [metric, setMetric] = useState<Metric>("oi");
  const s = desk.chain.summary;
  const rows = desk.chain.rows;
  const i = rows.findIndex((r) => r.strike === s.atm_strike);
  const near = rows.slice(Math.max(0, i - 11), i + 12);
  const max = Math.max(1, ...near.flatMap((r) => [Math.abs(r.CE[metric]), Math.abs(r.PE[metric])]));
  const labels: Record<Metric, string> = { oi: "Open interest", oi_change: "Change in OI", volume: "Volume" };
  return (
    <section className="panel rounded-2xl p-4">
      <Heading tone="purple" right={
        <div className="flex overflow-hidden rounded-full border border-line text-[11px] font-semibold">
          {(Object.keys(labels) as Metric[]).map((m) => (
            <button key={m} onClick={() => setMetric(m)} className={`px-2.5 py-1 ${m === metric ? "bg-purple-bg text-purple" : "text-muted hover:text-ink"}`}>{labels[m]}</button>
          ))}
        </div>
      }>Option chain</Heading>
      <div className="mb-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
        <Mini label="ATM IV" value={formatPct(s.atm_iv, 1)} />
        <Mini label="PCR (OI)" value={num(s.pcr_oi)} title="Put open interest ÷ call open interest for this expiry" />
        <Mini label="Max pain" value={level(s.max_pain)} />
        <Mini label="Exp. move" value={s.expected_move.pct != null ? `±${formatPct(s.expected_move.pct, 1)}` : "—"} />
        <Mini label="PE OI wall" value={level(s.oi_support[0]?.strike)} tone="pos" />
        <Mini label="CE OI wall" value={level(s.oi_resistance[0]?.strike)} tone="neg" />
      </div>
      <div className="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider">
        <span className="text-pos">◀ Put {labels[metric]}</span>
        <span className="flex items-center gap-1 text-faint">{metric === "oi_change" && "faded = reduction"} <Tip text={s.positioning.caveat} /></span>
        <span className="text-neg">Call {labels[metric]} ▶</span>
      </div>
      <div className="space-y-[3px]">
        {near.map((r) => {
          const atm = r.strike === s.atm_strike;
          const pv = r.PE[metric], cv = r.CE[metric];
          return (
            <div key={r.strike} className="grid grid-cols-[1fr_4.2rem_1fr] items-center gap-2 text-[11px]"
              title={`${r.strike}: put ${labels[metric]} ${pv.toLocaleString("en-IN")} · call ${labels[metric]} ${cv.toLocaleString("en-IN")}`}>
              <div className="flex justify-end"><div className="h-3 rounded-l-full" style={{ width: `${(Math.abs(pv) / max) * 100}%`, background: "var(--neon-green)", opacity: pv < 0 ? 0.3 : 0.75 }} /></div>
              <div className={`text-center font-bold tabular ${atm ? "rounded-full bg-cyan-bg text-cyan" : r.strike < desk.header.price ? "text-muted" : "text-faint"}`}>{r.strike.toLocaleString("en-IN")}</div>
              <div><div className="h-3 rounded-r-full" style={{ width: `${(Math.abs(cv) / max) * 100}%`, background: "var(--neon-red)", opacity: cv < 0 ? 0.3 : 0.75 }} /></div>
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-faint">{desk.chain.data_type === "synthetic" ? "Synthetic chain: positioning is shown for exploration and excluded from the direction score." : "Positioning is weak evidence on its own."}</p>
    </section>
  );
}

function Mini({ label, value, tone, title }: { label: string; value: string; tone?: Tone; title?: string }) {
  return (
    <div className="rounded-lg bg-panel-2/70 px-2 py-1.5" title={title}>
      <div className="text-[9px] font-semibold uppercase tracking-wider text-faint">{label}</div>
      <div className="text-sm font-bold tabular" style={{ color: tone ? TONE_COLOR[tone] : undefined }}>{value}</div>
    </div>
  );
}

function shortReason(reasons: string[]): string {
  const r = reasons.join(" ");
  if (/Unlimited loss/.test(r)) return "unlimited loss";
  if (/Margin requirement/.test(r)) return "margin data missing";
  if (/Risk budget/.test(r)) return "over budget";
  if (/spread/.test(r)) return "spread too wide";
  if (/open interest/.test(r)) return "illiquid";
  if (/no tradable/.test(r)) return "no price";
  return reasons.length ? "fails a rule" : "low grade";
}

function StrategyTable({ desk }: { desk: Desk }) {
  const cands = desk.decision.candidates;
  return (
    <section className="panel rounded-2xl p-4">
      <Heading tone="cyan">Strategies compared</Heading>
      {cands.length === 0 ? <p className="text-sm text-muted">No playbook applies to a {desk.direction.label} market.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-xs">
            <thead className="text-[10px] uppercase tracking-wider text-faint">
              <tr><th className="py-1 text-left">Strategy</th><th className="text-right">Net</th><th className="text-right">Max loss</th><th className="text-right">Max profit</th><th className="text-right">R:R</th><th className="text-left pl-3">Grade</th><th className="text-left">Status</th></tr>
            </thead>
            <tbody>
              {cands.map((c) => (
                <tr key={c.strategy} className="border-t border-line/50">
                  <td className="py-1.5 font-semibold">{c.label}<div className="text-[10px] font-normal text-faint">{c.legs.map((l) => `${l.side === "buy" ? "+" : "−"}${l.strike} ${l.type}`).join(" ")}</div></td>
                  <td className="text-right tabular">{c.net != null ? `₹${num(c.net)}` : "—"}<div className="text-[10px] text-faint">{c.kind}</div></td>
                  <td className="text-right tabular text-neg">{c.unlimited_loss ? "UNLIMITED" : rupees(c.max_loss_per_lot)}</td>
                  <td className="text-right tabular text-pos">{rupees(c.max_profit_per_lot)}</td>
                  <td className="text-right tabular">{c.risk_reward != null ? c.risk_reward.toFixed(2) : "—"}</td>
                  <td className="pl-3"><Pill tone={STATUS_TONE[c.grade ?? ""] ?? "neutral"}>{(c.grade ?? "—").replace(" SETUP", "")}</Pill></td>
                  <td title={c.exclusions.join(" ")}>{c.eligible ? <span className="font-bold text-pos">✓ eligible</span> : <span className="text-neg">✕ {shortReason(c.exclusions)}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-[11px] text-faint">Hover a status for every exclusion reason. Short-option strategies stay excluded until exchange margin data is loaded.</p>
    </section>
  );
}

function StrikeTable({ desk }: { desk: Desk }) {
  const prefer: "CE" | "PE" = desk.direction.label.includes("Bearish") ? "PE" : "CE";
  const [side, setSide] = useState<"CE" | "PE">(prefer);
  const ranked: StrikeRank[] = desk.decision.strikes[side] ?? [];
  const why = side === "CE" ? desk.decision.strikes.why_CE : desk.decision.strikes.why_PE;
  const top = ranked[0]?.score ?? 1;
  return (
    <section className="panel rounded-2xl p-4">
      <Heading tone="purple" right={
        <div className="flex overflow-hidden rounded-full border border-line text-[11px] font-semibold">
          {(["CE", "PE"] as const).map((k) => (
            <button key={k} onClick={() => setSide(k)} className={`px-3 py-1 ${k === side ? (k === "CE" ? "bg-pos-bg text-pos" : "bg-neg-bg text-neg") : "text-muted"}`}>Buy {k}</button>
          ))}
        </div>
      }>Strike comparison</Heading>
      {ranked.length === 0 ? <p className="text-sm text-muted">No strikes in the delta band have usable quotes.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-xs">
            <thead className="text-[10px] uppercase tracking-wider text-faint">
              <tr><th className="py-1 text-left">Strike</th><th className="text-right">Δ</th><th className="text-right">IV</th><th className="text-right">Ask</th><th className="text-right">Spread</th><th className="text-right">Decay/day</th><th className="text-right">1-ATR gain</th><th className="w-24 pl-3 text-left">Score</th></tr>
            </thead>
            <tbody>
              {ranked.map((r, n) => (
                <tr key={r.strike} className={`border-t border-line/50 ${n === 0 ? "bg-cyan-bg" : ""}`}>
                  <td className="py-1.5 font-bold tabular">{n === 0 && <span className="mr-1 text-cyan">★</span>}{r.strike.toLocaleString("en-IN")}</td>
                  <td className="text-right tabular">{Math.abs(r.delta).toFixed(2)}</td>
                  <td className="text-right tabular text-purple">{r.iv != null ? (r.iv * 100).toFixed(1) : "—"}</td>
                  <td className="text-right tabular">{num(r.ask)}</td>
                  <td className="text-right tabular">{formatPct(r.spread_pct, 1)}</td>
                  <td className="text-right tabular text-warn">{formatPct(r.decay_pct_per_day, 1)}</td>
                  <td className="text-right tabular text-pos">+{formatPct(r.one_atr_gain_pct, 0)}</td>
                  <td className="pl-3"><div className="h-2 rounded-full bg-panel-2"><div className="h-2 rounded-full bg-cyan" style={{ width: `${Math.max(5, (r.score / (top || 1)) * 100)}%`, opacity: 0.75 }} /></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {why && <p className="mt-2 text-xs text-muted"><span className="font-semibold text-cyan">Why:</span> {why}</p>}
    </section>
  );
}

function SignalsPanel({ signalId }: { signalId: string }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof deskApi.signals>> | null>(null);
  useEffect(() => { deskApi.signals().then(setData).catch(() => {}); }, [signalId]);
  if (!data) return null;
  return (
    <section className="panel rounded-2xl p-4">
      <Heading tone="warn" right={<span className="flex gap-1.5">{Object.entries(data.counts).map(([k, v]) => <Pill key={k} tone={STATUS_TONE[k] ?? "neutral"}>{k.replace(" SETUP", "")} {v}</Pill>)}</span>}>
        Signal history
      </Heading>
      <div className="flex flex-wrap gap-2">
        {data.signals.slice(0, 12).map((s) => (
          <span key={s.signal_id} className="rounded-lg border border-line bg-panel-2/60 px-2 py-1 text-[11px]" title={`${s.signal_id} · ${s.mode}`}>
            <span className="font-bold">{s.symbol}</span> · {formatDate(s.expiry)} · <span style={{ color: TONE_COLOR[STATUS_TONE[s.status] ?? "neutral"] }}>{s.status}</span>
            <span className="text-faint"> · {formatDateTime(s.created_at)}{s.mode === "dry_run" ? " · dry run" : ""}</span>
          </span>
        ))}
      </div>
      <p className="mt-2 text-[11px] text-faint">{data.performance} Every run is stored, including NO TRADE, and is never re-shown as a fresh signal.</p>
    </section>
  );
}
