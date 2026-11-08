import { Suspense } from "react";
import RunView from "@/components/RunView";

export default function RunPage({ params }: PageProps<"/runs/[id]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading analysis…</p>}>
      {params.then(({ id }) => <RunView runId={id} />)}
    </Suspense>
  );
}
