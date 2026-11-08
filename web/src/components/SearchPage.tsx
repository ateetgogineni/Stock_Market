"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Health, type Instrument, type Run, type UniverseCounts } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { Pill, RatingLight } from "./viz";

export default function SearchPage() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Instrument[]>([]);
  const [universe, setUniverse] = useState<Instrument[]>([]);
  const [counts, setCounts] = useState<UniverseCounts | null>(null);
  const [recent, setRecent] = useState<Run[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setError(`Backend not reachable (${e.message}). Start it with: uvicorn app.main:app`));
    api.instruments().then((r) => { setUniverse(r.instruments); setCounts(r.counts); }).catch(() => {});
    api.runs(8).then((r) => setRecent(r.runs)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!q.trim()) return; // results are hidden while the box is empty
    const t = setTimeout(() => {
      api.search(q).then((r) => setResults(r.results)).catch((e) => setError(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  async function start(inst: Instrument, exchange: string) {
    setStarting(`${inst.instrument_id}:${exchange}`);
    try {
      const { analysis_run_id } = await api.createRun(inst.instrument_id, exchange);
      router.push(`/runs/${analysis_run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setStarting(null);
    }
  }

  const shown = q.trim() ? results : [];
  const total = counts ? counts.core + counts.extended : null;

  return (
    <div className="space-y-8">
      <section className="pt-6 text-center">
        <h1 className="bg-gradient-to-r from-cyan via-purple to-neg bg-clip-text text-4xl font-black tracking-tight text-transparent sm:text-5xl">
          Research any NSE stock
        </h1>
        <p className="mt-2 text-sm text-muted">Name, symbol or ISIN. Every number links to its source.</p>
        <div className="mx-auto mt-6 max-w-2xl">
          <div className="relative">
            <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-xl text-cyan">⌕</span>
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Reliance, TCS, INE009A01021…"
              className="w-full rounded-2xl border border-cyan/40 bg-panel/90 py-4 pl-12 pr-4 text-lg outline-none transition focus:border-cyan focus:shadow-[0_0_16px_rgba(94,200,219,0.25)]"
            />
          </div>
          {health && (
            <div className="mt-3 flex flex-wrap justify-center gap-2">
              <Pill tone="warn" title="Unofficial Yahoo Finance data via yfinance; not an authorised NSE/BSE feed">Dev data · delayed</Pill>
              <Pill tone={health.agents.credentials && health.agents.enabled ? "pos" : "neutral"}
                title={health.agents.credentials ? `${health.agents.provider ?? ""} ${health.agents.model}` : "Add a free GEMINI_API_KEY (aistudio.google.com/apikey) or an ANTHROPIC_API_KEY to .env to turn the research agents on"}>
                AI agents {health.agents.enabled && health.agents.credentials ? `on · ${health.agents.provider === "gemini" ? "Gemini" : "Claude"}` : "off"}
              </Pill>
              <Pill tone="purple">No trading</Pill>
              {total && <Pill tone="cyan">{total.toLocaleString("en-IN")} stocks</Pill>}
            </div>
          )}
        </div>
      </section>

      {error && <div className="rounded-xl border border-neg/40 bg-neg-bg px-4 py-3 text-sm text-neg">{error}</div>}

      {q.trim() && (
        <section className="mx-auto max-w-3xl space-y-2">
          {shown.length === 0 && (
            <p className="text-center text-sm text-muted">No NSE main-board stock matches “{q.trim()}”. BSE-only and SME companies aren&apos;t loaded yet.</p>
          )}
          {shown.map((inst) => (
            <div key={inst.instrument_id} className="panel flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold">{inst.name}</span>
                  {inst.coverage === "core" ? <Pill tone="pos" title="Checked end to end against the data provider">Core</Pill>
                    : <Pill tone="warn" title={inst.coverage_note ?? undefined}>Extended</Pill>}
                </div>
                <div className="text-[11px] text-faint">ISIN {inst.isin}</div>
              </div>
              <div className="flex gap-2">
                {inst.listings.map((l) => (
                  <button
                    key={l.exchange}
                    disabled={!!starting}
                    onClick={() => start(inst, l.exchange)}
                    title={l.verification_source}
                    className="rounded-xl border border-cyan/50 bg-cyan-bg px-4 py-2 text-sm font-bold text-cyan transition hover:shadow-[0_0_10px_rgba(94,200,219,0.35)] disabled:opacity-50"
                  >
                    {starting === `${inst.instrument_id}:${l.exchange}` ? "Starting…" : `Analyse ${l.exchange}`}
                    {l.series && l.series !== "EQ" && <span className="ml-1 text-xs text-warn">{l.series}</span>}
                    {!l.identifier_verified && <span className="ml-1 text-xs text-warn">?</span>}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      {recent.length > 0 && (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <span className="h-4 w-1 rounded-full bg-purple" style={{ boxShadow: "0 0 3px var(--neon-purple)" }} />
            <h2 className="text-sm font-bold uppercase tracking-wider">Recent analyses</h2>
            <Link href="/runs" className="ml-auto text-xs font-semibold text-cyan">All →</Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {recent.map((r) => (
              <Link key={r.analysis_run_id} href={`/runs/${r.analysis_run_id}`} className="panel block rounded-2xl p-4 transition hover:border-cyan/60">
                <div className="truncate text-sm font-bold">{r.summary?.name ?? r.symbol}</div>
                <div className="text-[11px] text-faint">{r.exchange}:{r.symbol} · {formatDateTime(r.requested_at)}</div>
                <div className="mt-3 flex items-end justify-between gap-2">
                  <div className="text-lg font-black tabular">{r.summary?.price != null ? `₹${r.summary.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` : "—"}</div>
                  <div className="flex flex-col items-end gap-1">
                    {(["medium", "long"] as const).map((h) => r.summary?.ratings[h] && (
                      <span key={h} className="flex items-center gap-1 text-[10px] uppercase text-faint">{h === "medium" ? "Med" : "Long"} <RatingLight rating={r.summary.ratings[h]} size="sm" /></span>
                    ))}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section>
        <div className="mb-3 flex items-center gap-2">
          <span className="h-4 w-1 rounded-full bg-pos" style={{ boxShadow: "0 0 3px var(--neon-green)" }} />
          <h2 className="text-sm font-bold uppercase tracking-wider">Core companies</h2>
          {counts && <span className="ml-auto text-[11px] text-faint">+ {counts.extended.toLocaleString("en-IN")} more via search</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          {universe.map((u) => (
            <button key={u.instrument_id} onClick={() => setQ(u.listings[0].symbol)}
              className="rounded-full border border-line bg-panel/80 px-3 py-1 text-xs font-semibold text-muted transition hover:border-pos hover:text-pos hover:shadow-[0_0_8px_rgba(95,211,154,0.3)]">
              {u.listings[0].symbol}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
