"use client";

import { useEffect, useMemo, useState } from "react";
import { optionsApi, type Evaluation, type Template } from "@/lib/options";
import { KpiTile, Pill, type Tone } from "../viz";

const OUTLOOK_TONE: Record<string, Tone> = {
  bullish: "pos", "mildly bullish": "pos", bearish: "neg", "range-bound": "purple", "big move either way": "warn",
};
const money = (v: number | null | undefined) => (v == null ? "—" : `₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`);

export default function StrategyLab({ chainId, expiry, underlyingType, spot }: { chainId: string; expiry: string; underlyingType: string; spot: number }) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [template, setTemplate] = useState("bull_call_spread");
  const [width, setWidth] = useState(2);
  const [lots, setLots] = useState(1);
  const [ev, setEv] = useState<Evaluation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    optionsApi.templates().then((r) => setTemplates(r.templates)).catch(() => {});
  }, []);

  useEffect(() => {
    let live = true;
    optionsApi.evaluate(chainId, { template, expiry, width, lots })
      .then((r) => { if (live) { setEv(r); setError(null); } })
      .catch((e) => { if (live) { setEv(null); setError(e.message); } });
    return () => { live = false; };
  }, [chainId, expiry, template, width, lots]);

  const p = ev?.payoff;
  return (
    <section className="panel rounded-2xl p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="h-4 w-1 rounded-full bg-pos" style={{ boxShadow: "0 0 3px var(--neon-green)" }} />
        <h2 className="text-sm font-bold uppercase tracking-wider">Strategy lab</h2>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <Stepper label="Width" value={width} set={setWidth} min={1} max={10} title="Strikes between legs" />
          <Stepper label="Lots" value={lots} set={setLots} min={1} max={50} />
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {templates.map((t) => {
          const tone = OUTLOOK_TONE[t.outlook] ?? "cyan";
          const active = t.id === template;
          const disabled = t.stock_only && underlyingType !== "stock";
          return (
            <button key={t.id} disabled={disabled} onClick={() => setTemplate(t.id)} title={disabled ? "Needs the underlying shares; not available on an index" : `${t.outlook}: ${t.explain}`}
              className={`rounded-full border px-2.5 py-1 text-[11px] font-bold transition disabled:opacity-30 ${active ? "glow-cyan" : ""}`}
              style={{ borderColor: active ? `var(--neon-${tone === "pos" ? "green" : tone === "neg" ? "red" : tone === "warn" ? "yellow" : tone})` : "var(--border)",
                color: `var(--neon-${tone === "pos" ? "green" : tone === "neg" ? "red" : tone === "warn" ? "yellow" : tone})`,
                background: active ? "rgba(255,255,255,0.06)" : "transparent" }}>
              {t.label}
            </button>
          );
        })}
      </div>

      {error && <div className="mt-4 rounded-xl border border-neg/40 bg-neg-bg px-3 py-2 text-sm text-neg">{error}</div>}
      {ev && (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-black">{ev.label}</span>
            <Pill tone={OUTLOOK_TONE[ev.outlook] ?? "cyan"}>{ev.outlook}</Pill>
            <Pill tone={ev.risk.verdict === "rejected" ? "neg" : ev.risk.verdict === "passed" ? "pos" : "warn"} title={ev.risk.rejections.join(" ") || "Risk rules checked"}>
              Risk {ev.risk.verdict.replaceAll("_", " ")}
            </Pill>
            <Pill tone="warn" title={ev.risk.opportunity_reason}>{ev.risk.opportunity_status.replaceAll("_", " ")}</Pill>
          </div>
          {p && (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                <KpiTile label="Max profit" tone="pos" value={p.unlimited_profit ? "∞" : money(p.max_profit)} sub={p.unlimited_profit ? "unlimited" : "at expiry"} />
                <KpiTile label="Max loss" tone="neg" value={p.unlimited_loss ? <span className="animate-pulse">UNLIMITED</span> : `-${money(p.max_loss)}`} sub={p.unlimited_loss ? "no cap on losses" : "worst case"} />
                <KpiTile label="Break-even" tone="warn" value={p.breakevens.length ? p.breakevens.map((b) => b.toLocaleString("en-IN")).join(" / ") : "—"} sub={`spot ${spot.toLocaleString("en-IN")}`} />
                <KpiTile label={`Net ${p.net_premium_kind}`} tone={p.net_premium_kind === "credit" ? "cyan" : "purple"} value={money(p.net_premium)} sub={`${ev.lots} lot × ${ev.lot_size}`} />
                <KpiTile label="Reward / risk" tone="cyan" value={p.risk_reward != null ? `${p.risk_reward.toFixed(2)}x` : p.unlimited_profit ? "open" : "—"} sub={ev.verification?.consistent ? "✓ verified" : "unverified"} title={ev.verification?.method} />
              </div>
              {ev.curves && <PayoffChart curves={ev.curves} breakevens={p.breakevens} spot={spot} />}
            </>
          )}
          {ev.greeks && (
            <div className="grid grid-cols-5 gap-2 text-center">
              {(["delta", "gamma", "theta", "vega", "rho"] as const).map((g) => (
                <div key={g} className="rounded-xl bg-panel-2/70 px-2 py-2" title={g === "theta" ? "₹ per calendar day" : g === "vega" ? "₹ per 1 vol point" : g === "rho" ? "₹ per 1% rate" : g === "delta" ? "units of underlying" : "change in delta per ₹1"}>
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-faint">{g}</div>
                  <div className={`text-sm font-bold tabular ${(ev.greeks?.[g] ?? 0) >= 0 ? "text-pos" : "text-neg"}`}>
                    {ev.greeks?.[g] == null ? "—" : (ev.greeks[g] as number).toLocaleString("en-IN", { maximumFractionDigits: g === "gamma" ? 3 : 1 })}
                  </div>
                </div>
              ))}
            </div>
          )}
          {(ev.risk.rejections.length > 0 || ev.risk.flags.length > 0) && (
            <div className="flex flex-wrap gap-1.5">
              {ev.risk.rejections.map((r, i) => <Pill key={`r${i}`} tone="neg" title={r}>✕ {r.split(":")[0]}</Pill>)}
              {ev.risk.flags.map((f) => (
                <Pill key={f.id} tone={f.severity === "critical" || f.severity === "high" ? "neg" : f.severity === "medium" ? "warn" : "neutral"} title={f.text}>
                  ⚠ {f.id.replaceAll("_", " ")}
                </Pill>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            {ev.legs.map((l) => (
              <span key={l.leg} className={`rounded-lg border px-2 py-1 text-[11px] font-semibold ${l.side === "buy" ? "border-pos/40 text-pos" : "border-neg/40 text-neg"}`}
                title={l.quote ? `bid ${l.quote.bid} / ask ${l.quote.ask} · IV ${l.quote.iv != null ? (l.quote.iv * 100).toFixed(1) + "%" : "n/a"}` : undefined}>
                {l.side.toUpperCase()} {l.type === "STOCK" ? `${ev.units} shares` : `${l.strike?.toLocaleString("en-IN")} ${l.type}`} @ {l.fill?.toFixed(2) ?? "—"}
              </span>
            ))}
          </div>
          {ev.scenarios && <Heatmap scenarios={ev.scenarios} />}
          <p className="text-[11px] text-faint">{p?.basis} {ev.risk.probability_estimates}</p>
        </div>
      )}
    </section>
  );
}

function Stepper({ label, value, set, min, max, title }: { label: string; value: number; set: (n: number) => void; min: number; max: number; title?: string }) {
  return (
    <span className="flex items-center gap-1" title={title}>
      <span className="text-faint">{label}</span>
      <button onClick={() => set(Math.max(min, value - 1))} className="h-6 w-6 rounded-full border border-line text-muted hover:border-cyan hover:text-cyan">−</button>
      <span className="w-5 text-center font-bold tabular">{value}</span>
      <button onClick={() => set(Math.min(max, value + 1))} className="h-6 w-6 rounded-full border border-line text-muted hover:border-cyan hover:text-cyan">+</button>
    </span>
  );
}

export function PayoffChart({ curves, breakevens, spot }: { curves: NonNullable<Evaluation["curves"]>; breakevens: number[]; spot: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = 240, padL = 8, padR = 8, padT = 12, padB = 22;
  const xs = curves.prices;
  const today = curves.today.map((v) => v ?? NaN);
  const { yMin, yMax } = useMemo(() => {
    const all = [...curves.expiry, ...today.filter((v) => !Number.isNaN(v))];
    const lo = Math.min(0, ...all), hi = Math.max(0, ...all);
    const pad = (hi - lo) * 0.08 || 1;
    return { yMin: lo - pad, yMax: hi + pad };
  }, [curves.expiry, today]);
  const x = (v: number) => padL + ((v - xs[0]) / (xs[xs.length - 1] - xs[0])) * (W - padL - padR);
  const y = (v: number) => padT + ((yMax - v) / (yMax - yMin)) * (H - padT - padB);
  const line = (vals: number[]) => vals.map((v, i) => (Number.isNaN(v) ? null : `${x(xs[i])},${y(v)}`)).filter(Boolean).join(" ");
  const area = `${x(xs[0])},${y(0)} ${line(curves.expiry)} ${x(xs[xs.length - 1])},${y(0)}`;
  const zero = y(0);
  const h = hover;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-xl" style={{ background: "var(--chart-surface)" }}
        onMouseMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - r.left) / r.width) * W;
          const t = (px - padL) / (W - padL - padR);
          setHover(Math.max(0, Math.min(xs.length - 1, Math.round(t * (xs.length - 1)))));
        }}
        onMouseLeave={() => setHover(null)} role="img" aria-label="Payoff at expiry and today">
        <defs>
          <clipPath id="above"><rect x="0" y="0" width={W} height={zero} /></clipPath>
          <clipPath id="below"><rect x="0" y={zero} width={W} height={H - zero} /></clipPath>
        </defs>
        <polygon points={area} fill="var(--neon-green)" opacity="0.16" clipPath="url(#above)" />
        <polygon points={area} fill="var(--neon-red)" opacity="0.18" clipPath="url(#below)" />
        <line x1={padL} x2={W - padR} y1={zero} y2={zero} stroke="var(--faint)" strokeDasharray="3 4" />
        <line x1={x(spot)} x2={x(spot)} y1={padT} y2={H - padB} stroke="var(--neon-cyan)" strokeOpacity="0.6" strokeDasharray="2 3" />
        <text x={x(spot) + 4} y={padT + 8} fontSize="10" fill="var(--neon-cyan)">spot</text>
        {breakevens.map((b) => (
          <g key={b}>
            <circle cx={x(b)} cy={zero} r="4" fill="var(--neon-yellow)" style={{ filter: "drop-shadow(0 0 2px var(--neon-yellow))" }} />
            <text x={x(b)} y={zero + 15} fontSize="9" textAnchor="middle" fill="var(--neon-yellow)">{b.toLocaleString("en-IN")}</text>
          </g>
        ))}
        <polyline points={line(today)} fill="none" stroke="var(--neon-cyan)" strokeWidth="2" strokeDasharray="5 4" />
        <polyline points={line(curves.expiry)} fill="none" stroke="var(--neon-purple)" strokeWidth="2.5" style={{ filter: "drop-shadow(0 0 2px var(--neon-purple))" }} />
        {h != null && (
          <g>
            <line x1={x(xs[h])} x2={x(xs[h])} y1={padT} y2={H - padB} stroke="var(--text)" strokeOpacity="0.4" />
            <circle cx={x(xs[h])} cy={y(curves.expiry[h])} r="4" fill="var(--neon-purple)" />
          </g>
        )}
        <text x={padL} y={H - 6} fontSize="9" fill="var(--faint)">{xs[0].toLocaleString("en-IN", { maximumFractionDigits: 0 })}</text>
        <text x={W - padR} y={H - 6} fontSize="9" fill="var(--faint)" textAnchor="end">{xs[xs.length - 1].toLocaleString("en-IN", { maximumFractionDigits: 0 })}</text>
      </svg>
      <div className="mt-1 flex flex-wrap items-center gap-4 text-[11px]">
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-5 rounded bg-purple" />At expiry</span>
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-5 rounded border-t-2 border-dashed border-cyan" />Today (model)</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-warn" />Break-even</span>
        {h != null && (
          <span className="ml-auto rounded-lg bg-panel-2 px-2 py-0.5 tabular">
            @ {xs[h].toLocaleString("en-IN", { maximumFractionDigits: 0 })}: expiry{" "}
            <b className={curves.expiry[h] >= 0 ? "text-pos" : "text-neg"}>{curves.expiry[h] >= 0 ? "+" : "-"}₹{Math.abs(curves.expiry[h]).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</b>
            {curves.today[h] != null && <> · today <b className={(curves.today[h] as number) >= 0 ? "text-pos" : "text-neg"}>{(curves.today[h] as number) >= 0 ? "+" : "-"}₹{Math.abs(curves.today[h] as number).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</b></>}
          </span>
        )}
      </div>
    </div>
  );
}

function Heatmap({ scenarios }: { scenarios: NonNullable<Evaluation["scenarios"]> }) {
  const cols = Object.keys(scenarios[0]?.pnl ?? {});
  const maxAbs = Math.max(1, ...scenarios.flatMap((s) => Object.values(s.pnl).map((v) => Math.abs(v ?? 0))));
  return (
    <div>
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint">What-if P&amp;L (price move × time × volatility)</div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-separate border-spacing-[3px] text-[11px]">
          <thead>
            <tr className="text-faint">
              <th className="text-left font-semibold">When / IV</th>
              {cols.map((c) => <th key={c} className="font-semibold">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s, i) => (
              <tr key={i}>
                <td className="whitespace-nowrap pr-2 text-muted">{s.when}{s.vol_shift !== 0 && <span className="text-purple"> IV{s.vol_shift > 0 ? "+" : ""}{Math.round(s.vol_shift * 100)}</span>}</td>
                {cols.map((c) => {
                  const v = s.pnl[c];
                  const a = v == null ? 0 : Math.min(1, Math.abs(v) / maxAbs);
                  const bg = v == null ? "transparent" : v >= 0 ? `rgba(95,211,154,${0.08 + a * 0.5})` : `rgba(232,102,127,${0.08 + a * 0.55})`;
                  return (
                    <td key={c} className="rounded-md px-2 py-1 text-center font-semibold tabular text-ink" style={{ background: bg }} title={`${s.when}, IV shift ${s.vol_shift * 100} pts, price ${c}`}>
                      {v == null ? "—" : `${v >= 0 ? "+" : "-"}${Math.abs(v) >= 1e5 ? (Math.abs(v) / 1e5).toFixed(1) + "L" : Math.abs(v) >= 1e3 ? (Math.abs(v) / 1e3).toFixed(1) + "K" : Math.abs(v).toFixed(0)}`}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
