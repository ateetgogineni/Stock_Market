"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Run } from "@/lib/api";
import { formatDateTime, formatInr } from "@/lib/format";
import { Badge, DataStatusBadge, Panel, RatingBadge, StatusDot } from "./ui";

export default function RunHistory() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.runs(100).then((r) => setRuns(r.runs)).catch((e) => setError(e.message));
  }, []);

  return (
    <Panel title="Saved reports" subtitle="Every analysis run is stored with its input snapshot, so it can be reopened and replayed">
      {error && <p className="text-sm text-neg">{error}</p>}
      {runs && runs.length === 0 && <p className="text-sm text-muted">No analyses yet. <Link href="/" className="text-accent">Start one</Link>.</p>}
      {runs && runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-1 font-medium">Company</th>
                <th className="py-1 font-medium">Requested</th>
                <th className="py-1 font-medium">Price</th>
                <th className="py-1 font-medium">Data</th>
                <th className="py-1 font-medium">Medium term</th>
                <th className="py-1 font-medium">Long term</th>
                <th className="py-1 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.analysis_run_id} className="border-t border-line/60">
                  <td className="py-2">
                    <Link href={`/runs/${r.analysis_run_id}`} className="hover:text-accent">
                      {r.summary?.name ?? r.symbol} <span className="text-xs text-muted">{r.exchange}:{r.symbol}</span>
                    </Link>
                  </td>
                  <td className="py-2 text-xs text-muted">{formatDateTime(r.requested_at)}</td>
                  <td className="tabular py-2">{formatInr(r.summary?.price)}</td>
                  <td className="py-2">{r.data_status ? <DataStatusBadge status={r.data_status} /> : "—"}</td>
                  <td className="py-2">{r.summary?.ratings.medium ? <RatingBadge rating={r.summary.ratings.medium} /> : "—"}</td>
                  <td className="py-2">{r.summary?.ratings.long ? <RatingBadge rating={r.summary.ratings.long} /> : "—"}</td>
                  <td className="py-2 text-xs">
                    <span className="flex items-center gap-1.5"><StatusDot status={r.status === "partial" ? "partial" : r.status} />{r.status}</span>
                    {r.summary?.provider === "fixture" && <Badge tone="warn">synthetic</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
