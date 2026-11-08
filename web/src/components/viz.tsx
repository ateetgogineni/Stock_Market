"use client";

// At-a-glance visual primitives: rating lights, gauges, rings, meters, KPI tiles and sparklines.
// Colour always comes with a text label, so no meaning is carried by colour alone.

import type { ReactNode } from "react";

export type Tone = "pos" | "neg" | "warn" | "cyan" | "purple" | "neutral";

export const TONE_VAR: Record<Tone, string> = {
  pos: "var(--neon-green)",
  neg: "var(--neon-red)",
  warn: "var(--neon-yellow)",
  cyan: "var(--neon-cyan)",
  purple: "var(--neon-purple)",
  neutral: "var(--muted)",
};

const TONE_CLASS: Record<Tone, string> = {
  pos: "text-pos border-pos/50 bg-pos-bg glow-pos",
  neg: "text-neg border-neg/50 bg-neg-bg glow-neg",
  warn: "text-warn border-warn/50 bg-warn-bg glow-warn",
  cyan: "text-cyan border-cyan/50 bg-cyan-bg glow-cyan",
  purple: "text-purple border-purple/50 bg-purple-bg glow-purple",
  neutral: "text-muted border-line bg-neutral-bg",
};

/** Score in [-1, 1] -> tone, using the rating engine's neutral band of 0.10. */
export function scoreTone(score: number | null | undefined): Tone {
  if (score == null) return "neutral";
  return score >= 0.1 ? "pos" : score <= -0.1 ? "neg" : "neutral";
}

export function ratingTone(rating: string): Tone {
  return rating === "BUY" ? "pos" : rating === "SELL" ? "neg" : rating === "HOLD" ? "cyan" : "warn";
}

export function Pill({ tone = "neutral", children, title, className = "" }: { tone?: Tone; children: ReactNode; title?: string; className?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${TONE_CLASS[tone]} ${className}`}>
      {children}
    </span>
  );
}

export function RatingLight({ rating, size = "lg", muted }: { rating: string; size?: "sm" | "lg"; muted?: boolean }) {
  const tone: Tone = muted ? "neutral" : ratingTone(rating);
  const label = rating === "INSUFFICIENT_DATA" ? (muted ? "OFF" : "NO RATING") : rating;
  return (
    <span
      title={rating === "INSUFFICIENT_DATA" ? "INSUFFICIENT DATA" : rating}
      className={`inline-flex items-center justify-center rounded-xl border font-black tracking-widest ${TONE_CLASS[tone]} ${
        size === "lg" ? "min-w-28 px-4 py-2 text-xl" : "px-2 py-0.5 text-[11px]"
      }`}
    >
      {label}
    </span>
  );
}

/** Semicircle gauge for a score in [-1, 1] with the BUY/SELL thresholds marked. */
export function Gauge({ value, buy = 0.3, sell = -0.3, label }: { value: number | null; buy?: number; sell?: number; label?: string }) {
  const r = 52, cx = 64, cy = 64;
  const angle = (v: number) => Math.PI * (1 - (Math.max(-1, Math.min(1, v)) + 1) / 2); // -1 -> 180deg, +1 -> 0deg
  const pt = (v: number, rad = r) => [cx + rad * Math.cos(angle(v)), cy - rad * Math.sin(angle(v))];
  const arc = (a: number, b: number) => {
    const [x1, y1] = pt(a), [x2, y2] = pt(b);
    return `M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`;
  };
  const v = value ?? 0;
  const [nx, ny] = pt(v, r - 10);
  const tone = value == null ? "neutral" : v >= buy ? "pos" : v <= sell ? "neg" : "cyan";
  return (
    <svg viewBox="0 0 128 76" className="w-full max-w-[180px]" role="img" aria-label={`${label ?? "Score"} ${value == null ? "unavailable" : value.toFixed(2)}`}>
      <title>{`${label ?? "Composite score"}: ${value == null ? "unavailable" : value.toFixed(2)} (SELL ≤ ${sell}, BUY ≥ ${buy})`}</title>
      <path d={arc(-1, sell)} stroke="var(--neon-red)" strokeOpacity="0.55" strokeWidth="9" fill="none" />
      <path d={arc(sell, buy)} stroke="var(--border)" strokeWidth="9" fill="none" />
      <path d={arc(buy, 1)} stroke="var(--neon-green)" strokeOpacity="0.55" strokeWidth="9" fill="none" />
      {value != null && (
        <>
          <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={TONE_VAR[tone]} strokeWidth="3" strokeLinecap="round" style={{ filter: `drop-shadow(0 0 2px ${TONE_VAR[tone]})` }} />
          <circle cx={cx} cy={cy} r="4" fill={TONE_VAR[tone]} />
        </>
      )}
      <text x={cx} y={cy - 18} textAnchor="middle" fontSize="15" fontWeight="700" fill="var(--text)">
        {value == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}`}
      </text>
      <text x="10" y="74" fontSize="8" fill="var(--faint)">SELL</text>
      <text x="118" y="74" fontSize="8" fill="var(--faint)" textAnchor="end">BUY</text>
    </svg>
  );
}

