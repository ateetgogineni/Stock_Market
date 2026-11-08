"use client";

import { useEffect, useState } from "react";
import { api, type DataSource, type SystemSources } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { KpiTile, Pill, SectionTitle, Tip, type Tone } from "./viz";

const STATUS: Record<DataSource["status"], { tone: Tone; label: string; icon: string }> = {
  official: { tone: "pos", label: "Official", icon: "✓" },
  licensed: { tone: "pos", label: "Licensed", icon: "✓" },
  dev_only: { tone: "warn", label: "Dev only", icon: "!" },
  synthetic: { tone: "purple", label: "Synthetic", icon: "≈" },
  missing: { tone: "neg", label: "Missing", icon: "✕" },
};

export default function DataSources() {
  const [data, setData] = useState<SystemSources | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.sources().then(setData, (e: Error) => setError(e.message));
  }, []);

  if (error) return <div className="panel rounded-2xl p-5 text-sm text-neg">Could not load data sources: {error}</div>;
  if (!data) return <div className="h-96 animate-pulse rounded-2xl bg-panel-2" />;

  const count = (s: DataSource["status"]) => data.sources.filter((x) => x.status === s).length;
  const a = data.agents;
  return (
    <div className="space-y-5">
      <section className="panel rounded-2xl p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone="purple">v{data.app_version}</Pill>
          <Pill tone="neg">Trading {data.trading}</Pill>
        </div>
        <h1 className="mt-2 text-3xl font-black tracking-tight">Data sources</h1>
        <p className="text-xs text-faint">What every screen runs on, how far it can be trusted, and what could replace it.</p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <KpiTile label="Official" value={count("official") + count("licensed")} tone="pos" sub="exchange files" />
          <KpiTile label="Dev only" value={count("dev_only")} tone="warn" sub="unlicensed, delayed" />
          <KpiTile label="Synthetic" value={count("synthetic")} tone="purple" sub="generated prices" />
          <KpiTile label="Missing" value={count("missing")} tone="neg" sub="gated as unavailable" />
        </div>
      </section>

      <section className="panel rounded-2xl p-4">
        <SectionTitle>In use</SectionTitle>
        <div className="grid gap-2 md:grid-cols-2">
          {data.sources.map((s) => {
            const st = STATUS[s.status];
            return (
              <div key={s.id} className="flex gap-3 rounded-xl bg-panel-2/50 p-3">
                <Pill tone={st.tone} className="h-fit shrink-0">{st.icon} {st.label}</Pill>
                <div className="min-w-0 text-xs">
                  <div className="flex items-center gap-1.5 text-sm font-semibold">
                    {s.name}
                    <Tip text={s.notes} />
                  </div>
                  <div className="text-faint">
                    {s.provider ?? "not connected"}{s.as_of ? ` · ${formatDate(s.as_of)}` : ""}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {s.used_for.map((u) => <span key={u} className="rounded bg-panel-2 px-1.5 py-0.5 text-[10px] text-muted">{u}</span>)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="panel rounded-2xl p-4">
          <SectionTitle tone="purple" right={<Pill tone={a.enabled && a.credentials ? "pos" : "warn"}>{a.enabled && a.credentials ? "On" : "Off"}</Pill>}>AI agents</SectionTitle>
          <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-xs">
            <dt className="text-faint">Provider</dt><dd className="font-semibold">{a.provider}</dd>
            <dt className="text-faint">Model</dt><dd className="font-semibold">{a.model}</dd>
            <dt className="text-faint">Bull side</dt><dd><span className="text-pos">●</span> {a.debate.bull}</dd>
            <dt className="text-faint">Bear side</dt><dd><span className="text-neg">●</span> {a.debate.bear}</dd>
            {a.fallbacks.length > 0 && <><dt className="text-faint">Fallbacks</dt><dd className="text-muted">{a.fallbacks.join(" → ")}</dd></>}
            <dt className="text-faint">Key</dt><dd>{a.credentials ? "configured in .env" : "not set"}</dd>
          </dl>
        </section>
        <section className="panel rounded-2xl p-4">
          <SectionTitle tone="cyan">Engines and rules</SectionTitle>
          <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-xs">
            <dt className="text-faint">Analytics</dt><dd className="font-mono">{data.engines.analytics}</dd>
            <dt className="text-faint">Forecast</dt><dd className="font-mono">{data.engines.forecast} <span className="text-warn">paper</span></dd>
            <dt className="text-faint">Options</dt><dd className="font-mono">{data.engines.options}</dd>
            <dt className="text-faint">Pricing</dt><dd className="font-mono">{data.engines.pricing.join(" + ")}</dd>
            <dt className="text-faint">Rating rules</dt><dd className="font-mono">{data.engines.rating_rules} <span className="text-warn">draft</span></dd>
            <dt className="text-faint">Trade rules</dt><dd className="font-mono">{data.engines.trade_rules} <span className="text-warn">draft</span></dd>
          </dl>
        </section>
      </div>

      <section className="panel rounded-2xl p-4">
        <SectionTitle tone="warn" right={<Tip text="Candidates only. None is connected. Check licence terms, redistribution rights and cost with each vendor before use." />}>Upgrade path</SectionTitle>
        <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
          {data.candidates.map((c) => (
            <div key={c.name} className="rounded-xl border border-dashed border-line p-3 text-xs">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold">{c.url ? <a href={c.url} target="_blank" rel="noreferrer" className="hover:text-cyan">{c.name}</a> : c.name}</div>
                  <div className="text-faint">{c.kind}</div>
                </div>
                <Pill tone="neutral" className="shrink-0">Not connected</Pill>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {c.replaces.map((r) => <span key={r} className="rounded bg-warn-bg px-1.5 py-0.5 text-[10px] text-warn">replaces {r}</span>)}
              </div>
              <div className="mt-1.5 text-muted">{c.covers.join(" · ")}</div>
              {c.caveat && <div className="mt-1 text-[11px] text-faint">{c.caveat}</div>}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
