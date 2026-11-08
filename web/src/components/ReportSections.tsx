"use client";

import { useState } from "react";
import { api, type AgentResult, type Evidence, type Replay, type Report, type Run } from "@/lib/api";
import { formatDateTime, formatInr, formatPct } from "@/lib/format";
import { Badge, Cites, EV, Panel, RatingBadge, Score, ScoreBar, StatusDot } from "./ui";

// ------------------------------------------------------------------ agent output

export function AgentFindings({ agent }: { agent?: AgentResult }) {
  const [showRemoved, setShowRemoved] = useState(false);
  if (!agent) return null;
  if (agent.status !== "completed") {
    return (
      <div className="rounded border border-dashed border-line px-3 py-2 text-xs text-muted">
        <StatusDot status={agent.status} /> <span className="font-medium">{agent.title}</span> {agent.status}: {agent.reason}
      </div>
    );
  }
  return (
    <div className="rounded border border-line bg-panel-2/50 p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="accent">AI-generated</Badge>
        <span className="font-medium">{agent.title}</span>
        <span className="text-faint">{agent.model} · {agent.version}</span>
      </div>
      {agent.summary && <p className="mt-2 text-sm">{agent.summary}</p>}
      <ul className="mt-2 space-y-1.5 text-sm">
        {agent.findings.map((f, i) => (
          <li key={i} className="flex gap-2">
            <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${f.stance === "positive" ? "bg-pos" : f.stance === "negative" ? "bg-neg" : "bg-faint"}`} />
            <span>
              {f.statement}
              <span className="ml-1 text-[10px] uppercase tracking-wide text-faint">{f.kind}</span>
              <Cites ids={f.evidence_ids} />
            </span>
          </li>
        ))}
      </ul>
      {agent.limitations && agent.limitations.length > 0 && (
        <div className="mt-2 text-xs text-muted">Limitations: {agent.limitations.join(" ")}</div>
      )}
      {agent.removed.length > 0 && (
        <div className="mt-2 text-xs">
          <button onClick={() => setShowRemoved((v) => !v)} className="text-warn underline">
            {agent.removed.length} statement(s) removed by verification
          </button>
          {showRemoved && (
            <ul className="mt-1 space-y-1 text-muted">
              {agent.removed.map((r, i) => <li key={i}>• “{r.text}”: {r.reason}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------- technical

export function TechnicalPanel({ report }: { report: Report }) {
  const t = report.technical;
  if (t.status !== "ok") return <Panel title="Technical analysis"><p className="text-sm text-muted">Unavailable: not enough price history.</p></Panel>;
  return (
    <Panel title="Technical analysis" subtitle="Deterministic indicators on completed daily sessions; not a recommendation on their own">
      <div className="mb-3 flex flex-wrap gap-2 text-xs">
        <Badge tone={t.trend === "uptrend" ? "pos" : t.trend === "downtrend" ? "neg" : "neutral"}>Trend: {t.trend}</Badge>
        {t.rsi_zone && <Badge>RSI {t.rsi_zone}</Badge>}
        {t.range_condition && <Badge>{t.range_condition}</Badge>}
        {Boolean(t.abnormal_volume) && <Badge tone="warn">Abnormal volume</Badge>}
      </div>
      <div className="grid gap-x-6 sm:grid-cols-2">
        <div>
          <EV id="price.last_close" label="Last close" />
          <EV id="ind.sma50" label="SMA 50" />
          <EV id="ind.sma200" label="SMA 200" />
          <EV id="ind.ema20" label="EMA 20" />
          <EV id="ind.vwap20" label="VWAP 20 (rolling)" />
          <EV id="ind.rsi14" label="RSI 14" />
          <EV id="ind.macd_hist" label="MACD histogram" />
        </div>
        <div>
          <EV id="ind.bb_upper" label="Bollinger upper" />
          <EV id="ind.bb_lower" label="Bollinger lower" />
          <EV id="ind.atr14" label="ATR 14" />
          <EV id="tech.volatility_regime" label="Volatility regime" />
          <EV id="tech.support_60" label="Support (60 sessions)" />
          <EV id="tech.resistance_60" label="Resistance (60 sessions)" />
          <EV id="tech.volume_ratio" label="Volume vs 50-day median" />
        </div>
      </div>
      <div className="mt-4 grid grid-cols-5 gap-1 text-center text-xs">
        <div />
        {["1m", "3m", "6m", "1y"].map((k) => <div key={k} className="text-muted">{k.toUpperCase()}</div>)}
        <div className="text-left text-muted">Stock</div>
        {["1m", "3m", "6m", "1y"].map((k) => <div key={k} className="tabular">{formatPct(report.returns.stock[k])}</div>)}
        <div className="text-left text-muted">NIFTY 50</div>
        {["1m", "3m", "6m", "1y"].map((k) => <div key={k} className="tabular">{formatPct(report.returns.benchmark[k])}</div>)}
        <div className="text-left text-muted">Relative</div>
        {["1m", "3m", "6m", "1y"].map((k) => {
          const v = report.returns.relative[k];
          return <div key={k} className={`tabular ${v == null ? "" : v >= 0 ? "text-pos" : "text-neg"}`}>{formatPct(v)}</div>;
        })}
      </div>
      <p className="mt-2 text-xs text-faint">Support and resistance are rolling extremes (lowest low / highest high) over 20, 60 and 250 sessions.</p>
      <div className="mt-3"><AgentFindings agent={report.agents.technical_analysis} /></div>
    </Panel>
  );
}

// -------------------------------------------------------------------------- risk

export function RiskPanel({ report }: { report: Report }) {
  const r = report.risk;
  return (
    <Panel title="Risk analysis" subtitle="Historical statistics; examples are analytical, not personal stop-loss or sizing advice">
      <EV id="risk.volatility_1y" label="Volatility (1Y, annualised)" />
      <EV id="risk.max_drawdown_1y" label="Max drawdown (1Y)" />
      <EV id="risk.max_drawdown_full" label="Max drawdown (full history)" />
      <EV id="risk.beta_1y" label="Beta vs NIFTY 50 (1Y)" />
      <EV id="risk.var95_1d" label="1-day VaR 95% (historical)" />
      <EV id="risk.median_traded_value_20d" label="Median daily traded value (20D)" />
      <EV id="calc.debt_to_equity" label="Debt to equity" />
      <EV id="event.next_earnings" label="Next results date (provider estimate)" />
      {r.downside_examples && (
        <p className="mt-2 text-xs text-muted">
          A typical adverse day (95% VaR) is about {formatInr(r.downside_examples.var95_rupees)} per share; two ATRs is {formatInr(r.downside_examples.two_atr_rupees)}. {r.downside_examples.note}
        </p>
      )}
      <div className="mt-3 space-y-1.5">
        {r.flags.length === 0 && <p className="text-sm text-muted">No risk flags raised by the rules.</p>}
        {r.flags.map((f) => (
          <div key={f.id} className="text-sm">
            <Badge tone={f.severity === "high" ? "neg" : f.severity === "medium" ? "warn" : "neutral"}>{f.severity}</Badge>{" "}
            <span className="font-medium">{f.title}.</span> <span className="text-muted">{f.detail}</span>
            <Cites ids={f.evidence_ids} />
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------------ fundamentals

const METRIC_GROUPS: [string, string[]][] = [
  ["Growth", ["revenue_growth", "net_income_growth", "q_revenue_yoy", "q_net_income_yoy"]],
  ["Profitability", ["gross_margin", "operating_margin", "ebitda_margin", "net_margin", "roe", "roa", "roce"]],
  ["Balance sheet and cash", ["debt_to_equity", "interest_coverage", "current_ratio", "fcf_margin", "cash_conversion"]],
  ["Valuation", ["pe", "pb", "dividend_yield"]],
];

export function FundamentalsPanel({ report }: { report: Report }) {
  const f = report.fundamentals;
  if (f.status !== "ok") {
    return (
      <Panel title="Fundamentals">
        <p className="text-sm text-muted">Financial statements are unavailable for this run.</p>
        <div className="mt-3"><AgentFindings agent={report.agents.financial_analysis} /></div>
      </Panel>
    );
  }
  const inr = f.currency === "INR";
  const cols = ["revenue", "operating_income", "net_income", "diluted_eps", "operating_cash_flow", "total_debt", "equity"];
  const colLabels: Record<string, string> = {
    revenue: "Revenue", operating_income: "Operating income", net_income: "Net income", diluted_eps: "Diluted EPS",
    operating_cash_flow: "Operating cash flow", total_debt: "Total debt", equity: "Equity",
  };
  return (
    <Panel title="Fundamentals" subtitle={`Calculated in Decimal by the engine from provider statements · EPS basis: ${f.eps_basis ?? "—"} · filing dates not provided by the dev source`}>
      {f.sector_note && <p className="mb-3 rounded bg-warn-bg px-3 py-2 text-xs text-warn">{f.sector_note}</p>}
      <div className="grid gap-x-6 gap-y-4 md:grid-cols-2 xl:grid-cols-4">
        {METRIC_GROUPS.map(([title, keys]) => (
          <div key={title}>
            <div className="mb-1 text-xs font-medium text-muted">{title}</div>
            {keys.filter((k) => f.metrics[k]).map((k) => {
              const m = f.metrics[k];
              return (
                <div key={k} className="border-b border-line/60 py-1.5 text-sm last:border-0" title={m.sector_note ?? m.reason ?? undefined}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-muted">{m.label}</span>
                    <span className={`tabular ${m.status !== "ok" || m.sector_note ? "text-faint" : ""}`}>
                      {m.status === "ok" ? m.display : m.status === "not_meaningful" ? "n/m" : "n/a"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-faint">
                    <span>{m.sector_note ? "not meaningful for sector" : m.status !== "ok" ? m.reason : m.period}</span>
                    <Cites ids={[m.evidence_id]} />
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
      {f.annual_table.length > 0 && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[640px] text-right text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="py-1 text-left font-medium">{inr ? "Annual (₹ crore; EPS in ₹)" : `Annual (${f.currency})`}</th>
                {cols.map((c) => <th key={c} className="py-1 font-medium">{colLabels[c]}</th>)}
              </tr>
            </thead>
            <tbody className="tabular">
              {f.annual_table.map((row) => (
                <tr key={row.period} className="border-t border-line/60">
                  <td className="py-1 text-left">{row.label}</td>
                  {cols.map((c) => {
                    const cell = row[c] as { display: string; line_item: string } | null;
                    return <td key={c} className="py-1" title={cell?.line_item}>{cell ? (inr ? cell.display.replace(" crore", "") : cell.display) : <span className="text-faint">n/a</span>}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {f.quarterly_table.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[480px] text-right text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="py-1 text-left font-medium">Quarterly</th>
                <th className="py-1 font-medium">Revenue</th>
                <th className="py-1 font-medium">Net income</th>
                <th className="py-1 font-medium">Diluted EPS</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {f.quarterly_table.map((row) => (
                <tr key={row.period} className="border-t border-line/60">
                  <td className="py-1 text-left">{row.label}</td>
                  {["revenue", "net_income", "diluted_eps"].map((c) => {
                    const cell = row[c] as { display: string } | null;
                    return <td key={c} className="py-1">{cell ? cell.display : <span className="text-faint">n/a</span>}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-faint">Gaps mean the provider did not report that quarter; nothing is filled in.</p>
        </div>
      )}
      {f.notes.map((n, i) => <p key={i} className="mt-2 text-xs text-warn">{n}</p>)}
      <div className="mt-4"><AgentFindings agent={report.agents.financial_analysis} /></div>
    </Panel>
  );
}

// -------------------------------------------------------------- company and news

export function CompanyPanel({ report }: { report: Report }) {
  const c = report.company;
  const agent = report.agents.company_research;
  return (
    <Panel title="Company and sector" subtitle="Provider profile text; segment, geography and competitor data are not available from the dev source">
      {c.status !== "ok" ? (
        <p className="text-sm text-muted">Company profile unavailable.</p>
      ) : (
        <>
          <p className="text-sm leading-relaxed">{c.summary}</p>
          <div className="mt-2 text-xs text-muted">
            {[c.sector, c.industry, c.city, c.employees ? `${c.employees.toLocaleString("en-IN")} employees` : null].filter(Boolean).join(" · ")}
            {c.website && <> · <a className="text-accent underline" href={c.website} target="_blank" rel="noreferrer noopener">website</a></>}
          </div>
        </>
      )}
      <div className="mt-3"><AgentFindings agent={agent} /></div>
      {agent?.swot && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          {Object.entries(agent.swot).map(([k, pts]) => (
            <div key={k} className="rounded border border-line p-2">
              <div className="mb-1 font-medium capitalize text-muted">{k}</div>
              {pts.length === 0 ? <div className="text-faint">No evidence-backed points</div> : (
                <ul className="space-y-1">{pts.map((p, i) => <li key={i}>{p.point}<Cites ids={p.evidence_ids} /></li>)}</ul>
              )}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

export function NewsPanel({ report }: { report: Report }) {
  const n = report.news;
  return (
    <Panel title="News and events" subtitle={`${n.items.length} unique headlines (${n.duplicates_removed} syndicated duplicates removed) · official exchange filings unavailable without a licensed source`}>
      {n.items.length === 0 && <p className="text-sm text-muted">No news returned by the provider.</p>}
      <ul className="space-y-3">
        {n.items.map((item) => {
          const c = item.classification;
          return (
            <li key={item.evidence_id} className="text-sm">
              <div className="flex flex-wrap items-center gap-1.5">
                {c ? (
                  <Badge tone={c.label === "positive" ? "pos" : c.label === "negative" ? "neg" : c.label === "uncertain" ? "warn" : "neutral"} title="AI classification of the headline">
                    AI: {c.label}
                  </Badge>
                ) : <Badge>unclassified</Badge>}
                {c?.unverified_rumour && <Badge tone="warn">unverified</Badge>}
                {c && <span className="text-xs text-faint">{c.event_type} · {c.time_horizon}</span>}
              </div>
              <div className="mt-0.5">
                {item.url ? <a href={item.url} target="_blank" rel="noreferrer noopener" className="hover:text-accent">{item.title}</a> : item.title}
                <Cites ids={[item.evidence_id]} />
              </div>
              <div className="text-xs text-muted">{item.publisher ?? "Unknown publisher"} · {formatDateTime(item.published_at)}{item.duplicates.length > 0 && ` · also from ${item.duplicates.map((d) => d.publisher).join(", ")}`}</div>
              {c?.relevance && <div className="text-xs text-muted">{c.relevance}</div>}
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-faint">Headlines only: articles are not retrieved or verified. Labels are AI-generated and do not confirm the events.</p>
      <div className="mt-3"><AgentFindings agent={report.agents.news_events} /></div>
    </Panel>
  );
}

// ---------------------------------------------------------------- scoring detail

export function SubScoresPanel({ report }: { report: Report }) {
  const subs = Object.values(report.sub_scores);
  const horizons = (["medium", "long"] as const).map((h) => report.horizons[h]);
  return (
    <Panel title="How the ratings were scored" subtitle={report.ratings.scoring_method}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-xs text-muted">
            <tr>
              <th className="py-1 text-left font-medium">Sub-score</th>
              <th className="w-40 py-1 font-medium">Score</th>
              {horizons.map((h) => <th key={h.horizon} className="py-1 text-right font-medium">{h.label} weight</th>)}
              <th className="py-1 text-left font-medium">Components</th>
            </tr>
          </thead>
          <tbody>
            {subs.map((s) => (
              <tr key={s.name} className="border-t border-line/60 align-top">
                <td className="py-2 pr-3">
                  <div>{s.label}</div>
                  {s.reason && <div className="text-xs text-faint">{s.reason}</div>}
                  {s.note && <div className="text-xs text-faint">{s.note}</div>}
                </td>
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2"><Score value={s.score} /><ScoreBar value={s.score} /></div>
                </td>
                {horizons.map((h) => {
                  const c = h.contributions.find((x) => x.sub_score === s.name);
                  return <td key={h.horizon} className="tabular py-2 text-right text-muted">{c ? formatPct(c.weight, 0) : "—"}</td>;
                })}
                <td className="py-2 pl-3 text-xs">
                  {s.components.map((c) => (
                    <div key={c.name} className={c.status !== "ok" ? "text-faint" : ""}>
                      {c.label}: {c.display} <Score value={c.score} />
                      <Cites ids={c.evidence_ids} />
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-faint">
        BUY needs a composite of at least {report.ratings.thresholds.buy} and {formatPct(report.ratings.thresholds.min_agreement, 0)} agreement; SELL at most {report.ratings.thresholds.sell}.
        Below {formatPct(report.ratings.thresholds.min_coverage, 0)} evidence coverage, or when a critical data check fails, the engine returns INSUFFICIENT DATA instead of HOLD.
      </p>
    </Panel>
  );
}

// ---------------------------------------------------------- quality and evidence

export function QualityPanel({ report }: { report: Report }) {
  const gates = [...report.data_quality.gates].sort((a, b) => Number(a.passed) - Number(b.passed));
  return (
    <Panel title="Data-quality checks" subtitle={`Status: ${report.data_quality.status}. Critical failures block the ratings they affect.`}>
      <ul className="space-y-2 text-sm">
        {gates.map((g, i) => (
          <li key={`${g.id}-${i}`} className="flex gap-2">
            <Badge tone={g.passed ? "pos" : g.severity === "critical" ? "neg" : g.severity === "warning" ? "warn" : "neutral"}>
              {g.passed ? "pass" : g.status}
            </Badge>
            <div className="min-w-0">
              <span className="font-medium">{g.title}</span>
              {g.severity === "critical" && <span className="ml-1 text-[10px] uppercase text-faint">critical{g.affects.length && !g.affects.includes("all") ? ` · ${g.affects.join(", ")}` : ""}</span>}
              <div className="text-xs text-muted">{g.message}</div>
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function AgentPanel({ report }: { report: Report }) {
  const agents = Object.values(report.agents);
  const ran = agents.filter((a) => a.status === "completed");
  return (
    <Panel title="Research agents" subtitle="Agents explain evidence; numbers come from the calculation engine and are checked by the verifier">
      {ran.length === 0 && (
        <p className="mb-3 text-sm text-muted">
          No agent ran in this report. Add a free GEMINI_API_KEY (aistudio.google.com/apikey) or an ANTHROPIC_API_KEY to .env to enable the research and bull/bear debate agents.
        </p>
      )}
      <div className="grid gap-2 md:grid-cols-2">
        {agents.map((a) => (
          <div key={a.agent} className="flex items-start gap-2 rounded border border-line p-2 text-xs">
            <span className="mt-1"><StatusDot status={a.status} /></span>
            <div>
              <div className="font-medium">{a.title} <span className="text-faint">{a.version}</span></div>
              <div className="text-muted">
                {a.status === "completed"
                  ? `${a.findings.length} verified findings, ${a.removed.length} removed${a.usage ? ` · ${a.usage.input_tokens + a.usage.output_tokens} tokens` : ""}`
                  : `${a.status}: ${a.reason}`}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export function ReproducibilityPanel({ run, report }: { run: Run; report: Report }) {
  const [replay, setReplay] = useState<Replay | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const v = report.versions;
  return (
    <Panel
      title="Reproducibility and versions"
      right={
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setErr(null);
            try { setReplay(await api.replay(run.analysis_run_id)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
          }}
          className="rounded border border-line px-2 py-1 text-xs hover:border-accent hover:text-accent disabled:opacity-50"
        >
          {busy ? "Replaying…" : "Replay from snapshot"}
        </button>
      }
    >
      <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
        <div><dt className="inline text-muted">Run </dt><dd className="inline font-mono">{run.analysis_run_id}</dd></div>
        <div><dt className="inline text-muted">Snapshot </dt><dd className="inline font-mono">{v.snapshot_id}</dd></div>
        <div><dt className="inline text-muted">Output hash </dt><dd className="inline font-mono">{run.deterministic_hash?.slice(0, 24)}…</dd></div>
        <div><dt className="inline text-muted">Engine </dt><dd className="inline">{v.engine}</dd></div>
        <div><dt className="inline text-muted">Rules </dt><dd className="inline">{v.rules}</dd></div>
        <div><dt className="inline text-muted">Agent model </dt><dd className="inline">{v.agent_model}</dd></div>
        <div><dt className="inline text-muted">Requested </dt><dd className="inline">{formatDateTime(report.requested_at)}</dd></div>
        <div><dt className="inline text-muted">Market data as of </dt><dd className="inline">{formatDateTime(report.market_data_as_of)}</dd></div>
      </dl>
      {err && <p className="mt-2 text-xs text-neg">{err}</p>}
      {replay && (
        <div className={`mt-3 rounded px-3 py-2 text-xs ${replay.reproducible ? "bg-pos-bg text-pos" : replay.versions_changed ? "bg-warn-bg text-warn" : "bg-neg-bg text-neg"}`}>
          {replay.reproducible ? "Reproducible: " : replay.versions_changed ? "Different engine version: " : "Mismatch: "}
          snapshot integrity {replay.snapshot_integrity}; recomputed hash {replay.replay_hash.slice(0, 16)}… {replay.reproducible ? "matches" : "differs from"} the stored hash.{" "}
          {replay.explanation}
          {replay.versions_changed && (
            <div className="mt-1">Engine {replay.versions.engine?.stored ?? "unknown"} → {replay.versions.engine?.current}.</div>
          )}
          <div className="mt-1">
            Ratings now: {Object.entries(replay.replay_ratings).map(([h, r]) => `${h} ${r}`).join(", ")}
            {JSON.stringify(replay.replay_ratings) !== JSON.stringify(replay.stored_ratings) &&
              ` (stored: ${Object.entries(replay.stored_ratings).map(([h, r]) => `${h} ${r}`).join(", ")})`}.
          </div>
          <div className="mt-1 text-muted">{replay.note}</div>
        </div>
      )}
    </Panel>
  );
}

export function EvidencePanel({ evidence }: { evidence: Evidence[] }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const shown = evidence.filter((e) => !q || `${e.id} ${e.label}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <Panel
      title="Evidence store"
      subtitle={`${evidence.length} items: every displayed figure, with source, formula and inputs`}
      right={<button onClick={() => setOpen((o) => !o)} className="text-xs text-accent">{open ? "Hide" : "Show all"}</button>}
    >
      {open ? (
        <>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter evidence" className="mb-3 w-full rounded border border-line bg-bg px-2 py-1 text-sm" />
          <div className="max-h-[480px] overflow-y-auto">
            <table className="w-full text-xs">
              <tbody>
                {shown.map((e) => (
                  <tr key={e.id} className="border-t border-line/60 align-top">
                    <td className="py-1 pr-2"><Cites ids={[e.id]} /></td>
                    <td className="py-1 pr-2">{e.label}</td>
                    <td className={`tabular py-1 pr-2 text-right ${e.status !== "ok" ? "text-faint" : ""}`}>{e.display}</td>
                    <td className="py-1 text-faint">{e.formula ? e.formula.expression : e.source?.dataset}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="text-sm text-muted">Click any citation chip in the report to inspect one item, or show the full store.</p>
      )}
    </Panel>
  );
}

export function RatingsInline({ ratings }: { ratings: Record<string, string> }) {
  return (
    <span className="flex gap-1">
      {Object.entries(ratings).map(([h, r]) => <span key={h} className="flex items-center gap-1 text-xs text-muted">{h}<RatingBadge rating={r} /></span>)}
    </span>
  );
}
