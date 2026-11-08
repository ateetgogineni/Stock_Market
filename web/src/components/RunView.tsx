"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { api, type ChartData, type Evidence, type Horizon, type Report, type Run, type Step } from "@/lib/api";
import { DATA_STATUS_LABEL, formatCrore, formatDate, formatDateTime, formatInr, formatPct } from "@/lib/format";
import {
  AgentPanel, CompanyPanel, EvidencePanel, FundamentalsPanel, NewsPanel, QualityPanel, ReproducibilityPanel,
  RiskPanel, SubScoresPanel, TechnicalPanel,
} from "./ReportSections";
import { DebatePanel, ForecastCard } from "./Insights";
import { Cites, EvidenceProvider, StatusDot } from "./ui";
import {
  DotStrip, Gauge, KpiTile, Pill, RangeBar, RatingLight, Ring, RsiMeter, SignalBar, Sparkline, Tip, scoreTone, type Tone,
} from "./viz";

const PriceChart = dynamic(() => import("./PriceChart"), { ssr: false });

const SHORT: Record<string, string> = {
  technical: "Technicals", momentum: "Momentum", earnings_momentum: "Earnings", fundamental_quality: "Quality",
  valuation: "Valuation", risk: "Risk", news_events: "News",
};

export default function RunView({ runId }: { runId: string }) {
  const [run, setRun] = useState<Run | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [chart, setChart] = useState<ChartData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const r = await api.run(runId);
        if (stop) return;
        setRun(r);
        if (r.status === "queued" || r.status === "running") {
          timer = setTimeout(poll, 1000);
        } else if (r.report) {
          api.evidence(runId).then((e) => !stop && setEvidence(e.evidence)).catch(() => {});
          api.chart(runId).then((c) => !stop && setChart(c)).catch(() => {});
        }
      } catch (e) {
        if (!stop) setError((e as Error).message);
      }
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [runId]);

  if (error) return <div className="rounded-xl border border-neg/40 bg-neg-bg px-4 py-3 text-sm text-neg">{error}</div>;
  if (!run) return <p className="text-sm text-muted">Loading analysis…</p>;

  const report = run.report;
  if (!report) {
    return (
      <div className="space-y-5">
        <div className="panel rounded-2xl p-5">
          <div className="text-xs text-faint">{run.exchange}:{run.symbol}</div>
          <div className="mt-1 text-2xl font-bold text-cyan text-glow-cyan">{run.status === "failed" ? "Run failed" : "Analysing…"}</div>
          {run.error && <code className="mt-2 block text-xs text-neg">{run.error.split("\n")[0]}</code>}
        </div>
        <Activity steps={run.activity ?? []} live />
      </div>
    );
  }

  return (
    <EvidenceProvider evidence={evidence}>
      <div className="space-y-5">
        <Hero report={report} chart={chart} />
        <Verdict report={report} />
        <KpiStrip report={report} />
        <section className="panel rounded-2xl p-4">
          <div className="mb-3 flex items-center gap-2">
            <span className="h-4 w-1 rounded-full bg-cyan" style={{ boxShadow: "0 0 3px var(--neon-cyan)" }} />
            <h2 className="text-sm font-bold uppercase tracking-wider">Price</h2>
            <span className="ml-auto text-[11px] text-faint">to {formatDate(report.price.last_session)}</span>
          </div>
          {chart ? <PriceChart data={chart} /> : <div className="h-[560px] animate-pulse rounded-xl bg-panel-2" />}
        </section>
        <SignalBars report={report} />
        <div className="grid gap-5 lg:grid-cols-[1fr_1.6fr]">
          <ForecastCard report={report} />
          <DebatePanel report={report} />
        </div>
        <DetailTabs report={report} run={run} evidence={evidence} />
        <p className="text-center text-[11px] text-faint">{report.disclaimer}</p>
      </div>
    </EvidenceProvider>
  );
}

// ------------------------------------------------------------------------- hero

