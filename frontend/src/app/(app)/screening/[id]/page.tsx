import type { Metadata } from "next";
import { Suspense } from "react";

import { BatchView } from "@/components/screening/batch-view";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "岗位筛选 · AlphaJob" };

export default function BatchPage() {
  // 详情视图通过 useParams() 读取 id，只有运行时才知道，所以包在 Suspense 里
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 w-full max-w-4xl rounded-xl" />}>
      <BatchView />
    </Suspense>
  );
}
