"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import type { Evidence } from "@/lib/api";
import { DATA_STATUS_LABEL, RATING_LABEL, formatDateTime } from "@/lib/format";

export function Panel({ title, subtitle, children, right, id }: { title: string; subtitle?: ReactNode; children: ReactNode; right?: ReactNode; id?: string }) {
  return (
    <section id={id} className="panel rounded-2xl">
      <div className="flex items-start gap-3 px-4 pt-4">
        <span className="mt-0.5 h-4 w-1 shrink-0 rounded-full bg-cyan" style={{ boxShadow: "0 0 3px var(--neon-cyan)" }} />
        <div className="min-w-0">
          <h2 className="text-sm font-bold uppercase tracking-wider">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-faint">{subtitle}</p>}
        </div>
        {right && <div className="ml-auto">{right}</div>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

const TONE: Record<string, string> = {
  pos: "border-pos/40 bg-pos-bg text-pos",
  neg: "border-neg/40 bg-neg-bg text-neg",
  warn: "border-warn/40 bg-warn-bg text-warn",
  neutral: "border-line bg-neutral-bg text-muted",
  accent: "border-cyan/40 bg-cyan-bg text-cyan",
  purple: "border-purple/40 bg-purple-bg text-purple",
};

export function Badge({ tone = "neutral", children, title }: { tone?: keyof typeof TONE; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${TONE[tone]}`}>
      {children}
    </span>
  );
}

export function RatingBadge({ rating, large, muted }: { rating: string; large?: boolean; muted?: boolean }) {
  const tone = muted ? "neutral" : rating === "BUY" ? "pos" : rating === "SELL" ? "neg" : rating === "HOLD" ? "accent" : "warn";
  const glow = muted ? "" : tone === "pos" ? "glow-pos" : tone === "neg" ? "glow-neg" : tone === "accent" ? "glow-cyan" : "glow-warn";
  return (
    <span className={`inline-flex items-center rounded-full border font-bold tracking-wider ${TONE[tone]} ${glow} ${large ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-[10px]"}`}>
      {RATING_LABEL[rating] ?? rating}
    </span>
  );
}

export function DataStatusBadge({ status }: { status: string }) {
  // The UI never shows "Live" for dev data; delayed and end-of-day are labelled as such.
  const tone = status === "end_of_day" ? "accent" : status === "delayed" ? "warn" : status === "live" ? "pos" : "neg";
  return <Badge tone={tone}>{DATA_STATUS_LABEL[status] ?? status}</Badge>;
}

const STEP_TONE: Record<string, string> = {
  completed: "var(--neon-green)",
  partial: "var(--neon-yellow)",
  running: "var(--neon-cyan)",
  queued: "var(--faint)",
  failed: "var(--neon-red)",
  skipped: "var(--faint)",
  unavailable: "var(--neon-yellow)",
};

export function StatusDot({ status }: { status: string }) {
  const c = STEP_TONE[status] ?? "var(--faint)";
  return (
    <span
      className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${status === "running" ? "pulse-dot" : ""}`}
      style={{ background: c, boxShadow: status === "queued" || status === "skipped" ? "none" : `0 0 2px ${c}` }}
    />
  );
}

export function Score({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-faint">—</span>;
  const tone = value >= 0.1 ? "text-pos" : value <= -0.1 ? "text-neg" : "text-muted";
  return <span className={`tabular font-semibold ${tone}`}>{value >= 0 ? "+" : ""}{value.toFixed(2)}</span>;
}

export { SignalBar as ScoreBar } from "./viz";

// ---------------------------------------------------------------- evidence citations

type EvidenceCtx = { map: Record<string, Evidence>; open: (id: string) => void };
const Ctx = createContext<EvidenceCtx>({ map: {}, open: () => {} });

export function EvidenceProvider({ evidence, children }: { evidence: Evidence[]; children: ReactNode }) {
  const map = Object.fromEntries(evidence.map((e) => [e.id, e]));
  const [selected, setSelected] = useState<string | null>(null);
  const item = selected ? map[selected] : null;
  return (
    <Ctx.Provider value={{ map, open: setSelected }}>
      {children}
      {selected && (
        <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-cyan/40 bg-panel p-5 shadow-[0_0_20px_rgba(94,200,219,0.15)]">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Evidence</h3>
            <code className="text-xs text-muted">{selected}</code>
            <button onClick={() => setSelected(null)} className="ml-auto rounded px-2 py-1 text-sm text-muted hover:bg-panel-2">
              Close
            </button>
          </div>
          {!item ? (
            <p className="mt-4 text-sm text-muted">This evidence item is not in the store.</p>
          ) : (
            <dl className="mt-4 space-y-3 text-sm">
              <Row k="Label">{item.label}</Row>
              <Row k="Value"><span className="tabular font-medium">{item.display}</span></Row>
              {item.period && <Row k="Period">{item.period}</Row>}
              {item.observed_at && <Row k="Observed">{item.observed_at}</Row>}
              <Row k="Type">{item.kind}{item.status !== "ok" && <> · <span className="text-warn">{item.status}</span></>}</Row>
              {item.note && <Row k="Note">{item.note}</Row>}
              {item.formula && (
                <Row k="Calculation">
                  <code className="text-xs">{item.formula.expression}</code>
                  <div className="text-xs text-faint">{item.formula.id} v{item.formula.version}</div>
                </Row>
              )}
              {item.inputs.length > 0 && (
                <Row k="Inputs">
                  <div className="flex flex-wrap gap-1">{item.inputs.map((i) => <Cite key={i} id={i} />)}</div>
                </Row>
              )}
              {item.source && (
                <Row k="Source">
                  {item.source.provider} · {item.source.dataset}
                  {item.source.detail && <div className="text-xs text-muted">{item.source.detail}</div>}
                  {item.source.retrieved_at && <div className="text-xs text-faint">Retrieved {formatDateTime(item.source.retrieved_at)}</div>}
                  {item.source.url && (
                    <a className="text-xs text-accent underline" href={item.source.url} target="_blank" rel="noreferrer noopener">
                      Open source link
                    </a>
                  )}
                </Row>
              )}
            </dl>
          )}
        </aside>
      )}
    </Ctx.Provider>
  );
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[6.5rem_1fr] gap-2">
      <dt className="text-xs text-muted">{k}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function useEvidence(): Record<string, Evidence> {
  return useContext(Ctx).map;
}

/** One evidence value with its citation chip; shows "—" until the store loads or when unavailable. */
export function EV({ id, label }: { id: string; label?: string }) {
  const map = useEvidence();
  const item = map[id];
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line/60 py-1.5 text-sm last:border-0">
      <span className="text-muted">{label ?? item?.label ?? id}</span>
      <span className="flex items-baseline gap-1 text-right">
        <span className={`tabular ${item && item.status !== "ok" ? "text-faint" : ""}`}>{item ? item.display : "—"}</span>
        {item && <Cite id={id} />}
      </span>
    </div>
  );
}

export function Cite({ id }: { id: string }) {
  const { map, open } = useContext(Ctx);
  const known = id in map;
  return (
    <button
      onClick={() => open(id)}
      title={known ? `${map[id].label}: ${map[id].display}` : id}
      className={`rounded-md border px-1 font-mono text-[10px] leading-4 ${known ? "border-purple/40 text-purple/90 hover:border-cyan hover:text-cyan" : "border-neg/40 text-neg"}`}
    >
      {id}
    </button>
  );
}

export function Cites({ ids }: { ids: string[] }) {
  if (!ids.length) return null;
  return <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">{ids.map((i) => <Cite key={i} id={i} />)}</span>;
}