/** Ring meter for a 0..1 fraction. */
export function Ring({ value, label, tone, size = 56 }: { value: number | null; label: string; tone?: Tone; size?: number }) {
  const r = 22, c = 2 * Math.PI * r;
  const v = value == null ? 0 : Math.max(0, Math.min(1, value));
  const t: Tone = tone ?? (value == null ? "neutral" : v >= 0.7 ? "pos" : v >= 0.5 ? "warn" : "neg");
  return (
    <div className="flex flex-col items-center gap-1" title={`${label}: ${value == null ? "unavailable" : `${Math.round(v * 100)}%`}`}>
      <svg viewBox="0 0 56 56" width={size} height={size} role="img" aria-label={`${label} ${value == null ? "unavailable" : Math.round(v * 100) + "%"}`}>
        <circle cx="28" cy="28" r={r} stroke="var(--border)" strokeWidth="5" fill="none" />
        <circle cx="28" cy="28" r={r} stroke={TONE_VAR[t]} strokeWidth="5" fill="none" strokeLinecap="round"
          strokeDasharray={`${c * v} ${c}`} transform="rotate(-90 28 28)" style={{ filter: `drop-shadow(0 0 1px ${TONE_VAR[t]})` }} />
        <text x="28" y="32" textAnchor="middle" fontSize="12" fontWeight="700" fill="var(--text)">
          {value == null ? "—" : `${Math.round(v * 100)}`}
        </text>
      </svg>
      <span className="text-[10px] uppercase tracking-wider text-faint">{label}</span>
    </div>
  );
}

/** Horizontal bar from -1 to +1 with a centre line. */
export function SignalBar({ value }: { value: number | null }) {
  const pct = value == null ? 0 : Math.min(Math.abs(value), 1) * 50;
  const tone = scoreTone(value);
  return (
    <div className="relative h-2 w-full rounded-full bg-panel-2">
      <div className="absolute left-1/2 top-[-2px] h-3 w-px bg-faint/60" />
      {value != null && (
        <div
          className="absolute top-0 h-2 rounded-full"
          style={{
            background: TONE_VAR[tone === "neutral" ? "cyan" : tone],
            boxShadow: `0 0 3px ${TONE_VAR[tone === "neutral" ? "cyan" : tone]}`,
            ...(value >= 0 ? { left: "50%", width: `${pct}%` } : { right: "50%", width: `${pct}%` }),
          }}
        />
      )}
    </div>
  );
}

/** Position of a value between a low and a high (e.g. price inside its 52-week range). */
export function RangeBar({ low, high, value, lowLabel, highLabel }: { low: number | null; high: number | null; value: number | null; lowLabel: string; highLabel: string }) {
  if (low == null || high == null || value == null || high <= low) return <div className="text-xs text-faint">Range unavailable</div>;
  const pos = Math.max(0, Math.min(1, (value - low) / (high - low)));
  return (
    <div className="w-full" title={`${Math.round(pos * 100)}% of the way from ${lowLabel} to ${highLabel}`}>
      <div className="relative h-2 rounded-full" style={{ background: "linear-gradient(90deg, var(--neon-red), var(--neon-yellow), var(--neon-green))", opacity: 0.85 }}>
        <div className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink bg-bg" style={{ left: `${pos * 100}%`, boxShadow: "0 0 4px var(--neon-cyan)" }} />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-faint tabular"><span>{lowLabel}</span><span>{highLabel}</span></div>
    </div>
  );
}

