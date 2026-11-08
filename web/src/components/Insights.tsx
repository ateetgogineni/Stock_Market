"use client";

// Bull-vs-bear debate and the walk-forward forecast. Both are paper outputs: neither feeds the rating.

import type { AgentResult, ForecastHorizon, ForecastModelName, Report } from "@/lib/api";
import { formatDate, formatInr, formatPct } from "@/lib/format";
import { Cites } from "./ui";
import { Pill, SectionTitle, TONE_VAR, Tip, type Tone } from "./viz";

// ----------------------------------------------------------------------- debate

function Side({ agent, tone, label }: { agent?: AgentResult; tone: Tone; label: string }) {
  const color = TONE_VAR[tone];
  if (!agent || agent.status !== "completed") {
    return (
      <div className="rounded-xl border border-dashed border-line p-4 text-xs text-muted">
        <div className="mb-1 font-bold uppercase tracking-wider" style={{ color }}>{label}</div>
        {agent ? `${agent.status}: ${agent.reason ?? ""}` : "Not run in this report."}
      </div>
    );
  }
  return (
    <div className="relative overflow-hidden rounded-xl border bg-panel-2/40 p-4" style={{ borderColor: `color-mix(in srgb, ${color} 35%, transparent)` }}>
      <div className="absolute inset-y-0 left-0 w-0.5" style={{ background: color, boxShadow: `0 0 4px ${color}` }} />
      <div className="flex items-center gap-2">
        <span className="text-sm font-black uppercase tracking-widest" style={{ color }}>{label}</span>
        <span className="ml-auto truncate text-[10px] text-faint" title={agent.version}>{agent.model}</span>
      </div>
      {agent.summary && <p className="mt-2 text-sm font-medium">{agent.summary}</p>}
      <ul className="mt-3 space-y-1.5 text-[13px]">
        {agent.findings.map((f, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: color }} />
            <span>{f.statement}<Cites ids={f.evidence_ids} /></span>
          </li>
        ))}
      </ul>
      {agent.limitations?.[0] && (
        <div className="mt-3 rounded-lg bg-panel-2 px-2.5 py-1.5 text-[11px] text-muted">
          <span className="font-semibold text-faint">Biggest risk to this case: </span>{agent.limitations[0]}
        </div>
      )}
      {agent.removed.length > 0 && <div className="mt-2 text-[10px] text-warn">{agent.removed.length} unsupported statement(s) removed by the verifier</div>}
    </div>
  );
}

export function DebatePanel({ report }: { report: Report }) {
  const bull = report.agents.bull_case, bear = report.agents.bear_case;
  const ran = [bull, bear].filter((a) => a?.status === "completed");
  const nBull = bull?.status === "completed" ? bull.findings.length : 0;
  const nBear = bear?.status === "completed" ? bear.findings.length : 0;
  const share = nBull + nBear ? nBull / (nBull + nBear) : 0.5;
  const sameModel = bull?.model && bear?.model && bull.model === bear.model;
  return (
    <section className="panel rounded-2xl p-4">
      <SectionTitle tone="purple" right={
        <span className="flex items-center gap-2">
          <Pill tone="purple">AI debate</Pill>
          <Tip text="Two agents argue opposite sides from the same verified evidence, on different models where available. Every number is checked against its citation. The debate does not change the rating." />
        </span>
      }>Bull vs bear</SectionTitle>
      {ran.length === 0 ? (
        <p className="text-sm text-muted">Debate agents did not run. They need an AI key (see Data sources).</p>
      ) : (
        <>
          <div className="mb-3 flex items-center gap-2 text-[11px] tabular">
            <span className="font-bold text-pos">{nBull} for</span>
            <div className="flex h-2 flex-1 overflow-hidden rounded-full bg-panel-2" role="img" aria-label={`${nBull} bull arguments, ${nBear} bear arguments`}>
              <div style={{ width: `${share * 100}%`, background: "var(--neon-green)" }} />
              <div className="w-0.5 bg-bg" />
              <div className="flex-1" style={{ background: "var(--neon-red)" }} />
            </div>
            <span className="font-bold text-neg">{nBear} against</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <Side agent={bull} tone="pos" label="Bull case" />
            <Side agent={bear} tone="neg" label="Bear case" />
          </div>
          <p className="mt-2 text-[10px] text-faint">
            Argument counts show how much each side found, not who is right.{sameModel ? " Both sides ran on the same model this time." : ""}
          </p>
        </>
      )}
    </section>
  );
}

// --------------------------------------------------------------------- forecast

const MODEL_LABEL: Record<ForecastModelName, string> = { random_walk: "Random walk", drift: "Drift", momentum_ridge: "Momentum model" };

