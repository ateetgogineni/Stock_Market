import { Suspense } from "react";
import ChainView from "@/components/options/ChainView";

export default function ChainPage({ params }: PageProps<"/options/[chainId]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading option chain…</p>}>
      {params.then(({ chainId }) => <ChainView chainId={chainId} />)}
    </Suspense>
  );
}