/** RSI 0-100 with oversold (30) and overbought (70) zones. */
export function RsiMeter({ value }: { value: number | null }) {
  if (value == null) return <div className="text-xs text-faint">RSI unavailable</div>;
  const zone = value > 70 ? "Overbought" : value < 30 ? "Oversold" : "Neutral";
  const tone: Tone = value > 70 ? "neg" : value < 30 ? "pos" : "cyan";
  return (
    <div title={`RSI 14 = ${value.toFixed(1)} (${zone}; 30/70 zones)`}>
      <div className="relative h-2 rounded-full bg-panel-2">
        <div className="absolute inset-y-0 left-0 w-[30%] rounded-l-full bg-pos/25" />
        <div className="absolute inset-y-0 right-0 w-[30%] rounded-r-full bg-neg/25" />
        <div className="absolute top-1/2 h-4 w-1.5 -translate-y-1/2 rounded-full" style={{ left: `calc(${value}% - 3px)`, background: TONE_VAR[tone], boxShadow: `0 0 3px ${TONE_VAR[tone]}` }} />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-faint"><span>0</span><span>30</span><span>70</span><span>100</span></div>
    </div>
  );
}

export function KpiTile({ label, value, sub, tone = "neutral", icon, title, children }: {
  label: string; value: ReactNode; sub?: ReactNode; tone?: Tone; icon?: ReactNode; title?: string; children?: ReactNode;
}) {
  return (
    <div title={title} className="panel relative overflow-hidden rounded-xl p-3">
      <div className="absolute inset-x-0 top-0 h-0.5" style={{ background: TONE_VAR[tone], boxShadow: `0 0 4px ${TONE_VAR[tone]}` }} />
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-xl font-bold tabular" style={{ color: tone === "neutral" ? "var(--text)" : TONE_VAR[tone] }}>{value}</div>
      {sub && <div className="mt-0.5 truncate text-[11px] text-muted">{sub}</div>}
      {children && <div className="mt-2">{children}</div>}
    </div>
  );
}

export function Sparkline({ values, tone = "cyan", height = 44 }: { values: number[]; tone?: Tone; height?: number }) {
  if (values.length < 2) return null;
  const w = 200, min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${height - 2 - ((v - min) / span) * (height - 4)}`).join(" ");
  const color = TONE_VAR[tone];
  return (
    <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="h-11 w-full" aria-hidden>
      <defs>
        <linearGradient id={`spark-${tone}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${height} ${pts} ${w},${height}`} fill={`url(#spark-${tone})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" style={{ filter: `drop-shadow(0 0 1px ${color})` }} />
    </svg>
  );
}

/** Row of dots, one per check: green pass, yellow warning, red failure. */
export function DotStrip({ items }: { items: { id: string; status: "pass" | "warn" | "fail" | "info"; title: string }[] }) {
  const color = { pass: "var(--neon-green)", warn: "var(--neon-yellow)", fail: "var(--neon-red)", info: "var(--faint)" };
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((i, n) => (
        <span key={`${i.id}-${n}`} title={i.title} className="h-3 w-3 rounded-full" style={{ background: color[i.status], boxShadow: `0 0 2px ${color[i.status]}` }} />
      ))}
    </div>
  );
}

export function Tip({ text }: { text: string }) {
  return (
    <span title={text} aria-label={text} className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-faint/60 text-[10px] text-faint">
      i
    </span>
  );
}

export function SectionTitle({ children, right, tone = "cyan" }: { children: ReactNode; right?: ReactNode; tone?: Tone }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <span className="h-4 w-1 rounded-full" style={{ background: TONE_VAR[tone], boxShadow: `0 0 3px ${TONE_VAR[tone]}` }} />
      <h2 className="text-sm font-bold uppercase tracking-wider">{children}</h2>
      {right && <div className="ml-auto">{right}</div>}
    </div>
  );
}

export function Collapse({ title, children, defaultOpen = false, count }: { title: string; children: ReactNode; defaultOpen?: boolean; count?: ReactNode }) {
  return (
    <details open={defaultOpen} className="panel group rounded-2xl">
      <summary className="flex items-center gap-2 px-4 py-3 text-sm font-semibold">
        <span className="text-cyan transition group-open:rotate-90">▸</span>
        {title}
        {count != null && <span className="ml-1 rounded-full bg-panel-2 px-2 text-[11px] text-muted">{count}</span>}
      </summary>
      <div className="border-t border-line p-4">{children}</div>
    </details>
  );
}