function RangeRow({ h, lo, hi, spot }: { h: ForecastHorizon; lo: number; hi: number; spot: number }) {
  const s = h.scenarios!;
  const x = (v: number) => `${((v - lo) / (hi - lo || 1)) * 100}%`;
  const tone = h.approved ? "var(--neon-cyan)" : "var(--muted)";
  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-[11px]">
        <span className="font-bold uppercase tracking-wider">{h.sessions === 21 ? "1 month" : "3 months"}</span>
        {h.approved
          ? <Pill tone="cyan" title={h.reason}>{MODEL_LABEL[h.shown_model]} · beat baseline</Pill>
          : <Pill tone="neutral" title={h.reason}>No edge · baseline range</Pill>}
        <span className="ml-auto tabular text-muted">median {formatInr(s.base)}</span>
      </div>
      <div className="relative h-9">
        <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-line" />
        <div className="absolute top-1/2 h-3 -translate-y-1/2 rounded-full"
          style={{ left: x(s.bear), width: `calc(${x(s.bull)} - ${x(s.bear)})`, background: `color-mix(in srgb, ${tone} 28%, transparent)`, border: `1px solid ${tone}` }} />
        <div className="absolute top-1/2 h-5 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded" style={{ left: x(s.base), background: tone }} title={`Median ${formatInr(s.base)}`} />
        <div className="absolute top-0 h-9 w-px -translate-x-1/2 border-l border-dashed border-ink/60" style={{ left: x(spot) }} title={`Last close ${formatInr(spot)}`} />
      </div>
      <div className="flex justify-between text-[11px] tabular">
        <span className="text-neg" title="10th percentile">{formatInr(s.bear)}</span>
        <span className="text-pos" title="90th percentile">{formatInr(s.bull)}</span>
      </div>
    </div>
  );
}

function Scorecard({ h }: { h: ForecastHorizon }) {
  const names: ForecastModelName[] = ["random_walk", "drift", "momentum_ridge"];
  const maes = names.map((n) => h.models[n].holdout.mae ?? 0);
  const max = Math.max(...maes, 1e-9);
  const base = h.models.random_walk.holdout.mae;
  return (
    <div className="rounded-xl bg-panel-2/50 p-3">
      <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-faint">
        {h.sessions === 21 ? "1 month" : "3 months"} · holdout error
        <Tip text={`Average absolute error on the last ${h.models.random_walk.holdout.n} walk-forward forecasts (from ${formatDate(h.holdout_from)}), which no model saw while training. Shorter bar is better. ${h.reason}`} />
      </div>
      <div className="space-y-1.5">
        {names.map((n) => {
          const m = h.models[n].holdout;
          const better = n !== "random_walk" && m.mae != null && base != null && m.mae < base;
          const color = n === "random_walk" ? "var(--muted)" : better ? "var(--neon-cyan)" : "var(--neon-yellow)";
          return (
            <div key={n} className="grid grid-cols-[96px_1fr_88px] items-center gap-2 text-[11px]">
              <span className={h.selected === n ? "font-bold text-cyan" : "text-muted"}>{MODEL_LABEL[n]}</span>
              <div className="h-2 rounded-full bg-panel-2">
                <div className="h-2 rounded-full" style={{ width: `${((m.mae ?? 0) / max) * 100}%`, background: color }} />
              </div>
              <span className="tabular text-right text-muted" title={`Direction right ${m.direction == null ? "n/a" : formatPct(m.direction, 0)}; 10-90% band held ${formatPct(m.coverage, 0)}`}>
                {formatPct(m.mae, 1)}{m.direction != null && <span className="text-faint"> · {formatPct(m.direction, 0)}↕</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ForecastCard({ report, detailed }: { report: Report; detailed?: boolean }) {
  const f = report.forecast;
  const hs = (f.horizons ?? []).filter((h) => h.scenarios);
  const anyApproved = hs.some((h) => h.approved);
  return (
    <section className="panel rounded-2xl p-4">
      <SectionTitle tone="cyan" right={
        <span className="flex items-center gap-2">
          <Pill tone="warn" title="Forecasts are logged for evaluation only and never change the rating.">Paper mode</Pill>
          {f.method && <Tip text={`${f.method.evaluation} ${f.method.caveat} ${f.method.returns}.`} />}
        </span>
      }>Forecast range</SectionTitle>
      {f.status !== "ok" || !f.spot || hs.length === 0 ? (
        <p className="text-sm text-muted">{f.reason ?? "Forecast unavailable."}</p>
      ) : (() => {
        const lo = Math.min(...hs.map((h) => h.scenarios!.bear), f.spot) * 0.98;
        const hi = Math.max(...hs.map((h) => h.scenarios!.bull), f.spot) * 1.02;
        return (
          <>
            <div className="space-y-3">
              {hs.map((h) => <RangeRow key={h.sessions} h={h} lo={lo} hi={hi} spot={f.spot!} />)}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-faint">
              <span>▮ 10–90% range</span><span>│ median</span><span>┊ last close {formatInr(f.spot)}</span>
            </div>
            <p className="mt-2 text-[11px] text-muted">
              {anyApproved
                ? "A model beat the random-walk baseline on data it never saw. Treat the range as a paper forecast."
                : "No model beat a random walk on unseen data, so the bands show normal volatility only, not a prediction."}
            </p>
            {detailed && <div className="mt-3 grid gap-2 md:grid-cols-2">{hs.map((h) => <Scorecard key={h.sessions} h={h} />)}</div>}
          </>
        );
      })()}
    </section>
  );
}
