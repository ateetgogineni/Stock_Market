"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { formatDateTime } from "@/lib/format";
import { optionsApi, type Underlying } from "@/lib/options";
import { Pill } from "../viz";

export default function OptionsHome() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Underlying[]>([]);
  const [featured, setFeatured] = useState<Underlying[]>([]);
  const [meta, setMeta] = useState<{ count: number; date: string } | null>(null);
  const [recent, setRecent] = useState<{ chain_id: string; symbol: string; created_at: string; spot: number }[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    optionsApi.underlyings().then((r) => { setFeatured(r.results); setMeta({ count: r.count, date: r.contract_master_date }); }).catch((e) => setError(e.message));
    optionsApi.chains().then((r) => setRecent(r.chains)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!q.trim()) return;
    const t = setTimeout(() => optionsApi.underlyings(q).then((r) => setResults(r.results)).catch((e) => setError(e.message)), 200);
    return () => clearTimeout(t);
  }, [q]);

  async function open(symbol: string) {
    setBusy(symbol);
    setError(null);
    try {
      const { chain_id } = await optionsApi.createChain(symbol);
      router.push(`/options/${chain_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  const list = q.trim() ? results : featured;

  return (
    <div className="space-y-8">
      <section className="pt-6 text-center">
        <h1 className="bg-gradient-to-r from-purple via-cyan to-pos bg-clip-text text-4xl font-black tracking-tight text-transparent sm:text-5xl">
          Options lab
        </h1>
        <p className="mt-2 text-sm text-muted">Option chains, Greeks and strategy payoffs for NSE F&amp;O.</p>
        <div className="mx-auto mt-6 max-w-2xl">
          <div className="relative">
            <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-xl text-purple">⌕</span>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="NIFTY, BANKNIFTY, RELIANCE…"
              className="w-full rounded-2xl border border-purple/40 bg-panel/90 py-4 pl-12 pr-4 text-lg outline-none transition focus:border-purple focus:shadow-[0_0_16px_rgba(169,138,230,0.3)]" />
          </div>
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            <Pill tone="warn" title="No licensed NSE options feed is configured. Premiums, OI and volume are generated; contracts and the underlying price are real.">Synthetic prices</Pill>
            {meta && <Pill tone="cyan" title={`NSE F&O contract master dated ${meta.date}`}>{meta.count} underlyings</Pill>}
            <Pill tone="purple">No orders</Pill>
          </div>
        </div>
      </section>

      {error && <div className="mx-auto max-w-3xl rounded-xl border border-neg/40 bg-neg-bg px-4 py-3 text-sm text-neg">{error}</div>}

      <Link href="/options/desk" className="panel mx-auto flex max-w-3xl items-center gap-4 rounded-2xl p-4 transition hover:border-cyan/60">
        <span className="text-3xl">◎</span>
        <div>
          <div className="font-black">Index trade desk</div>
          <div className="text-xs text-muted">Pick NIFTY or BANKNIFTY and an expiry: direction, best candidate or NO TRADE, entry, stop, targets and sizing.</div>
        </div>
        <span className="ml-auto text-sm font-bold text-cyan">Open →</span>
      </Link>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {list.map((u) => (
          <button key={u.symbol} disabled={!!busy || !u.price_symbol} onClick={() => open(u.symbol)} title={u.price_note ?? undefined}
            className="panel rounded-2xl p-4 text-left transition hover:border-purple/70 hover:shadow-[0_0_8px_rgba(169,138,230,0.25)] disabled:opacity-50">
            <div className="flex items-center gap-2">
              <span className="text-lg font-black">{u.symbol}</span>
              <Pill tone={u.type === "index" ? "purple" : "cyan"}>{u.type}</Pill>
            </div>
            <div className="truncate text-xs text-muted">{u.name}</div>
            <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-faint">
              <span>Lot <b className="text-ink">{u.expiries[0]?.lot_size ?? "—"}</b></span>
              <span>Expiries <b className="text-ink">{u.expiries.length}</b></span>
              <span className={u.settlement === "physical" ? "text-warn" : ""}>{u.settlement}-settled</span>
            </div>
            {!u.price_symbol && <div className="mt-2 text-[11px] text-warn">No verified price source</div>}
            {busy === u.symbol && <div className="mt-2 text-[11px] text-cyan">Building chain…</div>}
          </button>
        ))}
        {q.trim() && list.length === 0 && <p className="col-span-full text-center text-sm text-muted">No F&amp;O underlying matches “{q}”. Only NSE derivatives-segment stocks and indices have options.</p>}
      </section>

      {recent.length > 0 && (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <span className="h-4 w-1 rounded-full bg-purple" style={{ boxShadow: "0 0 3px var(--neon-purple)" }} />
            <h2 className="text-sm font-bold uppercase tracking-wider">Recent chains</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {recent.slice(0, 10).map((c) => (
              <Link key={c.chain_id} href={`/options/${c.chain_id}`} className="rounded-full border border-line bg-panel/80 px-3 py-1.5 text-xs font-semibold text-muted hover:border-cyan hover:text-cyan">
                {c.symbol} · {c.spot.toLocaleString("en-IN")} · {formatDateTime(c.created_at)}
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