function Hero({ report, chart }: { report: Report; chart: ChartData | null }) {
  const { instrument: i, price: p, market } = report;
  const up = (p.change ?? 0) >= 0;
  const hist = p.history;
  const short = hist != null && hist.sessions < 250;
  const closes = chart ? chart.bars.slice(-250).map((b) => b.close) : [];
  const ent = p.source.entitlement;
  return (
    <section className="panel relative overflow-hidden rounded-2xl p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="purple">{i.exchange}:{i.symbol}</Pill>
        <Pill tone="cyan" title={`Data status: ${DATA_STATUS_LABEL[p.data_status]}. ${p.basis}, as of ${formatDateTime(p.as_of)}`}>{DATA_STATUS_LABEL[p.data_status] ?? p.data_status}</Pill>
        {i.coverage === "extended" && <Pill tone="warn" title={i.coverage_note ?? undefined}>Extended</Pill>}
        {i.series && i.series !== "EQ" && <Pill tone="warn">{i.series} series</Pill>}
        {!ent.production_use && <Pill tone="warn" title={ent.notes}>{ent.type === "synthetic" ? "Synthetic data" : "Dev data"}</Pill>}
        {short && <Pill tone="warn" title="Less than a year of trading history">{hist?.recently_listed ? `Listed ${formatDate(hist.listing_date)}` : `${hist?.sessions} sessions`}</Pill>}
        <span className="ml-auto text-[11px] text-faint" title={market.note}>Market {market.status.replace("_", " ")}</span>
      </div>
      <div className="mt-3 grid gap-5 md:grid-cols-[1.3fr_1fr]">
        <div>
          <h1 className="text-3xl font-black tracking-tight">{i.name}</h1>
          <div className="text-xs text-faint">{[i.sector, i.industry].filter(Boolean).join(" · ") || "Sector unavailable"} · ISIN {i.isin}</div>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <span className="text-5xl font-black tabular text-ink text-glow-cyan">{formatInr(p.price)}</span>
            {p.change != null && (
              <Pill tone={up ? "pos" : "neg"} className="mb-2 text-sm">{up ? "▲" : "▼"} {p.change.toFixed(2)} ({formatPct(p.change_pct)})</Pill>
            )}
          </div>
          <div className="mt-1 text-[11px] text-faint">{p.basis} · {formatDateTime(p.as_of)}</div>
        </div>
        <div className="flex flex-col justify-between gap-4">
          {closes.length > 1 && <Sparkline values={closes} tone={closes[closes.length - 1] >= closes[0] ? "pos" : "neg"} />}
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-faint">{short ? "Range since listing" : "52-week range"}</div>
            <RangeBar low={p.low_52w} high={p.high_52w} value={p.price} lowLabel={formatInr(p.low_52w)} highLabel={formatInr(p.high_52w)} />
          </div>
          <div className="flex gap-6 text-xs">
            <div><div className="text-[10px] uppercase tracking-wider text-faint">Market cap</div><div className="font-bold tabular">{formatCrore(p.market_cap)}</div></div>
            <div><div className="text-[10px] uppercase tracking-wider text-faint">Source</div><div className="font-bold">{p.source.provider}</div></div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------- verdict

function Verdict({ report }: { report: Report }) {
  const offered = (["short", "medium", "long"] as const).map((h) => report.horizons[h]).filter((h) => h.abstention_kind !== "horizon_disabled");
  const noRating = offered.length > 0 && offered.every((h) => h.rating === "INSUFFICIENT_DATA");
  const dq = report.data_quality;
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="h-4 w-1 rounded-full bg-purple" style={{ boxShadow: "0 0 3px var(--neon-purple)" }} />
        <h2 className="text-sm font-bold uppercase tracking-wider">Verdict</h2>
        <Pill tone="warn" title={report.ratings.validation_note}>Draft rules</Pill>
        <span className="ml-auto flex items-center gap-2 text-[11px] text-faint">
          Data checks {dq.passed}/{dq.total}
          <DotStrip items={dq.gates.map((g) => ({ id: g.id, status: g.passed ? "pass" : g.severity === "critical" ? "fail" : g.severity === "warning" ? "warn" : "info", title: `${g.title}: ${g.message}` }))} />
        </span>
      </div>
      {noRating && (
        <div className="mb-3 rounded-xl border border-warn/40 bg-warn-bg px-4 py-2 text-sm text-warn">
          No rating yet: {firstSentence(offered[0]?.abstention_reasons[0] ?? "")}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-3">
        {(["short", "medium", "long"] as const).map((h) => <HorizonCard key={h} h={report.horizons[h]} />)}
      </div>
    </section>
  );
}

function firstSentence(text: string): string {
  const body = text.includes(": ") ? text.slice(text.indexOf(": ") + 2) : text;
  const m = body.match(/^.*?[.!?](\s|$)/);
  return (m ? m[0] : body).trim();
}

function HorizonCard({ h }: { h: Horizon }) {
  const abstained = h.rating === "INSUFFICIENT_DATA";
  // Reports stored before abstention kinds existed: the short horizon was always switched off.
  const disabled = h.abstention_kind === "horizon_disabled" || (h.abstention_kind == null && h.horizon === "short" && abstained);
  return (
    <div className={`panel rounded-2xl p-4 ${disabled ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-2">
        <div>
          <div className="text-sm font-bold">{h.label}</div>
          <div className="text-[11px] text-faint">{h.window}</div>
        </div>
        <div className="ml-auto"><RatingLight rating={h.rating} muted={disabled} /></div>
      </div>
      {abstained ? (
        <p className="mt-4 text-sm text-muted">{disabled ? "Not offered for any stock yet." : firstSentence(h.abstention_reasons[0] ?? "")}</p>
      ) : (
        <>
          <div className="mt-3 flex items-center justify-between gap-2">
            <Gauge value={h.composite} label={`${h.label} composite`} />
            <div className="flex flex-col gap-2">
              <Ring value={h.coverage} label="Coverage" />
              <Ring value={h.agreement} label="Agreement" />
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {h.contributions.slice(0, 3).map((c) => (
              <Pill key={c.sub_score} tone={scoreTone(c.score)} title={c.label}>
                {c.score >= 0 ? "▲" : "▼"} {SHORT[c.sub_score] ?? c.label} {c.score >= 0 ? "+" : ""}{c.score.toFixed(2)}
              </Pill>
            ))}
          </div>
        </>
      )}
      <details className="mt-3 text-xs">
        <summary className="text-cyan">Why?</summary>
        <div className="mt-2 space-y-1.5 text-muted">
          {abstained ? h.abstention_reasons.map((a, i) => <p key={i}>• {a}</p>) : (
            <>
              {h.hold_reason && <p>{h.hold_reason}</p>}
              {h.key_reasons.map((k) => <p key={k.sub_score}>• {k.text}<Cites ids={k.evidence_ids} /></p>)}
              {h.strongest_opposing && <p className="text-warn">Against: {h.strongest_opposing.text}</p>}
              {h.invalidation.map((c, i) => <p key={i}>↺ {c.condition}</p>)}
            </>
          )}
        </div>
      </details>
    </div>
  );
}

// -------------------------------------------------------------------------- KPIs

function KpiStrip({ report }: { report: Report }) {
  const comp = Object.fromEntries(Object.values(report.sub_scores).flatMap((s) => s.components.map((c) => [c.name, c])));
  const t = report.technical as Record<string, number | string | null | undefined>;
  const m = report.fundamentals.metrics ?? {};
  const rel6 = report.returns.relative?.["6m"] ?? null;
  const rel3 = report.returns.relative?.["3m"] ?? null;
  const rel = rel6 ?? rel3;
  const trend = (t.trend as string | undefined) ?? "unavailable";
  const trendTone: Tone = trend === "uptrend" ? "pos" : trend === "downtrend" ? "neg" : "neutral";
  const risk = report.risk as Record<string, unknown>;
  const dd = (risk.max_drawdown_1y as { value: number } | null | undefined)?.value ?? null;
  const vol = (risk.volatility_1y as number | null | undefined) ?? null;
  const tone = (name: string): Tone => (comp[name]?.status === "ok" ? scoreTone(comp[name].score) : "neutral");
  const metric = (k: string) => (m[k]?.status === "ok" && !m[k]?.sector_note ? m[k].display : m[k]?.sector_note ? "n/m" : "—");
  const dq = report.data_quality;
  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <KpiTile label="Trend" icon={trend === "uptrend" ? "↗" : trend === "downtrend" ? "↘" : "→"} tone={trendTone}
        value={trend === "unavailable" ? "—" : trend.toUpperCase()} sub={t.price_vs_sma200 != null ? `${formatPct(t.price_vs_sma200 as number)} vs SMA200` : "needs 200 sessions"} />
      <KpiTile label="RSI 14" value={t.rsi14 != null ? (t.rsi14 as number).toFixed(1) : "—"} tone={t.rsi14 == null ? "neutral" : (t.rsi14 as number) > 70 ? "neg" : (t.rsi14 as number) < 30 ? "pos" : "cyan"}>
        <RsiMeter value={(t.rsi14 as number | null) ?? null} />
      </KpiTile>
      <KpiTile label={rel6 != null ? "6M vs NIFTY" : "3M vs NIFTY"} value={formatPct(rel)} tone={rel == null ? "neutral" : rel >= 0 ? "pos" : "neg"} sub="relative return" />
      <KpiTile label="Volatility 1Y" value={formatPct(vol)} tone={tone("volatility_1y")} sub="annualised" />
      <KpiTile label="Max drawdown 1Y" value={formatPct(dd)} tone={tone("max_drawdown_1y")} sub="peak to trough" />
      <KpiTile label="ROE" value={metric("roe")} tone={tone("roe")} sub={m.roe?.period} />
      <KpiTile label="Revenue growth" value={metric("revenue_growth")} tone={tone("revenue_growth")} sub={m.revenue_growth?.period} />
      <KpiTile label="P/E" value={metric("pe")} tone={tone("pe")} sub={m.pe?.status === "ok" ? m.pe.period : m.pe?.reason ?? undefined} title={m.pe?.reason ?? undefined} />
      <KpiTile label="Debt / equity" value={metric("debt_to_equity")} tone={tone("debt_to_equity")} sub={m.debt_to_equity?.sector_note ? "not used for lenders" : m.debt_to_equity?.period} />
      <KpiTile label="Data quality" value={`${dq.passed}/${dq.total}`} tone={dq.status === "good" ? "pos" : dq.status === "degraded" ? "warn" : "neg"} sub={dq.status} />
    </section>
  );
}

// ------------------------------------------------------------------- signal bars

function SignalBars({ report }: { report: Report }) {
  const subs = Object.values(report.sub_scores);
  const flags = report.risk.flags ?? [];
  return (
    <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
      <div className="panel rounded-2xl p-4">
        <div className="mb-3 flex items-center gap-2">
          <span className="h-4 w-1 rounded-full bg-cyan" style={{ boxShadow: "0 0 3px var(--neon-cyan)" }} />
          <h2 className="text-sm font-bold uppercase tracking-wider">Signals</h2>
          <span className="ml-auto flex gap-3 text-[10px] uppercase tracking-wider text-faint"><span className="text-neg">◀ negative</span><span className="text-pos">positive ▶</span></span>
        </div>
        <div className="space-y-2.5">
          {subs.map((s) => (
            <div key={s.name} className="grid grid-cols-[7rem_1fr_3rem] items-center gap-3" title={s.reason ?? s.components.map((c) => `${c.label}: ${c.display}`).join(" · ")}>
              <span className="truncate text-xs font-semibold">{SHORT[s.name] ?? s.label}</span>
              <SignalBar value={s.score} />
              <span className={`text-right text-xs font-bold tabular ${s.score == null ? "text-faint" : s.score >= 0.1 ? "text-pos" : s.score <= -0.1 ? "text-neg" : "text-muted"}`}>
                {s.score == null ? "n/a" : `${s.score >= 0 ? "+" : ""}${s.score.toFixed(2)}`}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="panel rounded-2xl p-4">
        <div className="mb-3 flex items-center gap-2">
          <span className="h-4 w-1 rounded-full bg-neg" style={{ boxShadow: "0 0 3px var(--neon-red)" }} />
          <h2 className="text-sm font-bold uppercase tracking-wider">Risk flags</h2>
          <span className="ml-auto text-xs font-bold text-neg">{flags.length}</span>
        </div>
        {flags.length === 0 ? <p className="text-sm text-pos">No risk flags raised.</p> : (
          <div className="flex flex-wrap gap-2">
            {flags.map((f) => (
              <Pill key={f.id} tone={f.severity === "high" ? "neg" : f.severity === "medium" ? "warn" : "neutral"} title={f.detail}>⚠ {f.title}</Pill>
            ))}
          </div>
        )}
        {report.news.items.length > 0 && (
          <div className="mt-4">
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint">Latest headlines</div>
            <ul className="space-y-1.5">
              {report.news.items.slice(0, 3).map((n) => {
                const c = n.classification?.label;
                const color = c === "positive" ? "var(--neon-green)" : c === "negative" ? "var(--neon-red)" : c === "uncertain" ? "var(--neon-yellow)" : "var(--faint)";
                return (
                  <li key={n.evidence_id} className="flex gap-2 text-xs">
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: color, boxShadow: `0 0 2px ${color}` }} />
                    <span className="line-clamp-2 text-muted">{n.title}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- detail tabs

const TABS = ["Fundamentals", "Technicals", "Risk", "News", "Company", "Scoring", "Forecast", "Data checks", "Activity", "Agents", "Evidence"] as const;

function DetailTabs({ report, run, evidence }: { report: Report; run: Run; evidence: Evidence[] }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Fundamentals");
  return (
    <section>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${tab === t ? "border-cyan bg-cyan-bg text-cyan glow-cyan" : "border-line text-muted hover:border-purple hover:text-purple"}`}>
            {t}
          </button>
        ))}
      </div>
      {tab === "Fundamentals" && <FundamentalsPanel report={report} />}
      {tab === "Technicals" && <TechnicalPanel report={report} />}
      {tab === "Risk" && <RiskPanel report={report} />}
      {tab === "News" && <NewsPanel report={report} />}
      {tab === "Company" && <CompanyPanel report={report} />}
      {tab === "Scoring" && <SubScoresPanel report={report} />}
      {tab === "Forecast" && <ForecastCard report={report} detailed />}
      {tab === "Data checks" && <QualityPanel report={report} />}
      {tab === "Activity" && <Activity steps={run.activity ?? []} />}
      {tab === "Agents" && <><AgentPanel report={report} /><div className="mt-4"><ReproducibilityPanel run={run} report={report} /></div></>}
      {tab === "Evidence" && <EvidencePanel evidence={evidence} />}
    </section>
  );
}

