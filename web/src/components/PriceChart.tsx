"use client";

import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import type { ChartData } from "@/lib/api";

const RANGES: [string, number][] = [["1M", 1], ["3M", 3], ["6M", 6], ["1Y", 12], ["5Y", 60], ["MAX", 0]];
const OVERLAY_LABELS = {
  sma50: "SMA 50",
  sma200: "SMA 200",
  ema20: "EMA 20",
  bollinger: "Bollinger (20, 2)",
  vwap20: "VWAP 20 (rolling)",
  levels: "60-session support/resistance",
} as const;
type OverlayKey = keyof typeof OVERLAY_LABELS;
const OVERLAY_COLOR: Record<OverlayKey, string> = {
  sma50: "var(--series-1)", sma200: "var(--series-2)", ema20: "var(--series-3)", bollinger: "var(--series-4)",
  vwap20: "var(--series-5)", levels: "var(--neon-yellow)",
};

function css(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function monthsBefore(iso: string, months: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() - months);
  return d.toISOString().slice(0, 10);
}

export default function PriceChart({ data }: { data: ChartData }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [range, setRange] = useState("1Y");
  const [line, setLine] = useState(false);
  const [overlays, setOverlays] = useState<Record<OverlayKey, boolean>>({
    sma50: true, sma200: true, ema20: false, bollinger: false, vwap20: false, levels: true,
  });

  useEffect(() => {
    if (!ref.current || data.bars.length === 0) return;
    const text = css("--muted"), grid = css("--chart-grid"), border = css("--border");
    const pos = css("--pos"), neg = css("--neg"), accent = css("--accent"), faint = css("--faint");
    const series = [1, 2, 3, 4, 5].map((n) => css(`--series-${n}`)); // validated for colour-blind separation
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: css("--chart-surface") }, textColor: text, fontSize: 11, panes: { separatorColor: border } },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderColor: border },
      timeScale: { borderColor: border },
      localization: { priceFormatter: (p: number) => p.toLocaleString("en-IN", { maximumFractionDigits: 2 }) },
      // Let the mouse wheel scroll the page; pan by dragging, zoom with the range buttons or pinch.
      handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
    });
    chartRef.current = chart;
    const t = (s: string) => s as Time;

    const main = line
      ? chart.addSeries(LineSeries, { color: accent, lineWidth: 2 }, 0)
      : chart.addSeries(CandlestickSeries, { upColor: pos, downColor: neg, wickUpColor: pos, wickDownColor: neg, borderVisible: false }, 0);
    if (line) {
      main.setData(data.bars.map((b) => ({ time: t(b.time), value: b.close })));
    } else {
      main.setData(data.bars.map((b) => ({ time: t(b.time), open: b.open, high: b.high, low: b.low, close: b.close })));
    }

    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "vol", lastValueVisible: false, priceLineVisible: false }, 0);
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(data.bars.map((b) => ({ time: t(b.time), value: b.volume, color: b.close >= b.open ? `${pos}55` : `${neg}55` })));

    const overlay = (points: { time: string; value: number }[], color: string, width: 1 | 2 = 1, style = LineStyle.Solid) => {
      const s = chart.addSeries(LineSeries, { color, lineWidth: width, lineStyle: style, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }, 0);
      s.setData(points.map((p) => ({ time: t(p.time), value: p.value })));
    };
    if (overlays.sma50) overlay(data.sma50, series[0], 2);
    if (overlays.sma200) overlay(data.sma200, series[1], 2);
    if (overlays.ema20) overlay(data.ema20, series[2], 2);
    if (overlays.bollinger) {
      overlay(data.bb_upper, series[3], 1, LineStyle.Dashed);
      overlay(data.bb_lower, series[3], 1, LineStyle.Dashed);
    }
    if (overlays.vwap20) overlay(data.vwap20, series[4], 2, LineStyle.Dotted);
    if (overlays.levels) {
      const lv = data.levels.find((l) => l.window === 60);
      if (lv) {
        main.createPriceLine({ price: lv.resistance, color: css("--neon-yellow"), lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: "60d resistance" });
        main.createPriceLine({ price: lv.support, color: css("--neon-yellow"), lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: "60d support" });
      }
    }

    const rsi = chart.addSeries(LineSeries, { color: accent, lineWidth: 1, priceLineVisible: false }, 1);
    rsi.setData(data.rsi14.map((p) => ({ time: t(p.time), value: p.value })));
    rsi.createPriceLine({ price: 70, color: faint, lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: false, title: "70" });
    rsi.createPriceLine({ price: 30, color: faint, lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: false, title: "30" });

    const hist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, 2);
    hist.setData(data.macd_hist.map((p) => ({ time: t(p.time), value: p.value, color: p.value >= 0 ? `${pos}99` : `${neg}99` })));
    const macd = chart.addSeries(LineSeries, { color: series[0], lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 2);
    macd.setData(data.macd.map((p) => ({ time: t(p.time), value: p.value })));
    const sig = chart.addSeries(LineSeries, { color: series[1], lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 2);
    sig.setData(data.macd_signal.map((p) => ({ time: t(p.time), value: p.value })));

    const panes = chart.panes();
    panes[0]?.setStretchFactor(5);
    panes[1]?.setStretchFactor(1.4);
    panes[2]?.setStretchFactor(1.4);

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [data, overlays, line]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || data.bars.length === 0) return;
    const months = RANGES.find(([k]) => k === range)?.[1] ?? 12;
    const last = data.bars[data.bars.length - 1].time;
    if (months === 0) chart.timeScale().fitContent();
    else chart.timeScale().setVisibleRange({ from: monthsBefore(last, months) as Time, to: last as Time });
  }, [range, data, overlays, line]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <div className="flex overflow-hidden rounded-full border border-line">
          {RANGES.map(([k]) => (
            <button key={k} onClick={() => setRange(k)}
              className={`px-3 py-1 font-semibold ${range === k ? "bg-cyan-bg text-cyan" : "text-muted hover:text-ink"}`}>
              {k}
            </button>
          ))}
        </div>
        <button onClick={() => setLine((v) => !v)} className="rounded-full border border-line px-3 py-1 font-semibold text-muted hover:border-purple hover:text-purple">
          {line ? "Candles" : "Line"}
        </button>
        {(Object.keys(OVERLAY_LABELS) as OverlayKey[]).map((k) => (
          <button key={k} onClick={() => setOverlays((o) => ({ ...o, [k]: !o[k] }))} aria-pressed={overlays[k]}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-semibold transition ${overlays[k] ? "border-line text-ink" : "border-line/50 text-faint opacity-60"}`}>
            <span className="h-2 w-3 rounded-full" style={{ background: OVERLAY_COLOR[k], boxShadow: overlays[k] ? `0 0 2px ${OVERLAY_COLOR[k]}` : "none" }} />
            {OVERLAY_LABELS[k]}
          </button>
        ))}
      </div>
      <div ref={ref} className="h-[560px] w-full overflow-hidden rounded-xl" />
      <p className="mt-2 text-[11px] text-faint">
        Price & volume · RSI 14 · MACD 12/26/9. Split-adjusted daily bars. Charts by TradingView Lightweight Charts™.
      </p>
    </div>
  );
}