function Activity({ steps, live }: { steps: Step[]; live?: boolean }) {
  const done = steps.filter((s) => !["queued", "running"].includes(s.status)).length;
  return (
    <section className="panel rounded-2xl p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="h-4 w-1 rounded-full bg-purple" style={{ boxShadow: "0 0 3px var(--neon-purple)" }} />
        <h2 className="text-sm font-bold uppercase tracking-wider">Pipeline</h2>
        <span className="ml-auto text-xs text-faint">{done}/{steps.length}</span>
      </div>
      {live && (
        <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-panel-2">
          <div className="h-full rounded-full bg-cyan transition-all" style={{ width: `${(done / Math.max(steps.length, 1)) * 100}%`, boxShadow: "0 0 4px var(--neon-cyan)" }} />
        </div>
      )}
      <ol className="grid gap-2 sm:grid-cols-2">
        {steps.map((s) => (
          <li key={s.id} className="flex items-start gap-2.5 rounded-lg bg-panel-2/60 px-3 py-2" title={s.message ?? s.description}>
            <span className="mt-1"><StatusDot status={s.status} /></span>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-xs font-semibold">
                {s.name}
                {s.kind === "agent" && <span className="rounded bg-purple-bg px-1 text-[9px] font-bold text-purple">AI</span>}
              </div>
              <div className="truncate text-[11px] text-faint">{s.message ?? s.description}</div>
            </div>
          </li>
        ))}
      </ol>
      {!live && <p className="mt-2 text-[11px] text-faint">Hover a step for its full message. <Tip text="Each service and agent writes its status as the run progresses." /></p>}
    </section>
  );
}
